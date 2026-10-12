"""基于 litellm 的大模型客户端实现。

封装统一的 chat / stream 接口，并附带 token 与费用估算、异常信息格式化等辅助逻辑。
"""

import inspect
import os
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
from ...utils.common import masking_str

# 关闭所有的调试信息输出
litellm.suppress_debug_info = True


async def _aclose_stream_quietly(response) -> None:
    """尽力关闭 litellm 流式响应对象（用于正常结束与取消/中止两种收尾）。

    被取消（Ctrl+C 中止本轮）时，异步生成器的 ``finally`` 仍会执行，这里做
    best-effort 关闭，释放底层 HTTP 连接；任何异常都被吞掉，避免影响上层收尾。
    """
    if response is None:
        return
    aclose = getattr(response, "aclose", None) or getattr(response, "close", None)
    if aclose is None:
        return
    try:
        result = aclose()
        if inspect.isawaitable(result):
            await result
    except BaseException:
        logger.opt(exception=True).debug('关闭 litellm 流式响应失败')


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


# 内置兜底单价（USD / 每百万 token）。
# 当 litellm 价格表未覆盖某模型时，按「厂商前缀」匹配兜底单价（可被环境变量覆盖）。
# 参考 DeepSeek 官方标准价（缓存未命中）：deepseek-chat 输入 ≈ $0.27 / 输出 ≈ $1.10。
_BUILTIN_FALLBACK_PRICES = {
    "deepseek": {"input": 0.27, "output": 1.10},
}


def _cost_from_env(prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    """环境变量兜底单价（优先级最高）：``MINICLAW_COST_INPUT_PER_1M`` / ``..._OUTPUT_PER_1M``。"""
    try:
        in_price = float(os.environ.get("MINICLAW_COST_INPUT_PER_1M", "0") or 0)
        out_price = float(os.environ.get("MINICLAW_COST_OUTPUT_PER_1M", "0") or 0)
    except (TypeError, ValueError):
        logger.opt(exception=True).debug('解析费用环境变量失败，跳过环境变量兜底单价')
        return None
    if in_price == 0 and out_price == 0:
        return None
    return prompt_tokens / 1_000_000 * in_price + completion_tokens / 1_000_000 * out_price


def _fallback_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
    """litellm 价格表未覆盖时的兜底计价：先环境变量，再按厂商内置单价。"""
    env_cost = _cost_from_env(prompt_tokens, completion_tokens)
    if env_cost is not None:
        return env_cost
    vendor = (model or "").split("/")[0].strip().lower()
    price = _BUILTIN_FALLBACK_PRICES.get(vendor)
    if price:
        return prompt_tokens / 1_000_000 * price["input"] + completion_tokens / 1_000_000 * price["output"]
    return None


def _compute_cost(model: str, prompt_tokens: Optional[int], completion_tokens: Optional[int]) -> Optional[float]:
    """依据 litellm 价格表计算费用；未覆盖时回退到环境变量 / 厂商内置单价。"""
    pt = prompt_tokens or 0
    ct = completion_tokens or 0
    try:
        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model, prompt_tokens=pt, completion_tokens=ct
        )
        return float(prompt_cost) + float(completion_cost)
    except Exception:
        logger.opt(exception=True).debug('litellm 价格表计算失败，回退到内置兜底单价')
        return _fallback_cost(model, pt, ct)


def _compute_tokens_and_cost(model: str, messages: list, completion_text: str):
    """估算 token 用量与费用。

    不依赖网关是否在流式响应中返回 usage：优先由 litellm 的 token_counter 估算 token，
    再由 cost_per_token 依据内置价格表计算费用（价格表未覆盖的模型返回 None）。
    返回 ``(prompt_tokens, completion_tokens, total_tokens, cost_usd)``。
    """
    prompt_tokens = completion_tokens = total_tokens = None
    cost_usd = None
    try:
        prompt_tokens = litellm.token_counter(model=model, messages=messages)
    except Exception:
        logger.opt(exception=True).debug('估算 prompt token 失败')
        prompt_tokens = None
    try:
        completion_tokens = litellm.token_counter(model=model, text=completion_text or "")
    except Exception:
        logger.opt(exception=True).debug('估算 completion token 失败')
        completion_tokens = None
    if prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
        cost_usd = _compute_cost(model, prompt_tokens, completion_tokens)
    return prompt_tokens, completion_tokens, total_tokens, cost_usd


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
    """基于 litellm 库的大模型客户端，实现非流式与流式对话。"""

    @classmethod
    def _build_completion_kwargs(
            cls,
            *,
            messages: list[dict],
            **kwargs
    ) -> dict:
        """构建并校验 litellm 请求参数。

        借助 LLMConfigurator 归一化连接配置，注入 messages，移除无效字段，
        并打印脱敏后的请求信息。

        :param messages: 对话消息列表
        :param kwargs: 其余连接/请求参数
        :return: 可直接传入 litellm 的请求参数字典
        """
        kwargs = LLMConfigurator.config_connection(**kwargs)

        kwargs["messages"] = messages

        if "usage_type" in kwargs:
            kwargs.pop("usage_type")

        logger.info(
            "构建 LiteLLM 请求参数: [model]:{}, [api_base]:{}, [api_key]:{}",
            kwargs.get("model"),
            kwargs.get("api_base"),
            masking_str(str(kwargs.get("api_key") or "")),
        )

        return kwargs

    async def chat(
            self,
            messages: list[dict],
            llm_usage_type: str = LLM_USAGE_MASTER,
            **kwargs
    ) -> LLMResponse:
        """发起非流式对话并返回完整结果。

        :param messages: 对话消息列表
        :param llm_usage_type: LLM 使用类型，用于选择对应配置
        :param kwargs: 其余请求参数
        :return: 包含内容、工具调用、token 用量与费用的 LLMResponse；出错时 error 字段携带错误信息
        """
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

            pt = ct = tt = None
            cost_usd = None
            usage_obj = getattr(response, "usage", None)
            if usage_obj is not None and getattr(usage_obj, "prompt_tokens", None) is not None:
                pt = getattr(usage_obj, "prompt_tokens", None)
                ct = getattr(usage_obj, "completion_tokens", None)
                tt = getattr(usage_obj, "total_tokens", None)
                cost_usd = _compute_cost(params.get("model"), pt, ct)
            else:
                pt, ct, tt, cost_usd = _compute_tokens_and_cost(params.get("model"), messages, content)

            return LLMResponse(
                content=content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=tt,
                cost_usd=cost_usd,
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
        """发起流式对话，逐块产出增量内容。

        处理 reasoning_content 与工具调用增量，在结束时附带 token 用量与费用；
        发生异常时产出一个带 error 的结束块，并统一关闭底层流。

        :param messages: 对话消息列表
        :param llm_usage_type: LLM 使用类型，用于选择对应配置
        :param kwargs: 其余请求参数
        :yield: 逐个 LLMStreamChunk 增量块
        """
        response = None
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
            completion_acc = ""

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
                    # 优先使用网关返回的 usage；缺失时由 token_counter 估算 token，并用价格表计算费用
                    usage_obj = getattr(chunk, "usage", None)
                    if usage_obj is not None and getattr(usage_obj, "prompt_tokens", None) is not None:
                        prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
                        completion_tokens = getattr(usage_obj, "completion_tokens", None)
                        total_tokens = getattr(usage_obj, "total_tokens", None)
                        cost_usd = _compute_cost(params.get("model"), prompt_tokens, completion_tokens)
                    else:
                        prompt_tokens, completion_tokens, total_tokens, cost_usd = \
                            _compute_tokens_and_cost(params.get("model"), messages, completion_acc)

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
                        cost_usd=cost_usd,
                    )
                else:
                    if not is_tool_call:
                        completion_acc += delta
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
        finally:
            # 正常结束、报错、以及被取消（Ctrl+C 中止本轮 / GeneratorExit）时统一关闭底层流。
            await _aclose_stream_quietly(response)
