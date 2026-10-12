"""系统信息路由。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query

from ..deps import get_session_manager, require_token
from ...__version__ import __version__
from ...agents.tools.file_io import _resolve_file_path
from ...constant import EnvVarLoader

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(require_token)])


@router.get("/system/info")
async def system_info():
    """GET /api/system/info：返回版本、provider、模型与当前会话运行信息。

    :return: 系统信息字典
    """
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


@router.get("/system/resolve-path")
async def resolve_path(path: str = Query(..., description="待解析的文件/目录路径（可相对路径）")):
    """GET /api/system/resolve-path：把路径解析为绝对路径并判断存在性。

    复用后端工具侧既有的路径解析逻辑 ``_resolve_file_path``，使前端（Electron）
    能对「相对路径」得到与后端一致的绝对路径，从而用于「打开文件 / 打开文件夹」。
    仅做解析与存在性判断，不读取文件内容。

    :param path: 待解析的原始路径（绝对或相对）
    :return: 含 input / abs_path / exists / is_dir 的字典
    """
    try:
        abs_path = _resolve_file_path(path)
    except Exception:
        abs_path = str(Path(path).expanduser())
    p = Path(abs_path)
    return {
        "input": path,
        "abs_path": abs_path,
        "exists": p.exists(),
        "is_dir": p.is_dir(),
    }


__all__ = ["router"]