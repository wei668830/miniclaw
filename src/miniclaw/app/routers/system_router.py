"""系统信息路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_session_manager, require_token
from ...__version__ import __version__
from ...constant import EnvVarLoader

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(require_token)])


@router.get("/system/info")
async def system_info():
    sm = get_session_manager()
    cur = sm.current()
    return {
        "version": __version__,
        "provider": EnvVarLoader.get_str("LLM_CLIENT_PROVIDER", "litellm"),
        "model": cur.model if cur else None,
        "runtime_mode": cur.runtime_mode if cur else "agent",
        "web_search_enabled": cur.web_search_enabled if cur else EnvVarLoader.get_bool("MINICLAW_WEB_SEARCH_ENABLED", False),
        "working_dir": str(EnvVarLoader.get_str("MINICLAW_WORKING_DIR", "~/.miniclaw")),
        "current_session_id": cur.session_id if cur else None,
    }


__all__ = ["router"]
