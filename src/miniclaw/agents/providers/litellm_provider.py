import os
from typing import AsyncIterator
from typing import Optional

from litellm import acompletion, completion_cost
from loguru import logger

from ..base_llm_client import BaseLLMClient, LLMResponse, LLMStreamChunk
from ..llm_configurator import (
    LLMConfigurator,
    LLM_USAGE_MASTER,
    LLM_USAGE_THINKING,
    LLM_USAGE_HAIKU,
    LLM_USAGE_SONNET,
    LLM_USAGE_OPUS,
)


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

        return kwargs

    async def chat(
            self,
            messages: list[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> LLMResponse:
        try:
            response = await acompletion(
                **self._build_completion_kwargs(
                    messages=messages,
                    stream=False,
                    llm_usage_type=llm_usage_type,
                    **kwargs
                )
            )

            content = ""
            if hasattr(response, "choices") and len(response.choices) > 0:
                msg = response.choices[0].message
                content = msg.content.strip() if hasattr(msg, "content") and msg.content else ""

            pt, ct, tt = None, None, None
            if hasattr(response, "usage") and response.usage is not None:
                pt = getattr(response.usage, "prompt_tokens", None)
                ct = getattr(response.usage, "completion_tokens", None)
                tt = getattr(response.usage, "total_tokens", None)

            cost = None
            try:
                cost = completion_cost(response)
            except Exception:
                pass

            return LLMResponse(
                content=content,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cost_usd=cost
            )

        except Exception as e:
            return LLMResponse(
                content="",
                error=str(e)
            )

    async def stream(
            self,
            messages: list[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> AsyncIterator[LLMStreamChunk]:
        try:
            response = await acompletion(
                **self._build_completion_kwargs(
                    messages=messages,
                    stream=True,
                    llm_usage_type=llm_usage_type,
                    **kwargs
                )
            )


            tool_call_id = ""
            tool_name = ""
            tool_arguments = ""

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
                    if hasattr(chunk, "usage") and chunk.usage is not None:
                        prompt_tokens = getattr(chunk.usage, "prompt_tokens", None)
                        completion_tokens = getattr(chunk.usage, "completion_tokens", None)
                        total_tokens = getattr(chunk.usage, "total_tokens", None)

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
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                        cost_usd=cost_usd
                    )
                else:
                    if not is_tool_call:
                        yield LLMStreamChunk(
                            delta=delta,
                            delta_type=delta_type,
                            finish=False
                        )

        except Exception as e:
            logger.exception(f"流式chat错误")
            yield LLMStreamChunk(
                delta="",
                finish=True,
                error=str(e)
            )
