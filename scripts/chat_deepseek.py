from litellm import completion
from loguru import logger

def chat():
    try:
        # 1. 发起请求
        # 注意：这里使用的是 LiteLLM 的标准调用方式
        response = completion(
            model="deepseek-v4-flash",  # 或者 deepseek-chat
            messages=[{"role": "user", "content": "你好，请简单地介绍下自己。"}],
            api_base="https://api.deepseek.com",
            api_key="",
            custom_llm_provider="openai",
        )

        print("🤖 DeepSeek 正在思考...\n" + "-" * 30)

        print()
        print(response)
        print()

        if hasattr(response, "choices") and len(response.choices) > 0:
            msg = response.choices[0].message
            content = msg.content.strip() if hasattr(msg, "content") and msg.content else ""
            print(f"💬 DeepSeek 回答: {content}")

        print("\n" + "-" * 30 + "\n生成完毕。")

    except Exception as e:
        print(f"\n发生错误: {e}")

def stream():
    try:
        # 1. 发起请求
        # 注意：这里使用的是 LiteLLM 的标准调用方式
        response = completion(
            model="deepseek-v4-flash",  # 或者 deepseek-chat
            messages=[{"role": "user", "content": "你好，请简单地介绍下自己。"}],
            stream=True,
            api_base="https://api.deepseek.com",
            api_key="",
            custom_llm_provider="openai",
        )

        print("🤖 DeepSeek 正在思考...\n" + "-" * 30)

        # 2. 处理流式响应
        for chunk in response:
            logger.debug(chunk)
            # 获取 delta 对象（增量数据）
            delta = chunk.choices[0].delta

            # --- 关键点 A: 处理思考过程 ---
            # DeepSeek R1 等模型会在 reasoning_content 中返回思维链
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                # 你可以选择打印它，或者将其存入缓冲区
                print(f"🧠 [思考]: {delta.reasoning_content}", end="", flush=True)

            # --- 关键点 B: 处理最终回答 ---
            # 标准的回答依然在 content 字段中
            if delta.content:
                # 如果是第一次输出回答，可以加个换行分隔思考和回答
                if not hasattr(delta, 'reasoning_content') or not delta.reasoning_content:
                    # 这里只是简单处理，实际可能需要更复杂的逻辑来判断换行
                    pass
                print(f"💬 [回答]: {delta.content}", end="", flush=True)

        print("\n" + "-" * 30 + "\n生成完毕。")

    except Exception as e:
        print(f"\n发生错误: {e}")


if __name__ == "__main__":
    chat()
    # stream()