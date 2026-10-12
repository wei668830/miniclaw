"""会话管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..deps import get_session_manager, require_token
from ..models import NewSessionRequest

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(require_token)])


@router.get("")
async def list_sessions(limit: int = 10):
    sm = get_session_manager()
    return {"sessions": sm.list_sessions(limit=limit), "current_session_id": sm.current().session_id if sm.current() else None}


@router.post("")
async def create_session(req: NewSessionRequest):
    sm = get_session_manager()
    session = sm.create(activate=req.activate)
    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "model": session.model,
        "runtime_mode": session.runtime_mode,
        "skills_loaded": session.loaded_skills(),
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    return session.snapshot()


@router.post("/{session_id}/activate")
async def activate_session(session_id: str):
    sm = get_session_manager()
    session = sm.activate(session_id)
    return {"session_id": session.session_id, "activated": True}


@router.post("/{session_id}/load")
async def load_session(session_id: str):
    """加载会话到上下文（不自动接续）。"""
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    return {"session_id": session.session_id, "messages": session.snapshot()["messages"]}


@router.post("/{session_id}/resume")
async def resume_session(session_id: str):
    """加载并设为当前会话（接续执行）。"""
    sm = get_session_manager()
    session = sm.activate(session_id)
    return {"session_id": session.session_id, "messages": session.snapshot()["messages"]}


@router.post("/{session_id}/clear")
async def clear_session(session_id: str):
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    session._init_messages()
    return {"session_id": session.session_id, "cleared": True}


@router.get("/{session_id}/export", response_class=PlainTextResponse)
async def export_session(session_id: str):
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    lines = [f"# MiniClaw 会话导出\n", f"- 会话 ID: {session.session_id}\n", f"- 导出时间: {session.created_at}\n"]
    for msg in session.messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            continue
        if isinstance(content, str) and content:
            lines.append(f"\n## {role}\n\n{content}\n")
        elif msg.get("tool_calls"):
            lines.append(f"\n## {role} (tool_calls)\n\n{msg.get('tool_calls')}\n")
    return "".join(lines)


__all__ = ["router"]
