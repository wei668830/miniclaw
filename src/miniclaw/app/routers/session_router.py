"""会话管理路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from ..deps import get_session_manager, require_token
from ..models import NewSessionRequest
from ..session_manager import DEFAULT_SESSION_PAGE_SIZE

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(require_token)])


@router.get("")
async def list_sessions(limit: int = DEFAULT_SESSION_PAGE_SIZE, offset: int = 0):
    """GET /api/sessions：列出会话及当前会话 ID（支持 limit/offset 分页）。

    :param limit: 返回的最大条数
    :param offset: 起始偏移（用于「加载更多」）
    :return: 含 sessions 列表与 current_session_id 的字典
    """
    sm = get_session_manager()
    return {
        "sessions": sm.list_sessions(limit=limit, offset=offset),
        "current_session_id": sm.current().session_id if sm.current() else None,
    }


@router.post("")
async def create_session(req: NewSessionRequest):
    """POST /api/sessions：新建会话（技能状态归零），可选激活。

    :param req: 新建会话请求体
    :return: 新会话的 ID、时间、模型、模式与已加载技能
    """
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
    """GET /api/sessions/{session_id}：返回指定会话的完整快照。

    :param session_id: 会话 ID
    :return: 会话快照字典
    """
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    return session.snapshot()


@router.post("/{session_id}/activate")
async def activate_session(session_id: str):
    """POST /api/sessions/{session_id}/activate：把指定会话设为当前会话。

    :param session_id: 会话 ID
    :return: 含 session_id 与 activated 的字典
    """
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
    """POST /api/sessions/{session_id}/clear：重置指定会话的上下文。

    :param session_id: 会话 ID
    :return: 含 session_id 与 cleared 的字典
    """
    sm = get_session_manager()
    session = sm.get_or_load(session_id)
    session._init_messages()
    return {"session_id": session.session_id, "cleared": True}


@router.get("/{session_id}/export", response_class=PlainTextResponse)
async def export_session(session_id: str):
    """GET /api/sessions/{session_id}/export：将会话导出为 Markdown 文本。

    :param session_id: 会话 ID
    :return: 纯文本响应（Markdown 内容）
    """
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


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """DELETE /api/sessions/{session_id}：删除会话（内存 + 磁盘历史 + 索引）。

    :param session_id: 会话 ID
    :return: 含 session_id、deleted 与当前会话 ID 的字典
    """
    sm = get_session_manager()
    deleted = sm.delete(session_id)
    return {
        "session_id": session_id,
        "deleted": deleted,
        "current_session_id": sm.current().session_id if sm.current() else None,
    }


__all__ = ["router"]
