import json

from loguru import logger
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel

from .console import console
from .stream_runner import run_stream_round
from ..agents.constant import LLM_FUNCTION_SUBAGENT
from ..constant import (
    CLERK_AUTONOMY_PROMPT,
    DEFAULT_MAX_SUBAGENT_LAYER,
    DEFAULT_MAX_TOOL_ITERATIONS,
    EnvVarLoader,
)
from ..utils.common import merge_system_prompt_into_user
from ..utils.turn_taking import get_messages_without_tool_calls

# system 消息中放置过长的中文内容时，部分大模型网关会直接断开连接，
# 因此 system 消息只保留简短指令，完整的系统提示词（CLERK_SYSTEM_PROMPT）合并到用户消息中。
CLERK_SHORT_SYSTEM_PROMPT = (
    "你是一个子任务执行者，负责处理决策者下达的任务，并简洁的回复执行结果成功或者失败，以及执行情况。"
    "请严格遵守用户消息中【系统指令】部分的要求。"
)


class Clerk:
    def __init__(
            self,
            message: str,
            usage_type=None,
            layer: int = 0,
            model: str = None,
            base_url: str = None,
            api_key: str = None,
            custom_llm_provider: str = None,
    ):
        """子任务执行器
        Args:
            message: 任务
            usage_type: 大模型应用场景
            layer: 子任务执行器所在的层级，默认为0，表示第一层子任务执行器，如果子任务执行器调用了另一个子任务执行器，那么被调用的子任务执行器的层级就是1，以此类推。这个参数主要用于日志记录和调试，帮助我们了解当前子任务执行器在整个任务树中的位置。
        """
        # Import here to avoid circular import
        from ..agents import get_llm_client, llm_tools_manager
        from ..agents.llm_configurator import LLM_USAGE_MASTER
        self.llm_usage_type = usage_type if usage_type is not None else LLM_USAGE_MASTER
        self.layer = layer

        # 子代理层级上限（安全网，防递归失控）：超过上限时不执行任务
        self._layer_exceeded = False
        _max_layer = EnvVarLoader.get_int(
            "MINICLAW_MAX_SUBAGENT_LAYER", DEFAULT_MAX_SUBAGENT_LAYER
        )
        if self.layer > _max_layer:
            self._layer_exceeded = True
            logger.warning(
                f"(layer:{self.layer}) 子代理层级超过上限 {_max_layer}，拒绝执行子任务"
            )
            console.print(
                f"[red]❌ 子代理层级超过上限（layer={self.layer} > {_max_layer}），"
                f"已拒绝执行该子任务[/red]"
            )
            return

        self.model = model
        self.base_url = base_url
        self.api_key = api_key
        self.custom_llm_provider = custom_llm_provider

        self.client = get_llm_client()
        self._llm_tools_manager = llm_tools_manager
        self.tools = self._llm_tools_manager.get_llm_tools(exclude=[LLM_FUNCTION_SUBAGENT])

        # 完整的系统提示词在首条用户消息中下发，避免部分网关对 system 消息长度的限制
        _clerk_system_prompt = EnvVarLoader.get_str(
            "CLERK_SYSTEM_PROMPT",
            "你是一个执行者，负责处理决策者下达的任务，并反馈处理的结果。"
        )
        # 注入自主执行提示词，驱动子代理端到端自推进（方案 B：提示词驱动的自主执行）
        _autonomy_prompt = EnvVarLoader.get_str(
            "CHAT_CLERK_AUTONOMY_PROMPT", CLERK_AUTONOMY_PROMPT
        )
        if _autonomy_prompt:
            _clerk_system_prompt = f"{_clerk_system_prompt}\n\n{_autonomy_prompt}"

        self.messages = [
            {
                "role": "system",
                "content": CLERK_SHORT_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": merge_system_prompt_into_user(_clerk_system_prompt, message)
            }
        ]

        logger.info(f"[clerk] 任务消息: {self.messages}")
        console.print(
            Panel(Markdown(f"【子任务执行器接受任务】\n\n{message}"), title=f"AI-CLERK-RECEIVED (layer: {self.layer})"))

    async def run(self) -> str:
        if self._layer_exceeded:
            _msg = (
                f"子代理层级超过上限（layer={self.layer}），未执行任务。"
            )
            logger.warning(f"[clerk] {_msg}")
            return _msg
        await self._stream()
        logger.debug(f"流式对话完成，开始总结任务执行结果。会话内容: {self.messages}")
        _messages_without_tool_calls = get_messages_without_tool_calls(self.messages)
        logger.debug(f"【总结前】任务执行的消息历史（不包含工具调用和工具回复）: {_messages_without_tool_calls}")
        _llm_response = await self.client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个任务执行情况的监督者，负责汇报执行情况，并给出简要的任务执行结果和执行情况。"
                },
                {
                    "role": "user",
                    "content": f"任务执行的消息历史（不包含工具调用和工具回复）: "
                               f"\n\n{json.dumps(_messages_without_tool_calls, ensure_ascii=False)} "
                               f"\n\n请根据上面的消息总结执行结果，要求简洁明了，突出重点，可以参照下面的格式回答："
                               f"\n【执行结果】：成功或者失败 "
                               f"\n【执行情况】：简要描述执行情况，突出重点，同时注意关键信息必须完整。"
                }
            ],
            llm_usage_type=self.llm_usage_type,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            custom_llm_provider=self.custom_llm_provider
        )
        logger.debug(f"【总结后】返回结果： {_llm_response}")
        return _llm_response.content

    async def _stream(self):
        """处理任务并流式显示 LLM 响应（统一流式循环，见 stream_runner）。"""
        # 连续工具调用轮次计数（安全网，防死循环）
        tool_iterations = 0
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
                    llm_tools_manager=self._llm_tools_manager,
                    title="AI-CLERK",
                    log_prefix=f"(layer:{self.layer}) ",
                    next_layer=self.layer + 1,
                )

                if result.error:
                    return None

                if result.tool_called:
                    # 连续工具调用轮次上限（安全网）
                    tool_iterations += 1
                    if tool_iterations > EnvVarLoader.get_int(
                            "MINICLAW_MAX_TOOL_ITERATIONS", DEFAULT_MAX_TOOL_ITERATIONS
                    ):
                        console.print(
                            "[yellow]⚠️ 工具调用达到上限，已暂停，请检查任务是否陷入循环[/yellow]"
                        )
                        return None
                    continue

                logger.debug(
                    f"clerk(layer:{self.layer})本轮对话完成，回复内容：{result.content}"
                )
                # 方案 B：纯文本收尾即结束本轮（移除裁判续跑逻辑）
                return None
            except Exception as e:
                logger.exception(f"(layer:{self.layer}) 流式处理发生错误")
                console.print(f"[red](layer:{self.layer}) 发生错误: {escape(str(e))}[/red]")
                self.messages.append({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
