"""MiniClaw 内置工具子包。

统一导出文件读写/搜索、Shell/Browser 控制、截图、时间与联网搜索等
可供大模型调用的工具函数。
"""

from .browser_control import browser_use
from .desktop_screenshot import desktop_screenshot
from .file_io import read_file, write_file, edit_file, append_file, tail_file
from .file_search import grep_search, glob_search
from .launch_detached import launch_detached
from .shell import execute_shell_command
from .get_current_time import get_current_time, set_user_timezone
from .web_search import web_search

__all__ = [
    "read_file",
    "write_file",
    "edit_file",
    "append_file",
    "tail_file",
    "grep_search",
    "glob_search",
    "browser_use",
    "desktop_screenshot",
    "execute_shell_command",
    "launch_detached",
    "get_current_time",
    "set_user_timezone",
    "web_search",
]
