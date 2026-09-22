"""上下文预算估算与工具输出裁剪模块。

本模块为 MiniClaw 的记忆（Memory）机制提供：
1. token 估算（优先 tiktoken，失败回退启发式）；
2. 上下文预算阈值判定（soft / hard）；
3. 超大工具结果落盘裁剪（shrink_tool_response）；
4. 较早消息瘦身（shrink_messages，保护最近若干轮原文）。

默认值统一从 ``miniclaw.constant`` 导入，均可通过同名环境变量覆盖。
"""

import json
import math
import uuid
from pathlib import Path

from loguru import logger

from ..constant import (
    DEFAULT_CONTEXT_HARD_RATIO,
    DEFAULT_CONTEXT_RESERVE_TOKENS,
    DEFAULT_CONTEXT_SOFT_RATIO,
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_TOOL_OUTPUT_DIR,
    DEFAULT_TOOL_OUTPUT_MAX_TOKENS,
    EnvVarLoader,
)

try:
    import tiktoken
except ImportError:  # pragma: no cover - 环境未安装 tiktoken 时回退启发式
    tiktoken = None

# 每条消息的固定 token 开销
MESSAGE_OVERHEAD_TOKENS = 4

# 工具输出裁剪后保留的头部摘要字符数
_TOOL_HEAD_CHARS = 800

# assistant 文本截断阈值与占位后缀
_ASSISTANT_TRUNCATE_CHARS = 1500
_ASSISTANT_TRUNCATE_SUFFIX = "…（已截断，完整内容见会话历史）"

# 较早工具输出被省略时的占位文本
_TOOL_ELIDED_PLACEHOLDER = "【较早的工具输出已省略，原始内容已持久化于会话历史 JSONL】"


_ENCODER = None
_ENCODER_LOADED = False


def _get_encoder():
    """惰性加载 tiktoken 的 cl100k_base 编码器；不可用时返回 None。"""
    global _ENCODER, _ENCODER_LOADED
    if _ENCODER_LOADED:
        return _ENCODER
    _ENCODER_LOADED = True
    if tiktoken is None:
        _ENCODER = None
        return None
    try:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    except Exception as e:  # pragma: no cover - 模型名不被识别等情况
        logger.debug(f"tiktoken 编码器加载失败，回退启发式估算: {e}")
        _ENCODER = None
    return _ENCODER


def _is_cjk(ch: str) -> bool:
    """判断字符是否属于 CJK（中日韩）范围。"""
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x20000 <= code <= 0x2A6DF
        or 0x2E80 <= code <= 0x303F
        or 0x3040 <= code <= 0x30FF  # 日文假名
        or 0xAC00 <= code <= 0xD7AF  # 韩文
        or 0xF900 <= code <= 0xFAFF
    )


def _heuristic_tokens(text: str) -> int:
    """启发式 token 估算：CJK×1.0、ASCII×0.25、其它×0.6，向上取整。"""
    cjk = 0
    ascii_cnt = 0
    other = 0
    for ch in text:
        if _is_cjk(ch):
            cjk += 1
        elif ord(ch) < 128:
            ascii_cnt += 1
        else:
            other += 1
    return math.ceil(cjk * 1.0 + ascii_cnt * 0.25 + other * 0.6)


def estimate_text_tokens(text: str) -> int:
    """估算文本的 token 数。

    优先使用 tiktoken（cl100k_base）；import 失败或编码失败时回退启发式。
    空串返回 0。
    """
    if not text:
        return 0
    encoder = _get_encoder()
    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception as e:  # pragma: no cover - 编码失败回退
            logger.debug(f"tiktoken 编码失败，回退启发式估算: {e}")
    return _heuristic_tokens(text)


def _content_to_text(content) -> str:
    """将消息 content 归一化为文本；list 时逐块取 text。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def estimate_message_tokens(msg: dict) -> int:
    """估算单条消息的 token 数（含固定开销）。"""
    if not isinstance(msg, dict):
        return 0
    total = 0
    total += estimate_text_tokens(str(msg.get("role") or ""))
    total += estimate_text_tokens(_content_to_text(msg.get("content")))
    if msg.get("name"):
        total += estimate_text_tokens(str(msg["name"]))
    if msg.get("tool_calls"):
        total += estimate_text_tokens(
            json.dumps(msg["tool_calls"], ensure_ascii=False)
        )
    if msg.get("reasoning_content"):
        total += estimate_text_tokens(str(msg["reasoning_content"]))
    return total + MESSAGE_OVERHEAD_TOKENS


def estimate_messages_tokens(messages: list) -> int:
    """估算消息列表的 token 总数；非 dict 元素跳过并记录 debug 日志。"""
    total = 0
    for m in messages or []:
        if not isinstance(m, dict):
            logger.debug(f"estimate_messages_tokens 跳过非 dict 元素: {type(m)}")
            continue
        total += estimate_message_tokens(m)
    return total


def get_context_budget() -> tuple[int, int, int]:
    """读取上下文预算配置，返回 (soft, hard, window)。

    保证 soft < hard，且 hard <= window - reserve；配置异常时回退默认值。
    """
    window = EnvVarLoader.get_int(
        "MINICLAW_CONTEXT_WINDOW", DEFAULT_CONTEXT_WINDOW
    )
    soft_ratio = EnvVarLoader.get_float(
        "MINICLAW_CONTEXT_SOFT_RATIO", DEFAULT_CONTEXT_SOFT_RATIO
    )
    hard_ratio = EnvVarLoader.get_float(
        "MINICLAW_CONTEXT_HARD_RATIO", DEFAULT_CONTEXT_HARD_RATIO
    )
    reserve = EnvVarLoader.get_int(
        "MINICLAW_CONTEXT_RESERVE_TOKENS", DEFAULT_CONTEXT_RESERVE_TOKENS
    )

    try:
        if window <= 0:
            raise ValueError(f"window 非法: {window}")
        soft = int(window * soft_ratio)
        hard = int(window * hard_ratio)
        max_hard = window - reserve
        # 预留使得硬阈值上界非正时，忽略预留约束（保守取窗口比例）
        if max_hard > 0 and hard > max_hard:
            hard = max_hard
        # 保证 soft < hard；不满足则回退默认比例
        if soft >= hard:
            soft = int(window * DEFAULT_CONTEXT_SOFT_RATIO)
            hard = int(window * DEFAULT_CONTEXT_HARD_RATIO)
            if max_hard > 0 and hard > max_hard:
                hard = max_hard
        if hard <= 0:
            raise ValueError(f"hard 阈值非法: {hard}")
        if soft >= hard:
            soft = max(1, int(hard * 0.6))
        return soft, hard, window
    except (TypeError, ValueError) as e:
        logger.debug(f"上下文预算配置异常，回退默认: {e}")
        window = DEFAULT_CONTEXT_WINDOW
        soft = int(window * DEFAULT_CONTEXT_SOFT_RATIO)
        hard = int(window * DEFAULT_CONTEXT_HARD_RATIO)
        return soft, hard, window


def check_budget(messages) -> tuple[str, int, int]:
    """判定消息列表的预算等级。

    返回 (level, used, limit)：level ∈ {"ok", "soft", "hard"}。
    used > hard → hard；used > soft → soft；否则 ok。limit 为 hard 阈值。
    """
    used = estimate_messages_tokens(messages)
    soft, hard, window = get_context_budget()
    if used > hard:
        level = "hard"
    elif used > soft:
        level = "soft"
    else:
        level = "ok"
    if EnvVarLoader.get_bool("MINICLAW_CONTEXT_DEBUG", False):
        logger.debug(
            f"[context] level={level} used={used} soft={soft} "
            f"hard={hard} window={window}"
        )
    return level, used, hard


def shrink_tool_response(text: str, *, name: str | None = None) -> str:
    """裁剪超大工具结果：全文落盘，返回摘要 + 路径的占位文本。

    - text 为空或 token <= 阈值时原样返回；
    - 否则全文写入 MINICLAW_TOOL_OUTPUT_DIR 下的 ``<uuid>.txt``，
      返回结构化占位文本（含工具名、原始 token 数、头部摘要、全文绝对路径）；
    - 落盘失败时降级为「仅截断 + 警告」，不抛异常。
    """
    if not text:
        return text

    max_tokens = EnvVarLoader.get_int(
        "MINICLAW_TOOL_OUTPUT_MAX_TOKENS", DEFAULT_TOOL_OUTPUT_MAX_TOKENS
    )
    tokens = estimate_text_tokens(text)
    if tokens <= max_tokens:
        return text

    head = text[:_TOOL_HEAD_CHARS]
    tool_name = name or "unknown"
    target_dir = Path(
        EnvVarLoader.get_str("MINICLAW_TOOL_OUTPUT_DIR", DEFAULT_TOOL_OUTPUT_DIR)
    ).expanduser()

    abs_path = None
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{uuid.uuid4().hex}.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        abs_path = file_path.resolve()
    except Exception as e:
        logger.warning(f"工具输出落盘失败，降级为仅截断: {e}")

    if abs_path is None:
        return (
            f"【工具输出已裁剪（未落盘）】工具: {tool_name}，"
            f"原始约 {tokens} tokens；\n"
            f"警告: 全文落盘失败，仅保留头部摘要。\n"
            f"---- 头部摘要 ----\n{head}"
        )

    return (
        f"【工具输出已裁剪】工具: {tool_name}，原始约 {tokens} tokens。\n"
        f"---- 头部摘要（前 {len(head)} 字符）----\n{head}\n"
        f"全文路径: {abs_path}\n"
        f"如需细节请用 read_file 读取该路径。"
    )


def _find_protect_boundary(messages: list, keep_recent_turns: int) -> int:
    """从尾部向前数 keep_recent_turns 个 role=="user" 的索引作为保护边界。"""
    if keep_recent_turns <= 0:
        return len(messages)
    count = 0
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            count += 1
            if count == keep_recent_turns:
                return i
    # 不足 keep_recent_turns 轮，全部视为受保护
    return 0


def shrink_messages(messages: list, keep_recent_turns: int = 6) -> list:
    """对较早消息做裁剪/占位替换，返回新列表（不修改入参）。

    - 从尾部向前数 keep_recent_turns 个 role=="user" 的位置为保护边界，
      边界之后的消息全部原样保留；
    - 边界之前的 tool 消息调用 shrink_tool_response；若裁剪后仍超阈值，
      替换为占位文本；
    - 边界之前的超长 assistant 文本截断为首 1500 字符 + 截断后缀。
    """
    result = [
        dict(m) if isinstance(m, dict) else m for m in (messages or [])
    ]

    boundary = _find_protect_boundary(result, keep_recent_turns)

    max_tokens = EnvVarLoader.get_int(
        "MINICLAW_TOOL_OUTPUT_MAX_TOKENS", DEFAULT_TOOL_OUTPUT_MAX_TOKENS
    )

    for i in range(0, boundary):
        m = result[i]
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "tool":
            content = m.get("content")
            if not isinstance(content, str) or not content:
                continue
            shrunk = shrink_tool_response(content, name=m.get("name"))
            if shrunk == content or estimate_text_tokens(shrunk) > max_tokens:
                shrunk = _TOOL_ELIDED_PLACEHOLDER
            m["content"] = shrunk
        elif role == "assistant":
            content = m.get("content")
            if isinstance(content, str) and len(content) > _ASSISTANT_TRUNCATE_CHARS:
                m["content"] = (
                    content[:_ASSISTANT_TRUNCATE_CHARS] + _ASSISTANT_TRUNCATE_SUFFIX
                )
    return result
