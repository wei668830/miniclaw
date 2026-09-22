"""统一的流式对话执行器（S3）。

抽取自 ``CommandLineInteraction.stream`` / ``Actor._stream`` / ``Clerk._stream``
三处高度重复的主循环，把差异通过参数与回调注入：

- 单轮流式渲染（``Live`` + ``Spinner`` + ``Markdown``）
- ``tool_calls`` 的工具分发（子代理 / 计划器 / 普通工具）
- 按正确顺序把消息写回调用方（通过 ``append`` 回调，兼容器/持久化两种存储方式）

调用方自行保留外层 ``while`` 循环与异常策略（如上下文超限重试、工具轮次上限），
从而最大限度保持原有对外行为不变。抽取后三处逻辑修一处即可全部受益。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from loguru import logger
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner

from .console import console
from ..agents.base_llm_client import TextBlock, ToolResponse
from ..agents.constant import LLM_FUNCTION_PLANNER, LLM_FUNCTION_SUBAGENT
from ..utils.common import clip
from ..utils.context import shrink_tool_response


@dataclass
class StreamResult:
    """单轮流式结果。

    - ``tool_called``：本轮触发了工具调用，调用方应继续下一轮（除非达到轮次上限）。
    - ``content`` / ``reasoning``：文本收尾时的最终内容。
    - ``error``：模型返回错误，调用方应立刻结束本轮（消息已落盘）。
    """

    tool_called: bool = False
    content: str = ""
    reasoning: str = ""
    error: Optional[str] = None


async def _execute_tool_call(
    function_obj: dict,
    *,
    llm_tools_manager,
    model: str,
    base_url: str,
    api_key: str,
    custom_llm_provider: str,
    next_layer: Optional[int] = None,
) -> ToolResponse:
    """分发并执行一次工具调用，异常统一包装成 ToolResponse 文本。"""
    name = function_obj["name"]
    arguments = function_obj["arguments"]

    if name == LLM_FUNCTION_SUBAGENT:
        try:
            _tool_arguments_obj = json.loads(arguments)
            _clerk_message = _tool_arguments_obj["message"]
            from .clerk import Clerk

            clerk_kwargs = dict(
                model=model,
                base_url=base_url,
                api_key=api_key,
                custom_llm_provider=custom_llm_provider,
            )
            # 仅当调用方显式指定层级时透传，保持 Actor/main 默认层级为 0
            if next_layer is not None:
                clerk_kwargs["layer"] = next_layer
            clerk = Clerk(_clerk_message, **clerk_kwargs)
            _clerk_response = await clerk.run()
            logger.debug(f"clerk response: {_clerk_response}")
            return ToolResponse(content=[TextBlock(type="text", text=_clerk_response)])
        except Exception as e:
            return ToolResponse(
                content=[TextBlock(type="text", text=f"调用工具 {LLM_FUNCTION_SUBAGENT} 错误: {str(e)}")]
            )

    if name == LLM_FUNCTION_PLANNER:
        try:
            from .planner import Planner

            planner = Planner(
                model=model,
                base_url=base_url,
                api_key=api_key,
                custom_llm_provider=custom_llm_provider,
            )
            tool_response = await planner.make(arguments)
            logger.debug(f"planner response: {tool_response.content}")
            return tool_response
        except Exception as e:
            return ToolResponse(
                content=[TextBlock(type="text", text=f"调用工具 {LLM_FUNCTION_PLANNER} 错误: {str(e)}")]
            )

    return await llm_tools_manager.execute_tool(name, arguments)


def _append_assistant_tool_calls(append: Callable[[dict], None], reasoning: str, tool_calls: list) -> None:
    if reasoning:
        append(
            {
                "role": "assistant",
                "content": None,
                "reasoning_content": reasoning,
                "tool_calls": tool_calls,
            }
        )
    else:
        append({"role": "assistant", "content": None, "tool_calls": tool_calls})


def _append_assistant_text(append: Callable[[dict], None], content: str, reasoning: str) -> None:
    if reasoning:
        append({"role": "assistant", "content": content, "reasoning_content": reasoning})
    else:
        append({"role": "assistant", "content": content})


async def run_stream_round(
    *,
    client,
    messages,
    tools,
    model: str,
    base_url: str,
    api_key: str,
    custom_llm_provider: str,
    append: Callable[[dict], None],
    llm_tools_manager,
    title: str = "AI",
    log_prefix: str = "",
    next_layer: Optional[int] = None,
    done_token: Optional[str] = None,
    on_tool_call: Optional[Callable[[str], None]] = None,
    **stream_kwargs,
) -> StreamResult:
    """执行一轮流式对话。

    渲染内容与思维链、处理工具调用，并把助手/工具消息按正确顺序写回 ``append``。
    返回 :class:`StreamResult`：``tool_called=True`` 表示本轮触发了工具调用，
    调用方应继续循环；否则为纯文本收尾，调用方可结束本轮。
    """
    collected_content = ""
    collected_reasoning = ""

    waiting_spinner = Spinner("dots", text="", style="bold blue")
    with Live(waiting_spinner, console=console, auto_refresh=False, vertical_overflow="visible") as live:
        async for chunk in client.stream(
            messages=messages,
            tools=tools,
            model=model,
            base_url=base_url,
            api_key=api_key,
            custom_llm_provider=custom_llm_provider,
            **stream_kwargs,
        ):
            if chunk.error:
                console.print(f"[red]{log_prefix}错误: {chunk.error}[/red]")
                append({"role": "assistant", "content": chunk.error})
                return StreamResult(error=chunk.error)

            # 处理内容流
            if chunk.delta:
                if chunk.delta_type == "content":
                    collected_content += chunk.delta
                    if collected_content.strip():
                        live.update(Panel(Markdown(collected_content), title=title), refresh=True)
                elif chunk.delta_type == "reasoning_content":
                    collected_reasoning += chunk.delta
                    if collected_reasoning.strip():
                        live.update(
                            Panel(
                                Markdown(collected_reasoning),
                                title=f"{title} 思维链",
                                border_style="grey50",
                                style="dim",
                            ),
                            refresh=True,
                        )

            # 处理完成
            if not chunk.finish:
                continue

            if chunk.finish_reason == "tool_calls":
                _append_assistant_tool_calls(append, collected_reasoning, chunk.tool_calls)

                tool_call_obj = chunk.tool_calls[0]
                function_obj = tool_call_obj["function"]

                console.print(
                    f"\n[bold yellow]{log_prefix}🛠️ 工具调用: {function_obj['name']}"
                    f"({clip(function_obj['arguments'], max_len=250)})[/bold yellow]"
                )
                logger.debug(f"{log_prefix}调用工具 {function_obj['name']} 参数: {function_obj['arguments']}")

                tool_response = await _execute_tool_call(
                    function_obj,
                    llm_tools_manager=llm_tools_manager,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    custom_llm_provider=custom_llm_provider,
                    next_layer=next_layer,
                )
                logger.debug(f"{log_prefix}工具 {function_obj['name']} 响应: {tool_response}")

                if on_tool_call is not None:
                    on_tool_call(function_obj["name"])

                # 工具结果入上下文前裁剪超长输出
                append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_obj["id"],
                        "name": function_obj["name"],
                        "content": shrink_tool_response(
                            tool_response.model_dump_json(), name=function_obj["name"]
                        ),
                    }
                )
                logger.debug(f"{log_prefix}工具调用结果已添加到消息历史，继续对话")
                return StreamResult(tool_called=True)

            # 纯文本收尾
            final_content = collected_content
            if done_token and done_token in final_content:
                console.print("[green]✅ 任务完成[/green]")
                final_content = final_content.replace(done_token, "").strip()

            _append_assistant_text(append, final_content, collected_reasoning)
            logger.debug(
                f"{log_prefix}大模型响应的消息：\n【content】:{final_content}\n\n"
                f"【reasoning_content:{collected_reasoning}】"
            )
            return StreamResult(content=final_content, reasoning=collected_reasoning)

    return StreamResult(content=collected_content, reasoning=collected_reasoning)
