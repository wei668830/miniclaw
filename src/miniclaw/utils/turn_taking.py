import json

from ..constant import EnvVarLoader


def get_messages_without_tool_calls(messages: list) -> list:
    """获取不包含工具调用以及工具回复的消息列表，即只含用户输入和大模型回复"""
    filtered_messages = []
    for m in messages:
        if m["role"] == "tool":
            continue
        if m["role"] == "assistant" and m["content"] is None:
            continue
        filtered_messages.append(m)

    return filtered_messages

def get_last_n_messages(messages: list, n: int = 3) -> list:
    """获取最后的 n 条消息，包括工具的回复内容"""
    last_n_messages = []

    count = len(messages)

    if count < n:
        return messages

    u_count = 0
    m_index = count - 1
    while m_index >= 0 and u_count < n:
        m = messages[m_index]

        if m["role"] == "user":
            last_n_messages.insert(0, m)
            u_count += 1
        elif m["role"] == "assistant" and m["content"] is not None:
            last_n_messages.insert(0, m)

        m_index -= 1

    return last_n_messages


def get_advance_messages(messages: list, n: int = 5) -> list:
    """获取决策者判断是否继续执行的消息列表"""
    _system_content = EnvVarLoader.get_str("CHAT_ADVANCE_SYSTEM_PROMPT",
                                           """你是一名决策者，根据会话的内容决定是继续执行下一步还是停止执行。""")
    _user_message = EnvVarLoader.get_str("CHAT_ADVANCE_USER_PROMPT", "结束")
    _last_n = get_last_n_messages(messages, n)
    _last_n_content = _user_message.replace("{{last_n_content}}", json.dumps(_last_n))
    advance_messages = [
        {
            "role": "system",
            "content": _system_content
        },
        {
            "role": "user",
            "content": _last_n_content
        }
    ]

    return advance_messages
