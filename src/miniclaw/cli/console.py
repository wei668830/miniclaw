import os
from typing import List

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from rich.console import Console

# 创建 Rich 控制台实例
console = Console()

class SlashCommandCompleter(Completer):
    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            for cmd in self.commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

_history_file = os.path.expanduser("~/.miniclaw/console/history.txt")
if os.path.dirname(_history_file):
    os.makedirs(os.path.dirname(_history_file),exist_ok=True)

def get_prompt_session(slash_commands:List[str]) -> PromptSession:
    return PromptSession(
        completer=SlashCommandCompleter(slash_commands),
        history=FileHistory(_history_file)
    )

__all__ = ["console", "get_prompt_session"]