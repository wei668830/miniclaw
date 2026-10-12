"""上下文预算路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_session_manager, require_token
from ..models import ContextActionRequest
from ...constant import DEFAULT_MEMORY_KEEP_RECENT, EnvVarLoader
from ...utils.context import (
    clear_budget_overrides,
    get_budget_overrides,
    get_context_budget,
    set_budget_override,
    shrink_messages,
)

router = APIRouter(prefix="/api/context", tags=["context"], dependencies=[Depends(require_token)])

_ACTION_TO_FIELD = {
    "window": "window",
    "soft": "soft_ratio",
    "hard": "hard_ratio",
    "reserve": "reserve",
}


@router.get("")
async def get_context(session_id: str):
    """GET /api/context：返回指定会话的上下文占用、预算阈值与覆盖项。

    :param session_id: 会话 ID
    :return: 含 used_tokens/window/soft/hard/overrides 的字典
    """
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    soft, hard, window = get_context_budget()
    from ...utils.context import estimate_messages_tokens

    return {
        "used_tokens": estimate_messages_tokens(session.messages),
        "window": window,
        "soft": soft,
        "hard": hard,
        "overrides": get_budget_overrides(),
    }


@router.post("/action")
async def context_action(req: ContextActionRequest):
    """POST /api/context/action：对会话执行精简或预算覆盖/重置操作。

    :param req: 上下文操作请求体（session_id、action、可选 value）
    :return: 操作后的上下文信息字典
    """
    sm = get_session_manager()
    session = sm.get_or_load(req.session_id)

    if req.action == "reset":
        clear_budget_overrides()
    elif req.action == "shrink":
        keep = EnvVarLoader.get_int("MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT)
        session.messages = shrink_messages(session.messages, keep_recent_turns=keep)
    elif req.action in _ACTION_TO_FIELD:
        if req.value is None:
            raise HTTPException(status_code=400, detail="缺少 value")
        set_budget_override(_ACTION_TO_FIELD[req.action], req.value)
    else:
        raise HTTPException(status_code=400, detail=f"未知 action: {req.action}")

    soft, hard, window = get_context_budget()
    from ...utils.context import estimate_messages_tokens

    return {
        "used_tokens": estimate_messages_tokens(session.messages),
        "window": window,
        "soft": soft,
        "hard": hard,
        "overrides": get_budget_overrides(),
    }


__all__ = ["router"]
