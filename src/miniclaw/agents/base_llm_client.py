from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import List, Optional, AsyncIterator, Dict, Any, Literal

from .llm_configurator import (
    LLMConfigurator,
    LLM_USAGE_MASTER,
    LLM_USAGE_THINKING,
    LLM_USAGE_HAIKU,
    LLM_USAGE_SONNET,
    LLM_USAGE_OPUS,
)


# ======================== 统一返回结构体（核心） ========================
# 流式 chunk：只返回增量 + 结束标记，结束时带回 token/费用
class LLMStreamChunk(BaseModel):
    type: Literal["text", "tool_call"] = "text"
    delta: str  # 增量内容
    delta_type: str = "content"  # 增量类型，默认为 content，可以是 reasoning_content、tool_call_start、tool_call_end 等(目前 tool_call 已经在 provider 内部处理了)
    finish: bool  # 是否结束
    finish_reason: Optional[str] = None  # 结束原因（如 max_tokens、stop_sequence、tool_call_end 等）
    tool_calls: Optional[List[Dict[str, Any]]] = None  # 如果 type=tool_call，则包含工具调用信息

    # 只有 finish=True 时才可能有值
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


# 非流式完整返回
class LLMResponse(BaseModel):
    content: str  # 必选：回复内容

    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


# 工具执行结果返回结构

class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class Base64Source(BaseModel):
    type: Literal["base64"] = "base64"
    media_type: str  # e.g., "image/png", "audio/mpeg", "video/mp4"
    data: str  # base64-encoded content

class URLSource(BaseModel):
    type: Literal["url"]
    url: str

class ImageBlock(BaseModel):
    type: Literal["image"]
    source: Optional[Base64Source | URLSource]

class ToolResponse(BaseModel):
    content: List[TextBlock | ImageBlock]

# ======================== 抽象客户端接口 ========================
class BaseLLMClient(ABC):

    @abstractmethod
    async def chat(
            self,
            *,
            messages: List[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> LLMResponse:
        """
        非流式对话
        返回：LLMResponse（固定结构）
        """
        pass

    @abstractmethod
    async def stream(
            self,
            *,
            messages: List[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        """
        流式对话
        返回：Iterator[LLMStreamChunk]
        """
        pass
