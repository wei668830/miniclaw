"""系统信息路由。"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from loguru import logger

from ..deps import get_session_manager, require_token
from ...__version__ import __version__
from ...agents.tools.file_io import _resolve_file_path
from ...constant import EnvVarLoader

router = APIRouter(prefix="/api", tags=["system"], dependencies=[Depends(require_token)])

# 需要剔除的零宽 / BOM 字符（模型输出或复制粘贴可能夹带）
_ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\ufeff")


def _clean(raw: str) -> str:
    """剔除零宽/BOM 字符并去除首尾空白与包裹引号/反引号。"""
    s = "".join(ch for ch in (raw or "") if ch not in _ZERO_WIDTH)
    return s.strip().strip('"').strip("'").strip("`").strip()


def _iter_candidates(path: str):
    """依次产出路径候选：原样、清洗后、NFC、NFD（去重）。"""
    seen: list[str] = []
    cleaned = _clean(path)
    for c in (path, cleaned, unicodedata.normalize("NFC", cleaned), unicodedata.normalize("NFD", cleaned)):
        if c and c not in seen:
            seen.append(c)
            yield c


def _safe_abs(path: str) -> str:
    """解析为绝对路径（异常时退回 expanduser）。"""
    try:
        return _resolve_file_path(path)
    except Exception:
        return str(Path(path).expanduser())


def _fallback_parent_match(path: str):
    """兜底：在父目录内按「大小写 / Unicode 规范化等价」匹配同名文件（唯一命中才返回）。

    :return: (匹配到的绝对路径, 命中方式) 或 (None, None)
    """
    for cand in _iter_candidates(path):
        p = Path(_safe_abs(cand))
        parent, name = p.parent, p.name
        if not parent.is_dir():
            continue
        lower = name.strip().lower()
        norm = unicodedata.normalize("NFC", name)
        matches = [
            child
            for child in parent.iterdir()
            if child.name.lower() == lower or unicodedata.normalize("NFC", child.name) == norm
        ]
        if len(matches) == 1:
            return str(matches[0]), "parent-scan"
    return None, None


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

    为避免因**不可见字符 / Unicode 规范化 / 首尾空白**等细微差异导致“文件明明存在却
    判定不存在”，在直接解析未命中时会尝试候选变体，并在父目录内做名称等价兜底匹配。
    仅做解析与存在性判断，不读取文件内容。

    :param path: 待解析的原始路径（绝对或相对）
    :return: 含 input / abs_path / exists / is_dir（及可选 resolved_by）的字典
    """
    abs_path: str | None = None
    resolved_by: str | None = None

    for cand in _iter_candidates(path):
        candidate_abs = _safe_abs(cand)
        if Path(candidate_abs).exists():
            abs_path = candidate_abs
            if cand != path:
                resolved_by = "normalized"
            break

    if abs_path is None:
        abs_path, resolved_by = _fallback_parent_match(path)

    if abs_path is None:
        abs_path = _safe_abs(path)

    p = Path(abs_path)
    exists = p.exists()
    result = {
        "input": path,
        "abs_path": abs_path,
        "exists": exists,
        "is_dir": p.is_dir(),
    }
    if resolved_by:
        result["resolved_by"] = resolved_by
    if not exists:
        logger.warning(f"resolve-path 未命中: input={path!r} abs_path={abs_path!r} 父目录存在={p.parent.exists()}")
    return result


__all__ = ["router"]
