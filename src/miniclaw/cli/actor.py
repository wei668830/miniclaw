"""Actor：具备流式对话能力的基础大模型执行体。

封装大模型客户端、可用工具集合与消息历史，供命令行交互、记忆精简、计划器等复用。
"""

from typing import List

from loguru import logger
from rich.markup import escape

from .console import console
from .stream_runner import run_stream_round


class Actor:
    """基础执行体：封装大模型客户端、可用工具与消息历史，提供流式与单轮对话能力。"""

    def __init__(
            self,
            usage_type=None,
            include_tools: List[str] = None,
            exclude_tools: List[str] = None,
            model: str = None,
            base_url: str = None,
            api_key: str = None,
            custom_llm_provider: str = None,
    ):
        """初始化执行体：装配大模型客户端、可用工具与空的消息历史。

        :param usage_type: 大模型使用场景；为 None 时默认取 LLM_USAGE_MASTER
        :param include_tools: 仅保留的工具名白名单
        :param exclude_tools: 需要排除的工具名黑名单
        :param model: 模型名称
        :param base_url: 接入点地址
        :param api_key: 接入点密钥
        :param custom_llm_provider: 自定义提供方标识
        """
        # Import here to avoid circular import
        from ..agents import get_llm_client, llm_tools_manager
        from ..agents.llm_configurator import LLM_USAGE_MASTER
        self.llm_usage_type = usage_type if usage_type is not None else LLM_USAGE_MASTER

        self.client = get_llm_client()
        self.llm_tools_manager = llm_tools_manager
        self.tools = self.llm_tools_manager.get_llm_tools(include=include_tools, exclude=exclude_tools)

        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.custom_llm_provider = custom_llm_provider

        self.messages = []

    async def _stream(self, requirements: str):
        """处理需求并流显示 LLM 响应（统一流式循环，见 stream_runner）。"""
        self.messages.append(
            {
                "role": "user",
                "content": requirements
            }
        )

        while True:
            try:
                result = await run_stream_round(
                    client=self.client,
                    messages=self.messages,
                    tools=self.tools,
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    custom_llm_provider=self.custom_llm_provider,
                    append=self.messages.append,
                    llm_tools_manager=self.llm_tools_manager,
                    title=f"{self.__class__.__name__} AI",
                )

                if result.error:
                    return

                if result.tool_called:
                    continue

                return

            except Exception as e:
                logger.exception(f"流式处理发生错误")
                console.print(f"[red]发生错误: {escape(str(e))}[/red]")
                self.messages.append({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
                break

    async def _chat(self, requirements: str):
        """单轮对话，不使用工具，快速响应"""
        self.messages.append(
            {
                "role": "user",
                "content": requirements
            }
        )

        chat_response = await self.client.chat(
            messages=self.messages,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            custom_llm_provider=self.custom_llm_provider
        )

        content = chat_response.content.strip()

        self.messages.append(
            {
                "role": "assistant",
                "content": content
            }
        )

        return content
