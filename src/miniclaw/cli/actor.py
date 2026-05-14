import json
from typing import List

from loguru import logger
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from .console import console
from ..agents.base_llm_client import ToolResponse, TextBlock
from ..agents.constant import LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER
from ..constant import EnvVarLoader
from ..utils.common import clip
from ..utils.turn_taking import get_advance_messages, get_messages_without_tool_calls



class Actor:
    def __init__(
            self,
            usage_type=None,
            include_tools:List[str] = None,
            exclude_tools:List[str] = None
    ):
        # Import here to avoid circular import
        from ..agents import get_llm_client, llm_tools_manager
        from ..agents.llm_configurator import LLM_USAGE_MASTER
        self.llm_usage_type = usage_type if usage_type is not None else LLM_USAGE_MASTER

        self.client = get_llm_client()
        self.llm_tools_manager = llm_tools_manager
        self.tools = self.llm_tools_manager.get_llm_tools(include=include_tools, exclude=exclude_tools)

        self.messages = []

    async def _stream(self, requirements: str):
        """处理需求并流显示 LLM 响应"""
        self.messages.append(
            {
                "role": "user",
                "content": requirements
            }
        )

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
                            console.print(f"[red]错误: {chunk.error}[/red]")
                            self.messages.append({
                                "role": "assistant",
                                "content": chunk.error
                            })
                            return

                        # 处理内容流
                        if chunk.delta:
                            if chunk.delta_type == "content":
                                collected_content += chunk.delta
                                # 实时渲染Markdown
                                if collected_content.strip():
                                    live.update(
                                        Panel(
                                            Markdown(collected_content),
                                            title="AI"
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
                                            title="AI 思维链",
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
                                    f"\n[bold yellow]🛠️ 工具调用: {function_obj['name']}({clip(function_obj['arguments'], max_len=100)})[/bold yellow]")
                                logger.debug(
                                    f"调用工具 {function_obj['name']} 参数: {function_obj['arguments']}")
                                if function_obj["name"] == LLM_FUNCTION_SUBAGENT:
                                    # 对cli_llm_agent工具的输入参数进行特殊处理，提取出message和llm_usage_type参数并传递给工具函数
                                    try:
                                        _tool_arguments_obj = json.loads(function_obj["arguments"])
                                        _clerk_message = _tool_arguments_obj["message"]
                                        from .clerk import Clerk
                                        clerk = Clerk(_clerk_message)
                                        _clerk_response = await clerk.run()
                                        logger.debug(f"clerk response: {_clerk_response}")
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=_clerk_response,
                                                )
                                            ]
                                        )
                                    except Exception as e:
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=f"调用工具 {LLM_FUNCTION_SUBAGENT} 错误: {str(e)}",
                                                )
                                            ]
                                        )
                                elif function_obj["name"] == LLM_FUNCTION_PLANNER:
                                    # 调用计划制定工具
                                    try:
                                        from .planner import Planner
                                        planner = Planner()
                                        tool_response = await planner.make(function_obj["arguments"])
                                        logger.debug(f"planner response: {tool_response.content}")
                                    except Exception as e:
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=f"调用工具 {LLM_FUNCTION_PLANNER} 错误: {str(e)}",
                                                )
                                            ]
                                        )
                                else:
                                    tool_response = await self.llm_tools_manager.execute_tool(
                                        function_obj["name"],
                                        function_obj["arguments"]
                                    )
                                logger.debug(f"工具 {function_obj['name']} 响应: {tool_response}")
                                # 继续对话流程
                                self.messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_obj["id"],
                                        "name": function_obj["name"],
                                        "content": tool_response.model_dump_json()
                                    }
                                )
                                logger.debug(f"工具调用结果已添加到消息历史，继续对话")
                                break

                            else:
                                # 显示token使用情况
                                if chunk.prompt_tokens:
                                    console.print(f"\n[dim]📊 Tokens: 输入={chunk.prompt_tokens}, "
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

                                return

            except Exception as e:
                logger.exception(f"流式处理发生错误")
                console.print(f"[red]发生错误: {e}[/red]")
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
            messages=get_advance_messages(self.messages),
        )

        self.messages.append(
            {
                "role": "assistant",
                "content": chat_response.content.strip()
            }
        )
