"""FastAPI 路由聚合：汇总各子路由为 ALL_ROUTERS 供应用统一挂载。"""

from .chat_router import router as chat_router
from .config_router import router as config_router
from .context_router import router as context_router
from .llm_router import router as llm_router
from .session_router import router as session_router
from .skill_router import router as skill_router
from .system_router import router as system_router

# 顺序无关；llm_router 为兼容保留（deprecated）
ALL_ROUTERS = (
    system_router,
    session_router,
    skill_router,
    config_router,
    context_router,
    chat_router,
    llm_router,
)

__all__ = [
    "ALL_ROUTERS",
    "system_router",
    "session_router",
    "skill_router",
    "config_router",
    "context_router",
    "chat_router",
    "llm_router",
]
