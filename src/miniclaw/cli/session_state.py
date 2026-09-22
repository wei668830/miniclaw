"""会话元数据（current_session.json）读写。

持久化「当前会话」元数据到 ``<MINICLAW_STATE_DIR>/current_session.json``，
用于崩溃后定位最近会话与人工恢复。字段：
``session_id`` / ``history_path`` / ``memory_file`` / ``active_plan`` /
``started_at``（首写保留）/ ``updated_at`` / ``clean_shutdown``。
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..constant import DEFAULT_STATE_DIR, EnvVarLoader


STATE_DIR = Path(
    EnvVarLoader.get_str("MINICLAW_STATE_DIR", DEFAULT_STATE_DIR)
).expanduser().resolve()
CURRENT_SESSION_FILE = STATE_DIR / "current_session.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _coerce(value):
    """将 Path 等类型归一化为可 JSON 序列化的值。"""
    if value is None:
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def _read_raw() -> dict | None:
    if not CURRENT_SESSION_FILE.exists():
        return None
    try:
        with open(CURRENT_SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"当前会话读取失败 {CURRENT_SESSION_FILE}: {e}")
        return None
    return data if isinstance(data, dict) else None


def _write_raw(data: dict) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CURRENT_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"当前会话写入失败 {CURRENT_SESSION_FILE}: {e}")


def save_current_session(
    session_id: str,
    history_path,
    memory_file=None,
    active_plan=None,
) -> None:
    """写入（刷新）当前会话元数据；``started_at`` 首次写入后保留。"""
    prev = _read_raw() or {}
    started_at = prev.get("started_at") or _now()
    data = {
        "session_id": session_id,
        "history_path": _coerce(history_path),
        "memory_file": _coerce(memory_file),
        "active_plan": _coerce(active_plan),
        "started_at": started_at,
        "updated_at": _now(),
        "clean_shutdown": False,
    }
    _write_raw(data)


def load_current_session() -> dict | None:
    """读取当前会话元数据；不存在或损坏时返回 None。"""
    return _read_raw()


def mark_clean_shutdown(flag: bool = True) -> None:
    """设置 ``clean_shutdown`` 标记并刷新 ``updated_at``。"""
    data = _read_raw() or {}
    data["clean_shutdown"] = flag
    data["updated_at"] = _now()
    _write_raw(data)


def update_current_session(**fields) -> None:
    """局部字段更新并刷新 ``updated_at``。"""
    data = _read_raw() or {}
    for key, value in fields.items():
        data[key] = _coerce(value)
    data["updated_at"] = _now()
    _write_raw(data)
