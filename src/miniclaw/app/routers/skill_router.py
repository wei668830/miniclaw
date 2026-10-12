"""技能路由（对话式加载）。

技能加载语义（与 CLI 完全一致，见 design/electron-gui/03-技能对话式加载机制.md）：
- 加载 = 把技能排入 ``skills_preload``，将在**下一条用户消息**注入 SKILL.md 全文；
- 加载后不可卸载；仅「新建会话」可重置。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_session_manager, require_token
from ..models import SkillLoadRequest

router = APIRouter(prefix="/api/skills", tags=["skills"], dependencies=[Depends(require_token)])


@router.get("")
async def list_skills():
    sm = get_session_manager()
    # 技能列表与具体会话无关（扫描技能目录）
    from ...utils.common import scan_skills

    skills = [
        {"name": name, "description": description, "path": str(path)}
        for (name, description, path) in scan_skills()
    ]
    return {"skills": skills}


@router.get("/loaded")
async def loaded_skills(session_id: str):
    sm = get_session_manager()
    session = sm.get(session_id)
    if session is None:
        return {"skills_loaded": []}
    return {"skills_loaded": session.loaded_skills()}


@router.post("/load")
async def load_skills(req: SkillLoadRequest):
    sm = get_session_manager()
    session = sm.get(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session.load_skills(req.names)


__all__ = ["router"]
