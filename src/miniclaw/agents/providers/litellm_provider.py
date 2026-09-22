from typing import AsyncIterator, Optional

import httpx
import litellm
from litellm import acompletion
from loguru import logger

from ..base_llm_client import BaseLLMClient, LLMResponse, LLMStreamChunk
from ..llm_configurator import (
    LLMConfigurator,
    LLM_USAGE_MASTER,
)

# 关闭所有的调试信息输出
litellm.suppress_debug_info = True


def _root_cause(e: Exception) -> Optional[Exception]:
    """获取异常链中最底层的异常（若不存在则返回 None）"""
    current = e
    seen = {id(e)}
    while True:
        nxt = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if nxt is None or id(nxt) in seen:
            return None if current is e else current
        seen.add(id(nxt))
        current = nxt


def _format_llm_error(e: Exception) -> str:
    """将大模型请求异常转换为便于排查的错误信息

    litellm 会把底层连接类异常统一包装为 “OpenAIException - Connection error.”，
    直接抛出该信息容易误判为配置问题，因此这里补充底层异常与排查提示。
    """
    detail = " ".join(str(e).split())
    message = f"{type(e).__name__}: {detail}"

    root = _root_cause(e)
    root_text = " ".join(str(root).split()) if root is not None else ""
    root_name = type(root).__name__ if root is not None else ""
    combined = f"{message} {root_text}"

    hint = None
    if root_name in ("ServerDisconnectedError", "IncompleteReadError") \
            or isinstance(root, (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)) \
            or "disconnected without sending a response" in combined \
            or "Server disconnected" in combined \
            or "Empty reply" in combined:
        hint = ("服务端在返回响应前断开了连接，通常是模型网关对请求的限制（如 system 消息过长、超出上下文或内容策略）"
                "或网关自身异常导致，请检查模型服务端")
    elif root_name in ("ConnectionRefusedError", "ClientConnectorError", "ClientConnectorSSLError", "ConnectError") \
            or isinstance(root, (httpx.ConnectError, httpx.ConnectTimeout)):
        hint = "无法连接到模型服务，请检查 base_url、网络连通性、代理设置及模型服务是否已启动"
    elif root_name in ("ConnectTimeoutError", "SocketTimeoutError", "ServerTimeoutError", "ReadTimeoutError") \
            or isinstance(root, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        hint = "请求模型服务超时，模型服务响应过慢或不可用"
    elif "Connection error" in combined or "Connection reset" in combined or "Connection refused" in combined:
        hint = "模型服务连接异常（连接被拒绝或被中断），请检查 base_url 与模型服务状态"

    if hint is not None:
        message = f"{message} | 排查提示：{hint}"

    if root_text != "" and root_text != detail:
        message = f"{message} | 底层错误：{type(root).__name__}: {root_text}"

    return message


class LiteLLMClient(BaseLLMClient):

    @classmethod
    def _build_completion_kwargs(
            cls,
            *,
            messages: list[dict],
            **kwargs
    ) -> dict:
        kwargs = LLMConfigurator.config_connection(**kwargs)

        kwargs["messages"] = messages

        if "usage_type" in kwargs:
            kwargs.pop("usage_type")

        logger.info(f"构建 LiteLLM 请求参数:[model]:{kwargs['model']}, [api_base]:{kwargs['api_base']}, [api_key]:{kwargs['api_key'][:10]}")

        return kwargs

    async def chat(
            self,
            messages: list[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> LLMResponse:
        try:
            params = self._build_completion_kwargs(
                messages=messages,
                stream=False,
                llm_usage_type=llm_usage_type,
                **kwargs
            )
            response = await acompletion(**params)

            content = ""
            reasoning_content = ""
            tool_calls = None
            if hasattr(response, "choices") and len(response.choices) > 0:
                msg = response.choices[0].message
                content = msg.content.strip() if hasattr(msg, "content") and msg.content else ""
                reasoning_content = msg.reasoning_content.strip() if hasattr(msg, "reasoning_content") and msg.reasoning_content else ""
                if hasattr(msg, "tool_calls") and msg.tool_calls is not None and len(msg.tool_calls) > 0:
                    tool_calls = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            }
                        }
                        for tc in msg.tool_calls
                    ]

            # pt, ct, tt = None, None, None
            # if hasattr(response, "usage") and response.usage is not None:
            #     pt = getattr(response.usage, "prompt_tokens", None)
            #     ct = getattr(response.usage, "completion_tokens", None)
            #     tt = getattr(response.usage, "total_tokens", None)
            #
            # cost = None
            # try:
            #     cost = completion_cost(response)
            # except Exception:
            #     pass

            return LLMResponse(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
                # prompt_tokens=pt,
                # completion_tokens=ct,
                # total_tokens=tt,
                # cost_usd=cost
            )

        except Exception as e:
            error = _format_llm_error(e)
            logger.exception(f"大模型非流式对话错误:{error}")
            return LLMResponse(
                content="",
                error=error
            )

    async def stream(
            self,
            messages: list[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        try:
            params = self._build_completion_kwargs(
                    messages=messages,
                    stream=True,
                    llm_usage_type=llm_usage_type,
                    **kwargs
                )

            tool_call_id = ""
            tool_name = ""
            tool_arguments = ""

            response = await acompletion(**params)
            async for chunk in response:
                # 默认增量类型为 content
                delta_type = "content"
                # 取增量
                delta = ""
                is_tool_call = False
                if hasattr(chunk, "choices") and len(chunk.choices) > 0:
                    delta_obj = chunk.choices[0].delta
                    # 添加对 reasoning_content 支持（针对 DeepSeek R1 等模型的思维链输出）
                    if hasattr(delta_obj, 'reasoning_content') and delta_obj.reasoning_content:
                        delta_type = "reasoning_content"
                        delta = delta_obj.reasoning_content or ""
                    else:
                        delta_type = "content"
                        delta = delta_obj.content or ""

                    # 取工具调用信息
                    if hasattr(delta_obj, "tool_calls") and delta_obj.tool_calls is not None and len(delta_obj.tool_calls) > 0:
                        is_tool_call = True
                        delta_type = "tool_calls"
                        ccdtc = delta_obj.tool_calls[0]
                        if hasattr(ccdtc, "id") and ccdtc.id is not None and ccdtc.id.strip() != "":
                            tool_call_id = ccdtc.id
                        if hasattr(ccdtc, "function") and ccdtc.function is not None:
                            function_obj = ccdtc.function
                            if hasattr(function_obj, "name") and function_obj.name is not None and function_obj.name.strip() != "":
                                tool_name = function_obj.name
                            if hasattr(function_obj, "arguments") and function_obj.arguments is not None:
                                tool_arguments += function_obj.arguments

                # 是否结束
                finish_reason = None
                if hasattr(chunk, "choices") and len(chunk.choices) > 0:
                    finish_reason = chunk.choices[0].finish_reason
                is_finish = finish_reason is not None

                # ------------------------------
                # 核心修复：结束时强制计算 Token & Cost
                # ------------------------------
                if is_finish:
                    prompt_tokens = None
                    completion_tokens = None
                    total_tokens = None
                    cost_usd = None

                    # 优先用模型返回的 usage（例如 OpenAI）
                    # if hasattr(chunk, "usage") and chunk.usage is not None:
                    #     prompt_tokens = getattr(chunk.usage, "prompt_tokens", None)
                    #     completion_tokens = getattr(chunk.usage, "completion_tokens", None)
                    #     total_tokens = getattr(chunk.usage, "total_tokens", None)

                    yield LLMStreamChunk(
                        delta=delta,
                        delta_type=delta_type,
                        tool_calls= [{
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_arguments,
                            }
                        }] if finish_reason == "tool_calls" else None,
                        finish=True,
                        finish_reason= finish_reason,
                        # prompt_tokens=prompt_tokens,
                        # completion_tokens=completion_tokens,
                        # total_tokens=total_tokens,
                        # cost_usd=cost_usd
                    )
                else:
                    if not is_tool_call:
                        yield LLMStreamChunk(
                            delta=delta,
                            delta_type=delta_type,
                            finish=False
                        )

        except Exception as e:
            error = _format_llm_error(e)
            logger.exception(f"大模型流式对话错误:{error}")
            yield LLMStreamChunk(
                delta="",
                finish=True,
                error=error
            )
