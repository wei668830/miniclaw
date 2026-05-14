import json

from loguru import logger
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from .console import console
from ..agents.base_llm_client import ToolResponse, TextBlock
from ..agents.constant import LLM_FUNCTION_SUBAGENT
from ..constant import EnvVarLoader
from ..utils.common import clip
from ..utils.turn_taking import get_advance_messages, get_messages_without_tool_calls


class Clerk:
    def __init__(self, message: str, usage_type=None, layer:int=0):
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

        self.client = get_llm_client()
        self._llm_tools_manager = llm_tools_manager
        self.tools = self._llm_tools_manager.get_llm_tools(exclude=[LLM_FUNCTION_SUBAGENT])

        self.messages = [
            {
                "role": "system",
                "content": EnvVarLoader.get_str(
                    "CLERK_SYSTEM_PROMPT",
                    "你是一个执行者，负责处理决策者下达的任务，并反馈处理的结果。"
                )
            },
            {
                "role": "user",
                "content": message
            }
        ]

        logger.info(f"[clerk] 任务消息: {self.messages}")
        console.print(Panel(Markdown(f"【子任务执行器接受任务】\n\n{message}"), title=f"AI-CLERK-RECEIVED (layer: {self.layer})"))

    async def run(self) -> str:
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
            llm_usage_type=self.llm_usage_type
        )
        logger.debug(f"【总结后】返回结果： {_llm_response}")
        return _llm_response.content

    async def _stream(self):
        """处理用户输入并流式显示 LLM 响应"""
        while True:
            try:
                # 每一轮请求都重新初始化内容收集器，确保流式渲染正确
                collected_content = ""
                collected_reasoning_content = ""
                # 使用Live组件实现流式Markdown渲染
                waiting_spinner = Spinner("dots", text="", style="bold blue")
                with Live(waiting_spinner, console=console, auto_refresh=False, vertical_overflow="visible") as live:
                    async for chunk in self.client.stream(messages=self.messages, tools=self.tools):
                        if chunk.error:
                            console.print(f"[red](layer:{self.layer}) 错误: {chunk.error}[/red]")
                            self.messages.append({
                                "role": "assistant",
                                "content": chunk.error
                            })
                            return None

                        # 处理内容流
                        if chunk.delta:
                            if chunk.delta_type == "content":
                                collected_content += chunk.delta
                                # 实时渲染Markdown
                                if collected_content.strip():
                                    live.update(
                                        Panel(
                                            Markdown(collected_content),
                                            title="AI-CLERK"
                                        ),
                                        refresh=True
                                    )
                            elif chunk.delta_type == "reasoning_content":
                                collected_reasoning_content += chunk.delta
                                # 实时渲染Markdown
                                if collected_reasoning_content.strip():
                                    live.update(
                                        Panel(
                                            Markdown(collected_reasoning_content),
                                            title="AI-CLERK 思维链",
                                            border_style="grey50",
                                            style="dim"
                                        ),
                                        refresh=True
                                    )


                        # 处理完成
                        if chunk.finish:
                            if chunk.finish_reason == "tool_calls":
                                if len(collected_reasoning_content) > 0:
                                    self.messages.append(
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "reasoning_content": collected_reasoning_content,
                                            "tool_calls": chunk.tool_calls
                                        }
                                    )
                                else:
                                    self.messages.append(
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "tool_calls": chunk.tool_calls
                                        }
                                    )

                                # 处理工具调用
                                tool_call_obj = chunk.tool_calls[0]
                                function_obj = tool_call_obj["function"]

                                console.print(
                                    f"\n[bold yellow](layer:{self.layer}) 🛠️ 工具调用: {function_obj['name']}({clip(function_obj['arguments'], max_len=100)})[/bold yellow]")
                                logger.debug(
                                    f"(layer:{self.layer}) 调用工具: {function_obj['name']}, 工具调用参数: {function_obj['arguments']}")

                                if function_obj["name"] == LLM_FUNCTION_SUBAGENT:
                                    # 对cli_llm_agent工具的输入参数进行特殊处理，提取出message和llm_usage_type参数并传递给工具函数
                                    _tool_arguments_obj = json.loads(function_obj["arguments"])
                                    _clerk_message = _tool_arguments_obj["message"]
                                    clerk = Clerk(_clerk_message, layer=self.layer+1)
                                    _clerk_response = await clerk.run()
                                    logger.debug(f"clerk(layer:{self.layer+1}) response: {_clerk_response}")
                                    tool_response = ToolResponse(
                                        content=[
                                            TextBlock(
                                                type="text",
                                                text=_clerk_response,
                                            )
                                        ]
                                    )
                                else:
                                    tool_response = await self._llm_tools_manager.execute_tool(
                                        function_obj["name"],
                                        function_obj["arguments"]
                                    )

                                logger.debug(f"(layer:{self.layer}) 工具 {function_obj['name']} 响应: {tool_response}")
                                # 继续对话流程
                                self.messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_obj["id"],
                                        "name": function_obj["name"],
                                        "content": tool_response.model_dump_json()
                                    }
                                )
                                logger.debug(f"(layer:{self.layer}) 工具调用结果已添加到消息历史，继续对话...")
                                break

                            else:
                                logger.debug(
                                    f"clerk(layer:{self.layer})本轮对话完成，结束原因: {chunk.finish_reason}，回复内容：{collected_content}")
                                # 显示token使用情况
                                if chunk.prompt_tokens:
                                    console.print(f"\n[dim](layer:{self.layer}) 📊 Tokens: 输入={chunk.prompt_tokens}, "
                                                  f"输出={chunk.completion_tokens}, "
                                                  f"总计={chunk.total_tokens}[/dim]")
                                if chunk.cost_usd:
                                    console.print(f"[dim]💰 费用: ${chunk.cost_usd:.6f}[/dim]")

                                # 将助手响应添加到历史
                                if len(collected_reasoning_content) > 0:
                                    self.messages.append({
                                        "role": "assistant",
                                        "content": collected_content,
                                        "reasoning_content": collected_reasoning_content
                                    })
                                else:
                                    self.messages.append({
                                        "role": "assistant",
                                        "content": collected_content
                                    })

                                # 如果本轮结束的对话是大模型询问用户是否继续或者要求用户确认，让大模型通过上下文的内容自行判断是否可以推动对话继续进行，而不是直接结束对话流程
                                chat_response_judgment = await self.client.chat(
                                    messages=get_advance_messages(self.messages),
                                )

                                if chat_response_judgment.content.strip() == "继续":
                                    console.print(
                                        f"\n[yellow](layer:{self.layer}) 大模型判断可以继续推动对话进行，继续下一轮对话...[/yellow]")

                                    self.messages.append({
                                        "role": "user",
                                        "content": "继续"
                                    })

                                    continue
                                else:
                                    return None
            except Exception as e:
                logger.exception(f"(layer:{self.layer}) 流式处理发生错误")
                console.print(f"[red](layer:{self.layer}) 发生错误: {e}[/red]")
                self.messages.append({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
