"""MiniClaw 大模型（LLM）子包。

统一导出大模型客户端抽象、返回结构体、配置器、工具管理器，
并提供按提供商获取客户端的工厂函数。
"""

from .base_llm_client import BaseLLMClient, LLMResponse, LLMStreamChunk
from .llm_configurator import LLMConfigurator
from .providers.litellm_provider import LiteLLMClient
from .llm_tools_manager import llm_tools_manager


def get_llm_client(provider: str | None = "litellm") -> BaseLLMClient:
    """按提供商名称创建对应的大模型客户端实例。

    :param provider: 提供商名称，为空或 "litellm" 时返回 LiteLLMClient
    :return: 对应提供商的 BaseLLMClient 实例
    :raises ValueError: 当传入不支持的提供商名称时抛出
    """
    if not provider or provider == "litellm":
        return LiteLLMClient()
    raise ValueError(f"Unsupported LLM provider: {provider}")


__all__ = [
    "BaseLLMClient",
    "LLMResponse",
    "LLMStreamChunk",
    "LiteLLMClient",
    "get_llm_client",
    "LLMConfigurator",
    "llm_tools_manager",
]
