"""配置路由（模型 / 采样参数 / 运行模式 / 联网开关）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_session_manager, require_token
from ..models import ConfigUpdateRequest, LLMUseRequest, ModeRequest, WebSearchRequest
from ..runtime import ChatSession
from ...agents.llm_configurator import LLMConfigurator
from ...utils.common import masking_str

router = APIRouter(prefix="/api/config", tags=["config"], dependencies=[Depends(require_token)])


def _current_or_create(sm) -> ChatSession:
    session = sm.current()
    if session is None:
        session = sm.create(activate=True)
    return session


def _config_payload(session: ChatSession) -> dict:
    return {
        "provider": session.provider,
        "model": session.model,
        "api_key_masked": masking_str(session.api_key or ""),
        "base_url": session.base_url,
        "custom_llm_provider": session.custom_llm_provider,
        "temperature": session.temperature,
        "max_tokens": session.max_tokens,
        "runtime_mode": session.runtime_mode,
        "web_search_enabled": session.web_search_enabled,
    }


@router.get("")
async def get_config():
    sm = get_session_manager()
    return _config_payload(_current_or_create(sm))


@router.patch("")
async def update_config(req: ConfigUpdateRequest):
    sm = get_session_manager()
    session = _current_or_create(sm)
    if req.model is not None:
        session.model = req.model
    if req.api_key is not None:
        session.api_key = req.api_key
    if req.base_url is not None:
        session.base_url = req.base_url
    if req.custom_llm_provider is not None:
        session.custom_llm_provider = req.custom_llm_provider
    if req.temperature is not None:
        session.temperature = req.temperature
    if req.max_tokens is not None:
        session.max_tokens = req.max_tokens
    return _config_payload(session)


@router.get("/llms")
async def list_llms():
    sm = get_session_manager()
    session = _current_or_create(sm)
    configs = LLMConfigurator.load_llm_configs_by_group()
    llms = []
    for name, cfg in configs.items():
        llms.append({
            "name": name,
            "model": cfg.get("model"),
            "base_url": cfg.get("base_url"),
            "current": cfg.get("model") == session.model and cfg.get("base_url") == session.base_url,
        })
    return {"llms": llms}


@router.post("/llm/use")
async def use_llm(req: LLMUseRequest):
    sm = get_session_manager()
    session = _current_or_create(sm)
    configs = LLMConfigurator.load_llm_configs_by_group()
    cfg = configs.get(req.name)
    if cfg is None:
        return {"ok": False, "detail": f"未找到大模型配置: {req.name}"}
    session.model = cfg.get("model") or session.model
    session.base_url = cfg.get("base_url") or session.base_url
    session.api_key = cfg.get("api_key") or session.api_key
    session.custom_llm_provider = cfg.get("custom_llm_provider") or session.custom_llm_provider
    return {"ok": True, **_config_payload(session)}


@router.post("/mode")
async def set_mode(req: ModeRequest):
    sm = get_session_manager()
    session = _current_or_create(sm)
    session.runtime_mode = req.mode
    return {"runtime_mode": session.runtime_mode}


@router.post("/web-search")
async def set_web_search(req: WebSearchRequest):
    sm = get_session_manager()
    session = _current_or_create(sm)
    session.web_search_enabled = req.enabled
    session._refresh_tools()
    return {"web_search_enabled": session.web_search_enabled}


__all__ = ["router"]
