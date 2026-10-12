# -*- coding: utf-8 -*-
"""MiniClaw 配置子包。

聚合默认浏览器探测、工作目录与容器环境判定等配置相关工具。
"""
from .utils import (
    get_playwright_chromium_executable_path,
    get_system_default_browser,
    is_running_in_container,
)

__all__ = [
    "get_playwright_chromium_executable_path",
    "get_system_default_browser",
    "is_running_in_container",
]
