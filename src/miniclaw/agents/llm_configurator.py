import os
from collections import defaultdict
from typing import Optional

from ..constant import EnvVarLoader

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
    def load_llm_configs_by_group(cls):
        suffixes = {
            "LLM_MODEL",
            "LLM_API_KEY",
            "LLM_BASE_URL",
            # "LLM_MAX_TOKENS",
            # "LLM_TEMPERATURE",
            "CUSTOM_LLM_PROVIDER",
        }

        configs = defaultdict(dict)

        for key, value in os.environ.items():
            for suf in suffixes:
                pn = suf.lower()
                if pn.startswith("llm_"):
                    pn = pn[4:]

                # 精确匹配：LLM_MODEL
                if key == suf:
                    configs["default"][pn] = value
                    break

                # 匹配：OMNIXAI1_LLM_MODEL
                if key.endswith("_" + suf):
                    group = key[:-(len(suf) + 1)].lower()
                    configs[group][pn] = value
                    break

        return dict(configs)

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
        kwargs_copy = kwargs.copy()
        if "base_url" in kwargs_copy and kwargs_copy["base_url"] is not None:
            kwargs_copy["api_base"] = kwargs_copy.pop("base_url")

        if kwargs_copy["model"] is None:
            raise ValueError("模型参数缺失，请通过参数或环境变量 LLM_MODEL 指定模型")
        if kwargs_copy["api_base"] is None:
            raise ValueError("API Base URL 缺失，请通过参数或环境变量 LLM_BASE_URL 指定 API BASE URL")
        if kwargs_copy["api_key"] is None:
            raise ValueError(
                "API Key 缺失，请通过参数或环境变量指定模型对应的 API Key，例如 LLM_API_KEY 或 OPENAI_API_KEY")

        return kwargs_copy
