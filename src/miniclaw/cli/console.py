"""CLI 控制台与交互式输入支持。

提供全局 Rich 控制台实例、斜杠命令补全器，以及带历史持久化的 prompt_toolkit 会话。
"""

import os
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from rich.console import Console

# 创建 Rich 控制台实例
console = Console()

class SlashCommandCompleter(Completer):
    """斜杠命令补全器：当输入以 ``/`` 开头时按前缀补全已注册的斜杠命令。"""

    def __init__(self, commands):
        """初始化补全器。

        :param commands: 可补全的斜杠命令列表
        """
        self.commands = commands

    def get_completions(self, document, complete_event):
        """生成器：产出与光标前文本前缀匹配的斜杠命令补全项。"""
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd in self.commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

_history_file = os.path.expanduser("~/.miniclaw/console/history.txt")
if os.path.dirname(_history_file):
    os.makedirs(os.path.dirname(_history_file),exist_ok=True)

def get_prompt_session(slash_commands:List[str]) -> PromptSession:
    """构造带斜杠命令补全与历史持久化的 prompt_toolkit 会话。

    :param slash_commands: 可补全的斜杠命令列表
    :return: 配置好补全器与历史文件的 PromptSession
    """
    return PromptSession(
        completer=SlashCommandCompleter(slash_commands),
        history=FileHistory(_history_file)
    )

__all__ = ["console", "get_prompt_session"]