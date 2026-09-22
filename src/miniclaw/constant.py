import os
from pathlib import Path


MINICLAW_LOG = """
  __  __ _      _  ___ _             
 |  \/  (_)_ _ (_)/ __| |__ ___ __ __
 | |\/| | | ' \| | (__| / _` \ V  V /
 |_|  |_|_|_||_|_|\___|_\__,_|\_/\_/ 
                                     
"""

class EnvVarLoader:
    """Utility to load and parse environment variables with type safety
    and defaults.
    """

    @staticmethod
    def get_bool(env_var: str, default: bool = False) -> bool:
        """Get a boolean environment variable,
        interpreting common truthy values."""
        val = os.environ.get(env_var, str(default)).lower()
        return val in ("true", "1", "yes")

    @staticmethod
    def get_float(
        env_var: str,
        default: float = 0.0,
        min_value: float | None = None,
        max_value: float | None = None,
        allow_inf: bool = False,
    ) -> float:
        """Get a float environment variable with optional bounds
        and infinity handling."""
        try:
            value = float(os.environ.get(env_var, str(default)))
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            if not allow_inf and (
                value == float("inf") or value == float("-inf")
            ):
                return default
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_int(
        env_var: str,
        default: int = 0,
        min_value: int | None = None,
        max_value: int | None = None,
    ) -> int:
        """Get an integer environment variable with optional bounds."""
        try:
            value = int(os.environ.get(env_var, str(default)))
            if min_value is not None and value < min_value:
                return min_value
            if max_value is not None and value > max_value:
                return max_value
            return value
        except (TypeError, ValueError):
            return default

    @staticmethod
    def get_str(env_var: str, default: str = "") -> str:
        """Get a string environment variable with a default fallback."""
        return os.environ.get(env_var, default)

WORKING_DIR = (
    Path(EnvVarLoader.get_str("MINICLAW_WORKING_DIR", "~/.miniclaw"))
    .expanduser()
    .resolve()
)

# ---------------------------------------------------------------------------
# 记忆（Memory）与上下文预算相关默认值
# 全部可由同名环境变量覆盖，未配置时使用以下安全默认值。
# ---------------------------------------------------------------------------

# 模型上下文窗口 token 数（保守值）
DEFAULT_CONTEXT_WINDOW = 128000
# 软阈值比例：上下文占用超过 window * ratio 时触发自动精简
DEFAULT_CONTEXT_SOFT_RATIO = 0.6
# 硬阈值比例：上下文占用超过 window * ratio 时强制精简
DEFAULT_CONTEXT_HARD_RATIO = 0.85
# 为模型回复预留的 token 数
DEFAULT_CONTEXT_RESERVE_TOKENS = 4096
# 单条工具结果超过该 token 数则落盘裁剪
DEFAULT_TOOL_OUTPUT_MAX_TOKENS = 4000
# 精简时保留的最近轮次数（tail）
DEFAULT_MEMORY_KEEP_RECENT = 6
# 分块 map-reduce 的单块 token 上限
DEFAULT_MEMORY_CHUNK_TOKENS = 20000
# 上下文超限后的最大重试次数
DEFAULT_CONTEXT_RETRY_MAX = 2
# 工具输出全文落盘目录
DEFAULT_TOOL_OUTPUT_DIR = "~/.miniclaw/multimodal/tool_outputs"
# JSONL 原始历史目录
DEFAULT_MEMORY_RAW_DIR = "~/.miniclaw/memory/raw"
# 会话状态目录
DEFAULT_STATE_DIR = "~/.miniclaw/state"
# 单轮对话内工具调用的最大迭代次数
DEFAULT_MAX_TOOL_ITERATIONS = 100000
# 子代理允许的最大嵌套层数
DEFAULT_MAX_SUBAGENT_LAYER = 1
# 任务完成标记 token（工具/子代理用于声明任务结束）
DEFAULT_TASK_DONE_TOKEN = "【TASK_DONE】"

# ---------------------------------------------------------------------------
# 方案 B：提示词驱动的自主执行
# ---------------------------------------------------------------------------

# agent 模式主循环的自主执行提示词（可由 CHAT_AGENT_AUTONOMY_PROMPT 覆盖）
AGENT_AUTONOMY_PROMPT = (
    "你是自主代理，负责端到端推进任务，无需向用户征求确认或询问是否继续。"
    "只要还能通过工具（读文件、写代码、执行命令、搜索等）取得进展，就持续执行，不要中途停下等待用户。"
    "仅当任务已完成，或确实被阻塞（缺少必要信息/权限/外部依赖，必须由用户提供）时才停止。"
    "任务完成时，在答复末尾输出标记 【TASK_DONE】。"
)

# 子代理（子任务执行者）版自主执行提示词（可由 CHAT_CLERK_AUTONOMY_PROMPT 覆盖）
CLERK_AUTONOMY_PROMPT = (
    "你是自主代理，负责端到端推进决策者下达的子任务，无需向用户征求确认或询问是否继续。"
    "只要还能通过工具（读文件、写代码、执行命令、搜索等）取得进展，就持续执行，不要中途停下等待。"
    "仅当任务已完成，或确实被阻塞（缺少必要信息/权限/外部依赖，必须由用户提供）时才停止。"
    "任务完成时，在答复末尾输出标记 【TASK_DONE】。"
)

# Env to indicate running inside a container (e.g. Docker). Set to 1/true/yes.
RUNNING_IN_CONTAINER = EnvVarLoader.get_bool(
    "MINICLAW_RUNNING_IN_CONTAINER",
    False,
)

# Playwright: use system Chromium when set (e.g. in Docker).
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH_ENV = "PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH"