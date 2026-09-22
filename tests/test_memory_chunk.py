"""组件4 单元测试：Memory 分块（map-reduce）逻辑。

通过 monkeypatch 将 ``Memory._chat`` 替换为桩函数，避免真实 LLM 调用。

运行：``set PYTHONPATH=src && python -m pytest tests/test_memory_chunk.py -q``
"""

import pytest

from miniclaw.cli.memory import Memory
from miniclaw.utils.context import (
    estimate_messages_tokens,
    estimate_text_tokens,
)


def _text_with_tokens(target: int) -> str:
    """构造 token 数约等于 target 的 ASCII 文本（二分查找，单调）。"""
    hi = 1
    while estimate_text_tokens("a" * hi) < target:
        hi *= 2
    lo = 1
    while lo < hi:
        mid = (lo + hi) // 2
        if estimate_text_tokens("a" * mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    return "a" * lo


def _make_memory() -> Memory:
    """绕过 Actor.__init__ 构造一个仅含分块所需属性的 Memory 实例。"""
    mem = Memory.__new__(Memory)
    mem.path = "unused.md"
    mem.last_tail = []
    mem.messages = []
    return mem


def test_chunk_messages_empty():
    mem = _make_memory()
    assert mem._chunk_messages([], max_tokens=100) == []


def test_chunk_messages_single_chunk():
    mem = _make_memory()
    messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "ok"},
    ]
    chunks = mem._chunk_messages(messages, max_tokens=100000)
    assert len(chunks) == 1
    assert chunks[0] == messages


def test_chunk_messages_multi_chunk():
    mem = _make_memory()
    per_turn = _text_with_tokens(300)
    messages = []
    for i in range(5):
        messages.append({"role": "user", "content": f"u{i}-{per_turn}"})
        messages.append({"role": "assistant", "content": "ok"})

    chunks = mem._chunk_messages(messages, max_tokens=500)
    assert len(chunks) > 1
    # 普通（非成对超限）块均不超过单块上限
    for c in chunks:
        assert estimate_messages_tokens(c) <= 500
    # 所有消息都保留、顺序不变
    flat = [m for c in chunks for m in c]
    assert flat == messages


def test_chunk_messages_oversized_single_turn_split():
    mem = _make_memory()
    big = _text_with_tokens(1200)
    messages = [
        {"role": "user", "content": big},
        {"role": "assistant", "content": "ok"},
    ]
    chunks = mem._chunk_messages(messages, max_tokens=500)
    # 单轮超限被二次切分为多个块
    assert len(chunks) >= 2
    flat = [m for c in chunks for m in c]
    assert flat == messages
    # 超大消息单独成块（不可再拆）
    big_chunks = [c for c in chunks if any(m["content"] == big for m in c)]
    assert len(big_chunks) == 1
    assert len(big_chunks[0]) == 1


def test_chunk_messages_keeps_tool_pair_together():
    mem = _make_memory()
    big1 = _text_with_tokens(400)
    big2 = _text_with_tokens(400)
    messages = [
        {"role": "user", "content": "small"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": big1},
        {"role": "tool", "tool_call_id": "c1", "name": "read_file", "content": big2},
        {"role": "assistant", "content": "done"},
    ]
    chunks = mem._chunk_messages(messages, max_tokens=500)
    # 找到包含 assistant(tool_calls) 的块
    pair_chunk = None
    for c in chunks:
        if any(
            isinstance(m, dict) and m.get("role") == "assistant" and m.get("tool_calls")
            for m in c
        ):
            pair_chunk = c
            break
    assert pair_chunk is not None
    # 其后的两条 tool 消息必须与 assistant(tool_calls) 处于同一块
    roles = [m.get("role") for m in pair_chunk]
    assert roles.count("tool") == 2


@pytest.mark.asyncio
async def test_condense_over_budget_chat_call_count(tmp_path, monkeypatch):
    mem = _make_memory()
    mem.path = str(tmp_path / "mem.md")

    calls = {"n": 0}

    async def fake_chat(self, requirements):
        calls["n"] += 1
        return "SUMMARY"

    monkeypatch.setattr(Memory, "_chat", fake_chat)

    per_turn = _text_with_tokens(300)
    messages = []
    for i in range(6):
        messages.append({"role": "user", "content": f"u{i}-{per_turn}"})
        messages.append({"role": "assistant", "content": "ok"})

    summary = await mem.condense(
        messages,
        token_budget=500,
        keep_recent=0,
        session_id="s-test",
        active_plan=None,
    )

    expected_chunks = mem._chunk_messages(messages, max_tokens=500)
    # 桩返回 "SUMMARY"（很短），不会触发递归汇总；调用次数 == 块数 + 终稿 1 次
    assert calls["n"] == len(expected_chunks) + 1
    assert summary == "SUMMARY"
    # 记忆文件已写出
    assert (tmp_path / "mem.md").exists()
