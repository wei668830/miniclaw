"""统一的流式对话执行器（S3）。

抽取自 ``CommandLineInteraction.stream`` / ``Actor._stream`` / ``Clerk._stream``
三处高度重复的主循环，把差异通过参数与回调注入：

- 单轮流式渲染（``Live`` + ``Spinner`` + ``Markdown``）
- ``tool_calls`` 的工具分发（子代理 / 计划器 / 普通工具）
- 按正确顺序把消息写回调用方（通过 ``append`` 回调，兼容器/持久化两种存储方式）

调用方自行保留外层 ``while`` 循环与异常策略（如上下文超限重试、工具轮次上限），
从而最大限度保持原有对外行为不变。抽取后三处逻辑修一处即可全部受益。

控制台打印约定（本轮审阅修复）：
- 所有拼接进富文本标签的动态内容（模型产出的参数、错误文本等）一律经
  :func:`rich.markup.escape` 转义，避免模型输出中的 ``[...]`` 触发 ``MarkupError``；
- 助手 ``tool_calls`` 消息与对应 ``tool`` 消息**成对原子落盘**，二者之间不做任何
  可能抛异常的渲染/打印，避免出现悬空 ``tool_calls`` 被服务端拒绝；
- ``Live`` 采用 ``transient=True``：流式过程中的思维链/正文预览只是「临时状态」，
  退出时会自动清除；所有需要保留在滚动历史中的输出一律通过 ``console.print`` 显式落屏。
  这样可避免非 transient 模式下「已落屏内容」与「Live 末帧」在同一屏重复显示
  （尤其是工具调用轮次：思维链预览仍是 Live 末帧时又被补打一次）；
- 思维链（``reasoning_content``）仅在预览阶段用 ``Live`` 展示，切换到正文或结束时通过
  ``console.print`` 补一次落屏，保证退出后仍可在滚动历史中回溯；
- 正文 ``Markdown`` 与思维链的 ``Live`` 预览均按增量阈值（``render_step``）节流，
  避免逐 token 全量重渲染（O(n^2)）；流式结束时再显式落屏一次完整正文；
- ``Live`` 预览按「终端可视行数」而非逻辑行数裁剪（``_preview_text`` / ``_PREVIEW_MAX_ROWS``），
  使预览区高度恒定且远小于终端视口，避免预览区高过屏幕导致 ``transient`` 清除时的
  相对游标定位失效，从而把思维链预览残留在最终回复下方（表现为「思考内容在最后输出」）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, List, Optional

from loguru import logger
from rich.cells import cell_len
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.spinner import Spinner

from .console import console
from ..agents.base_llm_client import TextBlock, ToolResponse
from ..agents.constant import LLM_FUNCTION_PLANNER, LLM_FUNCTION_SUBAGENT
from ..constant import EnvVarLoader
from ..utils.common import clip
from ..utils.context import shrink_tool_response


# 需要在入参中原样回传 ``reasoning_content``（思维链）的接入点关键字。
#
# DeepSeek「思考模式」规则（https://api-docs.deepseek.com/guides/thinking_mode）：
# 当请求携带 ``tools`` 参数时，**所有**历史轮次 assistant 消息的 ``reasoning_content``
# 都必须完整回传，即使某些轮次并未发生工具调用；一旦缺失，服务端返回 400
# （"The ``reasoning_content`` in the thinking mode must be passed back to the API."）。
# 不带 ``tools`` 时该字段会被忽略，传与不传均无副作用。
# 而多数 OpenAI 兼容端点并不接受该字段，故默认仅对已知需要回传的接入点保留。
_REASONING_PASSTHROUGH_KEYWORDS = ("deepseek",)


def _should_keep_reasoning(model: str, base_url: str, custom_llm_provider: str) -> bool:
    """判断当前目标模型是否需要在入参中保留 ``reasoning_content``。

    优先读取环境变量 ``MINICLAW_KEEP_REASONING_CONTENT`` 作为显式开关
    （``1/true/yes/on`` 强制保留，``0/false/no/off`` 强制剥离）；
    未设置时按模型名/接入点/提供方自动识别：命中 DeepSeek 等需要回传思维链的
    端点则保留，其余一律剥离，避免把 ``reasoning_content`` 发给不支持该字段的模型
    （如 OpenAI）导致新的 400。
    """
    override = EnvVarLoader.get_str("MINICLAW_KEEP_REASONING_CONTENT", "").strip().lower()
    if override in ("1", "true", "yes", "on"):
        return True
    if override in ("0", "false", "no", "off"):
        return False

    haystack = f"{model or ''} {base_url or ''} {custom_llm_provider or ''}".lower()
    return any(keyword in haystack for keyword in _REASONING_PASSTHROUGH_KEYWORDS)


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


def _sanitize_messages(messages: List[dict], keep_reasoning: bool = True) -> List[dict]:
    """构造发送给模型的消息副本，修复可能存在的非法配对。

    OpenAI 兼容协议要求：带 ``tool_calls`` 的助手消息后必须紧跟针对每个
    ``tool_call_id`` 的 ``tool`` 消息。历史中若因异常/精简出现悬空 ``tool_calls``
    或被孤立的 ``tool`` 消息，会被服务端以 400 拒绝（insufficient tool messages）。
    这里做一次保守清理：

    - 助手 ``tool_calls`` 若缺少对应的 ``tool`` 响应：移除其 ``tool_calls``（仅在仍有
      正文时保留该消息，否则整条丢弃）；
    - 紧随被丢弃助手消息的孤立 ``tool`` 消息一并丢弃；
    - 单独出现的孤立 ``tool`` 消息丢弃。

    ``keep_reasoning`` 控制是否保留助手消息中的 ``reasoning_content``（思维链）：

    - ``True``（默认）：原样保留。DeepSeek 思考模式在**携带 ``tools`` 参数**时，要求
      历史所有轮次 assistant 消息的 ``reasoning_content`` 完整回传，否则返回 400
      （"The ``reasoning_content`` in the thinking mode must be passed back to the API."）；
    - ``False``：剥离 ``reasoning_content``。用于不支持该字段的端点（如多数 OpenAI
      兼容服务），避免因其导致 400。

    是否保留由 :func:`_should_keep_reasoning` 依据目标模型/接入点判定后传入。
    """
    strip = (lambda m: m) if keep_reasoning else _strip_reasoning
    result: List[dict] = []
    i = 0
    n = len(messages)
    while i < n:
        msg = messages[i]
        role = msg.get("role")

        if role == "assistant" and msg.get("tool_calls"):
            ids = [tc.get("id") for tc in (msg.get("tool_calls") or [])]
            j = i + 1
            responded = set()
            while j < n and messages[j].get("role") == "tool":
                responded.add(messages[j].get("tool_call_id"))
                j += 1

            if all(cid in responded for cid in ids):
                result.append(strip(msg))
                result.extend(strip(m) for m in messages[i + 1:j])
            else:
                # 悬空 tool_calls：丢弃调用信息与其孤立 tool 响应
                content = msg.get("content")
                if content:
                    cleaned = {k: v for k, v in msg.items() if k != "tool_calls"}
                    result.append(strip(cleaned))
            i = j
            continue

        if role == "tool":
            # 孤立 tool 消息（前面没有匹配的助手 tool_calls）
            i += 1
            continue

        result.append(strip(msg))
        i += 1

    return result


def _strip_reasoning(msg: dict) -> dict:
    if "reasoning_content" in msg:
        msg = {k: v for k, v in msg.items() if k != "reasoning_content"}
    return msg


# Live 预览区允许占用的最大可视行数（含换行折行）。
#
# ``Live`` 采用 ``transient=True``，退出时依赖 ``LiveRender.restore_cursor()`` 按
# 「上一次渲染高度」上移并逐行清除预览区。该相对高度一旦接近/超过终端可视高度
# （即预览区几乎占满整屏，渲染过程中控制台已发生滚动），游标就回不到预览区顶部，
# 清除不彻底，会把最后一帧（通常是思维链预览）残留在最终回复下方——表现为
# 「思考内容出现在最后」。
#
# 故预览必须按「终端可视行数」裁剪，并同时约束「逻辑行数」与「显示宽度（cell，
# 兼容 CJK 宽字符）」：只要预览区高度恒定为若干行、远离整屏高度，清除就不会失配。
# 最终完整内容仍由 ``console.print`` 全量落屏，不受影响。
_PREVIEW_MAX_ROWS = 6


def _tail_cells(text: str, max_cells: int) -> str:
    """取字符串末尾、显示宽度不超过 ``max_cells`` 的部分（兼容 CJK 宽字符）。"""
    if cell_len(text) <= max_cells:
        return text
    out: List[str] = []
    used = 0
    for ch in reversed(text):
        w = cell_len(ch)
        if used + w > max_cells:
            break
        out.append(ch)
        used += w
    return "".join(reversed(out))


def _preview_text(text: str, max_rows: int = _PREVIEW_MAX_ROWS) -> str:
    """把文本裁剪为高度受限的 ``Live`` 预览（不改动最终落屏的完整文本）。

    只取末尾内容（最新进度），并按终端可视宽/高折算行数，保证换行折行后的高度
    仍远小于终端视口——这是 ``transient`` 预览能被正确清除的前提。
    """
    if not text:
        return ""
    width = getattr(console, "width", None) or 80
    height = getattr(console, "height", None) or 24
    # 预留安全边距（标题/边框，以及每行最多折两行的余量）：预览总高 <= height - 6。
    rows = max(1, min(max_rows, (height - 6) // 2))
    cell_width = max(8, width - 4)
    budget = cell_width * rows

    kept: List[str] = []
    used = 0
    for line in reversed(text.splitlines()):
        cost = cell_len(line)
        if kept and (used + cost > budget or len(kept) >= rows):
            break
        kept.append(line)
        used += cost
    kept.reverse()
    result = "\n".join(kept)
    # 单行过长（无换行、整段推理）时保留其尾部，避免预览看不到最新内容。
    if len(kept) <= 1 and cell_len(result) > budget:
        result = _tail_cells(result, budget)
    return result


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
    reasoning_flushed = False

    # 渲染节流：正文与思维链的 Live 预览均仅当新增字符达到阈值或出现换行时刷新，
    # 避免逐 token 全量重渲染（O(n^2)）。
    render_step = 24
    last_rendered_len = 0
    last_reasoning_len = 0

    def _flush_reasoning() -> None:
        """把思维链一次性落屏到滚动历史（Live 退出后仍可回溯）。"""
        nonlocal reasoning_flushed
        if not reasoning_flushed and collected_reasoning.strip():
            console.print(
                Panel(
                    Markdown(collected_reasoning),
                    title=f"{title} 思维链",
                    border_style="grey50",
                    style="dim",
                )
            )
            reasoning_flushed = True

    # 依据目标模型/接入点决定是否保留思维链：DeepSeek 思考模式携带 tools 时必须回传
    # reasoning_content，否则 400；不支持该字段的端点则必须剥离，详见 _should_keep_reasoning。
    keep_reasoning = _should_keep_reasoning(model, base_url, custom_llm_provider)
    safe_messages = _sanitize_messages(messages, keep_reasoning=keep_reasoning)

    waiting_spinner = Spinner("dots", text="", style="bold blue")
    # transient=True：预览区域退出即清除，持久内容一律由 console.print 落屏，
    # 避免「补打落屏」与「Live 末帧」重复显示（详见模块 docstring）。
    with Live(waiting_spinner, console=console, auto_refresh=False,
              transient=True, vertical_overflow="visible") as live:
        async for chunk in client.stream(
            messages=safe_messages,
            tools=tools,
            model=model,
            base_url=base_url,
            api_key=api_key,
            custom_llm_provider=custom_llm_provider,
            **stream_kwargs,
        ):
            if chunk.error:
                console.print(f"[red]{escape(log_prefix)}错误: {escape(str(chunk.error))}[/red]")
                append({"role": "assistant", "content": chunk.error})
                return StreamResult(error=chunk.error)

            # 处理内容流
            if chunk.delta:
                if chunk.delta_type == "content":
                    collected_content += chunk.delta
                    if collected_content.strip() and (
                        len(collected_content) - last_rendered_len >= render_step
                        or "\n" in chunk.delta
                    ):
                        _flush_reasoning()
                        live.update(Panel(Markdown(_preview_text(collected_content)), title=title), refresh=True)
                        last_rendered_len = len(collected_content)
                elif chunk.delta_type == "reasoning_content":
                    collected_reasoning += chunk.delta
                    if (
                        collected_reasoning.strip()
                        and not reasoning_flushed
                        and (
                            len(collected_reasoning) - last_reasoning_len >= render_step
                            or "\n" in chunk.delta
                        )
                    ):
                        # 思维链在切换正文前仅用于 Live 预览（按阈值节流）；
                        # 预览仅取末尾若干行，避免预览区高过终端视口（见 _PREVIEW_MAX_LINES）。
                        live.update(
                            Panel(
                                Markdown(_preview_text(collected_reasoning)),
                                title=f"{title} 思维链",
                                border_style="grey50",
                                style="dim",
                            ),
                            refresh=True,
                        )
                        last_reasoning_len = len(collected_reasoning)

            # 处理完成
            if not chunk.finish:
                continue

            if chunk.finish_reason == "tool_calls":
                tool_call_obj = chunk.tool_calls[0]
                function_obj = tool_call_obj["function"]
                fn_name = str(function_obj["name"])
                fn_args = str(function_obj["arguments"])

                tool_response = await _execute_tool_call(
                    function_obj,
                    llm_tools_manager=llm_tools_manager,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    custom_llm_provider=custom_llm_provider,
                    next_layer=next_layer,
                )

                if on_tool_call is not None:
                    on_tool_call(fn_name)

                # 原子落盘：助手 tool_calls 与 tool 响应必须成对写入，
                # 二者之间不执行任何可抛异常的打印/渲染，避免悬空 tool_calls。
                _append_assistant_tool_calls(append, collected_reasoning, chunk.tool_calls)
                append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_obj["id"],
                        "name": fn_name,
                        "content": shrink_tool_response(
                            tool_response.model_dump_json(), name=fn_name
                        ),
                    }
                )

                # 落盘后再做信息展示（动态内容全部转义）
                _flush_reasoning()
                console.print(
                    f"\n[bold yellow]{escape(log_prefix)}🛠️ 工具调用: "
                    f"{escape(fn_name)}({escape(clip(fn_args, max_len=250))})[/bold yellow]"
                )
                logger.debug(f"{log_prefix}调用工具 {fn_name} 参数: {fn_args}")
                logger.debug(f"{log_prefix}工具 {fn_name} 响应: {tool_response}")
                logger.debug(f"{log_prefix}工具调用结果已添加到消息历史，继续对话")
                return StreamResult(tool_called=True)

            # 纯文本收尾
            final_content = collected_content
            if done_token and done_token in final_content:
                console.print("[green]✅ 任务完成[/green]")
                final_content = final_content.replace(done_token, "").strip()

            _flush_reasoning()
            _append_assistant_text(append, final_content, collected_reasoning)
            # Live 为 transient，退出后会清除预览区域，故显式落屏一次完整正文，
            # 保证退出后屏幕/滚动历史保留完整回复（与「无效内容不落屏」一致）。
            if final_content.strip():
                console.print(Panel(Markdown(final_content), title=title))
            logger.debug(
                f"{log_prefix}大模型响应的消息：\n【content】:{final_content}\n\n"
                f"【reasoning_content:{collected_reasoning}】"
            )
            return StreamResult(content=final_content, reasoning=collected_reasoning)

    # 流意外结束（未收到 finish）：尽力把已产出的内容落屏
    _flush_reasoning()
    if collected_content.strip():
        console.print(Panel(Markdown(collected_content), title=title))
    return StreamResult(content=collected_content, reasoning=collected_reasoning)
