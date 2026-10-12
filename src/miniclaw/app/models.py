"""Web 后端请求/响应模型（Pydantic）。

与前端 ``frontend/src/api/types.ts`` 保持字段一致；
接口语义详见 ``design/electron-gui/02-后端API设计.md``。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 会话
# ---------------------------------------------------------------------------
class NewSessionRequest(BaseModel):
    activate: bool = Field(default=True, description="创建后是否切为当前会话")


class SessionInfo(BaseModel):
    session_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: int = 0
    summary: str = ""
    current: bool = False


# ---------------------------------------------------------------------------
# 聊天
# ---------------------------------------------------------------------------
class ChatStreamRequest(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入（纯文本；技能由后端注入）")
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    mode: Optional[Literal["agent", "chat"]] = Field(default=None, description="运行模式覆盖")


class ChatResponse(BaseModel):
    session_id: str
    content: str
    reasoning_content: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    injected_skills: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 技能
# ---------------------------------------------------------------------------
class SkillLoadRequest(BaseModel):
    session_id: str
    names: list[str] = Field(default_factory=list, description="要加载的技能名列表")


class SkillItem(BaseModel):
    name: str
    description: str
    path: Optional[str] = None


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class ConfigUpdateRequest(BaseModel):
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    custom_llm_provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ModeRequest(BaseModel):
    mode: Literal["agent", "chat"]


class WebSearchRequest(BaseModel):
    enabled: bool


class LLMUseRequest(BaseModel):
    name: str


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------
class ContextActionRequest(BaseModel):
    session_id: str
    action: Literal["shrink", "window", "soft", "hard", "reserve", "reset"]
    value: Optional[Any] = None


__all__ = [
    "NewSessionRequest",
    "SessionInfo",
    "ChatStreamRequest",
    "ChatResponse",
    "SkillLoadRequest",
    "SkillItem",
    "ConfigUpdateRequest",
    "ModeRequest",
    "WebSearchRequest",
    "LLMUseRequest",
    "ContextActionRequest",
]
