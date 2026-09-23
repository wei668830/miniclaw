import asyncio
import json
import os
import shutil
from pathlib import Path

from aioconsole import aprint
from loguru import logger
from rich.markup import escape
from rich.table import Table

from miniclaw.cli.memory import Memory
from . import commands
from .console import console, get_prompt_session
from .stream_runner import run_stream_round
from .history_store import HistoryStore
from .session_state import (
    save_current_session,
    load_current_session,
    mark_clean_shutdown,
    update_current_session,
)
from .state import load_active_plan
from ..agents import get_llm_client, llm_tools_manager
from ..agents.constant import LLM_FUNCTION_PLANNER
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
    clear_budget_overrides,
    estimate_messages_tokens,
    get_budget_overrides,
    get_context_budget,
    set_budget_override,
    shrink_messages,
)
from ..utils.logger import setup_logger
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

# 交互展示相关默认值（避免散落的魔法数字）
HISTORY_DEFAULT_COUNT = 3        # /history 默认展示的最近消息条数
SESSION_LIST_DEFAULT_COUNT = 10  # /session-list 默认展示的会话数
SESSION_SUMMARY_CLIP = 40        # 会话摘要展示的最大字符数
MEMORY_LIST_DEFAULT_COUNT = 10   # /memory-list 默认展示的记忆文件数
MEMORY_FILE_MAX_COUNT = 1000     # 记忆文件总量上限，超出后自动清理最旧部分

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
        # 采样参数（None 表示使用模型默认值，不向网关显式下发）
        self.temperature = None
        self.max_tokens = None

        self.client = get_llm_client()
        self.tools = llm_tools_manager.get_llm_tools()
        self.messages = []
        self.should_exit = False  # 增加退出标志
        # 非调试代码时使用，调试时请注释
        self.prompt_session = get_prompt_session(commands.SLASH_COMMANDS)

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

        # 显示欢迎信息
        console.print()
        console.print(MINICLAW_LOG)
        console.print("[bold]欢迎使用 MiniClaw！念远既达[/bold]")
        console.print("大模型: [cyan]" + escape(str(self.model)) + "[/cyan]")
        console.print("记忆缓存: [cyan]" + escape(str(self.memory_file)) + "[/cyan]")
        console.print("会话历史: [cyan]" + escape(str(self.history_store.path)) + "[/cyan]")
        console.print("运行模式: [cyan]" + escape(str(self.runtime_mode)) + "[/cyan]")
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
        self._register_session_meta()
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

    def _sampling_kwargs(self) -> dict:
        """构造采样参数；值为 None 的不下发，交由模型使用默认值。"""
        kwargs = {}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            kwargs["max_tokens"] = self.max_tokens
        return kwargs

    def _make_memory(self) -> Memory:
        """构造 Memory 实例（统一入口，避免在多处重复拼装连接配置）。"""
        return Memory(
            self.memory_file,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            custom_llm_provider=self.custom_llm_provider,
        )

    async def _condense(self) -> tuple[str, list]:
        """执行记忆精简，返回 ``(摘要, 保留的最近原文)``。"""
        memory = self._make_memory()
        summary = await memory.condense(
            self.messages,
            token_budget=get_context_budget()[1],
            session_id=self.session_id,
            active_plan=self.active_plan_path,
        )
        tail = list(getattr(memory, "last_tail", []) or [])
        self._last_summary = summary
        self._last_tail = tail
        return summary, tail

    async def _condense_memory(self):
        """处理记忆缓存（带预算/分块，不打断任务）"""
        summary, _ = await self._condense()
        return summary

    async def _condense_and_rebuild(self, force: bool = False):
        """精简记忆，并用「记忆摘要 + 活跃计划 + 最近轮次」重建上下文。

        整体 try/except 兜底，不向上抛出异常，保证主流程可运行。
        """
        try:
            summary, tail = await self._condense()
            await self._rebuild_messages_from_memory(summary=summary, tail=tail)
        except Exception as e:
            logger.exception("精简并重建上下文失败")
            console.print(f"[red]精简并重建上下文失败: {escape(str(e))}[/red]")

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

    def _session_meta_path(self, session_id: str) -> Path:
        """返回会话元数据文件路径（记录该会话绑定的记忆文件）。"""
        return self._history_raw_dir() / f"{session_id}.meta.json"

    def _register_session_meta(self, session_id: str | None = None) -> None:
        """记录「会话 -> 记忆文件」绑定，供会话加载时准确恢复记忆。"""
        sid = session_id or self.session_id
        try:
            path = self._session_meta_path(sid)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8")) or {}
                except Exception:
                    data = {}
            data["session_id"] = sid
            data["memory_file"] = self.memory_file
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.debug(f"会话元数据写入失败: {e}")

    def _load_session_memory_file(self, session_id: str) -> str | None:
        """读取会话绑定的记忆文件；不存在或已删除时返回 None。"""
        try:
            path = self._session_meta_path(session_id)
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            logger.debug(f"会话元数据读取失败: {e}")
            return None
        memory_file = data.get("memory_file")
        if memory_file and os.path.exists(memory_file):
            return memory_file
        return None

    def _cmd_context(self, arg: str | None):
        """处理 /context 命令。

        - 无参：展示当前上下文占用与阈值；
        - ``shrink``：立即裁剪较早的工具输出；
        - ``window|soft|hard|reserve <值>``：设置运行期预算覆盖（优先级高于 .env）；
        - ``reset``：清除运行期覆盖，回退到 .env / 默认值。
        """
        parts = (arg or "").split()
        if not parts:
            self._print_context_status()
            return

        sub = parts[0].lower()

        if sub == "shrink":
            before = estimate_messages_tokens(self.messages)
            keep_recent = EnvVarLoader.get_int(
                "MINICLAW_MEMORY_KEEP_RECENT", DEFAULT_MEMORY_KEEP_RECENT
            )
            self.messages = shrink_messages(self.messages, keep_recent)
            after = estimate_messages_tokens(self.messages)
            console.print(f"[green]✅ 已裁剪较早的工具输出：{before} → {after} tokens[/green]")
            return

        if sub == "reset":
            clear_budget_overrides()
            console.print("[green]✅ 已清除运行期预算覆盖，回退到 .env / 默认值[/green]")
            self._print_context_status()
            return

        if sub in ("window", "soft", "hard", "reserve"):
            self._apply_context_override(sub, parts[1:])
            return

        console.print(
            "[red]❌ 未知子命令；用法：/context \\[shrink|reset|"
            "window <n>|soft <ratio>|hard <ratio>|reserve <n>][/red]"
        )

    def _apply_context_override(self, sub: str, rest: list[str]):
        """处理 /context window|soft|hard|reserve 的运行期覆盖。"""
        if not rest:
            console.print(f"[red]❌ 请提供数值，例如 /context {sub} <value>[/red]")
            return
        raw = rest[0]
        key = {"window": "window", "soft": "soft_ratio",
               "hard": "hard_ratio", "reserve": "reserve"}[sub]

        if key in ("window", "reserve"):
            try:
                value = int(raw)
            except ValueError:
                console.print("[red]❌ 无效输入，请输入一个整数。[/red]")
                return
            if key == "window" and value <= 0:
                console.print("[red]❌ window 必须为正整数。[/red]")
                return
            if key == "reserve" and value < 0:
                console.print("[red]❌ reserve 不能为负数。[/red]")
                return
        else:
            try:
                value = float(raw)
            except ValueError:
                console.print("[red]❌ 无效输入，请输入一个 0~1 之间的小数。[/red]")
                return
            if not (0.0 < value < 1.0):
                console.print("[red]❌ 比例需在 0.0 与 1.0 之间（不含端点）。[/red]")
                return
            soft_now, hard_now, window_now = get_context_budget()
            if window_now > 0:
                soft_eff = soft_now / window_now
                hard_eff = hard_now / window_now
                if key == "soft_ratio" and value >= hard_eff:
                    console.print("[red]❌ soft 比例需小于当前 hard 比例。[/red]")
                    return
                if key == "hard_ratio" and value <= soft_eff:
                    console.print("[red]❌ hard 比例需大于当前 soft 比例。[/red]")
                    return

        set_budget_override(key, value)
        soft, hard, window = get_context_budget()
        console.print(
            f"[green]✅ 已设置运行期预算 {sub}={value}（仅当前进程生效，"
            f"如需持久化请写入 .env 对应环境变量）[/green]"
        )
        console.print(f"[dim]当前预算 soft/hard/window = {soft} / {hard} / {window}[/dim]")

    def _print_context_status(self):
        """打印上下文状态表格。"""
        soft, hard, window = get_context_budget()
        level, used, limit = check_budget(self.messages)
        stats = self.history_store.stats()
        overrides = get_budget_overrides()
        table = Table(title="上下文状态", style="cyan")
        table.add_column("项", style="green", no_wrap=True)
        table.add_column("值", style="white")
        table.add_row("估算 token", str(used))
        table.add_row("预算 soft/hard/window", f"{soft} / {hard} / {window}")
        table.add_row(
            "有效比例 soft/hard",
            f"{soft / window:.3f} / {hard / window:.3f}" if window else "-",
        )
        table.add_row("预算等级", level)
        table.add_row("消息条数", str(len(self.messages)))
        table.add_row(
            "运行期覆盖",
            ", ".join(f"{k}={v:g}" for k, v in overrides.items())
            if overrides else "（无，使用 .env/默认）",
        )
        table.add_row("会话 ID", self.session_id)
        table.add_row("会话历史消息数", str(stats.get("messages")))
        table.add_row("会话历史文件", str(stats.get("path")))
        table.add_row("记忆文件", self.memory_file)
        console.print(table)

    def _cmd_session_list(self, arg: str | None):
        """处理 /session-list [N] 命令。"""
        last_count = SESSION_LIST_DEFAULT_COUNT
        if arg is not None:
            try:
                last_count = int(arg)
            except ValueError:
                last_count = SESSION_LIST_DEFAULT_COUNT

        raw_dir = self._history_raw_dir()
        if not raw_dir.exists():
            console.print(f"[yellow]暂无会话历史目录: {escape(str(raw_dir))}[/yellow]")
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
                summary = clip(str(first_user or "").replace("\n", " "), SESSION_SUMMARY_CLIP)
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

    async def _cmd_session_load(self, arg: str | None) -> bool:
        """加载指定会话到内存上下文；不自动接续。成功返回 True。"""
        if not arg or not arg.strip():
            console.print("[red]❌ 请指定 session_id[/red]")
            return False
        session_id = arg.strip()
        raw_dir = self._history_raw_dir()
        store = HistoryStore(session_id, base_dir=str(raw_dir))
        if not store.path.exists():
            console.print(f"[red]❌ 会话不存在: {escape(session_id)}[/red]")
            return False
        try:
            msgs = store.load_all()
        except Exception as e:
            console.print(f"[red]❌ 会话读取失败（JSONL 可能损坏）: {escape(str(e))}[/red]")
            return False
        if not msgs:
            console.print(f"[red]❌ 会话为空: {escape(session_id)}[/red]")
            return False

        self._init_messages()
        self.session_id = session_id
        self.history_store = store
        for m in msgs:
            if isinstance(m, dict):
                self._append_message(dict(m))

        # 恢复该会话绑定的记忆文件（按其自身 session_id 检索）与活跃计划
        restored_memory = self._load_session_memory_file(session_id)
        if restored_memory:
            self.memory_file = restored_memory
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
        self._register_session_meta()

        console.print(f"[green]✅ 已加载会话 {escape(session_id)}（{len(msgs)} 条消息）[/green]")
        return True

    def _cmd_session_export(self, arg: str | None):
        """导出指定会话为可读 Markdown（arg: ``<session_id> [path]``）。"""
        if not arg or not arg.strip():
            console.print("[red]❌ 请指定 session_id[/red]")
            return
        _parts = arg.split()
        session_id = _parts[0]
        out_path = _parts[1] if len(_parts) > 1 else None
        raw_dir = self._history_raw_dir()
        store = HistoryStore(session_id, base_dir=str(raw_dir))
        if not store.path.exists():
            console.print(f"[red]❌ 会话不存在: {escape(session_id)}[/red]")
            return
        try:
            msgs = store.load_all()
        except Exception as e:
            console.print(f"[red]❌ 会话读取失败: {escape(str(e))}[/red]")
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
            console.print(f"[red]❌ 导出失败: {escape(str(e))}[/red]")
            return
        console.print(f"[green]✅ 会话已导出: {escape(str(target))}[/green]")

    async def command_handler(self, raw_command: str):
        """处理斜杠命令（统一分发到 commands 注册表）。"""
        await commands.dispatch(self, raw_command)

    # ------------------------------------------------------------------
    # 各命令实现：均由 commands.COMMAND_SPECS 注册，签名为 (arg: str | None)
    # ------------------------------------------------------------------

    def _cmd_help(self, arg: str | None):
        """处理 /help 命令。"""
        console.print(commands.build_help_table())

    def _cmd_llm(self, arg: str | None):
        """处理 /llm 命令。"""
        if arg is None:
            if self.llm_name not in self.llms:
                console.print(
                    f"[green]* {escape(str(self.llm_name))}$$${escape(str(self.model))}$$${escape(str(self.base_url))}$$${escape(masking_str(self.api_key))}$$${escape(str(self.custom_llm_provider))}[/green]"
                )
            for key, cfg in self.llms.items():
                color = "green" if key == self.llm_name else "white"
                mark = "*" if key == self.llm_name else "-"
                console.print(
                    f"[{color}]{mark} {escape(str(key))}$$${escape(str(cfg.get('model')))}$$${escape(str(cfg.get('base_url')))}$$${escape(masking_str(cfg.get('api_key')))}$$${escape(str(cfg.get('custom_llm_provider')))}[/{color}]"
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
                console.print(f"[red]❌ 未找到 LLM: {escape(str(subarg))}[/red]")
                return
            self.llm_name = subarg
            cfg = self.llms[subarg]
            self.model = cfg["model"]
            self.base_url = cfg["base_url"]
            self.api_key = cfg["api_key"]
            self.custom_llm_provider = cfg.get("custom_llm_provider")
            console.print(f"[green]✅ 已切换到 LLM: {escape(str(subarg))}[/green]")
        elif subcmd == "set":
            _fmt = "model$$$url$$$api_key[$$$custom_llm_provider]"
            seg = (subarg or "").split("$$$")
            if len(seg) < 3:
                console.print(f"[red]❌ 格式错误，应为 {escape(_fmt)}[/red]")
                return
            self.llm_name = "temp"
            self.model = seg[0]
            self.base_url = seg[1]
            self.api_key = seg[2]
            self.custom_llm_provider = seg[3] if len(seg) > 3 else None
            console.print(
                f"[green]✅ LLM 已设置为 {escape(str(self.model))}$$${escape(str(self.base_url))}$$${escape(masking_str(self.api_key))}$$${escape(str(self.custom_llm_provider))}[/green]"
            )
        else:
            console.print("[red]❌ 未知子命令[/red]")

    def _cmd_agent(self, arg: str | None):
        """处理 /agent 命令。"""
        self.runtime_mode = "agent"

    def _cmd_chat(self, arg: str | None):
        """处理 /chat 命令。"""
        self.runtime_mode = "chat"

    def _cmd_clear(self, arg: str | None):
        """处理 /clear 命令。"""
        self._init_messages()
        console.print("[green]✅ 清除对话上下文完成[/green]")

    def _cmd_history(self, arg: str | None):
        """处理 /history 命令。"""
        lookup_count = HISTORY_DEFAULT_COUNT
        if arg is not None:
            try:
                lookup_count = int(arg)
            except ValueError:
                pass
        for m in self.messages[-1 * lookup_count:]:
            console.print_json(data=m)

    async def _cmd_memory(self, arg: str | None):
        """处理 /memory 命令。"""
        if arg is None:  # 精简记忆
            try:
                await self._condense_memory()
                console.print(
                    f"[green]✅ 精简记忆完成（memory file:{escape(os.path.basename(self.memory_file))}）[/green]"
                )
                self.update_memory = True
            except Exception as e:
                console.print(f"[red]精简记忆错误：{escape(str(e))}[/red]")
                logger.exception("精简记忆错误")
            return

        _memory_file = os.path.join(self.memory_dir, arg)
        if not os.path.exists(_memory_file):
            console.print(f"[red]错误：记忆文件 '{escape(str(arg))}' 不存在[/red]")
            return
        self.memory_file = _memory_file
        _frontmatter, _body = Memory.load(_memory_file)
        if not _frontmatter:
            console.print("[yellow]⚠️ 该记忆文件缺少可解析的 frontmatter，仍允许切换[/yellow]")
        self._register_session_meta()
        console.print("[green]✅ 提取记忆完成[/green]")
        self.update_memory = True

    def _cmd_memory_list(self, arg: str | None):
        """处理 /memory-list 命令。"""
        try:
            files = [
                f for f in os.listdir(self.memory_dir)
                if os.path.isfile(os.path.join(self.memory_dir, f))
            ]
            files.sort(reverse=True)
            last_count = MEMORY_LIST_DEFAULT_COUNT if arg is None else int(arg)
            for _file_index, filename in enumerate(files[:last_count], start=1):
                console.print(f"[green]{_file_index}. {escape(str(filename))}[/green]")
            # 记忆文件总量超过上限则自动清理最旧的部分
            if len(files) > MEMORY_FILE_MAX_COUNT:
                for filename in files[MEMORY_FILE_MAX_COUNT:]:
                    os.remove(os.path.join(self.memory_dir, filename))
        except FileNotFoundError:
            console.print(f"[red]错误：文件夹 '{escape(str(self.memory_dir))}' 不存在[/red]")
        except PermissionError:
            console.print(f"[red]错误：没有权限访问文件夹 '{escape(str(self.memory_dir))}'[/red]")
        except Exception as e:
            console.print(f"[red]错误：{escape(str(e))}[/red]")

    async def _cmd_session_resume(self, arg: str | None):
        """处理 /session-resume 命令：加载会话并接续执行。"""
        if not arg:
            console.print("[red]❌ 请指定 session_id[/red]")
            return
        try:
            ok = await self._cmd_session_load(arg)
            if not ok:
                return
            await self._ensure_context(force=True)
            self._append_message({
                "role": "user",
                "content": "【会话恢复】请读取活跃计划文件，从中断处继续执行标记为 [ ] 的未完成步骤。"
            })
            await self.stream("", append_user_message=False)
        except Exception as e:
            console.print(f"[red]❌ 会话恢复失败: {escape(str(e))}[/red]")

    def _cmd_skill_list(self, arg: str | None):
        """处理 /skill-list 命令。"""
        try:
            self._reload_skills()
            if not self.skills:
                console.print("[yellow]未发现技能[/yellow]")
                return

            table = Table(
                title=f"技能列表({len(self.skills)})",
                style="cyan",
                padding=(0, 0, 1, 0)  # (上, 右, 下, 左) 行间距由上下 padding 控制
            )
            table.add_column("名称", style="green", no_wrap=True)
            table.add_column("描述", style="white")
            for name, description, dir_name in self.skills:
                table.add_row(name, description)
            console.print(table)
        except Exception as e:
            console.print(f"[red]❌ 获取技能列表失败: {escape(str(e))}[/red]")

    def _cmd_skill_load(self, arg: str | None):
        """处理 /skill-load 命令。"""
        if arg is None:
            console.print("[yellow]请指定加载的技能名称，若需要加载多个使用逗号分隔[/yellow]")
            return

        self._reload_skills()

        try:
            skills_dict = {name: (name, description, skill_dir)
                           for name, description, skill_dir in self.skills}
            skill_loaded_dict = {name: (name, description, skill_dir)
                                 for name, description, skill_dir in self.skills_loaded}
            for name in arg.split(","):
                if name in skills_dict and name not in skill_loaded_dict:  # 加载未加载的技能
                    self.skills_preload.append(skills_dict[name])
        except Exception as e:
            console.print(f"[red]❌ 加载技能失败: {escape(str(e))}[/red]")

    def _cmd_model(self, arg: str | None):
        """处理 /model 命令。"""
        if arg is None:
            console.print(f"[green]当前模型: {escape(str(self.model))}[/green]")
            return
        self.model = arg
        console.print(f"[green]✅ 模型已更新为: {escape(str(self.model))}[/green]")

    def _cmd_api_key(self, arg: str | None):
        """处理 /api_key 命令。"""
        if arg is None:
            console.print(f"[green]当前模型 API_KEY: {escape(masking_str(self.api_key))}[/green]")
            return
        self.api_key = arg
        console.print(f"[green]✅ 模型 API_KEY 已更新为: {escape(masking_str(self.api_key))}[/green]")

    def _cmd_base_url(self, arg: str | None):
        """处理 /base_url 命令。"""
        if arg is None:
            console.print(f"[green]当前模型 URL: {escape(str(self.base_url))}[/green]")
            return
        self.base_url = arg
        console.print(f"[green]✅ 模型 URL 已更新为: {escape(str(self.base_url))}[/green]")

    def _cmd_custom_llm_provider(self, arg: str | None):
        """处理 /custom_llm_provider 命令。"""
        if arg is None:
            console.print(f"[green]自定义大模型供应商: {escape(str(self.custom_llm_provider))}[/green]")
            return
        self.custom_llm_provider = arg
        console.print(f"[green]✅ 自定义大模型供应商已更新为: {escape(str(self.custom_llm_provider))}[/green]")

    def _cmd_temperature(self, arg: str | None):
        """处理 /temperature 命令。"""
        if arg is None:
            console.print(f"[green]温度值为: {escape(str(self.temperature))}[/green]")
            return
        try:
            new_temp = float(arg)
        except ValueError:
            console.print("[red]❌ 无效输入，请输入一个数字。[/red]")
            return
        if 0.0 <= new_temp <= 1.0:
            self.temperature = new_temp
            console.print(f"[green]✅ 温度已更新为: {escape(str(self.temperature))}[/green]")
        else:
            console.print("[red]❌ 无效的温度值，请输入 0.0 到 1.0 之间的数字。[/red]")

    def _cmd_max_token(self, arg: str | None):
        """处理 /max_token 命令。"""
        if arg is None:
            console.print(f"[green]最大词元数为: {escape(str(self.max_tokens))}[/green]")
            return
        try:
            new_max_tokens = int(arg)
        except ValueError:
            console.print("[red]❌ 无效输入，请输入一个整数。[/red]")
            return
        if new_max_tokens > 0:
            self.max_tokens = new_max_tokens
            console.print(f"[green]✅ 最大词元数已更新为: {escape(str(self.max_tokens))}[/green]")
        else:
            console.print("[red]❌ 无效的最大词元数，请输入一个正整数。[/red]")

    def _cmd_quit(self, arg: str | None):
        """处理 /quit 命令：标记干净退出并触发中断以优雅退出。"""
        self.should_exit = True
        try:
            mark_clean_shutdown(True)
        except Exception:
            pass
        console.print("[bold green]检测到退出指令，再见！[/bold green]")
        raise KeyboardInterrupt

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
                append_user = True
                if self.update_memory:
                    _, memory_content = Memory.load(self.memory_file)
                    await self._rebuild_messages_from_memory(summary=memory_content)
                    self._append_message({
                        "role": "user",
                        "content": f"【用户最新输入】\n\n{user_input}",
                    })
                    append_user = False
                    self.update_memory = False

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

    def _append_user_message(self, user_input: str):
        """把用户输入（含预加载技能）写入上下文。"""
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

    def _refresh_active_plan(self, tool_name: str):
        """计划器执行后刷新活跃计划路径。"""
        if tool_name == LLM_FUNCTION_PLANNER:
            self.active_plan_path = load_active_plan() or self.active_plan_path

    async def stream(self, user_input: str, append_user_message: bool = True):
        """处理用户输入并流式显示 LLM 响应（统一流式循环，见 stream_runner）。"""
        if append_user_message:
            self._append_user_message(user_input)

        # 连续工具调用轮次计数（安全网，防死循环）
        tool_iterations = 0

        while True:
            try:
                # 每轮 LLM 调用前做上下文预算检查与自动精简
                await self._ensure_context()

                done_token = None
                if self.runtime_mode == "agent":
                    done_token = EnvVarLoader.get_str("CHAT_TASK_DONE_TOKEN", DEFAULT_TASK_DONE_TOKEN)

                result = await run_stream_round(
                    client=self.client,
                    messages=self.messages,
                    tools=self.tools if self.runtime_mode == "agent" else None,
                    model=self.model,
                    base_url=self.base_url,
                    api_key=self.api_key,
                    custom_llm_provider=self.custom_llm_provider,
                    append=self._append_message,
                    llm_tools_manager=llm_tools_manager,
                    title="AI",
                    log_prefix="",
                    done_token=done_token,
                    on_tool_call=self._refresh_active_plan,
                    **self._sampling_kwargs(),
                )

                if result.error:
                    return

                if result.tool_called:
                    # 连续工具调用轮次上限（安全网）
                    tool_iterations += 1
                    if tool_iterations > EnvVarLoader.get_int(
                            "MINICLAW_MAX_TOOL_ITERATIONS", DEFAULT_MAX_TOOL_ITERATIONS
                    ):
                        console.print(
                            "[yellow]⚠️ 工具调用达到上限，已暂停，请检查任务是否陷入循环[/yellow]"
                        )
                        return
                    continue

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
                console.print(f"[red]发生错误: {escape(str(e))}[/red]")
                self._append_message({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
                break


async def cli_run():
    cli = CommandLineInteraction()
    try:
        await cli.run()
    finally:
        # 保证退出时清理 prompt_session 等资源（原先 cleanup 从未被调用）
        await cli.cleanup()


if __name__ == "__main__":
    asyncio.run(cli_run())
