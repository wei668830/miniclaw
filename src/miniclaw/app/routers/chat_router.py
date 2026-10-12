"""会话化聊天路由（SSE 流式 + 非流式）。

SSE 事件协议见 design/electron-gui/02-后端API设计.md：
meta / reasoning / chunk / tool_call / tool_result / done / error。
前端使用 ``fetch + ReadableStream`` 自解析（原生 EventSource 仅支持 GET）。
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import get_session_manager, require_token
from ..models import ChatResponse, ChatStreamRequest

router = APIRouter(prefix="/api/chat", tags=["chat"], dependencies=[Depends(require_token)])


def _apply_overrides(session, req: ChatStreamRequest) -> None:
    if req.model:
        session.model = req.model
    if req.temperature is not None:
        session.temperature = req.temperature
    if req.max_tokens is not None:
        session.max_tokens = req.max_tokens
    if req.mode:
        session.runtime_mode = req.mode


@router.post("/stream")
async def chat_stream(req: ChatStreamRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    sm = get_session_manager()
    session = sm.get_or_load(req.session_id)
    _apply_overrides(session, req)

    async def event_generator() -> AsyncIterator[str]:
        async for event in session.stream_events(req.message):
            name = event["event"]
            data = event["data"]
            yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ChatResponse)
async def chat(req: ChatStreamRequest):
    if not req.message or not req.message.strip():
        raise HTTPException(status_code=400, detail="message 不能为空")

    sm = get_session_manager()
    session = sm.get_or_load(req.session_id)
    _apply_overrides(session, req)

    try:
        result = await session.chat_once(req.message)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ChatResponse(**result)


@router.get("/cost")
async def chat_cost(session_id: str):
    """查询指定会话的累计 token 用量（本地统计）。"""
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    return session.cost_info()


@router.get("/balance")
async def chat_balance(session_id: str):
    """查询官方余额与会话官方花费（DeepSeek /user/balance 及余额差值）。"""
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    return await session.official_cost_info()


__all__ = ["router"]
