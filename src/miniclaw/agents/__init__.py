from .base_llm_client import BaseLLMClient, LLMResponse, LLMStreamChunk
from .llm_configurator import LLMConfigurator
from .providers.litellm_provider import LiteLLMClient
from .llm_tools_manager import llm_tools_manager


def get_llm_client(provider: str | None = "litellm") -> BaseLLMClient:
    if provider == "litellm":
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
