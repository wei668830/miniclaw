"""原生 LLM 接口路由（保留/兼容）：直接代理单轮与流式大模型调用。

与 ``chat_router`` 的会话化聊天不同，本路由按 CID 读写聊天上下文，
适用于不依赖会话运行时的轻量直连场景。
"""

import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from ..deps import require_token
from ..llm_chat_context import store_chat_context, fetch_chat_context
from ...agents import get_llm_client
from ...agents.llm_tools_manager import llm_tools_manager

router = APIRouter(
    prefix="/api/llm",
    tags=["llm"],
    dependencies=[Depends(require_token)],
)


class ChatRequest(BaseModel):
    """原生聊天请求体（聊天 ID、消息列表与可选模型/采样/provider）。"""

    cid: str = Field(..., description="Chat ID")
    messages: list[dict[str, Any]]
    model: str | None = Field(default=None, description="litellm model id, e.g. openai/gpt-4o-mini")
    temperature: float | None = None
    max_tokens: int | None = None
    provider: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    """POST /api/llm/chat：拼接 CID 历史后单轮调用模型并回写上下文。

    仅接受单条非空用户消息；返回内容、思考及用量。

    :param req: 原生聊天请求体
    :return: 含内容/用量字段的字典
    """
    if not req.messages or len(req.messages) != 1 or req.messages[0].get('role') != 'user' or not req.messages[0].get('content', '').strip():
        raise HTTPException(status_code=400, detail="必须传递一条非空的用户消息")

    client = get_llm_client(req.provider)

    # 1. 获取历史消息（需要 await）
    history_messages = await fetch_chat_context(req.cid)
    logger.debug(f"Fetched chat context for CID {req.cid}: {json.dumps(history_messages, ensure_ascii=False)}")

    # 2. 构建完整的消息列表：历史消息 + 当前用户消息
    messages = history_messages + req.messages
    logger.debug(f"Full messages: {json.dumps(messages, ensure_ascii=False)}")

    # 3. 调用 LLM
    result = await client.chat(
        messages=messages,  # 使用完整的消息列表
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    if result.error:
        raise HTTPException(status_code=400, detail=result.error)

    # 4. 存储用户消息（使用 req.messages 中的用户输入）
    # 假设 req.messages 的最后一条是用户消息
    await store_chat_context(
        req.cid,
        req.messages[0]
    )

    # 5. 存储助手回复
    await store_chat_context(
        req.cid,
        {
            "role": "assistant",
            "content": result.content,
            "reasoning_content": result.reasoning_content
        }
    )

    return {
        "content": result.content,
        "reasoning_content": result.reasoning_content,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "cost_usd": result.cost_usd,
    }


@router.post("/stream")
async def stream_chat(req: ChatRequest):
    """POST /api/llm/stream：以 SSE 流式调用模型，支持工具调用回路。

    :param req: 原生聊天请求体
    :return: text/event-stream 流式响应
    """
    client = get_llm_client(req.provider)

    tools = llm_tools_manager.get_llm_tools()
    logger.warning(f"可用工具列表：{tools}")

    messages = req.messages

    async def event_generator() -> AsyncIterator[str]:
        """按 SSE 编码逐块产出模型结果，处理工具调用并以循环续接对话。"""
        while True:
            try:
                logger.warning("@@@@@@@@@@ 开始新的对话流 @@@@@@@@@@")
                logger.warning(f"当前对话消息：{messages}")
                logger.info(f"\n[dim]📊 默认messages: {messages} [/dim]")
                async for chunk in client.stream(
                        messages=messages,
                        model=req.model,
                        temperature=req.temperature,
                        max_tokens=req.max_tokens,
                        tools=tools,
                ):
                    if chunk.error:
                        payload = {"error": chunk.error}
                        yield f"event: error\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                        return

                    payload = {"delta": chunk.delta}
                    yield f"event: chunk\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

                    if chunk.finish:
                        logger.warning(f"Chunk finished: {chunk}")
                        if chunk.finish_reason == "tool_calls":
                            # llm_tools_manager.get_tool_func(chunk.tool_call["name"])(**chunk.tool_call["arguments"])
                            messages.append(
                                {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": chunk.tool_calls
                                }
                            )

                            tool_call_obj = chunk.tool_calls[0]
                            function_obj = tool_call_obj["function"]

                            yield f"event: tool_call\ndata: {json.dumps(tool_call_obj, ensure_ascii=False)}\n\n"

                            logger.warning(f"实际工具调用。。。。")
                            tool_response = await llm_tools_manager.execute_tool(
                                function_obj["name"],
                                function_obj["arguments"]
                            )
                            logger.warning(f"工具调用结果：{tool_response}")
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call_obj["id"],
                                    "name": function_obj["name"],
                                    "content": tool_response.model_dump_json()
                                }
                            )
                            logger.warning("工具调用结果已添加到对话消息中，继续对话流。。。")
                            break

                        else:
                            done_payload = {
                                "finish_reason": chunk.finish_reason,
                                "prompt_tokens": chunk.prompt_tokens,
                                "completion_tokens": chunk.completion_tokens,
                                "total_tokens": chunk.total_tokens,
                                "cost_usd": chunk.cost_usd,
                            }
                            yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                            return

            except Exception as e:
                logger.opt(exception=True).error(f'对话流发生异常：{e}')
                error_payload = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")
