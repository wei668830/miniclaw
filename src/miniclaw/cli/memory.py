import json
from typing import Optional


class Memory:
    """精简大模型对话内容并保留关键信息的类"""

    def __init__(self, path: str, usage_type: Optional[str] = None):
        self.path = path

        from ..agents import get_llm_client
        from ..agents.llm_configurator import LLM_USAGE_MASTER
        self.llm_usage_type = usage_type if usage_type is not None else LLM_USAGE_MASTER
        self.client = get_llm_client()

    async def condense(self, messages:list):
        """精简对话内容并保留关键信息"""
        chat_response = await self.client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是一个对话内容精简器，负责精简对话内容并保留关键信息，精简规则如下："
                               "\n- 不要保留 role=system 的内容"
                               "\n- 若精简的时机发生在一个任务执行的过程中间，请务必保留必要的过程信息，并根据任务的执行情况要求继续执行后续处理，不要因为精简的处理而导致任务执行中断"
                               "\n- 精简后的内容必须保留必要的用户输入和大模型回复的核心信息，去掉冗余的细节和工具调用相关的信息"
                               "\n- 若发现最新对话内容与历史的对话内容重复，请去掉重复的部分，保留最新的内容"
                               "\n- 若发现历史的对话内容与最新的对话内容无直接或间接联系，请直接去掉无关的历史对话信息"
                               "\n- 精简后的内容必须保留对话的连贯性和完整性，确保能够反映出对话的主要脉络和关键信息"
                               "\n- 特别是在精简的过程中，如果发现有重要的上下文信息或者关键信息可能会被丢失，请务必保留这些信息，以确保对话内容的完整性和连贯性"
                               "\n- 特别是对话中出现的参考文档，请尽量保留文档的路径并说明文档的作用和内容摘要，以确保对话内容的完整性和连贯性"
                               "\n- 特别是对话中涉及的执行跟踪文件，务必保留文档的路径并说明跟踪文件的作用和内容摘要，以确保对话内容的完整性和连贯性"
                               "\n- 精简后的内容不要再以 JSON 的方式出现，而是以 markdown 文本的方式呈现"

                },
                {
                    "role": "user",
                    "content": "原始的对话完整内容如下(JSON 格式):\n\n" + json.dumps(messages, ensure_ascii=False)
                }
            ],
        )

        content = chat_response.content

        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

