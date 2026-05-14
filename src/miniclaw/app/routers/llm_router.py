import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel, Field

from ...agents import get_llm_client
from ...agents.llm_tools_manager import llm_tools_manager

router = APIRouter(prefix="/api/llm", tags=["llm"])

class ChatRequest(BaseModel):
    model: str = Field(..., description="litellm model id, e.g. openai/gpt-4o-mini")
    messages: list[dict[str, Any]]
    temperature: float = 0.7
    max_tokens: int = 4096
    provider: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest):
    client = get_llm_client(req.provider)
    result = await client.chat(
        messages=req.messages,
        model=req.model,
        temperature=req.temperature,
        max_tokens=req.max_tokens,
    )

    if result.error:
        raise HTTPException(status_code=400, detail=result.error)

    return {
        "content": result.content,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "total_tokens": result.total_tokens,
        "cost_usd": result.cost_usd,
    }


@router.post("/stream")
async def stream_chat(req: ChatRequest):
    client = get_llm_client(req.provider)

    tools = llm_tools_manager.get_llm_tools()
    logger.warning(f"可用工具列表：{tools}")

    messages = req.messages

    async def event_generator() -> AsyncIterator[str]:
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
                logger.error(f"对话流发生异常：{e}", exc_info=True)
                error_payload = {"error": str(e)}
                yield f"event: error\ndata: {json.dumps(error_payload, ensure_ascii=False)}\n\n"
                return

    return StreamingResponse(event_generator(), media_type="text/event-stream")
