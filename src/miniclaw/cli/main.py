import asyncio
import json
import os
import warnings
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
from ..agents import get_llm_client, llm_tools_manager
from ..agents.base_llm_client import ToolResponse, TextBlock
from ..agents.constant import LLM_FUNCTION_SUBAGENT, LLM_FUNCTION_PLANNER
from ..constant import MINICLAW_LOG, EnvVarLoader
from ..utils.common import clip, dt_uuid
from ..utils.logger import setup_logger
from ..utils.security import mask_password
from ..utils.turn_taking import get_advance_messages

# 抑制 asyncio 的资源警告
# warnings.filterwarnings("ignore", category=ResourceWarning)



class CommandLineInteraction:
    """命令行交互界面"""

    def __init__(
            self,
            **kwargs
    ):
        self.provider = os.getenv("LLM_CLIENT_PROVIDER", "litellm")
        self.model = os.getenv("LLM_MODEL")
        self.api_key = os.getenv("LLM_API_KEY")
        self.base_url = os.getenv("LLM_BASE_URL")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", 1))
        self.max_tokens = int(os.getenv("LLM_MAX_TOKENS", 4096))

        self.client = get_llm_client()
        self.tools = llm_tools_manager.get_llm_tools()
        self.messages = []
        self.should_exit = False  # 增加退出标志
        # 非调试代码时使用，调试时请注释
        self.prompt_session = get_prompt_session(
            ["/help", "/chat", "/agent", "/clear", "/memory", "/memory-list", "/quit"])

        self.runtime_mode = "agent"  # 默认运行模式为代理机器人模式

        # 初始化
        setup_logger(enable_console=False)  # 日志初始化
        # 记忆初始化
        self.update_memory = False  # 更新记忆
        memory_filename = f"m{dt_uuid()}.md"
        self.memory_dir = str(
            Path(EnvVarLoader.get_str("MINICLAW_MEMORY_DIR", "~/.miniclaw/memory")).expanduser().resolve())
        self.memory_file = os.path.join(self.memory_dir, memory_filename)
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        # 显示欢迎信息
        console.print()
        console.print(MINICLAW_LOG)
        console.print("[bold]欢迎使用 MiniClaw！这是一个专注于智能体编排和工具管理的框架。[/bold]")
        console.print("大模型: [cyan]" + self.model + "[/cyan]")
        console.print("记忆缓存: [cyan]" + self.memory_file + "[/cyan]")
        console.print("运行模式: [cyan]" + self.runtime_mode + "[/cyan]")
        console.print("\n[italic]请使用 /help 查看指令，/quit 退出[/italic]\n")

        # 大模型提示词
        self._init_messages()

    def _init_messages(self):
        """实始化消息"""
        self.messages = [
            {
                "role": "system",
                "content": EnvVarLoader.get_str("CHAT_SYSTEM_PROMPT", """你是一个人工智能助手，协助用户完成各种任务。\n""")
            },
            {
                "role": "system",
                "content": f"Do not stop this application process by invoking the shell command tool (execute_shell_command), PID: {os.getpid()}\n"
            }
        ]

    async def _condense_memory(self):
        """处理记忆缓存"""
        memory = Memory(self.memory_file)
        await memory.condense(self.messages)

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
            table.add_row("/agent", "运行模式切换为代理模式", "/agent 代理模式下大模型将尽量自动推进任务执行")
            table.add_row("/chat", "运行模式切切换为对话模式", "/chat 对话模式下大模型将采用一问一答的方式")
            table.add_row("/clear", "清除对话上下文", "/clear")
            table.add_row("/memory", "记忆缓存", "/memory 精简记忆  /memory <记忆缓存> 提取记忆")
            table.add_row("/memory-list", "记忆缓存列表",
                          "/memory-list 查看记忆缓存列表(默认最新的前10个记忆)\n/memory-list 20 查看最新的前20个记忆")
            table.add_row("/quit", "退出 MiniClaw", "/quit")

            console.print(table)
        elif command == "chat":
            self.runtime_mode = "chat"
        elif command == "clear":
            self._init_messages()
            console.print(f"[green]✅ 清除对话上下文完成[/green]")
        elif command == "memory":
            if arg is None:  # 精简记忆
                await self._condense_memory()
                console.print(f"[green]✅ 精简记忆完成[/green]")
            else:
                _memory_file = os.path.join(self.memory_dir, arg)
                if not os.path.exists(_memory_file):
                    console.print(f"[red]错误：记忆文件 '{arg}' 不存在[/red]")
                    return
                else:
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

        elif command == "model":
            if arg is None:
                console.print(f"[green]当前模型: {self.model}[/green]")
                return

            self.model = arg
            console.print(f"[green]✅ 模型已更新为: {self.model}[/green]")
        elif command == "api_key":
            if arg is None:
                console.print(f"[green]当前模型 API_KEY: {mask_password(self.api_key)}[/green]")
                return

            self.api_key = arg
            console.print(f"[green]✅ 模型 API_KEY 已更新为: {mask_password(self.api_key)}[/green]")
        elif command == "base_url":
            if arg is None:
                console.print(f"[green]当前模型 URL: {self.base_url}[/green]")
                return

            self.base_url = arg
            console.print(f"[green]✅ 模型 URL 已更新为: {self.base_url}[/green]")
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
        elif command == "quit":
            self.should_exit = True  # 设置退出标志
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
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, self.prompt_session.prompt, "miniclaw> "
                )

                if not user_input.strip():
                    continue

                # 指令处理
                if user_input.startswith("/"):
                    command = user_input[1:].strip().lower()
                    await self.command_handler(command)
                    if self.should_exit:
                        break
                    continue

                if not user_input.strip():
                    continue

                # 若执行了精简记忆或者指定新的记忆缓存文件，则在下一轮用户输入时将记忆内容添加到用户输入的前面，供大模型参考
                if self.update_memory:
                    self._init_messages()
                    with open(self.memory_file, "r", encoding="utf-8") as f:
                        memory_content = f.read()
                    user_input = f"【对话历史缓存】\n\n{memory_content}\n\n【用户最新输入】\n\n{user_input}"
                    self.update_memory = False

                await self.stream(user_input)

            except KeyboardInterrupt:
                await aprint("\n\n检测到中断信息，再见！")
                break
            except EOFError:
                await aprint("\n\n检测到结束信号，再见！")
                break
            except Exception as e:
                await aprint(f"\n\n发生错误: {e}")

    async def stream(self, user_input: str):
        """处理用户输入并流��显示 LLM 响应"""
        self.messages.append({"role": "user", "content": user_input})

        while True:
            try:
                # 每一轮请求都重新初始化内容收集器，确保流式渲染正确
                collected_content = ""
                collected_reasoning_content = ""
                # 使用Live组件实现流式Markdown渲染
                waiting_spinner = Spinner("dots", text="", style="bold blue")
                with Live(waiting_spinner, console=console, auto_refresh=False, vertical_overflow="visible") as live:
                    async for chunk in self.client.stream(messages=self.messages, tools=self.tools):
                        if chunk.error:
                            console.print(f"[red]错误: {chunk.error}[/red]")
                            self.messages.append({
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
                                    self.messages.append(
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "reasoning_content": collected_reasoning_content,
                                            "tool_calls": chunk.tool_calls
                                        }
                                    )
                                else:
                                    self.messages.append(
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
                                    f"\n[bold yellow]🛠️ 工具调用: {function_obj['name']}({clip(function_obj['arguments'], max_len=100)})[/bold yellow]")
                                logger.debug(
                                    f"调用工具 {function_obj['name']} 参数: {function_obj['arguments']}")
                                if function_obj["name"] == LLM_FUNCTION_SUBAGENT:
                                    # 调用子任务执行器工具
                                    try:
                                        _tool_arguments_obj = json.loads(function_obj["arguments"])
                                        _clerk_message = _tool_arguments_obj["message"]
                                        from .clerk import Clerk
                                        clerk = Clerk(_clerk_message)
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
                                        planner = Planner()
                                        tool_response = await planner.make(function_obj["arguments"])
                                        logger.debug(f"planner response: {tool_response.content}")
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
                                # 继续对话流程
                                self.messages.append(
                                    {
                                        "role": "tool",
                                        "tool_call_id": tool_call_obj["id"],
                                        "name": function_obj["name"],
                                        "content": tool_response.model_dump_json()
                                    }
                                )
                                logger.debug(f"工具调用结果已添加到消息历史，继续对话")
                                break

                            else:
                                # 显示token使用情况
                                if chunk.prompt_tokens:
                                    console.print(f"\n[dim]📊 Tokens: 输入={chunk.prompt_tokens}, "
                                                  f"输出={chunk.completion_tokens}, "
                                                  f"总计={chunk.total_tokens}[/dim]")
                                if chunk.cost_usd:
                                    console.print(f"[dim]💰 费用: ${chunk.cost_usd:.6f}[/dim]")

                                # 将助手响应添加到历史
                                if len(collected_reasoning_content) > 0:
                                    self.messages.append({
                                        "role": "assistant",
                                        "content": collected_content,
                                        "reasoning_content": collected_reasoning_content
                                    })
                                else:
                                    self.messages.append({
                                        "role": "assistant",
                                        "content": collected_content
                                    })




                                if self.runtime_mode == "agent":
                                    # 如果本轮结束的对话是大模型询问用户是否继续或者要求用户确认，让大模型通过上下文的内容自行判断是否可以推动对话继续进行，而不是直接结束对话流程
                                    chat_response_judgment = await self.client.chat(
                                        messages=get_advance_messages(self.messages),
                                    )

                                    if chat_response_judgment.content.strip() == "继续":
                                        console.print(
                                            f"\n[yellow]大模型判断可以继续推动对话进行，继续下一轮对话...[/yellow]")

                                        self.messages.append({
                                            "role": "user",
                                            "content": "继续"
                                        })

                                        continue
                                    else:
                                        return
                                else:
                                    return
            except Exception as e:
                logger.exception(f"流式处理发生错误")
                console.print(f"[red]发生错误: {e}[/red]")
                self.messages.append({
                    "role": "assistant",
                    "content": f"发生错误: {str(e)}"
                })
                break


async def cli_run():
    cli = CommandLineInteraction()
    await cli.run()


if __name__ == "__main__":
    asyncio.run(cli_run())
