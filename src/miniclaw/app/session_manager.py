"""会话管理器：为 Web 后端维护「session_id -> ChatSession」的运行态容器。

- 进程内缓存会话运行时；配合 ``~/.miniclaw`` 落盘（JSONL 历史）。
- 「新建会话」= 新建 ``ChatSession``（技能加载状态归零），满足
  「技能加载后不可卸载、仅新会话可重置」的语义。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from ..cli.history_store import HistoryStore
from ..constant import DEFAULT_MEMORY_RAW_DIR, EnvVarLoader
from ..utils.common import dt_uuid
from .runtime import ChatSession


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, ChatSession] = {}
        self._current_id: Optional[str] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------
    def _raw_dir(self) -> Path:
        base = EnvVarLoader.get_str("MINICLAW_MEMORY_RAW_DIR", DEFAULT_MEMORY_RAW_DIR)
        return Path(base).expanduser()

    def create(self, activate: bool = True) -> ChatSession:
        session = ChatSession()
        self._sessions[session.session_id] = session
        if activate:
            self._current_id = session.session_id
        logger.info(f"新建会话: {session.session_id}")
        return session

    def get(self, session_id: str) -> Optional[ChatSession]:
        return self._sessions.get(session_id)

    def get_or_load(self, session_id: str) -> ChatSession:
        """取会话；不存在则从磁盘历史恢复（无历史则视为新会话）。"""
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        return self._load_from_disk(session_id)

    def current(self) -> Optional[ChatSession]:
        if self._current_id is None:
            return None
        return self._sessions.get(self._current_id)

    def activate(self, session_id: str) -> ChatSession:
        session = self.get_or_load(session_id)
        self._current_id = session.session_id
        return session

    def _load_from_disk(self, session_id: str) -> ChatSession:
        session = ChatSession(session_id=session_id)
        store = HistoryStore(session_id)
        history = store.load_all()
        if history:
            # 保留 system 前缀 + 磁盘历史（磁盘不含 system 消息）
            system_msgs = [m for m in session.messages if m.get("role") == "system"]
            session.messages = system_msgs + history
            logger.info(f"从磁盘恢复会话 {session_id}，消息数: {len(history)}")
        else:
            logger.info(f"会话 {session_id} 无磁盘历史，作为新会话处理")
        self._sessions[session_id] = session
        return session

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------
    def list_sessions(self, limit: int = 10) -> List[dict]:
        """列出最近会话（内存 + 磁盘去重），按更新时间倒序。"""
        raw_dir = self._raw_dir()
        entries: Dict[str, dict] = {}

        # 内存中的会话
        for sid, session in self._sessions.items():
            entries[sid] = {
                "session_id": sid,
                "created_at": session.created_at,
                "updated_at": session.created_at,
                "messages": len([m for m in session.messages if m.get("role") != "system"]),
                "summary": session.summary(),
            }

        # 磁盘上的历史文件
        if raw_dir.exists():
            for jsonl in raw_dir.glob("s*.jsonl"):
                sid = jsonl.stem
                if sid in entries:
                    continue
                try:
                    stat = jsonl.stat()
                    updated_at = datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds")
                except Exception:
                    logger.opt(exception=True).debug('读取会话文件时间戳失败，按未知处理')
                    updated_at = None
                store = HistoryStore(sid)
                messages = store.load_all()
                summary = ""
                for m in messages:
                    if m.get("role") == "user" and isinstance(m.get("content"), str):
                        content = m["content"]
                        marker = "【用户最新输入】"
                        if marker in content:
                            content = content.split(marker, 1)[1]
                        summary = content.strip().replace("\n", " ")[:60]
                        break
                entries[sid] = {
                    "session_id": sid,
                    "created_at": updated_at,
                    "updated_at": updated_at,
                    "messages": len([m for m in messages if m.get("role") != "system"]),
                    "summary": summary,
                }

        sessions = sorted(
            entries.values(),
            key=lambda e: e.get("updated_at") or "",
            reverse=True,
        )
        for s in sessions:
            s["current"] = (s["session_id"] == self._current_id)
        return sessions[:limit]

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def lock(self) -> asyncio.Lock:
        return self._lock


__all__ = ["SessionManager"]
