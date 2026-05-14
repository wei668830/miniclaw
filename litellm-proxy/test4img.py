# 注意：这个示例需要你先运行 litellm-proxy，并且确保它支持接收图片数据。请根据你的实际情况调整代码中的路径和参数。
# 这个示例展示了如何将图片数据以 base64 编码的形式发送给 litellm-proxy，并让模型分析图片内容。请确保你的模型和代理都支持这种输入格式。
# 模型要使用支持多模态的版本，例如 gpt-4o 或者其他支持图像输入的模型。同时，litellm-proxy 也需要正确处理这种输入格式并将其转发给模型。
import base64
import os
from pathlib import Path

from litellm import completion

with open(Path("resources/images/abc01.jfif").resolve(), "rb") as f:
    data = base64.b64encode(f.read()).decode("utf-8")

try:
    response = completion(
        model="litellm_proxy",           # 你的自定义别名
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "看一下这个图片画的是什么？"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}
                ]
            },
        ],
        api_base="http://localhost:4000", # 指向本地代理
        api_key="sk-123456",            # 随便填
        custom_llm_provider="openai"    # 👈 关键！强制指定为 openai 协议
    )
    print(response.choices[0].message.content)

except Exception as e:
    print(f"出错了: {e}")