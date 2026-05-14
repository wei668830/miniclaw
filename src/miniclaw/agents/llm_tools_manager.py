import json
from typing import Optional, List

from loguru import logger

from .base_llm_client import ToolResponse, TextBlock
from .constant import LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER
from .tools import (read_file, write_file, edit_file, append_file,
                    execute_shell_command, view_image, browser_use, desktop_screenshot, grep_search, glob_search,
                    launch_detached, get_current_time, set_user_timezone, tail_file)
from ..constant import EnvVarLoader

BUILTIN_TOOLS = {
    "read_file": {
        "invoke": read_file,
        "definition": {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": """Read a file.
                Use start_line/end_line to read a specific line range (output includes
                line numbers). Omit both to read the full file.
                IMPORTANT: This function accepts ONLY a single JSON object as arguments.
                Do NOT concatenate multiple JSON objects (e.g., {"file_path":"a"}{"file_path":"b"} is INVALID).
                Each invocation reads exactly ONE file; to read multiple files you MUST call this tool separately for each file.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file. Relative paths resolve from WORKING_DIR.",
                            "minLength": 1
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "First line to read (1-based, inclusive)",
                            "minLength": 1
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "Last line to read (1-based, inclusive)",
                            "minLength": 1
                        },
                    },
                    "required": ["file_path"]
                },
            }
        }
    },
    "write_file": {
        "invoke": write_file,
        "definition": {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": """Create or overwrite a file.
                IMPORTANT: Simultaneous writing of multiple files is not supported. If you need to write multiple files, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file. Relative paths resolve from WORKING_DIR.",
                            "minLength": 1
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write.",
                            "minLength": 1
                        },
                    },
                    "required": ["file_path", "content"]
                },
            }
        }
    },
    "edit_file": {
        "invoke": edit_file,
        "definition": {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": """Find-and-replace text in a file. 
                All occurrences of old_text are replaced with new_text.
                IMPORTANT: Simultaneous editing of multiple files is not supported. If you need to edit multiple files, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file. Relative paths resolve from WORKING_DIR.",
                            "minLength": 1
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Exact text to find.",
                            "minLength": 1
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text.",
                            "minLength": 1
                        },
                    },
                    "required": ["file_path", "old_text", "new_text"]
                },
            }
        }
    },
    "append_file": {
        "invoke": append_file,
        "definition": {
            "type": "function",
            "function": {
                "name": "append_file",
                "description": """Append content to the end of a file.
                IMPORTANT: Simultaneous appending of multiple files is not supported. If you need to append multiple files, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file. Relative paths resolve from WORKING_DIR.",
                            "minLength": 1
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to append.",
                            "minLength": 1
                        },
                    },
                    "required": ["file_path", "content"]
                },
            }
        }
    },
    "tail_file": {
        "invoke": tail_file,
        "definition": {
            "type": "function",
            "function": {
                "name": "tail_file",
                "description": """Read last N lines from a file.
                IMPORTANT: Simultaneous appending of multiple files is not supported. If you need to append multiple files, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the file. Relative paths resolve from WORKING_DIR.",
                            "minLength": 1
                        },
                        "lines": {
                            "type": "integer",
                            "description": "Number of lines to read from the end. Default: 100.",
                            "minLength": 1
                        },
                    },
                    "required": ["file_path"]
                },
            }
        }
    },
    "view_image": {
        "invoke": view_image,
        "definition": {
            "type": "function",
            "function": {
                "name": "view_image",
                "description": """Load an image file into the LLM context so the model can see it.
                IMPORTANT: Simultaneous viewing of multiple images is not supported. If you need to view multiple images, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "Path to the image file to view."
                        }
                    },
                    "required": ["file_path", "content"]
                },
            }
        }
    },
    "execute_shell_command": {
        "invoke": execute_shell_command,
        "definition": {
            "type": "function",
            "function": {
                "name": "execute_shell_command",
                "description": """Execute a shell command and return its output.
                Platform shells: Windows uses cmd.exe; Linux/macOS use /bin/sh or /bin/bash.
                IMPORTANT: Always consider the operating system before choosing commands.
                IMPORTANT: Simultaneous executing of multiple commands is not supported. If you need to execute multiple commands, please call them separately.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute."
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "The maximum time (in seconds) allowed for the command to run. Default is 60 seconds."
                        },
                        "cwd": {
                            "type": "integer",
                            "description": "The working directory for the command execution. If None, defaults to WORKING_DIR."
                        },
                    },
                    "required": ["command"]
                },
            }
        }
    },
    "control_browser": {
        "invoke": browser_use,
        "definition": {
            "type": "function",
            "function": {
                "name": "control_browser",
                "description": "Control browser using Playwright automation. Supports headless or headed mode. Provides comprehensive web automation including navigation, clicking, typing, screenshots, form filling, network monitoring, and multi-tab management. Use snapshot to get element refs for stable interaction.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Required. Browser action to perform.",
                            "enum": [
                                "start", "stop", "open", "navigate", "navigate_back", "snapshot",
                                "screenshot", "click", "type", "eval", "evaluate", "resize",
                                "console_messages", "network_requests", "handle_dialog", "file_upload",
                                "fill_form", "install", "press_key", "run_code", "drag", "hover",
                                "select_option", "tabs", "wait_for", "pdf", "close", "cookies_get",
                                "cookies_set", "cookies_clear", "connect_cdp", "list_cdp_targets",
                                "clear_browser_cache"
                            ]
                        },
                        "url": {
                            "type": "string",
                            "description": "URL to open. Required for action=open or navigate. For cookies_get, optional URL or JSON array of URLs to filter cookies by domain."
                        },
                        "page_id": {
                            "type": "string",
                            "description": "Page/tab identifier, default 'default'. Use different page_id for multiple tabs.",
                            "default": "default"
                        },
                        "selector": {
                            "type": "string",
                            "description": "CSS selector to locate element for click/type/hover etc. Prefer ref when available."
                        },
                        "ref": {
                            "type": "string",
                            "description": "Element ref from snapshot output; use for stable targeting. Prefer ref for click/type/hover/screenshot/evaluate/select_option."
                        },
                        "text": {
                            "type": "string",
                            "description": "Text to type. Required for action=type."
                        },
                        "code": {
                            "type": "string",
                            "description": "JavaScript code. Required for action=eval, evaluate, or run_code."
                        },
                        "path": {
                            "type": "string",
                            "description": "File path for screenshot save or PDF export."
                        },
                        "wait": {
                            "type": "integer",
                            "description": "Milliseconds to wait after click. Used with action=click.",
                            "minimum": 0
                        },
                        "full_page": {
                            "type": "boolean",
                            "description": "Whether to capture full page. Used with action=screenshot.",
                            "default": False
                        },
                        "width": {
                            "type": "integer",
                            "description": "Viewport width in pixels. Used with action=resize.",
                            "minimum": 1
                        },
                        "height": {
                            "type": "integer",
                            "description": "Viewport height in pixels. Used with action=resize.",
                            "minimum": 1
                        },
                        "level": {
                            "type": "string",
                            "description": "Console log level filter, e.g. 'info' or 'error'. Used with action=console_messages.",
                            "enum": ["info", "warning", "error", "debug"]
                        },
                        "filename": {
                            "type": "string",
                            "description": "Filename for saving logs or screenshot. Used with console_messages, network_requests, screenshot."
                        },
                        "accept": {
                            "type": "boolean",
                            "description": "Whether to accept dialog (true) or dismiss (false). Used with action=handle_dialog.",
                            "default": False
                        },
                        "prompt_text": {
                            "type": "string",
                            "description": "Input for prompt dialog. Used with action=handle_dialog when dialog is prompt."
                        },
                        "element": {
                            "type": "string",
                            "description": "Element description for evaluate etc. Prefer ref when available."
                        },
                        "paths_json": {
                            "type": "string",
                            "description": "JSON array string of file paths. Used with action=file_upload.",
                            "format": "json"
                        },
                        "fields_json": {
                            "type": "string",
                            "description": "JSON object string of form field name to value. Used with action=fill_form.",
                            "format": "json"
                        },
                        "key": {
                            "type": "string",
                            "description": "Key name, e.g. 'Enter', 'Control+a'. Required for action=press_key."
                        },
                        "submit": {
                            "type": "boolean",
                            "description": "Whether to submit (press Enter) after typing. Used with action=type.",
                            "default": False
                        },
                        "slowly": {
                            "type": "boolean",
                            "description": "Whether to type character by character. Used with action=type.",
                            "default": False
                        },
                        "include_static": {
                            "type": "boolean",
                            "description": "Whether to include static resource requests. Used with action=network_requests.",
                            "default": False
                        },
                        "screenshot_type": {
                            "type": "string",
                            "description": "Screenshot format, 'png' or 'jpeg'. Used with action=screenshot.",
                            "enum": ["png", "jpeg"],
                            "default": "png"
                        },
                        "snapshot_filename": {
                            "type": "string",
                            "description": "File path to save snapshot output. Used with action=snapshot."
                        },
                        "double_click": {
                            "type": "boolean",
                            "description": "Whether to double-click. Used with action=click.",
                            "default": False
                        },
                        "button": {
                            "type": "string",
                            "description": "Mouse button: 'left', 'right', or 'middle'. Used with action=click.",
                            "enum": ["left", "right", "middle"],
                            "default": "left"
                        },
                        "modifiers_json": {
                            "type": "string",
                            "description": "JSON array of modifier keys, e.g. ['Shift','Control']. Used with action=click.",
                            "format": "json"
                        },
                        "start_ref": {
                            "type": "string",
                            "description": "Drag start element ref. Used with action=drag."
                        },
                        "end_ref": {
                            "type": "string",
                            "description": "Drag end element ref. Used with action=drag."
                        },
                        "start_selector": {
                            "type": "string",
                            "description": "Drag start CSS selector. Used with action=drag."
                        },
                        "end_selector": {
                            "type": "string",
                            "description": "Drag end CSS selector. Used with action=drag."
                        },
                        "start_element": {
                            "type": "string",
                            "description": "Drag start element description. Used with action=drag."
                        },
                        "end_element": {
                            "type": "string",
                            "description": "Drag end element description. Used with action=drag."
                        },
                        "values_json": {
                            "type": "string",
                            "description": "JSON of option value(s) for select. Used with action=select_option.",
                            "format": "json"
                        },
                        "tab_action": {
                            "type": "string",
                            "description": "Tab action: list, new, close, or select. Required for action=tabs.",
                            "enum": ["list", "new", "close", "select"]
                        },
                        "index": {
                            "type": "integer",
                            "description": "Tab index for tabs select, zero-based. Used with action=tabs.",
                            "minimum": 0
                        },
                        "wait_time": {
                            "type": "number",
                            "description": "Seconds to wait. Used with action=wait_for.",
                            "minimum": 0
                        },
                        "text_gone": {
                            "type": "string",
                            "description": "Wait until this text disappears from page. Used with action=wait_for."
                        },
                        "frame_selector": {
                            "type": "string",
                            "description": "iframe selector, e.g. 'iframe#main'. Set when operating inside that iframe in snapshot/click/type etc."
                        },
                        "headed": {
                            "type": "boolean",
                            "description": "When True with action=start, launch a visible browser window (non-headless). User can see the real browser.",
                            "default": False
                        },
                        "cdp_port": {
                            "type": "integer",
                            "description": "When > 0 with action=start, Chrome is launched with --remote-debugging-port=N so external tools (or connect_cdp) can attach.",
                            "minimum": 0,
                            "default": 0
                        },
                        "cdp_url": {
                            "type": "string",
                            "description": "CDP base URL, e.g. 'http://localhost:9222'. Required for action=connect_cdp.",
                            "format": "uri"
                        },
                        "port": {
                            "type": "integer",
                            "description": "Scan a single specific port for action=list_cdp_targets.",
                            "minimum": 1,
                            "maximum": 65535
                        },
                        "port_min": {
                            "type": "integer",
                            "description": "Lower bound of port range for action=list_cdp_targets. Defaults to 9000.",
                            "minimum": 1,
                            "maximum": 65535,
                            "default": 9000
                        },
                        "port_max": {
                            "type": "integer",
                            "description": "Upper bound of port range for action=list_cdp_targets. Defaults to 10000.",
                            "minimum": 1,
                            "maximum": 65535,
                            "default": 10000
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    },
    "capture_screenshot": {
        "invoke": desktop_screenshot,
        "definition": {
            "type": "function",
            "function": {
                "name": "capture_screenshot",
                "description": "Capture a screenshot of the entire desktop (all monitors) or a single window. On macOS, can capture a specific window by user click; on Windows/Linux, only full-screen capture is supported.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Optional path to save the screenshot. If empty, saves under the current workspace directory. Should end in .png for PNG output.",
                            "default": ""
                        },
                        "capture_window": {
                            "type": "boolean",
                            "description": "If True on macOS, the user can click a window to capture just that window. On Windows/Linux, this parameter is ignored (only full-screen supported).",
                            "default": False
                        }
                    },
                    "additionalProperties": False
                }
            }
        }
    },
    "search_file_contents": {
        "invoke": grep_search,
        "definition": {
            "type": "function",
            "function": {
                "name": "search_file_contents",
                "description": """Search file contents by pattern, recursively. Returns results in format: path:line_number: content""",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Search string (or regex when is_regex is True), If you need to search for multiple keywords, please use regular expressions and set is_regex=True，for example 'error|exception|failed'",
                        },
                        "path": {
                            "type": "string",
                            "description": "File or directory to search in. Defaults to WORKING_DIR",
                            "default": None
                        },
                        "is_regex": {
                            "type": "boolean",
                            "description": "Treat pattern as a regular expression. Defaults to False",
                            "default": None
                        },
                        "case_sensitive": {
                            "type": "boolean",
                            "description": "Case-sensitive matching. Defaults to True",
                            "default": None
                        },
                        "context_lines": {
                            "type": "integer",
                            "description": "Context lines before and after each match (like grep -C). Capped at 5",
                            "default": 0,
                            "minimum": 0,
                            "maximum": 5
                        },
                        "include_pattern": {
                            "type": "string",
                            "description": "Only search files whose name matches this glob (e.g. '*.py'). Defaults to None (all text files)",
                            "default": None
                        }
                    },
                    "required": ["pattern"]
                }
            }
        }
    },
    "find_files": {
        "invoke": glob_search,
        "definition": {
            "type": "function",
            "function": {
                "name": "find_files",
                "description": """Find files matching a glob pattern (e.g. '*.py', '**/*.json'). Relative paths resolve from WORKING_DIR.
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            },
                            "description": "Glob pattern to array match (e.g. ['*.py','*.md'], ['**/*.json'], ['src/**/*.ts'])"
                        },
                        "path": {
                            "type": "string",
                            "description": "Root directory to search from. Defaults to WORKING_DIR",
                            "default": None
                        }
                    },
                    "required": ["pattern"]
                }
            }
        }
    },
    "subtask_executor": {
        "invoke": None,
        "definition": {
            "type": "function",
            "function": {
                "name": LLM_FUNCTION_SUBAGENT,
                "description": """The subtask executor uses an independent dialogue context to execute subtasks, which is suitable for complex subtasks that require multiple rounds of interaction. The parameter message is the subtask description, and a simplified execution report will be returned after the execution is completed.
                IMPORTANT: 子任务执行器在执行时必须获取足够的相关信息，比如参考文档、相关文件内容、注意事项、特殊问题处理方案等，以确保子任务能够独立完成。子任务执行过程中可以调用其他工具。
                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "task content"
                        },
                    },
                    "required": ["message"]
                }
            }
        }
    },
    "make_plans": {
        "invoke": None,
        "definition": {
            "type": "function",
            "function": {
                "name": LLM_FUNCTION_PLANNER,
                "description": "根据用户任务需求制定结构化、可落地、可分步执行的标准Markdown任务计划。自动拆分任务步骤、梳理优先级与依赖关系，严格遵守单步骤仅单次工具调用规范，生成含标题、计划说明、进度跟踪清单、明细执行步骤的标准方案，并自动持久化保存计划文件到本地 .miniclaw/plans 目录，返回文件绝对路径；生成失败时自动分析并返回具体原因。【适用场景】1. 用户下达复杂项目、多流程、多步骤类任务，需要拆解为有序执行方案；2. 需要生成正式工作规划、执行方案、任务流程、项目路线图；3. 任务涉及多工具串行依赖、有先后执行顺序，需要标准化步骤约束；4. 需要产出可存档、可跟踪进度的Markdown计划文档；5. 开发、调研、学习、工程落地等需要整体规划执行步骤的场景。【不适用场景】1. 简单常识问答、单词查询、代码小问题即时答疑；2. 无需拆解步骤、可直接一次性给出答案的简单请求；3. 闲聊讨论、观点交流，不需要落地执行规划的对话；4. 已处于任务执行中途，仅需调用单个工具完成当前原子操作。",
                "parameters": {
                  "type": "object",
                  "properties": {
                    "requirements": {
                      "type": "string",
                      "description": "用户待完成任务的完整需求、目标、约束条件及背景说明，是制定计划的核心输入依据"
                    }
                  },
                  "required": ["requirements"]
                },
                "exclude_related": ["subagent"]
              }
        }
    },
    "launch_detached": {
        "invoke": launch_detached,
        "definition": {
            "type": "function",
            "function": {
                "name": "launch_detached",
                "description": "在后台启动一个完全独立的进程，脱离当前Python程序独立运行。"
                               "\n所有输出重定向到日志文件。"
                               "\n适用于启动Spring Boot、Node.js、执行yarn/npm构建等场景。路径支持~表示用户目录。"
                               "\n重要说明：本工具是通过调用 subprocess.Popen 启动独立进程的方式实现。"
                               '\n  对于 Windows 系统，将命令写入 bat 文件再通过 start /min cmd /c "{bat_file}" 方式执行'
                               '\n  对于 Linux/Mac 系统，将命令写入 script 文件再通过 nohup "{script_file}" > /dev/null 2>&1 & 方式执行'
                               '\n  其中，Windows 系统在脚本中通过 chcp 65001 > nul 改变执行环境字符集',
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cmd": {
                            "type": "string",
                            "description": "要执行的命令字符串，如'java -jar app.jar'、'node server.js'、'yarn install'、'npm run build'、'yarn install && yarn build'"
                        },
                        "cwd": {
                            "type": "string",
                            "description": "工作目录，支持~，如'~/projects/backend'，必须是项目根目录"
                        },
                        "log_file": {
                            "type": "string",
                            "description": "日志文件路径，支持~，如'~/logs/app.log'，进程所有输出写入此文件"
                        },
                        "env": {
                            "type": "object",
                            "description": "额外环境变量，如{\"NODE_ENV\":\"production\",\"PORT\":\"3000\"}",
                            "default": None
                        }
                    },
                    "required": ["cmd", "cwd", "log_file"]
                }
            }
        }
    },
    "get_current_time": {
        "invoke": get_current_time,
        "definition": {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": """Get the current time in format `%Y-%m-%d %H:%M:%S TZ (Day)`, e.g. "2026-02-13 19:30:45 Asia/Shanghai (Friday)".\n Call this tool when the user asks for the current time or when the current time is needed for other operations.""",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
    },
    "set_user_timezone": {
        "invoke": set_user_timezone,
        "definition": {
            "type": "function",
            "function": {
                "name": "set_user_timezone",
                "description": "Set the user timezone. Only call this tool when the user explicitly asks to change their timezone.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone_name": {
                            "type": "string",
                            "description": """IANA timezone name (e.g. "Asia/Shanghai", "America/New_York", "Europe/London", "UTC")."""
                        }
                    },
                    "required": ["timezone_name"]
                }
            }
        }
    },
}


def _get_enabled_tools():
    enabled_tools_str = EnvVarLoader.get_str("LLM_ENABLED_TOOLS")
    disabled_tools_str = EnvVarLoader.get_str("LLM_DISABLED_TOOLS")

    enabled_tools = []
    if enabled_tools_str is not None:
        if enabled_tools_str == "*" or enabled_tools_str.lower() == "all":
            enabled_tools = list(BUILTIN_TOOLS.keys())
        else:
            for tn in enabled_tools_str.strip().split(","):
                if len(tn.strip()) > 0:
                    enabled_tools.append(tn.strip())

    if disabled_tools_str is not None:
        for tn in disabled_tools_str.strip().split(","):
            if len(tn.strip()) > 0 and tn.strip() in enabled_tools:
                enabled_tools.pop(enabled_tools.index(tn.strip()))

    return enabled_tools


class LLMToolsManager:
    """LLMToolsManager is responsible for managing tools that agents can use."""

    def __init__(self):
        """Initialize the ToolsManager with an empty registry."""
        self.tools = {}
        self.register_builtin_tools()

    def register_builtin_tools(self):
        """Register the built-in tools."""
        enabled_tools = _get_enabled_tools()
        for key, value in BUILTIN_TOOLS.items():
            if key in enabled_tools:
                self.tools[key] = value

    def get_tool_func(self, key):
        """Get a tool by name."""
        return self.tools.get(key)["invoke"]

    def _detect_multiple_json_objects(self, arguments: str) -> bool:
        """Detect if arguments contain concatenated JSON objects (e.g., {"a":1}{"b":2})."""
        stripped = arguments.strip()
        import re
        return bool(re.search(r'\}\s*\{', stripped))

    async def execute_tool(self, key, arguments: Optional[str] = None) -> ToolResponse:
        try:
            # Check if arguments contain multiple concatenated JSON objects (common LLM mistake)
            if arguments is not None and self._detect_multiple_json_objects(arguments):
                error_msg = (
                    f"Argument format error: detected multiple JSON objects concatenated together ({arguments}). "
                    f"This tool does not support processing multiple objects at once. Please call the tool separately for each file/command."
                )
                logger.warning(f"Error executing tool {key} - {error_msg}")
                return ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=error_msg
                        )
                    ]
                )

            args = {} if arguments is None else json.loads(arguments)
            return await self.get_tool_func(key)(**args)
        except Exception as e:
            logger.exception(f"Error executing tool {key} with arguments {arguments}")
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"Error executing tool: {str(e)}"
                    )
                ]
            )

    def get_llm_tools(self, include: Optional[List[str]] = None, exclude: Optional[List[str]] = None) -> List:
        """Get the list of registered tools."""
        _tools = []
        if include is not None:
            for key, value in self.tools.items():
                if key in include:
                    _tools.append(value["definition"])
        elif exclude is not None:
            for key, value in self.tools.items():
                if key not in exclude:
                    _tools.append(value["definition"])
        else:
            for key, value in self.tools.items():
                _tools.append(value["definition"])

        return _tools


llm_tools_manager = LLMToolsManager()

__all__ = ["llm_tools_manager"]
