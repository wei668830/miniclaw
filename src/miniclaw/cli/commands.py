"""Slash 命令注册表。

单一数据源 ``COMMAND_SPECS`` 同时驱动三处，保证「分发 / 帮助 / 补全」永远一致：

- 命令分发：``dispatch()``
- ``/help`` 帮助表格：``build_help_table()``
- 输入补全列表：``SLASH_COMMANDS``

每个命令对应 ``CommandLineInteraction`` 上的一个 ``_cmd_<name>`` 方法，
方法签名为 ``(arg: str | None)``，可同步或异步。
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass

from rich.table import Table

from .console import console


@dataclass(frozen=True)
class CommandSpec:
    """单条命令的元数据。"""

    name: str          # 不含前导 '/'，例如 "session-list"
    summary: str       # 简短说明
    example: str       # 示例（可含换行）
    handler: str       # CommandLineInteraction 上的处理方法名


# ---------------------------------------------------------------------------
# 命令元数据（唯一事实来源）
# ---------------------------------------------------------------------------
COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "help", "显示帮助信息", "/help", "_cmd_help"
    ),
    CommandSpec(
        "llm", "显示/切换/设置大模型配置",
        "/llm 显示大模型列表，* 号标记正在使用的大模型配置\n"
        "/llm use <name> 切换大模型配置\n"
        "/llm set <model>$$$<api_url>$$$<api_key>[$$$<custom_llm_provider>] 设置临时大模型配置",
        "_cmd_llm",
    ),
    CommandSpec(
        "agent", "运行模式切换为代理模式",
        "/agent 代理模式下大模型将尽量自动推进任务执行",
        "_cmd_agent",
    ),
    CommandSpec(
        "chat", "运行模式切换为对话模式",
        "/chat 对话模式下大模型将采用一问一答的方式",
        "_cmd_chat",
    ),
    CommandSpec(
        "clear", "清除对话上下文", "/clear", "_cmd_clear"
    ),
    CommandSpec(
        "history", "历史对话记录",
        "/history N 最近 N 条历史对话记录，若不指定 N 默认看最后 3 条记录",
        "_cmd_history",
    ),
    CommandSpec(
        "memory", "记忆缓存",
        "/memory 精简记忆\n/memory <记忆缓存文件名> 提取记忆",
        "_cmd_memory",
    ),
    CommandSpec(
        "memory-list", "记忆缓存列表",
        "/memory-list 查看记忆缓存列表（默认最新 10 个）\n/memory-list 20 查看最新的前 20 个记忆",
        "_cmd_memory_list",
    ),
    CommandSpec(
        "context", "查看上下文 token 占用与阈值状态",
        "/context\n/context shrink 立即裁剪工具输出",
        "_cmd_context",
    ),
    CommandSpec(
        "session-list", "列出最近的会话",
        "/session-list N 查看最近 N 个会话（默认 10，* 标记当前会话）",
        "_cmd_session_list",
    ),
    CommandSpec(
        "session-load", "加载指定会话到上下文（不自动接续）",
        "/session-load <session_id>", "_cmd_session_load",
    ),
    CommandSpec(
        "session-resume", "恢复并接续执行指定会话",
        "/session-resume <session_id>", "_cmd_session_resume",
    ),
    CommandSpec(
        "session-export", "导出指定会话为 Markdown",
        "/session-export <session_id> [path]", "_cmd_session_export",
    ),
    CommandSpec(
        "skill-list", "可用的技能列表",
        "/skill-list 扫描技能目录下的技能列表", "_cmd_skill_list",
    ),
    CommandSpec(
        "skill-load", "加载技能",
        "/skill-load <skill-name>,... 同时加载多个技能以逗号分隔",
        "_cmd_skill_load",
    ),
    CommandSpec(
        "model", "查看/设置当前模型",
        "/model\n/model <model>", "_cmd_model",
    ),
    CommandSpec(
        "api_key", "查看/设置当前 API KEY",
        "/api_key\n/api_key <key>", "_cmd_api_key",
    ),
    CommandSpec(
        "base_url", "查看/设置当前 Base URL",
        "/base_url\n/base_url <url>", "_cmd_base_url",
    ),
    CommandSpec(
        "custom_llm_provider", "查看/设置自定义模型供应商",
        "/custom_llm_provider\n/custom_llm_provider <provider>",
        "_cmd_custom_llm_provider",
    ),
    CommandSpec(
        "temperature", "查看/设置温度（0.0~1.0）",
        "/temperature\n/temperature 0.7", "_cmd_temperature",
    ),
    CommandSpec(
        "max_token", "查看/设置最大词元数",
        "/max_token\n/max_token 4096", "_cmd_max_token",
    ),
    CommandSpec(
        "quit", "退出 MiniClaw", "/quit", "_cmd_quit"
    ),
)

COMMAND_MAP: dict[str, CommandSpec] = {spec.name: spec for spec in COMMAND_SPECS}

# 供 prompt_toolkit 补全使用的斜杠命令列表
SLASH_COMMANDS: list[str] = ["/" + spec.name for spec in COMMAND_SPECS]


def build_help_table() -> Table:
    """构造 /help 帮助表格。"""
    table = Table(title="可用命令", style="cyan")
    table.add_column("命令", style="green", no_wrap=True)
    table.add_column("说明", style="white")
    table.add_column("示例", style="yellow")
    for spec in COMMAND_SPECS:
        table.add_row("/" + spec.name, spec.summary, spec.example)
    return table


async def dispatch(cli, raw_command: str) -> None:
    """解析并分发一条斜杠命令。

    ``raw_command`` 为去掉前导 '/' 后的命令文本。未识别命令给出友好提示。
    """
    raw_command = (raw_command or "").strip()
    if not raw_command:
        return

    parts = raw_command.split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else None

    spec = COMMAND_MAP.get(name)
    if spec is None:
        console.print(f"[red]❌ 未识别的指令: {name}[/red]")
        console.print("[italic]输入 /help 查看可用命令[/italic]\n")
        return

    handler = getattr(cli, spec.handler, None)
    if handler is None:
        console.print(f"[red]❌ 命令未实现: {name}[/red]")
        return

    result = handler(arg)
    if inspect.isawaitable(result):
        await result
