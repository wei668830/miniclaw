"""会话管理器：为 Web 后端维护「session_id -> ChatSession」的运行态容器。

- 进程内缓存会话运行时；配合 ``~/.miniclaw`` 落盘（JSONL 历史）。
- 「新建会话」= 新建 ``ChatSession``（技能加载状态归零），满足
  「技能加载后不可卸载、仅新会话可重置」的语义。
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger

from ..cli.history_store import HistoryStore
from ..cli.session_index import session_index
from ..constant import DEFAULT_MEMORY_RAW_DIR, EnvVarLoader
from .runtime import ChatSession

# 列表对账（reconcile）的最小间隔（秒）：避免每次列表都全目录 stat
_RECONCILE_TTL_SECONDS = 2.0


class SessionManager:
    """会话运行时容器：维护 session_id 到 ChatSession 的映射与当前会话。"""

    def __init__(self) -> None:
        """初始化空的会话表、当前会话标记与并发锁。"""
        self._sessions: Dict[str, ChatSession] = {}
        self._current_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._reconcile_ts = 0.0

    # ------------------------------------------------------------------
    # 基础查询
    # ------------------------------------------------------------------
    def _raw_dir(self) -> Path:
        """返回会话历史原始目录（由环境变量或默认值决定）。

        :return: 展开后的目录路径
        """
        base = EnvVarLoader.get_str("MINICLAW_MEMORY_RAW_DIR", DEFAULT_MEMORY_RAW_DIR)
        return Path(base).expanduser()

    @staticmethod
    def _is_empty(session: ChatSession) -> bool:
        """判断会话是否为空（除 system 外无任何消息）。

        :param session: 待判断的会话
        :return: 无有效消息返回 True
        """
        return not any(m.get("role") != "system" for m in session.messages)

    def create(self, activate: bool = True) -> ChatSession:
        """新建并缓存一个会话，可选地设为当前会话。

        若已存在空会话，则直接复用它（并可选地切为当前会话），避免「新建会话」
        反复堆积多个空会话。

        :param activate: 是否将目标会话切为当前会话
        :return: 复用的空会话或新建的 ChatSession 实例
        """
        for sid, existing in self._sessions.items():
            if self._is_empty(existing):
                if activate:
                    self._current_id = sid
                logger.info(f"检测到已存在的空会话，直接复用: {sid}")
                return existing
        session = ChatSession()
        self._sessions[session.session_id] = session
        if activate:
            self._current_id = session.session_id
        logger.info(f"新建会话: {session.session_id}")
        return session

    def get(self, session_id: str) -> Optional[ChatSession]:
        """按 ID 从内存缓存取会话，不存在则返回 None。

        :param session_id: 会话 ID
        :return: 会话实例或 None
        """
        return self._sessions.get(session_id)

    def get_or_load(self, session_id: str) -> ChatSession:
        """取会话；不存在则从磁盘历史恢复（无历史则视为新会话）。"""
        session = self._sessions.get(session_id)
        if session is not None:
            return session
        return self._load_from_disk(session_id)

    def current(self) -> Optional[ChatSession]:
        """返回当前激活的会话，未设置则返回 None。

        :return: 当前会话实例或 None
        """
        if self._current_id is None:
            return None
        return self._sessions.get(self._current_id)

    def activate(self, session_id: str) -> ChatSession:
        """取（必要时从磁盘恢复）会话并设为当前会话。

        :param session_id: 目标会话 ID
        :return: 被激活的会话实例
        """
        session = self.get_or_load(session_id)
        self._current_id = session.session_id
        return session

    def _load_from_disk(self, session_id: str) -> ChatSession:
        """从磁盘历史恢复会话（保留 system 前缀），无历史则视为新会话并缓存。

        :param session_id: 会话 ID
        :return: 恢复或新建的会话实例
        """
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
    def list_sessions(self, limit: int = 10, offset: int = 0) -> List[dict]:
        """列出会话（索引 + 内存会话合并），按更新时间倒序，支持分页。

        读取「轻量索引」（``session_index``），**不整读任何 JSONL**；仅在索引过期时
        触发一次目录对账（仅 stat + 对缺失条目读首行）。返回条目不再统计 ``messages``
        （前端列表不展示，恒为 0）。

        :param limit: 单页最大条数
        :param offset: 起始偏移（用于「加载更多」分页）
        :return: 会话概要字典列表
        """
        now = time.time()
        if now - self._reconcile_ts > _RECONCILE_TTL_SECONDS:
            session_index.reconcile(self._raw_dir())
            self._reconcile_ts = now

        entries: Dict[str, dict] = session_index.all()

        # 合并内存中会话（空会话也要出现；摘要/时间以内存为准补全）
        for sid, session in self._sessions.items():
            entry = entries.get(sid)
            if entry is None:
                entries[sid] = {
                    "created_at": session.created_at,
                    "updated_at": session.created_at,
                    "summary": session.summary(),
                }
            else:
                if not entry.get("summary"):
                    entry["summary"] = session.summary()
                if not entry.get("updated_at"):
                    entry["updated_at"] = session.created_at

        sessions = sorted(
            (
                {
                    "session_id": sid,
                    "created_at": e.get("created_at"),
                    "updated_at": e.get("updated_at"),
                    "summary": e.get("summary", ""),
                    "messages": 0,
                }
                for sid, e in entries.items()
            ),
            key=lambda e: e.get("updated_at") or "",
            reverse=True,
        )
        for s in sessions:
            s["current"] = (s["session_id"] == self._current_id)

        if offset < 0:
            offset = 0
        return sessions[offset: offset + limit]

    def delete(self, session_id: str) -> bool:
        """删除会话：移除内存会话、磁盘历史文件与索引条目。

        :param session_id: 会话 ID
        :return: 是否存在被删除的内容（文件或内存会话）
        """
        existed = False
        if session_id in self._sessions:
            self._sessions.pop(session_id, None)
            existed = True
        try:
            store = HistoryStore(session_id)
            if store.path.exists():
                store.path.unlink()
                existed = True
        except Exception:
            logger.opt(exception=True).warning(f"删除会话历史文件失败: {session_id}")
        session_index.remove(session_id)
        if self._current_id == session_id:
            self._current_id = None
        logger.info(f"删除会话: {session_id} (existed={existed})")
        return existed

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    @property
    def lock(self) -> asyncio.Lock:
        """返回保护会话状态变更的并发锁。

        :return: asyncio 锁对象
        """
        return self._lock


__all__ = ["SessionManager"]
