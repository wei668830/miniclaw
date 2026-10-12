"""依赖注入：会话管理器单例与 Token 鉴权。"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException

from .session_manager import SessionManager

_session_manager: Optional[SessionManager] = None

AUTH_TOKEN_ENV = "MINICLAW_API_TOKEN"


def get_session_manager() -> SessionManager:
    """返回进程级会话管理器单例。"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


def require_token(authorization: Optional[str] = Header(default=None)) -> None:
    """校验 ``Authorization: Bearer <token>``。

    未配置 ``MINICLAW_API_TOKEN`` 时视为开发模式，跳过鉴权。
    """
    token = os.environ.get(AUTH_TOKEN_ENV, "").strip()
    if not token:
        return
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="unauthorized")


__all__ = ["get_session_manager", "require_token", "AUTH_TOKEN_ENV"]
