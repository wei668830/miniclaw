"""大模型客户端统一抽象与数据结构定义。

定义流式/非流式返回结构体、工具执行结果结构，以及所有 LLM 客户端需实现的
抽象基类 BaseLLMClient。
"""

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
    """流式对话的单个增量块。

    只携带本次产出的增量内容与结束标记，结束时附带 token 用量与费用信息。
    """

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
    """非流式对话的完整返回结构。"""

    content: str  # 必选：回复内容
    reasoning_content: Optional[str] = None  # 思考内容
    tool_calls: Optional[List[Dict[str, Any]]] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    error: Optional[str] = None


# 工具执行结果返回结构

class TextBlock(BaseModel):
    """文本内容块。"""

    type: Literal["text"] = "text"
    text: str

class Base64Source(BaseModel):
    """以 base64 编码内嵌的媒体数据来源。"""

    type: Literal["base64"] = "base64"
    media_type: str  # e.g., "image/png", "audio/mpeg", "video/mp4"
    data: str  # base64-encoded content

class URLSource(BaseModel):
    """通过 URL 引用的媒体数据来源。"""

    type: Literal["url"]
    url: str

class ImageBlock(BaseModel):
    """图片内容块，其数据来源为 base64 或 URL。"""

    type: Literal["image"]
    source: Optional[Base64Source | URLSource]

class ToolResponse(BaseModel):
    """工具执行的返回结构，由若干文本/图片内容块组成。"""

    content: List[TextBlock | ImageBlock]

# ======================== 抽象客户端接口 ========================
class BaseLLMClient(ABC):
    """大模型客户端抽象基类。

    规定所有提供商客户端必须实现非流式 chat 与流式 stream 两套接口。
    """

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
