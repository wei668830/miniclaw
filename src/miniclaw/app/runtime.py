"""会话运行时（Web 后端）。

``ChatSession`` 是无 UI 的会话核心：持有对话上下文、技能、模型配置与运行模式，
并提供「流式对话（产出事件）」与「技能对话式加载」能力。

设计目标（与 CLI ``CommandLineInteraction`` 语义一致）：
- 技能通过**用户消息**注入 ``SKILL.md`` 全文（不改 system prompt），加载后不可卸载；
- 仅「新建会话」（新建 ``ChatSession``）可重置已加载技能；
- agent 模式启用工具，chat 模式不启用（与 CLI 一致）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, AsyncIterator, List, Optional, Tuple

from loguru import logger

from ..agents import get_llm_client, llm_tools_manager
from ..agents.base_llm_client import ToolResponse
from ..agents.llm_configurator import LLMConfigurator
from ..cli.history_store import HistoryStore
from ..cli.stream_runner import _sanitize_messages, _should_keep_reasoning
from ..constant import (
    AGENT_AUTONOMY_PROMPT,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MEMORY_KEEP_RECENT,
    EnvVarLoader,
)
from ..utils.balance import fetch_balance
from ..utils.common import (
    build_skill_injection,
    clip,
    dt_uuid,
    merge_system_prompt_into_user,
    scan_skills,
)
from ..utils.context import (
    check_budget,
    estimate_messages_tokens,
    estimate_text_tokens,
    get_context_budget,
    shrink_messages,
)

SHORT_SYSTEM_PROMPT = (
    "你是一个应用解决方案专家，协助用户从设计方案到实现产品。"
    "请严格遵守用户消息中【系统指令】部分的要求。"
)
DEFAULT_SYSTEM_PROMPT = "你是一个人工智能助手，协助用户完成各种任务。"

# 工具结果回传给模型时的文本上限（字符），避免单条过长撑爆上下文
_TOOL_RESULT_MAX_CHARS = 20000


def _tool_response_to_text(result: ToolResponse) -> str:
    """把工具结果转换为回传给模型的文本（与既有实现一致：JSON 序列化）。"""
    try:
        return result.model_dump_json()
    except Exception:
        return json.dumps({"content": [{"type": "text", "text": str(result)}]}, ensure_ascii=False)


def _tool_response_display(result: ToolResponse) -> str:
    """抽取工具结果的可读文本，用于前端展示。"""
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            parts.append(getattr(block, "text", ""))
        elif btype == "image":
            parts.append("[image]")
    text = "\n".join(p for p in parts if p)
    if len(text) > _TOOL_RESULT_MAX_CHARS:
        text = text[:_TOOL_RESULT_MAX_CHARS] + "...(已截断)"
    return text


class ChatSession:
    """单个会话的运行时状态。"""

    def __init__(self, session_id: Optional[str] = None):
        self.session_id = session_id or f"s{dt_uuid()}"
        self.created_at = datetime.now().isoformat(timespec="seconds")

        # —— LLM 配置（默认取 default 分组，可运行期覆盖）——
        self.provider = EnvVarLoader.get_str("LLM_CLIENT_PROVIDER", "litellm")
        llms = LLMConfigurator.load_llm_configs_by_group()
        default_llm = llms.get("default", {})
        self.model = default_llm.get("model")
        self.api_key = default_llm.get("api_key")
        self.base_url = default_llm.get("base_url")
        self.custom_llm_provider = default_llm.get("custom_llm_provider")
        self.temperature: Optional[float] = None
        self.max_tokens: Optional[int] = None
        self.client = get_llm_client(self.provider)

        # —— 运行模式与工具 ——
        self.runtime_mode: str = "agent"
        self.web_search_enabled = EnvVarLoader.get_bool("MINICLAW_WEB_SEARCH_ENABLED", False)
        self.tools: List[dict] = []
        self._refresh_tools()

        # —— 对话上下文与技能 ——
        self.messages: List[dict] = []
        self.skills_preload: list[Tuple[str, str, Any]] = []
        self.skills_loaded: list[Tuple[str, str, Any]] = []

        # —— 历史持久化 ——
        self.history_store = HistoryStore(self.session_id)

        # —— 本会话累计用量（供 UI/接口查询）——
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "turns": 0,
        }

        # —— 官方余额（DeepSeek /user/balance）；会话花费由余额差值推导（含缓存命中折扣）——
        self.balance_baseline: Optional[float] = None
        self.balance_currency: Optional[str] = None
        self.balance_last: Optional[float] = None

        self._init_messages()

    # ------------------------------------------------------------------
    # 初始化 / 配置
    # ------------------------------------------------------------------
    def _init_messages(self) -> None:
        self.system_prompt = EnvVarLoader.get_str("CHAT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
        self.messages = [
            {"role": "system", "content": SHORT_SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    "Do not stop this application process by invoking the shell command tool "
                    f"(execute_shell_command), PID: {os.getpid()}\n"
                ),
            },
        ]
        self.skills_loaded.clear()

    def _refresh_tools(self) -> None:
        exclude = [] if self.web_search_enabled else ["web_search"]
        self.tools = llm_tools_manager.get_llm_tools(exclude=exclude)

    def _active_tools(self) -> Optional[List[dict]]:
        return self.tools if self.runtime_mode == "agent" else None

    def _sampling_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        return kwargs

    def _effective_system_prompt(self) -> str:
        """返回本次请求生效的系统提示词（agent 模式附带自主执行提示词）。"""
        system_prompt = self.system_prompt
        if self.runtime_mode == "agent":
            autonomy_prompt = EnvVarLoader.get_str("CHAT_AGENT_AUTONOMY_PROMPT", AGENT_AUTONOMY_PROMPT)
            if autonomy_prompt:
                system_prompt = f"{system_prompt}\n\n{autonomy_prompt}"
        return system_prompt

    def _build_request_messages(self) -> List[dict]:
        """构造发送给模型的请求消息（在副本上，不落盘）。

        系统提示词**不写入 jsonl 历史**：每次请求在此把完整系统提示词注入到
        **第一条用户消息**（确定性、仅副本），历史文件中只保留「干净」的用户输入。
        """
        messages = [dict(m) for m in self.messages]
        system_prompt = self._effective_system_prompt()
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                msg["content"] = merge_system_prompt_into_user(system_prompt, msg["content"])
                break
        return messages

    def _append_message(self, msg: dict) -> None:
        self.messages.append(msg)
        try:
            self.history_store.append(msg)
        except Exception:
            logger.debug("会话历史写入失败", exc_info=True)

    # ------------------------------------------------------------------
    # 技能（对话式加载）
    # ------------------------------------------------------------------
    def list_skills(self) -> List[dict]:
        return [
            {"name": name, "description": description, "path": str(path)}
            for (name, description, path) in scan_skills()
        ]

    def loaded_skills(self) -> List[dict]:
        return [{"name": n, "description": d} for (n, d, _p) in self.skills_loaded]

    def load_skills(self, names: List[str]) -> dict:
        """把技能排入 ``skills_preload``，将在**下一条用户消息**注入。

        已加载 / 已排队者去重；返回各状态列表（语义见设计文档 03）。
        """
        available = {n: (n, d, p) for (n, d, p) in scan_skills()}
        loaded_names = {n for (n, _d, _p) in self.skills_loaded}
        pending_names = {n for (n, _d, _p) in self.skills_preload}

        pending: list[str] = []
        already: list[str] = []
        for name in names:
            if name in loaded_names or name in pending_names:
                already.append(name)
            elif name in available:
                self.skills_preload.append(available[name])
                pending.append(name)

        return {
            "pending": pending,
            "already_loaded": already,
            "skills_loaded": [{"name": n, "description": d} for (n, d, _p) in self.skills_loaded],
        }

    def append_user_message(self, user_input: str) -> list[str]:
        """把用户消息写入上下文（**不含系统提示词**）；若有待注入技能，则把 SKILL.md 全文并入本消息。

        系统提示词不再落盘：由 :meth:`_build_request_messages` 在每次请求时重组注入。
        """
        injected: list[str] = []
        text = user_input
        if self.skills_preload:
            text = build_skill_injection(user_input, self.skills_preload)
            injected = [name for (name, _d, _p) in self.skills_preload]
            self.skills_loaded.extend(self.skills_preload)
            self.skills_preload = []
        self._append_message({"role": "user", "content": text})
        return injected

    # ------------------------------------------------------------------
    # 上下文预算
    # ------------------------------------------------------------------
    def _used_tokens(self) -> int:
        """估算当前上下文占用（含未落盘、请求时注入的系统提示词）。"""
        return estimate_messages_tokens(self.messages) + estimate_text_tokens(self._effective_system_prompt())

    async def ensure_context(self) -> None:
        try:
            level, _used, _hard = check_budget(
                self.messages, extra_tokens=estimate_text_tokens(self._effective_system_prompt())
            )
            if level in ("soft", "hard"):
                keep = EnvVarLoader.get_int("MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT)
                self.messages = shrink_messages(self.messages, keep_recent_turns=keep)
        except Exception:
            logger.debug("ensure_context 精简失败", exc_info=True)

    def context_info(self) -> dict:
        soft, hard, window = get_context_budget()
        return {"used_tokens": self._used_tokens(), "window": window, "soft": soft, "hard": hard}

    # ------------------------------------------------------------------
    # 用量/费用
    # ------------------------------------------------------------------
    def _accumulate_usage(self, chunk) -> None:
        """累计一次 LLM 调用的 token 与费用。"""
        self.usage["prompt_tokens"] += int(getattr(chunk, "prompt_tokens", 0) or 0)
        self.usage["completion_tokens"] += int(getattr(chunk, "completion_tokens", 0) or 0)
        self.usage["total_tokens"] += int(getattr(chunk, "total_tokens", 0) or 0)
        self.usage["cost_usd"] += float(getattr(chunk, "cost_usd", 0.0) or 0.0)
        self.usage["turns"] += 1

    def cost_info(self) -> dict:
        return dict(self.usage)

    # ------------------------------------------------------------------
    # 官方余额 / 官方花费（DeepSeek /user/balance）
    # ------------------------------------------------------------------
    async def query_balance(self) -> dict:
        """查询官方余额（只读，不改变基线）。"""
        return await fetch_balance(self.base_url or "", self.api_key or "")

    async def _ensure_balance_baseline(self) -> None:
        """首次对话前记录余额基线，用于按余额差值计算会话官方花费。"""
        if self.balance_baseline is not None:
            return
        info = await self.query_balance()
        if info.get("ok") and info.get("total_balance") is not None:
            self.balance_baseline = info["total_balance"]
            self.balance_currency = info.get("currency")
            self.balance_last = info["total_balance"]

    async def official_cost_info(self) -> dict:
        """官方口径的会话花费：基线余额 - 当前余额（含缓存命中折扣）。"""
        info = await self.query_balance()
        current = info.get("total_balance") if info.get("ok") else None
        spent = None
        if current is not None and self.balance_baseline is not None:
            spent = round(self.balance_baseline - current, 6)
        if current is not None:
            self.balance_last = current
        return {
            "ok": info.get("ok"),
            "error": info.get("error"),
            "is_available": info.get("is_available"),
            "currency": info.get("currency") or self.balance_currency,
            "total_balance": current,
            "granted_balance": info.get("granted_balance"),
            "topped_up_balance": info.get("topped_up_balance"),
            "baseline_balance": self.balance_baseline,
            "session_spent": spent,
        }

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "runtime_mode": self.runtime_mode,
            "model": self.model,
            "messages": self.messages,
            "skills_loaded": self.loaded_skills(),
            "usage": self.cost_info(),
        }

    def summary(self) -> str:
        for msg in self.messages:
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    # 去掉系统提示词前缀，取用户正文首段
                    marker = "【用户最新输入】"
                    if marker in content:
                        content = content.split(marker, 1)[1]
                    return clip(content.strip().replace("\n", " "), 60)
        return ""

    # ------------------------------------------------------------------
    # 流式对话（产出事件）
    # ------------------------------------------------------------------
    async def stream_events(self, user_input: str) -> AsyncIterator[dict]:
        """执行一轮（含多轮工具回路）对话，逐事件产出。

        事件类型：meta / reasoning / chunk / tool_call / tool_result / done / error。
        """
        injected = self.append_user_message(user_input)
        try:
            await self._ensure_balance_baseline()
        except Exception:
            logger.debug("余额基线获取失败（不影响对话）", exc_info=True)
        yield {
            "event": "meta",
            "data": {
                "session_id": self.session_id,
                "model": self.model,
                "runtime_mode": self.runtime_mode,
                "injected_skills": injected,
            },
        }

        max_iters = EnvVarLoader.get_int("MINICLAW_MAX_TOOL_ITERATIONS", DEFAULT_MAX_TOOL_ITERATIONS)
        tool_iterations = 0

        while True:
            await self.ensure_context()

            collected_content = ""
            collected_reasoning = ""
            tool_called = False

            keep_reasoning = _should_keep_reasoning(self.model, self.base_url, self.custom_llm_provider)
            # 系统提示词在此按需重组注入（不落盘）
            safe_messages = _sanitize_messages(self._build_request_messages(), keep_reasoning=keep_reasoning)

            try:
                async for chunk in self.client.stream(
                    messages=safe_messages,
                    tools=self._active_tools(),
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    custom_llm_provider=self.custom_llm_provider,
                    **self._sampling_kwargs(),
                ):
                    if chunk.error:
                        yield {"event": "error", "data": {"error": chunk.error}}
                        return

                    if chunk.delta:
                        if chunk.delta_type == "reasoning_content":
                            collected_reasoning += chunk.delta
                            yield {"event": "reasoning", "data": {"delta": chunk.delta}}
                        else:
                            collected_content += chunk.delta
                            yield {"event": "chunk", "data": {"delta": chunk.delta}}

                    if not chunk.finish:
                        continue

                    # —— 本轮结束 ——
                    if chunk.finish_reason == "tool_calls":
                        self._accumulate_usage(chunk)
                        tool_calls = chunk.tool_calls or []
                        assistant_msg: dict = {
                            "role": "assistant",
                            "content": collected_content or None,
                            "tool_calls": tool_calls,
                        }
                        if collected_reasoning:
                            assistant_msg["reasoning_content"] = collected_reasoning
                        self._append_message(assistant_msg)

                        for tool_call_obj in tool_calls:
                            function_obj = tool_call_obj.get("function", {}) or {}
                            tool_name = function_obj.get("name")
                            yield {"event": "tool_call", "data": tool_call_obj}

                            tool_response = await llm_tools_manager.execute_tool(
                                tool_name, function_obj.get("arguments")
                            )
                            result_text = _tool_response_to_text(tool_response)
                            self._append_message(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call_obj.get("id"),
                                    "name": tool_name,
                                    "content": result_text,
                                }
                            )
                            yield {
                                "event": "tool_result",
                                "data": {
                                    "tool_call_id": tool_call_obj.get("id"),
                                    "name": tool_name,
                                    "content": _tool_response_display(tool_response),
                                    "is_error": result_text.strip().lower().startswith('{"content":[{"type":"text","text":"error'),
                                },
                            }
                        tool_called = True
                        break

                    # 纯文本收尾
                    assistant_msg = {"role": "assistant", "content": collected_content}
                    if collected_reasoning:
                        assistant_msg["reasoning_content"] = collected_reasoning
                    self._append_message(assistant_msg)
                    self._accumulate_usage(chunk)
                    yield {
                        "event": "done",
                        "data": {
                            "finish_reason": chunk.finish_reason or "stop",
                            "prompt_tokens": chunk.prompt_tokens,
                            "completion_tokens": chunk.completion_tokens,
                            "total_tokens": chunk.total_tokens,
                            "cost_usd": chunk.cost_usd,
                            "session_cost_usd": self.usage["cost_usd"],
                            "session_total_tokens": self.usage["total_tokens"],
                            "session_prompt_tokens": self.usage["prompt_tokens"],
                            "session_completion_tokens": self.usage["completion_tokens"],
                            "session_turns": self.usage["turns"],
                        },
                    }
                    return

            except Exception as e:
                logger.exception("流式对话发生异常")
                yield {"event": "error", "data": {"error": str(e)}}
                return

            if tool_called:
                tool_iterations += 1
                if tool_iterations > max_iters:
                    yield {"event": "error", "data": {"error": "工具调用达到上限，已暂停"}}
                    return
                continue

            # 未产生 finish 的兜底
            yield {"event": "done", "data": {"finish_reason": "stop"}}
            return

    async def chat_once(self, user_input: str) -> dict:
        """非流式对话：聚合事件，返回完整结果。"""
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        injected: list[str] = []
        usage: dict = {}
        async for event in self.stream_events(user_input):
            name = event["event"]
            data = event["data"]
            if name == "chunk":
                content_parts.append(data.get("delta", ""))
            elif name == "reasoning":
                reasoning_parts.append(data.get("delta", ""))
            elif name == "meta":
                injected = data.get("injected_skills", [])
            elif name == "done":
                usage = data
            elif name == "error":
                raise RuntimeError(data.get("error"))
        return {
            "session_id": self.session_id,
            "content": "".join(content_parts),
            "reasoning_content": "".join(reasoning_parts) or None,
            "injected_skills": injected,
            **{k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cost_usd")},
        }


__all__ = ["ChatSession"]
