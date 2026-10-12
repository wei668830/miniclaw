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
    """新建会话请求体。"""

    activate: bool = Field(default=True, description="创建后是否切为当前会话")


class SessionInfo(BaseModel):
    """会话概要信息（会话 ID、时间戳、消息数、摘要与是否当前会话）。"""

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
    """聊天请求体（流式与非流式共用：会话 ID、用户消息与可选采样/模式覆盖）。"""

    session_id: str = Field(..., description="会话 ID")
    message: str = Field(..., description="用户输入（纯文本；技能由后端注入）")
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    mode: Optional[Literal["agent", "chat"]] = Field(default=None, description="运行模式覆盖")


class ChatResponse(BaseModel):
    """聊天响应体（非流式聚合结果：内容、思考、用量与注入技能）。"""

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
    """技能加载请求体（目标会话与待加载技能名列表）。"""

    session_id: str
    names: list[str] = Field(default_factory=list, description="要加载的技能名列表")


class SkillItem(BaseModel):
    """技能条目（名称、描述与可选路径）。"""

    name: str
    description: str
    path: Optional[str] = None


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
class ConfigUpdateRequest(BaseModel):
    """会话配置更新请求体（仅提供需覆盖的模型/密钥/采样等字段）。"""

    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    custom_llm_provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ModeRequest(BaseModel):
    """运行模式切换请求体（agent 或 chat）。"""

    mode: Literal["agent", "chat"]


class WebSearchRequest(BaseModel):
    """联网搜索开关请求体。"""

    enabled: bool


class LLMUseRequest(BaseModel):
    """按名称选用预置大模型配置的请求体。"""

    name: str


# ---------------------------------------------------------------------------
# 上下文
# ---------------------------------------------------------------------------
class ContextActionRequest(BaseModel):
    """上下文操作请求体（精简消息、设置预算覆盖或重置覆盖）。"""

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
