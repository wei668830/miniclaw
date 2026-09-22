import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
from loguru import logger

from miniclaw.cli.actor import Actor
from ..constant import (
    DEFAULT_MEMORY_CHUNK_TOKENS,
    DEFAULT_MEMORY_KEEP_RECENT,
    EnvVarLoader,
)
from ..utils.common import extract_yaml_frontmatter
from ..utils.context import (
    estimate_messages_tokens,
    estimate_text_tokens,
    get_context_budget,
)
from ..utils.turn_taking import get_last_n_messages


# 记忆精简的结构化 system 提示词。
# 强制输出固定 8 章节的 Markdown 正文，保证任务连续性要素（计划路径、待办、文件路径）不丢失。
MEMORY_SYSTEM_PROMPT = (
    "你是一个对话内容精简器，负责将冗长的对话上下文精简为一份结构化记忆，"
    "以便后续在上下文超限时能够无缝恢复任务并继续执行。\n"
    "精简规则如下：\n"
    "- 只输出 Markdown 正文；不要输出 JSON；不要用整篇代码块（```）包裹整篇内容；不要输出 role=system 的内容。\n"
    "- 输出必须包含且严格使用以下 8 个二级章节标题（标题文字必须完全一致，顺序固定）：\n"
    "## 会话目标\n"
    "## 当前任务进度\n"
    "## 已完成\n"
    "## 待办与下一步\n"
    "## 关键文件与路径\n"
    "## 关键决策与约束\n"
    "## 最近对话摘要\n"
    "## 用户最新意图\n"
    "- `## 当前任务进度` 必须包含活跃计划文件的绝对路径（若存在活跃计划文件）。\n"
    "- `## 关键文件与路径` 需列出参考文档、执行跟踪文件、计划文件，含绝对路径与其作用说明。\n"
    "- `## 关键决策与约束` 需保留环境变量、编码规范等关键约束。\n"
    "- 若精简发生在任务执行过程中，务必保留必要的过程信息，并指出应继续执行的后续处理，避免导致任务中断。\n"
    "- 保留必要的用户输入和大模型回复的核心信息，去掉冗余细节与工具调用相关信息。\n"
    "- 若最新对话与历史重复，去掉重复部分，保留最新内容；若历史与最新无直接或间接联系，直接去掉无关历史。\n"
    "- 保留对话的连贯性与完整性，确保能够反映对话的主要脉络与关键信息。\n"
)

# 分块 map-reduce 的递归汇总最大层数
_MAX_REDUCE_LAYERS = 3


class Memory(Actor):
    """精简大模型对话内容并保留关键信息的类"""

    def __init__(self, path: str, usage_type: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)

        self.path = path

        from ..agents.llm_configurator import LLM_USAGE_MASTER
        self.llm_usage_type = usage_type if usage_type is not None else LLM_USAGE_MASTER

        # 保留最近若干轮原文，供调用方在重建上下文时原样回填
        self.last_tail = []

        self.messages = [
            {
                "role": "system",
                "content": MEMORY_SYSTEM_PROMPT,
            }
        ]

    def _chunk_messages(self, messages: list, max_tokens: int | None = None) -> list[list[dict]]:
        """按轮次切块，避免精简调用自身溢出。

        - max_tokens 默认取 ``MINICLAW_MEMORY_CHUNK_TOKENS``；
        - 以 ``role == "user"`` 为轮次边界累积分块；
        - 单轮超过 max_tokens 时对该轮内部逐条二次切分；
        - 不得拆散 ``assistant(tool_calls)`` 与其后续 ``tool`` 消息（成对保留），
          必要时允许该块略超上限并记录 logger.warning。
        """
        if max_tokens is None:
            max_tokens = EnvVarLoader.get_int(
                "MINICLAW_MEMORY_CHUNK_TOKENS", DEFAULT_MEMORY_CHUNK_TOKENS
            )

        messages = messages or []
        if not messages:
            return []

        # 1. 以 user 为边界切分为「轮次」
        turns: list[list[dict]] = []
        current: list[dict] = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else None
            if role == "user" and current:
                turns.append(current)
                current = [m]
            else:
                current.append(m)
        if current:
            turns.append(current)

        # 2. 累加轮次为块；单轮超限时逐条二次切分
        chunks: list[list[dict]] = []
        cur_chunk: list[dict] = []
        cur_tokens = 0
        for turn in turns:
            turn_tokens = estimate_messages_tokens(turn)
            if turn_tokens <= max_tokens:
                if cur_chunk and cur_tokens + turn_tokens > max_tokens:
                    chunks.append(cur_chunk)
                    cur_chunk = []
                    cur_tokens = 0
                cur_chunk.extend(turn)
                cur_tokens += turn_tokens
            else:
                # 单轮超限：先冲掉已累积块，再对该轮逐条二次切分
                if cur_chunk:
                    chunks.append(cur_chunk)
                    cur_chunk = []
                    cur_tokens = 0
                chunks.extend(self._split_oversized_turn(turn, max_tokens))
        if cur_chunk:
            chunks.append(cur_chunk)

        return chunks

    def _split_oversized_turn(self, turn: list, max_tokens: int) -> list[list[dict]]:
        """对单轮超限内容逐条二次切分，成对保留 assistant(tool_calls) 与其 tool 回复。"""
        # 聚合为不可拆单元：assistant(tool_calls) + 其后续 tool 消息为一个单元
        units: list[list[dict]] = []
        i = 0
        n = len(turn)
        while i < n:
            m = turn[i]
            role = m.get("role") if isinstance(m, dict) else None
            if role == "assistant" and isinstance(m, dict) and m.get("tool_calls"):
                unit = [m]
                j = i + 1
                while j < n and isinstance(turn[j], dict) and turn[j].get("role") == "tool":
                    unit.append(turn[j])
                    j += 1
                units.append(unit)
                i = j
            else:
                units.append([m])
                i += 1

        chunks: list[list[dict]] = []
        cur: list[dict] = []
        cur_tokens = 0
        for unit in units:
            unit_tokens = estimate_messages_tokens(unit)
            if cur and cur_tokens + unit_tokens > max_tokens:
                chunks.append(cur)
                cur = []
                cur_tokens = 0
            cur.extend(unit)
            cur_tokens += unit_tokens
            if unit_tokens > max_tokens:
                logger.warning(
                    f"记忆分块：存在不可拆的成对单元（约 {unit_tokens} tokens）略超单块上限 {max_tokens}"
                )
        if cur:
            chunks.append(cur)
        return chunks

    async def condense(
        self,
        messages: list,
        *,
        token_budget: int | None = None,
        keep_recent: int | None = None,
        session_id: str | None = None,
        active_plan: str | None = None,
    ) -> str:
        """精简对话内容并保留关键信息。

        预算内一次性精简；超预算时分块 map-reduce 递进式精简（最多 3 层递归汇总），
        最后做一次终稿结构化调用。结果写入带 YAML frontmatter 的记忆文件。
        返回摘要文本，并设置 ``self.last_tail`` 为保留的最近原文。
        """
        if token_budget is None:
            token_budget = get_context_budget()[1]
        if keep_recent is None:
            keep_recent = EnvVarLoader.get_int(
                "MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT
            )

        messages = messages or []
        token_before = estimate_messages_tokens(messages)

        # 取 tail（保留最近原文）与 head（待精简的前段）
        tail = get_last_n_messages(messages, keep_recent) if messages else []
        self.last_tail = tail
        head_len = len(messages) - len(tail)
        if head_len < 0:
            head_len = 0
        head = messages[:head_len]

        chunk_count = 1

        if not head:
            # 没有更早的历史需要精简，最近对话已原样保留
            summary = "（无更早的对话需要精简，最近对话已原样保留）"
            chunk_count = 0
        else:
            head_tokens = estimate_messages_tokens(head)
            if head_tokens <= token_budget:
                # 预算内：一次性精简
                summary = await self._chat(
                    MEMORY_SYSTEM_PROMPT
                    + "\n\n原始的对话完整内容如下(JSON 格式):\n\n"
                    + json.dumps(head, ensure_ascii=False)
                )
                chunk_count = 1
            else:
                # 超预算：分块 map-reduce 递进式精简
                chunks = self._chunk_messages(head, max_tokens=token_budget)
                chunk_count = len(chunks)
                partial_summaries: list[str] = []
                for chunk in chunks:
                    partial = await self._chat(
                        MEMORY_SYSTEM_PROMPT
                        + "\n\n请按下述规则精简以下对话片段，务必保留任务锚点信息"
                          "（计划文件路径、未完成步骤、关键文件路径）。\n\n片段内容(JSON 格式):\n\n"
                        + json.dumps(chunk, ensure_ascii=False)
                    )
                    partial_summaries.append(partial)

                merged = "\n\n".join(partial_summaries)
                layer = 0
                while estimate_text_tokens(merged) > token_budget and layer < _MAX_REDUCE_LAYERS:
                    layer += 1
                    logger.warning(f"记忆精简：递归汇总第 {layer} 层（拼接结果仍超预算）")
                    sub_messages = [
                        {"role": "user", "content": s} for s in partial_summaries
                    ]
                    sub_chunks = self._chunk_messages(sub_messages, max_tokens=token_budget)
                    partial_summaries = []
                    for chunk in sub_chunks:
                        partial = await self._chat(
                            MEMORY_SYSTEM_PROMPT
                            + "\n\n请继续精简以下片段摘要，保留任务锚点信息。\n\n片段内容(JSON 格式):\n\n"
                            + json.dumps(chunk, ensure_ascii=False)
                        )
                        partial_summaries.append(partial)
                    merged = "\n\n".join(partial_summaries)

                # 终稿结构化：产出符合 8 章节模板的最终摘要
                summary = await self._chat(
                    MEMORY_SYSTEM_PROMPT
                    + "\n\n请基于以下片段摘要，产出符合上述 8 章节模板的最终结构化记忆摘要：\n\n"
                    + merged
                )

        token_after = estimate_text_tokens(summary)

        frontmatter = {
            "type": "memory",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "session_id": session_id,
            "message_range": [0, len(messages) - 1],
            "token_before": token_before,
            "token_after": token_after,
            "chunk_count": chunk_count,
            "active_plan": active_plan,
            "keep_recent": keep_recent,
        }
        yaml_str = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
        content = "---\n" + yaml_str + "---\n" + summary

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

        return summary

    @staticmethod
    def load(path: str) -> tuple[dict, str]:
        """读取记忆文件，返回 ``(frontmatter, 正文)``。

        文件不存在或读取失败时返回 ``({}, "")`` 并记录 logger.warning。
        """
        p = Path(path)
        if not p.exists():
            logger.warning(f"记忆文件不存在: {path}")
            return {}, ""
        try:
            content = p.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"记忆文件读取失败 {path}: {e}")
            return {}, ""

        frontmatter = extract_yaml_frontmatter(content)
        match = re.match(r"^---\s*\n.*?\n---\s*\n", content, re.DOTALL)
        body = content[match.end():] if match else content
        return (frontmatter or {}, body)
