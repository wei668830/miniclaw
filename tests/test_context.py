"""组件1/组件2 单元测试：token 估算、预算判定、工具输出裁剪与消息瘦身。

运行：``set PYTHONPATH=src && python -m pytest tests/test_context.py -q``
"""

import copy
import os
import re
from pathlib import Path

import pytest

from miniclaw.utils.context import (
    check_budget,
    estimate_messages_tokens,
    estimate_text_tokens,
    get_context_budget,
    shrink_messages,
    shrink_tool_response,
)


def _content_for_level(level: str) -> str:
    """构造一个使 check_budget 落在指定等级的 content（window=100 时使用）。"""
    soft, hard, window = get_context_budget()
    step = max(1, window // 10)
    length = step
    for _ in range(20000):
        content = "a" * length
        used = estimate_messages_tokens([{"role": "user", "content": content}])
        if level == "soft" and soft < used <= hard:
            return content
        if level == "hard" and used > hard:
            return content
        length += step
    raise AssertionError(f"未能构造出 {level} 等级的 content")


def test_estimate_text_tokens_empty():
    assert estimate_text_tokens("") == 0


def test_estimate_text_tokens_positive_and_density():
    cn = estimate_text_tokens("你好世界，这是一个测试。")
    en = estimate_text_tokens("hello world this is a test")
    assert cn > 0
    assert en > 0
    # 中文信息密度更高：同等字符数下中文 token 不少于英文
    assert estimate_text_tokens("中" * 20) >= estimate_text_tokens("a" * 20)


def test_estimate_messages_tokens_with_tool_calls_and_list_content():
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "第一段"},
                {"type": "text", "text": "第二段"},
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "name": "read_file", "content": "ok"},
    ]
    # 不应抛异常，且估算为正
    total = estimate_messages_tokens(messages)
    assert total > 0


def test_estimate_messages_tokens_non_dict_skipped():
    total = estimate_messages_tokens([{"role": "user", "content": "hi"}, "bad", None])
    assert total > 0


def test_check_budget_level_transition(monkeypatch):
    monkeypatch.setenv("MINICLAW_CONTEXT_WINDOW", "100")
    monkeypatch.setenv("MINICLAW_CONTEXT_RESERVE_TOKENS", "4096")

    soft, hard, window = get_context_budget()
    assert window == 100
    assert 0 < soft < hard

    # ok
    level_ok, used_ok, _ = check_budget([{"role": "user", "content": ""}])
    assert level_ok == "ok"
    assert used_ok <= soft

    # soft 跃迁
    content_soft = _content_for_level("soft")
    level_soft, used_soft, limit = check_budget([{"role": "user", "content": content_soft}])
    assert level_soft == "soft"
    assert soft < used_soft <= hard
    assert limit == hard

    # hard 跃迁
    content_hard = _content_for_level("hard")
    level_hard, used_hard, _ = check_budget([{"role": "user", "content": content_hard}])
    assert level_hard == "hard"
    assert used_hard > hard


def test_shrink_tool_response_short_unchanged(monkeypatch):
    monkeypatch.setenv("MINICLAW_TOOL_OUTPUT_MAX_TOKENS", "4000")
    text = "short text"
    assert shrink_tool_response(text) == text


def test_shrink_tool_response_long_persisted(tmp_path, monkeypatch):
    monkeypatch.setenv("MINICLAW_TOOL_OUTPUT_MAX_TOKENS", "50")
    monkeypatch.setenv("MINICLAW_TOOL_OUTPUT_DIR", str(tmp_path / "tool_outputs"))

    original = "A" * 40000
    result = shrink_tool_response(original, name="read_file")

    assert result != original
    assert "全文路径:" in result
    match = re.search(r"全文路径: ([^\n]+)", result)
    assert match is not None
    path = Path(match.group(1).strip())
    assert path.exists()
    assert path.read_text(encoding="utf-8") == original


def test_shrink_messages_protects_recent_and_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("MINICLAW_TOOL_OUTPUT_MAX_TOKENS", "50")
    monkeypatch.setenv("MINICLAW_TOOL_OUTPUT_DIR", str(tmp_path / "tool_outputs"))

    messages = [
        {"role": "user", "content": "u0"},
        {"role": "assistant", "content": "a0"},
        {"role": "tool", "name": "early", "content": "B" * 40000},
    ]
    for i in range(1, 8):
        messages.append({"role": "user", "content": f"u{i}"})
        messages.append({"role": "assistant", "content": f"a{i}"})
    # 在最近轮次内插入一个超长工具消息（应受保护，不被裁剪）
    recent_tool_index = len(messages) - 1
    messages.insert(recent_tool_index, {"role": "tool", "name": "recent", "content": "C" * 40000})

    snapshot = copy.deepcopy(messages)
    out = shrink_messages(messages, keep_recent_turns=3)

    # 不修改入参
    assert messages == snapshot
    # 条数不变
    assert len(out) == len(snapshot)
    # 较早的工具消息被替换
    assert out[2]["content"] != "B" * 40000
    # 最近轮次内的工具消息原样保留
    assert out[recent_tool_index]["content"] == "C" * 40000
    # 返回的是新列表
    assert out is not messages
