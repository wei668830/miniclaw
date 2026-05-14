from litellm import completion

try:
    response = completion(
        model="deepseek/deepseek-chat",           # 你的自定义别名
        messages=[{"role": "user", "content": "你好"}],
        api_base="https://api.deepseek.com", # 指向本地代理
        api_key="sk-57e9b4180a464cc7a29a887fe2b76a3c",            # 随便填
        # custom_llm_provider="openai"    # 👈 关键！强制指定为 openai 协议
    )
    print(response.choices[0].message.content)

except Exception as e:
    print(f"出错了: {e}")