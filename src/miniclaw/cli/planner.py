import re
from pathlib import Path

from .actor import Actor
from . import state
from ..agents import LLMResponse
from ..agents.base_llm_client import ToolResponse, TextBlock
from ..agents.constant import LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER
from ..utils.common import dt_uuid, extract_yaml_frontmatter


class Planner(Actor):
    def __init__(self, session_id: str | None = None, **kwargs):
        if "exclude_tools" not in kwargs:
            kwargs["exclude_tools"] = [LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER]

        super().__init__(**kwargs)

        self.session_id = session_id

        self.path = Path.home() / ".miniclaw" / "plans" / f"plan-{dt_uuid()}.md"
        self.path = self.path.resolve()  # 转换为绝对路径

        # 确保父目录存在
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.messages.append(
            {
                "role": "system",
                "content": "你是一个计划的制定者，负责根据用户的需求制定一个详细的计划和执行步骤，以帮助用户高效地完成任务。"
                           "\n## 制定计划的要求如下："
                           "\n- 请确保计划具有可操作性和可执行性，并且能够清晰地使用工具来完成任务。"
                           "\n- 计划应该包含明确的步骤，每个步骤都应该清晰地描述需要完成的具体任务和使用的工具。"
                           "\n- 计划应该具有层次结构，能够清晰地展示任务的优先级和依赖关系。"
                           "\n- 计划应该具有灵活性，能够适应任务执行过程中可能出现的变化和调整。"
                           "\n- 计划应该具有可衡量的目标，能够帮助用户评估任务完成的进度和效果。"
                           "\n- 计划的文本格式使用 Markdown，以便于用户阅读和理解。"
                           "\n- 计划中的处理步骤要有相应的校验方法，确保每个步骤的完成情况都能够被准确地跟踪和评估。"
                           "\n  - 对于数据库表的新建、修改要有校验方法"
                           "\n  - 对于非直接创建的文件要校验文件的存在性，比如通过自动化脚本生成的文件要校验物理文件的存在性。"
                           "\n  - 对于启动的应用程序服务要校验对应的地址是否能够访问，或者校验对应的进程是否在运行。"
                           "\n"
                           "\n## 关于执行步骤中涉及工具使用的要求"
                           "\n- 一个步骤只涉及一次工具调用，不允许调用工具时处理多个事项。比如：一次读取、写入、编辑多个文件等类似操作。"
                           "\n- 若单步骤中涉及一个工具的多次调用，或者多个工具的调用，必须按照依赖关系拆分为多个步骤。"
                           "\n"
                           "\n## 计划的存储要求"
                           f"\n- 计划内容要求存储在指定文件，文件路径：{self.path}"
                           "\n- 计划文件必须以 YAML frontmatter 开头，字段包括：type: plan、created_at、session_id、title、status: in_progress。"
                           f"\n- frontmatter 中的 session_id 取值：{self.session_id}"
                           "\n- 计划文件必须包含固定的「## 进度摘要」章节（3-6 行，说明当前处于第几步、最近一次执行结果、下一步要做什么），并在每次更新计划时同步刷新该章节。"
                           "\n- 未完成步骤必须使用 [ ] 标注并保持顺序，便于恢复时按序继续执行。"
                           "\n"
                           "\n## 计划的输出要求"
                           "\n- 计划的首行为标题，指明是什么计划。"
                           "\n- 计划的第一部分为计划说明，简述要完成的任务。"
                           "\n- 计划的第二部分为计划的总体步骤及完成情况跟踪情况。"
                           "\n  比如：[X] 阅读用户需求说明书；"
                           "\n  比如：[ ] 分析用户的需求；"
                           "\n  其中，[X]: 表示该计划已经完成，后续不需要再执行了；[ ]: 表示该计划未完成，后续需要继续执行。"
                           "\n- 计划的第三部分为计划的明细步骤，详细分析并拆分每个步骤的具体内容和要求，明确每个步骤需要完成的任务和使用的工具。"
                           "\n"

            }
        )

    @staticmethod
    def _extract_progress_summary(content: str) -> str:
        """提取计划文件中 `## 进度摘要` 章节正文（取不到返回空串）。"""
        if not content:
            return ""
        match = re.search(r"##\s*进度摘要\s*\n(.*?)(?=\n##\s|\Z)", content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    async def make(self, requirements: str) -> ToolResponse:
        await self._stream(requirements=requirements)

        if self.path.exists():
            # 登记活跃计划（任务锚点），并回传进度摘要
            title = None
            summary = ""
            try:
                content = self.path.read_text(encoding="utf-8")
                frontmatter = extract_yaml_frontmatter(content)
                if isinstance(frontmatter, dict):
                    title = frontmatter.get("title")
                summary = self._extract_progress_summary(content)
            except Exception:
                title = None
            if not title:
                title = self.path.name

            state.save_active_plan(
                str(self.path),
                session_id=self.session_id,
                title=title,
            )

            text = f"计划文件已生成，文件路径: {self.path}"
            if summary:
                text = f"{text}\n进度摘要: {summary}"
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=text,
                    ),
                ],
            )

        # 未输出计划文件
        chat_response = await self._chat("请明确说明无法输出计划文件的原因")
        if chat_response.content.strip() == "":
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"未输出计划文件，且原因不明确。",
                    ),
                ],
            )
        else:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"未输出计划文件，原因为: {chat_response.content.strip()}",
                    )
                ]
            )

    async def resume(self, plan_path: str, instruction: str = None) -> ToolResponse:
        """读取既有计划文件，注入计划全文与未完成步骤，驱动从中断处继续执行。"""
        p = Path(plan_path)
        if not p.exists():
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"计划文件不存在，无法恢复执行: {plan_path}",
                    ),
                ],
            )

        try:
            content = p.read_text(encoding="utf-8")
        except Exception as e:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"计划文件读取失败: {e}",
                    ),
                ],
            )

        pending = re.findall(r"^- \[ \]\s*(.+)$", content, re.MULTILINE)
        if not pending:
            return ToolResponse(
                content=[
                    TextBlock(
                        type="text",
                        text=f"计划已全部完成，无需恢复: {plan_path}",
                    ),
                ],
            )

        default_instruction = (
            "请依据计划文件与当前代码状态，从中断处继续执行未完成步骤；"
            "执行前先读取计划文件确认最新进度，执行后更新计划文件的进度标记与「进度摘要」章节。"
        )
        resume_instruction = instruction or default_instruction
        pending_list = "\n".join(f"- {s}" for s in pending)

        requirements = (
            "【任务恢复】\n"
            f"计划文件路径: {plan_path}\n\n"
            f"{content}\n\n"
            "【未完成步骤】\n"
            f"{pending_list}\n\n"
            "【恢复指令】\n"
            f"{resume_instruction}"
        )

        await self._stream(requirements=requirements)

        # 刷新活跃计划登记（可能在执行后更新了计划文件）
        state.save_active_plan(plan_path, session_id=self.session_id)

        summary = ""
        try:
            summary = self._extract_progress_summary(p.read_text(encoding="utf-8"))
        except Exception:
            summary = ""

        text = f"已恢复执行计划，文件路径: {plan_path}"
        if summary:
            text = f"{text}\n进度摘要: {summary}"
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=text,
                ),
            ],
        )
