import os
from typing import Optional

from ..constant import EnvVarLoader

# LLM usage type string constants
LLM_USAGE_MASTER = "Master"
LLM_USAGE_THINKING = "Thinking"
LLM_USAGE_HAIKU = "Haiku"
LLM_USAGE_SONNET = "Sonnet"
LLM_USAGE_OPUS = "Opus"


class LLMConfigurator:
    """大模型配置器
    提供大模型连接配置
    """

    def __init__(self):
        self.llm_client_provider = os.getenv("LLM_CLIENT_PROVIDER")

    @classmethod
    def _get_api_key(cls, usage_type: str = LLM_USAGE_MASTER) -> Optional[str]:
        """获取 API KEY
        Args:
            usage_type: llm 使用类型，字符串常量，默认 Master
        Returns:
            API KEY
        """
        return os.getenv("LLM_API_KEY")

    @classmethod
    def config_connection(cls, **kwargs) -> dict:
        """获取连接配置
        Args:
            sub_type: 子类型，字符串常量，默认 Master
            usage_type: llm 使用类型，字符串常量，默认 Master
            kwargs: 连接配置参数，可以包含 model、api_base、api_key 等
        Returns:
            连接配置字典，包含必要的连接参数，例如 model、api_base、api_key 等
        """
        if "model" not in kwargs:
            kwargs["model"] = EnvVarLoader.get_str("LLM_MODEL")
        # 特例：如果是 litellm_proxy 模模型，强制使用 openai 协议（因为 litellm_proxy 本质上是一个兼容 OpenAI 协议的代理）
        if kwargs["model"] and kwargs["model"] == "litellm_proxy":
            kwargs["custom_llm_provider"] = "openai"

        if "base_url" not in kwargs:
            kwargs["api_base"] = EnvVarLoader.get_str("LLM_BASE_URL")
        elif kwargs["base_url"] is not None:
            kwargs["api_base"] = kwargs.pop("base_url")
        if "api_key" not in kwargs:
            usage_type = kwargs.get("usage_type", LLM_USAGE_MASTER)
            kwargs["api_key"] = cls._get_api_key(usage_type)

        if kwargs["model"] is None:
            raise ValueError("模型参数缺失，请通过参数或环境变量 LLM_MODEL 指定模型")
        if kwargs["api_base"] is None:
            raise ValueError("API Base URL 缺失，请通过参数或环境变量 LLM_BASE_URL 指定 API BASE URL")
        if kwargs["api_key"] is None:
            raise ValueError(
                "API Key 缺失，请通过参数或环境变量指定模型对应的 API Key，例如 LLM_API_KEY 或 OPENAI_API_KEY")

        return kwargs
