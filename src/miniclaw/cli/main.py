import asyncio
import json
import os
import shutil
from pathlib import Path

from aioconsole import aprint
from loguru import logger
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table

from miniclaw.cli.memory import Memory
from .console import console, get_prompt_session
from .history_store import HistoryStore
from .session_state import (
    save_current_session,
    load_current_session,
    mark_clean_shutdown,
    update_current_session,
)
from .state import load_active_plan
from ..agents import get_llm_client, llm_tools_manager
from ..agents.base_llm_client import ToolResponse, TextBlock
from ..agents.constant import LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER
from ..agents.llm_configurator import LLMConfigurator
from ..constant import (
    MINICLAW_LOG,
    AGENT_AUTONOMY_PROMPT,
    DEFAULT_CONTEXT_RETRY_MAX,
    DEFAULT_MAX_TOOL_ITERATIONS,
    DEFAULT_MEMORY_KEEP_RECENT,
    DEFAULT_MEMORY_RAW_DIR,
    DEFAULT_TASK_DONE_TOKEN,
    EnvVarLoader,
)
from ..utils.common import clip, dt_uuid, extract_yaml_frontmatter, masking_str, merge_system_prompt_into_user
from ..utils.context import (
    check_budget,
    estimate_messages_tokens,
    get_context_budget,
    shrink_tool_response,
    shrink_messages,
)
from ..utils.logger import setup_logger
from ..utils.security import mask_password
from ..utils.turn_taking import get_last_n_messages


# 抑制 asyncio 的资源警告
# warnings.filterwarnings("ignore", category=ResourceWarning)

# system 消息中放置过长的中文内容时，部分大模型网关会直接断开连接，
# 因此 system 消息只保留简短指令，完整的系统提示词（CHAT_SYSTEM_PROMPT）合并到用户消息中。
SHORT_SYSTEM_PROMPT = (
    "你是一个应用解决方案专家，协助用户从设计方案到实现产品。"
    "请严格遵守用户消息中【系统指令】部分的要求。"
)
DEFAULT_SYSTEM_PROMPT = "你是一个人工智能助手，协助用户完成各种任务。"

# 上下文超限错误识别模式（小写匹配）
CONTEXT_OVERFLOW_PATTERNS = (
    "context length",
    "maximum token",
    "max_tokens",
    "too long",
    "context_length_exceeded",
    "reduce the length",
    "输入过长",
)


def _is_context_overflow_error(err: str) -> bool:
    """判断错误信息是否属于「上下文超限」类错误。"""
    if not err:
        return False
    low = err.lower()
    return any(p.lower() in low for p in CONTEXT_OVERFLOW_PATTERNS)


class CommandLineInteraction:
    """命令行交互界面"""

    def __init__(
            self,
            **kwargs
    ):
        self.provider = EnvVarLoader.get_str("LLM_CLIENT_PROVIDER", "litellm")
        # 分组加载 LLM 配置
        self.llms = LLMConfigurator.load_llm_configs_by_group()
        self.llm_name = "default"
        default_llm = self.llms.get("default", {})
        self.model = default_llm.get("model")
        self.api_key = default_llm.get("api_key")
        self.base_url = default_llm.get("base_url")
        self.custom_llm_provider = default_llm.get("custom_llm_provider")

        self.client = get_llm_client()
        self.tools = llm_tools_manager.get_llm_tools()
        self.messages = []
        self.should_exit = False  # 增加退出标志
        # 非调试代码时使用，调试时请注释
        self.prompt_session = get_prompt_session(
            [
                "/help",
                "/llm",
                "/agent",
                "/chat",
                "/clear",
                "/history",
                "/memory",
                "/memory-list",
                "/context",
                "/session-list",
                "/session-load",
                "/session-resume",
                "/session-export",
                "/skill-list",
                "/skill-load",
                "/quit"
            ]
        )

        self.runtime_mode = "agent"  # 默认运行模式为代理机器人模式

        self.skills = []  # 扫描的技能列表 (name,descriptions,dir)
        self.skills_preload = []  # 预加载技能列表，加载后清空。 (name,descriptions,dir)
        self.skills_loaded = []  # 已经加载的技能列表 (name,descriptions,dir)

        # 初始化
        setup_logger(enable_console=False)  # 日志初始化
        # 记忆初始化
        self.update_memory = False  # 更新记忆
        memory_filename = f"m{dt_uuid()}.md"
        self.memory_dir = str(
            Path(EnvVarLoader.get_str("MINICLAW_MEMORY_DIR", "~/.miniclaw/memory")).expanduser().resolve())
        self.memory_file = os.path.join(self.memory_dir, memory_filename)
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)

        # 会话状态与外部记忆（JSONL）初始化
        self.session_id = f"s{dt_uuid()}"
        self.history_store = HistoryStore(self.session_id)
        self.active_plan_path = load_active_plan()
        self.context_condense_count = 0
        self.pending_condense = None
        self._last_summary = None
        self._last_tail = []
        self._user_input_appended = False

        # 显示欢迎信息
        console.print()
        console.print(MINICLAW_LOG)
        console.print("[bold]欢迎使用 MiniClaw！这是一个专注于智能体编排和工具管理的框架。[/bold]")
        console.print("大模型: [cyan]" + self.model + "[/cyan]")
        console.print("记忆缓存: [cyan]" + self.memory_file + "[/cyan]")
        console.print("会话历史: [cyan]" + str(self.history_store.path) + "[/cyan]")
        console.print("运行模式: [cyan]" + self.runtime_mode + "[/cyan]")
        console.print("\n[italic]请使用 /help 查看指令，/quit 退出[/italic]\n")

        # 登记当前会话元数据，并在上次会话异常退出时给出恢复提示
        prev = load_current_session()
        try:
            save_current_session(
                self.session_id,
                str(self.history_store.path),
                self.memory_file,
                self.active_plan_path,
            )
        except Exception as e:
            logger.debug(f"当前会话元数据写入失败: {e}")
        if prev and prev.get("clean_shutdown") is False:
            console.print(
                f"[yellow]⚠️ 检测到上次会话未正常结束（session_id={prev.get('session_id')}），"
                f"可使用 /session-list 查看、/session-resume <id> 恢复[/yellow]"
            )

        # 大模型提示词
        self._init_messages()

    def _init_messages(self):
        """实始化消息"""
        # 完整的系统提示词在首条用户消息中下发，避免部分网关对 system 消息长度的限制
        self.system_prompt = EnvVarLoader.get_str("CHAT_SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT)
        self.messages = [
            {
                "role": "system",
                "content": SHORT_SYSTEM_PROMPT
            },
            {
                "role": "system",
                "content": f"Do not stop this application process by invoking the shell command tool (execute_shell_command), PID: {os.getpid()}\n"
            }
        ]

        self.skills_loaded.clear()

    def _compose_user_content(self, user_input: str) -> str:
        """构造用户消息内容

        会话（或本轮上下文）中的首条用户消息里合并完整的系统提示词，
        system 消息只保留简短指令，以规避部分大模型网关对 system 消息长度的限制。
        agent 模式下额外注入自主执行提示词，驱动模型端到端自推进。
        """
        if any(m.get("role") == "user" for m in self.messages):
            return user_input

        system_prompt = self.system_prompt
        if self.runtime_mode == "agent":
            autonomy_prompt = EnvVarLoader.get_str(
                "CHAT_AGENT_AUTONOMY_PROMPT", AGENT_AUTONOMY_PROMPT
            )
            if autonomy_prompt:
                system_prompt = f"{system_prompt}\n\n{autonomy_prompt}"

        return merge_system_prompt_into_user(system_prompt, user_input)

    def _append_message(self, message: dict):
        """将消息追加到内存上下文，同时持久化到会话历史（外部记忆）"""
        self.messages.append(message)
        try:
            self.history_store.append(message)
        except Exception as e:
            logger.debug(f"会话历史落盘失败: {e}")
        return message

    async def _condense_memory(self):
        """处理记忆缓存（带预算/分块，不打断任务）"""
        memory = Memory(self.memory_file,
                        model=self.model,
                        base_url=self.base_url,
                        api_key=self.api_key,
                        custom_llm_provider=self.custom_llm_provider)
        summary = await memory.condense(
            self.messages,
            token_budget=get_context_budget()[1],
            session_id=self.session_id,
            active_plan=self.active_plan_path,
        )
        self._last_summary = summary
        self._last_tail = list(getattr(memory, "last_tail", []) or [])
        return summary

    async def _condense_and_rebuild(self, force: bool = False):
        """精简记忆，并用「记忆摘要 + 活跃计划 + 最近轮次」重建上下文。

        整体 try/except 兜底，不向上抛出异常，保证主流程可运行。
        """
        try:
            memory = Memory(self.memory_file,
                            model=self.model,
                            base_url=self.base_url,
                            api_key=self.api_key,
                            custom_llm_provider=self.custom_llm_provider)
            summary = await memory.condense(
                self.messages,
                token_budget=get_context_budget()[1],
                session_id=self.session_id,
                active_plan=self.active_plan_path,
            )
            self._last_summary = summary
            tail = list(getattr(memory, "last_tail", []) or [])
            self._last_tail = tail
            await self._rebuild_messages_from_memory(summary=summary, tail=tail)
        except Exception as e:
            logger.exception("精简并重建上下文失败")
            console.print(f"[red]精简并重建上下文失败: {e}[/red]")

    async def _ensure_context(self, force: bool = False):
        """LLM 调用前的上下文预算检查与自动精简。

        - force 或 hard：精简记忆并重建上下文；
        - soft：直接对当前消息做轻量裁剪以立即降低占用。
        任一分支均不抛出异常。
        """
        try:
            level, used, limit = check_budget(self.messages)
            if force or level == "hard":
                await self._condense_and_rebuild()
                console.print(
                    f"[yellow]⚠️ 上下文接近上限（{used}/{limit} tokens），"
                    f"已自动精简记忆并重建上下文[/yellow]"
                )
            elif level == "soft":
                keep_recent = EnvVarLoader.get_int(
                    "MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT
                )
                self.messages = shrink_messages(self.messages, keep_recent)
                console.print(
                    f"[dim]上下文占用偏高（{used}/{limit} tokens），已裁剪较早的工具输出[/dim]"
                )
        except Exception as e:
            logger.exception("上下文预算检查失败")

    async def _rebuild_messages_from_memory(self, summary: str | None = None, tail: list | None = None):
        """用「记忆摘要 + 活跃计划 + 最近 tail」重建上下文。"""
        if summary is None:
            _, summary = Memory.load(self.memory_file)
        keep_recent = EnvVarLoader.get_int(
            "MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT
        )
        if tail is None:
            tail = get_last_n_messages(self.messages, keep_recent)

        self._init_messages()

        if self.active_plan_path:
            plan_line = f"\n计划文件路径: {self.active_plan_path}"
        else:
            plan_line = "\n（无活跃计划文件）"
        injected = (
            f"【对话历史缓存】\n\n{summary}\n\n"
            f"【活跃计划】{plan_line}\n\n"
            f"【继续执行指令】\n"
            f"请依据计划文件中标记为 [ ] 的未完成步骤继续执行，不要重复已完成步骤；"
            f"如需细节请用 read_file 读取计划文件。"
        )
        self._append_message({
            "role": "user",
            "content": self._compose_user_content(injected),
        })
        self._append_message({
            "role": "assistant",
            "content": "收到，将继续执行未完成步骤。",
        })
        for m in (tail or []):
            if isinstance(m, dict):
                self._append_message(dict(m))
        self._append_message({
            "role": "system",
            "content": "【上下文已重建】以上为精简后的记忆摘要与最近对话，请据此继续执行未完成任务。",
        })

    async def cleanup(self):
        """清理资源"""
        try:
            # 获取当前事件循环
            loop = asyncio.get_event_loop()

            # 取消所有正在运行的任务（除了当前任务）
            tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()

            # 等待所有任务取消
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # 关闭 prompt_session
            if hasattr(self, 'prompt_session') and self.prompt_session:
                try:
                    if hasattr(self.prompt_session, 'close'):
                        self.prompt_session.close()
                except Exception:
                    pass

            # 给事件循环一点时间处理清理
            await asyncio.sleep(0)

        except Exception as e:
            logger.debug(f"清理资源时出错: {e}")


    def _reload_skills(self):
        skills_dir = Path(
            EnvVarLoader.get_str("MINICLAW_SKILLS_DIR", "~/.miniclaw/skills")).expanduser().resolve()
        if not skills_dir.exists():
            src_skills_dir = Path(__file__).parent.parent / "agents" / "skills"
            shutil.copytree(src_skills_dir, skills_dir, dirs_exist_ok=True)

        # 收集所有一级文件夹中的 SKILL.md
        self.skills.clear()
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    with open(skill_md, 'r', encoding='utf-8') as f:
                        content = f.read()

                    frontmatter = extract_yaml_frontmatter(content)
                    if frontmatter and frontmatter.get("name") is not None and frontmatter.get(
                            "description") is not None:
                        name = frontmatter.get('name')
                        description = frontmatter.get('description')
                        self.skills.append((name, description, skill_dir))

    def _history_raw_dir(self) -> Path:
        return Path(
            EnvVarLoader.get_str("MINICLAW_MEMORY_RAW_DIR", DEFAULT_MEMORY_RAW_DIR)
        ).expanduser()

    def _cmd_context(self, arg: str | None):
        """处理 /context 命令。"""
        if arg is not None and arg.strip() == "shrink":
            before = estimate_messages_tokens(self.messages)
            keep_recent = EnvVarLoader.get_int(
                "MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT
            )
            self.messages = shrink_messages(self.messages, keep_recent)
            after = estimate_messages_tokens(self.messages)
            console.print(f"[green]✅ 已裁剪较早的工具输出：{before} → {after} tokens[/green]")
            return

        soft, hard, window = get_context_budget()
        level, used, limit = check_budget(self.messages)
        stats = self.history_store.stats()
        table = Table(title="上下文状态", style="cyan")
        table.add_column("项", style="green", no_wrap=True)
        table.add_column("值", style="white")
        table.add_row("估算 token", str(used))
        table.add_row("预算 soft/hard/window", f"{soft} / {hard} / {window}")
        table.add_row("预算等级", level)
        table.add_row("消息条数", str(len(self.messages)))
        table.add_row("会话 ID", self.session_id)
        table.add_row("会话历史消息数", str(stats.get("messages")))
        table.add_row("会话历史文件", str(stats.get("path")))
        table.add_row("记忆文件", self.memory_file)
        console.print(table)

    def _cmd_session_list(self, arg: str | None):
        """处理 /session-list [N] 命令。"""
        last_count = 10
        if arg is not None:
            try:
                last_count = int(arg)
            except ValueError:
                last_count = 10

        raw_dir = self._history_raw_dir()
        if not raw_dir.exists():
            console.print(f"[yellow]暂无会话历史目录: {raw_dir}[/yellow]")
            return

        rows = []
        for f in raw_dir.glob("*.jsonl"):
            try:
                stats = HistoryStore(f.stem, base_dir=str(raw_dir)).stats()
                rows.append((f.stem, stats))
            except Exception as e:
                logger.debug(f"读取会话 {f.stem} 统计失败: {e}")
        rows.sort(key=lambda x: x[1].get("updated_at") or "", reverse=True)
        if last_count > 0:
            rows = rows[:last_count]

        table = Table(title=f"会话列表（{len(rows)}）", style="cyan")
        table.add_column("会话 ID", style="green", no_wrap=True)
        table.add_column("消息数", style="white")
        table.add_column("更新时间", style="white")
        table.add_column("摘要", style="dim")
        for sid, stats in rows:
            summary = ""
            try:
                msgs = HistoryStore(sid, base_dir=str(raw_dir)).load_all()
                first_user = next(
                    (m.get("content") for m in msgs if m.get("role") == "user"), ""
                )
                summary = clip(str(first_user or "").replace("\n", " "), 40)
            except Exception:
                summary = ""
            mark = " *" if sid == self.session_id else ""
            table.add_row(
                f"{sid}{mark}",
                str(stats.get("messages")),
                str(stats.get("updated_at")),
                summary,
            )
        console.print(table)

    async def _cmd_session_load(self, session_id: str) -> bool:
        """加载指定会话到内存上下文；不自动接续。成功返回 True。"""
        raw_dir = self._history_raw_dir()
        store = HistoryStore(session_id, base_dir=str(raw_dir))
        if not store.path.exists():
            console.print(f"[red]❌ 会话不存在: {session_id}[/red]")
            return False
        try:
            msgs = store.load_all()
        except Exception as e:
            console.print(f"[red]❌ 会话读取失败（JSONL 可能损坏）: {e}[/red]")
            return False
        if not msgs:
            console.print(f"[red]❌ 会话为空: {session_id}[/red]")
            return False

        self._init_messages()
        self.session_id = session_id
        self.history_store = store
        for m in msgs:
            if isinstance(m, dict):
                self._append_message(dict(m))

        # 恢复记忆文件（若该会话对应记忆文件存在则复用）与活跃计划
        prev = load_current_session() or {}
        prev_memory = prev.get("memory_file")
        if prev_memory and os.path.exists(prev_memory):
            self.memory_file = prev_memory
        active_plan = load_active_plan()
        if active_plan:
            self.active_plan_path = active_plan

        try:
            update_current_session(
                session_id=self.session_id,
                history_path=str(store.path),
                memory_file=self.memory_file,
                active_plan=self.active_plan_path,
            )
        except Exception as e:
            logger.debug(f"更新当前会话失败: {e}")

        console.print(f"[green]✅ 已加载会话 {session_id}（{len(msgs)} 条消息）[/green]")
        return True

    def _cmd_session_export(self, session_id: str, out_path: str | None = None):
        """导出指定会话为可读 Markdown。"""
        raw_dir = self._history_raw_dir()
        store = HistoryStore(session_id, base_dir=str(raw_dir))
        if not store.path.exists():
            console.print(f"[red]❌ 会话不存在: {session_id}[/red]")
            return
        try:
            msgs = store.load_all()
        except Exception as e:
            console.print(f"[red]❌ 会话读取失败: {e}[/red]")
            return

        lines = [f"# 会话 {session_id}", ""]
        for m in msgs:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            content = m.get("content")
            if isinstance(content, list):
                content = json.dumps(content, ensure_ascii=False)
            if role == "user":
                lines.append(f"## 用户\n\n{content}\n")
            elif role == "assistant":
                block = "" if content is None else str(content)
                if m.get("tool_calls"):
                    block += f"\n\n[工具调用] {json.dumps(m.get('tool_calls'), ensure_ascii=False)}"
                lines.append(f"## AI\n\n{block}\n")
            elif role == "tool":
                lines.append(f"## 工具（{m.get('name')}）\n\n{content}\n")
            elif role == "system":
                lines.append(f"## 系统\n\n{content}\n")
        markdown = "\n".join(lines)

        if out_path:
            target = Path(out_path).expanduser()
        else:
            export_dir = Path(
                EnvVarLoader.get_str("MINICLAW_MEMORY_DIR", "~/.miniclaw/memory")
            ).expanduser().resolve() / "export"
            target = export_dir / f"{session_id}.md"
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(markdown)
        except Exception as e:
            console.print(f"[red]❌ 导出失败: {e}[/red]")
            return
        console.print(f"[green]✅ 会话已导出: {target}[/green]")

    async def command_handler(self, raw_command: str):
        """处理命令"""
        raw_command = raw_command.strip()
        if not raw_command:
            return

        parts = raw_command.split(maxsplit=1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if command == "help":
            # 创建帮助表格
            table = Table(title="可用命令", style="cyan")
            table.add_column("命令", style="green", no_wrap=True)
            table.add_column("说明", style="white")
            table.add_column("示例", style="yellow")

            table.add_row("/help", "显示帮助信息", "/help")
            table.add_row("/llm", "显示/切换/设置大模型配置",
                          "/llm 显示大模型列表*号标记正在使用的大模型配置\n/llm use <model> 切换大模型配置\n/llm set <model>:<api_url>:<api_key>[:<custom_llm_provider>] 设置临时大模型配置")
            table.add_row("/agent", "运行模式切换为代理模式", "/agent 代理模式下大模型将尽量自动推进任务执行")
            table.add_row("/chat", "运行模式切切换为对话模式", "/chat 对话模式下大模型将采用一问一答的方式")
            table.add_row("/clear", "清除对话上下文", "/clear")
            table.add_row("/history", "历史对话记录", "/history N 最近N条历史对话记录，若不指定N默认看最后3条记录")
            table.add_row("/memory", "记忆缓存", "/memory 精简记忆  /memory <记忆缓存> 提取记忆")
            table.add_row("/memory-list", "记忆缓存列表",
                          "/memory-list 查看记忆缓存列表(默认最新的前10个记忆)\n/memory-list 20 查看最新的前20个记忆")
            table.add_row("/context", "查看上下文 token 占用与阈值状态",
                          "/context\n/context shrink 立即裁剪工具输出")
            table.add_row("/session-list", "列出最近的会话",
                          "/session-list N 查看最近N个会话（默认10，* 标记当前会话）")
            table.add_row("/session-load", "加载指定会话到上下文（不自动接续）", "/session-load <session_id>")
            table.add_row("/session-resume", "恢复并接续执行指定会话", "/session-resume <session_id>")
            table.add_row("/session-export", "导出指定会话为 Markdown", "/session-export <session_id> [path]")
            table.add_row("/skill-list", "可用的技能列表", "/skill-list 扫描 '~/code-agent/skills' 目录下的技能列表")
            table.add_row("/skill-load", "加载技能", "/skill-load <skill-name>,... 同时加载多个技能以逗号分隔")
            table.add_row("/quit", "退出 MiniClaw", "/quit")

            console.print(table)
        elif command == "llm":
            if arg is None:
                if self.llm_name not in self.llms:
                    console.print(
                        f"[green]* {self.llm_name}$$${self.model}$$${self.base_url}$$${masking_str(self.api_key)}$$${self.custom_llm_provider}[/green]"
                    )
                for key, cfg in self.llms.items():
                    if key == self.llm_name:
                        console.print(
                            f"[green]* {key}$$${cfg.get('model')}$$${cfg.get('base_url')}$$${masking_str(cfg.get('api_key'))}$$${cfg.get('custom_llm_provider')}[/green]"
                        )
                    else:
                        console.print(
                            f"[white]- {key}$$${cfg.get('model')}$$${cfg.get('base_url')}$$${masking_str(cfg.get('api_key'))}$$${cfg.get('custom_llm_provider')}[/white]"
                        )
                return

            parts = arg.split()
            subcmd = parts[0]
            subarg = parts[1] if len(parts) > 1 else None

            if subcmd == "use":
                if subarg is None:
                    console.print("[red]❌ 请指定模型名称[/red]")
                    return

                if subarg not in self.llms:
                    console.print(f"[red]❌ 未找到 LLM: {subarg}[/red]")
                    return

                self.llm_name = subarg
                cfg = self.llms[subarg]

                self.model = cfg["model"]
                self.base_url = cfg["base_url"]
                self.api_key = cfg["api_key"]
                self.custom_llm_provider = cfg.get("custom_llm_provider")

                console.print(f"[green]✅ 已切换到 LLM: {subarg}[/green]")
            elif subcmd == "set":
                try:
                    model, base_url, api_key, clp = subarg.split("$$$", 3)
                    self.llm_name = "temp"
                    self.model = model
                    self.base_url = base_url
                    self.api_key = api_key
                    self.custom_llm_provider = clp

                    console.print(
                        f"[green]✅ LLM 已设置为 {self.model}$$${self.base_url}$$${masking_str(self.api_key)}$$${self.custom_llm_provider}[/green]"
                    )
                except ValueError:
                    console.print("[red]❌ 格式错误，应为 model$$$url$$$api_key[$$$custom_llm_provider][/red]")
                    return


            else:
                console.print("[red]❌ 未知子命令[/red]")


        elif command == "chat":
            self.runtime_mode = "chat"
        elif command == "agent":
            self.runtime_mode = "agent"
        elif command == "clear":
            self._init_messages()
            console.print(f"[green]✅ 清除对话上下文完成[/green]")
        elif command == "history":
            lookup_count = 3
            if arg is not None:
                try:
                    lookup_count = int(arg)
                except ValueError:
                    pass

            for m in self.messages[-1 * lookup_count:]:
                print(json.dumps(m, ensure_ascii=False))

        elif command == "memory":
            if arg is None:  # 精简记忆
                try:
                    await self._condense_memory()
                    console.print(f"[green]✅ 精简记忆完成（memory file:{os.path.basename(self.memory_file)}）[/green]")
                    self.update_memory = True
                except Exception as e:
                    console.print(f"[red]精简记忆错误：{str(e)}[/red]")
                    logger.exception("精简记忆错误")
                return

            _memory_file = os.path.join(self.memory_dir, arg)
            if not os.path.exists(_memory_file):
                console.print(f"[red]错误：记忆文件 '{arg}' 不存在[/red]")
                return
            else:
                self.memory_file = _memory_file
                _frontmatter, _body = Memory.load(_memory_file)
                if not _frontmatter:
                    console.print("[yellow]⚠️ 该记忆文件缺少可解析的 frontmatter，仍允许切换[/yellow]")
                console.print(f"[green]✅ 提取记忆完成[/green]")
                self.update_memory = True


        elif command == "memory-list":
            try:
                # 获取文件夹下所有文件名（不包括路径）
                files = [f for f in os.listdir(self.memory_dir) if os.path.isfile(os.path.join(self.memory_dir, f))]

                # 按文件名倒序排序
                files.sort(reverse=True)

                # 打印文件名
                if arg is None:
                    last_count = 10
                else:
                    last_count = int(arg)

                _file_index = 1
                for filename in files:
                    if _file_index > last_count:
                        break
                    console.print(f"[green]{_file_index}. {filename}[/green]")
                    _file_index += 1

                # 若记忆文件总量超过1000则自动清理
                if len(files) > 1000:
                    # console.print(f"[yellow]⚠️ 记忆文件总量超过1000，正在自动清理...[/yellow]")
                    for filename in files[1000:]:
                        os.remove(os.path.join(self.memory_dir, filename))
                    # console.print(f"[green]✅ 自动清理完成，已保留最新的1000条记忆文件[/green]")

            except FileNotFoundError:
                console.print(f"[red]错误：文件夹 '{self.memory_dir}' 不存在[/red]")
            except PermissionError:
                console.print(f"[red]错误：没有权限访问文件夹 '{self.memory_dir}'[/red]")
            except Exception as e:
                console.print(f"[red]错误：{str(e)}[/red]")

        elif command == "context":
            try:
                self._cmd_context(arg)
            except Exception as e:
                console.print(f"[red]❌ 查看上下文状态失败: {e}[/red]")

        elif command == "session-list":
            try:
                self._cmd_session_list(arg)
            except Exception as e:
                console.print(f"[red]❌ 会话列表读取失败: {e}[/red]")

        elif command == "session-load":
            if not arg:
                console.print("[red]❌ 请指定 session_id[/red]")
                return
            try:
                await self._cmd_session_load(arg.strip())
            except Exception as e:
                console.print(f"[red]❌ 加载会话失败: {e}[/red]")

        elif command == "session-resume":
            if not arg:
                console.print("[red]❌ 请指定 session_id[/red]")
                return
            try:
                ok = await self._cmd_session_load(arg.strip())
                if not ok:
                    return
                await self._ensure_context(force=True)
                self._append_message({
                    "role": "user",
                    "content": "【会话恢复】请读取活跃计划文件，从中断处继续执行标记为 [ ] 的未完成步骤。"
                })
                await self.stream("", append_user_message=False)
            except Exception as e:
                console.print(f"[red]❌ 会话恢复失败: {e}[/red]")

        elif command == "session-export":
            if not arg:
                console.print("[red]❌ 请指定 session_id[/red]")
                return
            try:
                _export_parts = arg.split()
                _sid = _export_parts[0]
                _out = _export_parts[1] if len(_export_parts) > 1 else None
                self._cmd_session_export(_sid, _out)
            except Exception as e:
                console.print(f"[red]❌ 导出会话失败: {e}[/red]")

        elif command == "model":
            if arg is None:
                console.print(f"[green]当前模型: {self.model}[/green]")
                return

            self.model = arg
            console.print(f"[green]✅ 模型已更新为: {self.model}[/green]")
        elif command == "api_key":
            if arg is None:
                console.print(f"[green]当前模型 API_KEY: {masking_str(self.api_key)}[/green]")
                return

            self.api_key = arg
            console.print(f"[green]✅ 模型 API_KEY 已更新为: {masking_str(self.api_key)}[/green]")
        elif command == "base_url":
            if arg is None:
                console.print(f"[green]当前模型 URL: {self.base_url}[/green]")
                return

            self.base_url = arg
            console.print(f"[green]✅ 模型 URL 已更新为: {self.base_url}[/green]")
        elif command == "custom_llm_provider":
            if arg is None:
                console.print(f"[green]自定义大模型供应商: {self.custom_llm_provider}[/green]")
                return

            self.custom_llm_provider = arg
            console.print(f"[green]✅ 自定义大模型供应商已更新为: {self.custom_llm_provider}[/green]")
        elif command == "temperature":
            if arg is None:
                console.print(f"[green]温度值为: {self.temperature}[/green]")
                return

            try:
                new_temp = float(arg)
                if 0.0 <= new_temp <= 1.0:
                    self.temperature = new_temp
                    console.print(f"[green]✅ 温度已更新为: {self.temperature}[/green]")
                else:
                    console.print("[red]❌ 无效的温度值，请输入 0.0 到 1.0 之间的数字。[/red]")
            except ValueError:
                console.print("[red]❌ 无效输入，请输入一个数字。[/red]")
        elif command == "max_token":
            if arg is None:
                console.print(f"[green]最大词元数为: {self.max_tokens}[/green]")
                return

            try:
                new_max_tokens = int(arg)
                if new_max_tokens > 0:
                    self.max_tokens = new_max_tokens
                    console.print(f"[green]✅ 最大词元数已更新为: {self.max_tokens}[/green]")
                else:
                    console.print("[red]❌ 无效的最大词元数，请输入一个正整数。[/red]")
            except ValueError:
                console.print("[red]❌ 无效输入，请输入一个整数。[/red]")

        elif command == "skill-list":
            try:
                self._reload_skills()

                # 打印结果
                if not self.skills:
                    console.print("[yellow]未发现技能[/yellow]")
                    return

                table = Table(
                    title=f"技能列表({len(self.skills)})",
                    style="cyan",
                    padding=(0, 0, 1, 0)  # (上, 右, 下, 左) 行间距由上下padding控制
                )
                table.add_column("名称", style="green", no_wrap=True)
                table.add_column("描述", style="white")
                for idx, (name, description, dir_name) in enumerate(self.skills, start=1):
                    table.add_row(name, description)
                console.print(table)

            except Exception as e:
                console.print("[red]❌ 获取技能列表失败[/red]")

        elif command == "skill-load":
            if arg is None:
                console.print(f"[yellow]请指定加载的技能名称，若需要加载多个使用逗号分隔[/yellow]")
                return

            self._reload_skills()

            try:
                skill_names = arg
                skills_dict = {name: (name, description, skill_dir) for name, description, skill_dir in self.skills}
                skill_loaded_dict = {name: (name, description, skill_dir) for name, description, skill_dir in
                                     self.skills_loaded}
                for name in skill_names.split(","):
                    if name in skills_dict and name not in skill_loaded_dict:  # 加载未加载的技能
                        self.skills_preload.append(skills_dict[name])
            except Exception as e:
                console.print("[red]❌ 加载技能失败[/red]")

        elif command == "quit":
            self.should_exit = True  # 设置退出标志
            try:
                mark_clean_shutdown(True)
            except Exception:
                pass
            console.print("[bold green]检测到退出指令，再见！[/bold green]")
            raise KeyboardInterrupt  # 触发 KeyboardInterrupt 来优雅退出
        else:
            console.print(f"[red]❌ 未识别的指令: {command}[/red]")
            console.print("[italic]输入 /help 查看可用命令[/italic]\n")

    async def run(self):
        """运行命令行交互界面"""
        while True:
            try:
                if self.should_exit:
                    break

                # 调试代码时使用
                # user_input = input("miniclaw> ")
                # 非高度代码时使用
                user_input = await self.prompt_session.prompt_async("miniclaw> ")

                if not user_input.strip():
                    continue

                # 指令处理
                if user_input.startswith("/"):
                    command = user_input[1:].strip()
                    await self.command_handler(command)
                    if self.should_exit:
                        break
                    continue

                if not user_input.strip():
                    continue

                # 若执行了精简记忆或者指定新的记忆缓存文件，则在下一轮用户输入时重建上下文，
                # 由大模型参考记忆摘要与活跃计划继续执行未完成步骤。
                if self.update_memory:
                    _, memory_content = Memory.load(self.memory_file)
                    await self._rebuild_messages_from_memory(summary=memory_content)
                    self._append_message({
                        "role": "user",
                        "content": f"【用户最新输入】\n\n{user_input}",
                    })
                    self._user_input_appended = True
                    self.update_memory = False

                append_user = not self._user_input_appended
                self._user_input_appended = False
                await self.stream(user_input, append_user_message=append_user)

            except KeyboardInterrupt:
                try:
                    mark_clean_shutdown(True)
                except Exception:
                    pass
                await aprint("\n\n检测到中断信息，再见！")
                break
            except EOFError:
                try:
                    mark_clean_shutdown(True)
                except Exception:
                    pass
                await aprint("\n\n检测到结束信号，再见！")
                break
            except Exception as e:
                await aprint(f"\n\n发生错误: {e}")

    async def stream(self, user_input: str, append_user_message: bool = True):
        """处理用户输入并流式显示 LLM 响应"""

        if append_user_message:
            if self.skills_preload is not None and len(self.skills_preload) > 0:
                user_input_with_skills = user_input.strip()

                for (name, description, skill_dir) in self.skills_preload:
                    if not skill_dir.exists():
                        continue
                    skill_md = skill_dir / "SKILL.md"
                    if not skill_md.exists():
                        continue

                    # 加载 SKILL.md 全文到用户输入中
                    with open(skill_md, 'r', encoding='utf-8') as f:
                        content = f.read()
                        user_input_with_skills += f"\n\n**【技能名称：{name}，技能文件夹路径：{str(skill_dir)}，技能指引如下】：**\n\n{content}\n\n"

                # 清空预加载技能列表
                self.skills_preload.clear()

                self._append_message({"role": "user", "content": self._compose_user_content(user_input_with_skills)})

            else:
                self._append_message({"role": "user", "content": self._compose_user_content(user_input)})

        # 连续工具调用轮次计数（安全网，防死循环）
        tool_iterations = 0

        while True:
            try:
                # 每轮 LLM 调用前做上下文预算检查与自动精简
                await self._ensure_context()

                # 每一轮请求都重新初始化内容收集器，确保流式渲染正确
                collected_content = ""
                collected_reasoning_content = ""
                # 使用Live组件实现流式Markdown渲染
                waiting_spinner = Spinner("dots", text="", style="bold blue")
                with Live(waiting_spinner, console=console, auto_refresh=False, vertical_overflow="visible") as live:
                    async for chunk in self.client.stream(messages=self.messages,
                                                          tools= self.tools if self.runtime_mode == "agent" else None,
                                                          model=self.model,
                                                          base_url=self.base_url,
                                                          api_key=self.api_key,
                                                          custom_llm_provider=self.custom_llm_provider):
                        if chunk.error:
                            console.print(f"[red]错误: {chunk.error}[/red]")
                            self._append_message({
                                "role": "assistant",
                                "content": chunk.error
                            })
                            return

                        # 处理内容流
                        if chunk.delta:
                            if chunk.delta_type == "content":
                                collected_content += chunk.delta
                                # 实时渲染Markdown
                                if collected_content.strip():
                                    live.update(
                                        Panel(
                                            Markdown(collected_content),
                                            title="AI"
                                        ),
                                        refresh=True
                                    )
                            elif chunk.delta_type == "reasoning_content":
                                collected_reasoning_content += chunk.delta
                                # 实时渲染Markdown
                                if collected_reasoning_content.strip():
                                    live.update(
                                        Panel(
                                            Markdown(collected_reasoning_content),
                                            title="AI 思维链",
                                            border_style="grey50",
                                            style="dim"
                                        ),
                                        refresh=True
                                    )

                        # 处理完成
                        if chunk.finish:
                            if chunk.finish_reason == "tool_calls":
                                if len(collected_reasoning_content) > 0:
                                    self._append_message(
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "reasoning_content": collected_reasoning_content,
                                            "tool_calls": chunk.tool_calls
                                        }
                                    )
                                else:
                                    self._append_message(
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "tool_calls": chunk.tool_calls
                                        }
                                    )

                                # 处理工具调用
                                tool_call_obj = chunk.tool_calls[0]
                                function_obj = tool_call_obj["function"]

                                console.print(
                                    f"\n[bold yellow]🛠️ 工具调用: {function_obj['name']}({clip(function_obj['arguments'], max_len=250)})[/bold yellow]")
                                logger.debug(
                                    f"调用工具 {function_obj['name']} 参数: {function_obj['arguments']}")
                                if function_obj["name"] == LLM_FUNCTION_SUBAGENT:
                                    # 调用子任务执行器工具
                                    try:
                                        _tool_arguments_obj = json.loads(function_obj["arguments"])
                                        _clerk_message = _tool_arguments_obj["message"]
                                        from .clerk import Clerk
                                        clerk = Clerk(_clerk_message,
                                                      model=self.model,
                                                      base_url=self.base_url,
                                                      api_key=self.api_key,
                                                      custom_llm_provider=self.custom_llm_provider)
                                        _clerk_response = await clerk.run()
                                        logger.debug(f"clerk response: {_clerk_response}")
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=_clerk_response,
                                                )
                                            ]
                                        )
                                    except Exception as e:
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=f"调用工具 {LLM_FUNCTION_SUBAGENT} 错误: {str(e)}",
                                                )
                                            ]
                                        )
                                elif function_obj["name"] == LLM_FUNCTION_PLANNER:
                                    # 调用计划制定工具
                                    try:
                                        from .planner import Planner
                                        planner = Planner(model=self.model,
                                                          base_url=self.base_url,
                                                          api_key=self.api_key,
                                                          custom_llm_provider=self.custom_llm_provider)
                                        tool_response = await planner.make(function_obj["arguments"])
                                        logger.debug(f"planner response: {tool_response.content}")
                                        self.active_plan_path = load_active_plan() or self.active_plan_path
                                    except Exception as e:
                                        tool_response = ToolResponse(
                                            content=[
                                                TextBlock(
                                                    type="text",
                                                    text=f"调用工具 {LLM_FUNCTION_PLANNER} 错误: {str(e)}",
                                                )
                                            ]
                                        )
                                else:
                                    tool_response = await llm_tools_manager.execute_tool(
                                        function_obj["name"],
                                        function_obj["arguments"]
                                    )
                                logger.debug(f"工具 {function_obj['name']} 响应: {tool_response}")
                                # 继续对话流程（工具结果入上下文前裁剪超长输出）
                                self._append_message(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_obj["id"],
                                        "name": function_obj["name"],
                                        "content": shrink_tool_response(tool_response.model_dump_json(),
                                                                        name=function_obj["name"])
                                    }
                                )
                                logger.debug(f"工具调用结果已添加到消息历史，继续对话")

                                # 连续工具调用轮次上限（安全网）
                                tool_iterations += 1
                                if tool_iterations > EnvVarLoader.get_int(
                                        "MINICLAW_MAX_TOOL_ITERATIONS", DEFAULT_MAX_TOOL_ITERATIONS
                                ):
                                    console.print(
                                        "[yellow]⚠️ 工具调用达到上限，已暂停，请检查任务是否陷入循环[/yellow]"
                                    )
                                    return
                                break

                            else:
                                # 显示token使用情况
                                # if chunk.prompt_tokens:
                                #     console.print(f"\n[dim]📊 Tokens: 输入={chunk.prompt_tokens}, "
                                #                   f"输出={chunk.completion_tokens}, "
                                #                   f"总计={chunk.total_tokens}[/dim]")
                                # if chunk.cost_usd:
                                #     console.print(f"[dim]💰 费用: ${chunk.cost_usd:.6f}[/dim]")

                                # 可选哨兵：任务完成标记识别与剥离
                                done_token = EnvVarLoader.get_str(
                                    "CHAT_TASK_DONE_TOKEN", DEFAULT_TASK_DONE_TOKEN
                                )
                                final_content = collected_content
                                if self.runtime_mode == "agent" and done_token and done_token in final_content:
                                    console.print("[green]✅ 任务完成[/green]")
                                    final_content = final_content.replace(done_token, "").strip()

                                # 将助手响应添加到历史
                                if len(collected_reasoning_content) > 0:
                                    self._append_message({
                                        "role": "assistant",
                                        "content": final_content,
                                        "reasoning_content": collected_reasoning_content
                                    })
                                else:
                                    self._append_message({
                                        "role": "assistant",
                                        "content": final_content
                                    })

                                logger.debug(
                                    f"大模型响应的消息：\n【content】:{final_content}\n\n【reasoning_content:{collected_reasoning_content}】")

                                # 方案 B：纯文本收尾即结束本轮（移除裁判续跑逻辑）
                                return
            except Exception as e:
                if _is_context_overflow_error(str(e)):
                    self.context_condense_count += 1
                    retry_max = EnvVarLoader.get_int(
                        "MINICLAW_CONTEXT_RETRY_MAX", DEFAULT_CONTEXT_RETRY_MAX
                    )
                    if self.context_condense_count <= retry_max:
                        console.print(
                            f"[yellow]⚠️ 检测到上下文超限，正在精简记忆并重建上下文后重试"
                            f"（{self.context_condense_count}/{retry_max}）...[/yellow]"
                        )
                        await self._condense_and_rebuild(force=True)
                        self._append_message({
                            "role": "user",
                            "content": "上一轮因上下文超限中断，请从中断处继续执行未完成任务。"
                        })
                        continue
                    else:
                        console.print("[red]上下文超限且重试失败，已停止本轮处理。[/red]")
                        self._append_message({
                            "role": "assistant",
                            "content": f"发生错误: {str(e)}"
                        })
                        return

                logger.exception(f"流式处理发生错误")
                console.print(f"[red]发生错误: {e}[/red]")
                self._append_message({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
                break


async def cli_run():
    cli = CommandLineInteraction()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(cli_run())
