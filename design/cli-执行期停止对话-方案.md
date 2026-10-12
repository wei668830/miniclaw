---
type: plan
created_at: 2026-10-12 11:10:09
session_id: None
title: MiniClaw CLI 执行期 Ctrl+C 中止当前轮次
status: in_progress
---

# MiniClaw CLI 执行期「Ctrl+C 中止当前轮次」实现计划

## 进度摘要

- 当前进度：处于「现状梳理 / 交互约定固化」阶段（步骤0、步骤1 已完成），尚未改动任何源码。
- 最近一次执行结果：已阅读 `cli/main.py`、`cli/stream_runner.py`、`agents/providers/litellm_provider.py`、`agents/tools/shell.py`、`cli/session_state.py`、`cli/console.py`、`cli/commands.py`、`.miniclaw/repro_console.py`，确认仓库当前无任何 signal/cancel/SIGINT 处理。
- 关键结论：助手 `tool_calls` 与 `tool` 结果在 `run_stream_round` 中「无 await 间隔地」原子落盘，因此工具执行中途取消不会产生悬空 `tool_calls`；主要风险集中在 `asyncio.to_thread` 子进程不可被 cancel。
- 下一步：执行步骤2，在 `cli/main.py` 中引入 SIGINT handler 基础设施（`import signal` + 字段 + handler 方法 + 可取消轮次封装）。
- 阻塞/待确认：Ctrl+C 退出语义取舍（见步骤1约定表）需最终拍板；本计划默认「提示符处 Ctrl+C 不退出，退出统一用 /quit 或 Ctrl+D」。

---

## 计划说明

目标：让 MiniClaw 命令行交互（`src/miniclaw/cli/main.py`）在**执行过程中**（模型流式生成 / 工具执行阶段）按 `Ctrl+C` 能够**中止当前这一轮对话**并安全返回 `miniclaw>` 输入提示符，而不是退出整个程序；同时不破坏对话历史、不产生悬空 `tool_calls`、正确清理资源（`rich.Live(transient)`、litellm 异步流、shell 子进程）。

现状要点（已核对代码）：

- `CommandLineInteraction.run()` 用 `prompt_async("miniclaw> ")` 读输入；现有 `except KeyboardInterrupt` 直接 `mark_clean_shutdown(True)` 并退出整个 CLI。
- 一轮对话由 `stream()` 的 `while True` 驱动，每轮调用 `run_stream_round()`；`run_stream_round()` 用 `with Live(..., transient=True) as live:` 包裹 `async for chunk in client.stream(...)`，工具调用经 `_execute_tool_call()`（含 Clerk / Planner / `llm_tools_manager.execute_tool`）。
- `client.stream` 由 `agents/providers/litellm_provider.py` 实现，基于 `litellm.acompletion(stream=True)` 异步迭代。
- shell 工具 Windows 分支用 `asyncio.to_thread(_execute_subprocess_sync, ...)`；Linux 分支用 `asyncio.create_subprocess_shell(..., start_new_session=True)`。
- 会话历史以 append-only JSONL 落盘：`<MINICLAW_MEMORY_RAW_DIR>/<session_id>.jsonl`；`mark_clean_shutdown` 只应表示「进程退出」。

交付约束：保持 CLI 既有对外行为（命令集、`/quit` 单条退出语义）尽量不变；源码统一 4 空格缩进；不引入新第三方依赖。

---

## 总体步骤及完成情况跟踪

- [X] 步骤0：现状梳理与关键代码阅读（0.1~0.7）
- [X] 步骤1：固化交互约定（Ctrl+C 语义取舍表）
- [ ] 步骤2：`cli/main.py` 引入 SIGINT handler 基础设施
- [ ] 步骤3：`cli/main.py` 重写 `run()` 主循环（可取消轮次 + 空闲 Ctrl+C 不退出）
- [ ] 步骤4：`cli/stream_runner.py` 增加 spinner 中止提示与取消清理
- [ ] 步骤5：`agents/providers/litellm_provider.py` 增加异步流关闭（finally）
- [ ] 步骤6：`agents/tools/shell.py` 增加子进程注册表与取消时杀进程树
- [ ] 步骤7：可发现性文案（welcome / help）
- [ ] 步骤8：扩展 `.miniclaw/repro_console.py` 支持 Ctrl+C 注入与场景化用例
- [ ] 步骤9：用例 a~e 真机验证
- [ ] 步骤10：会话历史一致性校验
- [ ] 步骤11：回归验证（/quit、Ctrl+D、命令行为不变）
- [ ] 步骤12：风险、回滚与文档

---

## 明细步骤

> 约定：每个子步骤只包含**一次工具调用**；若同一目标需要多次调用同一工具，拆分为多个子步骤。
> 校验命令统一使用 MiniClaw 解释器：`C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe`
> 工作目录：`D:\wormsleep\workspace\MiniClaw`

### 步骤0：现状梳理与关键代码阅读（已完成）

- [X] 0.1 阅读 `src/miniclaw/cli/main.py` 第 1~1320 行：`run()`（1088-1145）、`stream()`（1176-1290）、`cleanup()`、`_cmd_quit`。
  - 工具：`read_file`
  - 校验：确认 `run()` 现有 `except KeyboardInterrupt` 会 `break` 退出。
- [X] 0.2 阅读 `src/miniclaw/cli/stream_runner.py`：`run_stream_round()`、`_execute_tool_call()`、`_append_assistant_tool_calls()`、`Live(transient=True)` 使用。
  - 工具：`read_file`
  - 校验：确认助手 `tool_calls` 与 `tool` 消息为「无 await 间隔」的原子落盘。
- [X] 0.3 阅读 `src/miniclaw/agents/providers/litellm_provider.py`：`LiteLLMClient.stream()` 的 `response = await acompletion(**params); async for chunk in response:`。
  - 工具：`read_file`
  - 校验：确认流式响应对象在取消时**没有** finally 关闭逻辑。
- [X] 0.4 阅读 `src/miniclaw/agents/tools/shell.py`：`_execute_subprocess_sync()`（`asyncio.to_thread` 目标）与 Linux 分支 `create_subprocess_shell`。
  - 工具：`read_file`
  - 校验：确认线程内 `proc.wait(timeout=...)` 阻塞，无法被 asyncio cancel 打断。
- [X] 0.5 阅读 `src/miniclaw/cli/session_state.py`：`mark_clean_shutdown()` 语义。
  - 工具：`read_file`
  - 校验：确认该标记仅描述「进程退出是否干净」。
- [X] 0.6 阅读 `src/miniclaw/cli/console.py` 与 `src/miniclaw/cli/commands.py`：`get_prompt_session()`（prompt_toolkit 无自定义 Ctrl+C 处理）、`COMMAND_SPECS`/`build_help_table()`。
  - 工具：`read_file`
  - 校验：确认提示符由 prompt_toolkit 自行处理 Ctrl+C（抛 KeyboardInterrupt）。
- [X] 0.7 阅读 `.miniclaw/repro_console.py`：真实控制台 + `WriteConsoleInput` 注入。
  - 工具：`read_file`
  - 校验：确认现有脚本仅注入 `/quit`，需扩展 Ctrl+C 注入。

### 步骤1：固化交互约定（Ctrl+C 语义取舍表）

- [X] 1.1 形成并确认如下约定表（作为实现与验收基线）：

  | 场景 | 现状行为 | 目标行为 |
  | --- | --- | --- |
  | 空闲提示符 `miniclaw>` 按 Ctrl+C | 退出整个 CLI | **不退出**：清空当前输入行并重绘提示符（忽略） |
  | 执行期（流式生成中）按 Ctrl+C | （无处理，通常直到结束/或退出） | **中止当前轮次**，打印提示，回到 `miniclaw>`，会话继续可用 |
  | 执行期（工具执行中）按 Ctrl+C | 同上 | **中止当前轮次**，尽力终止工具子进程，回到 `miniclaw>` |
  | 空闲提示符按 Ctrl+D（EOF） | 退出 | **保持退出**（打印“检测到结束信号，再见！”） |
  | 输入 `/quit` | 退出 | **保持退出**（单条退出，打印“检测到退出指令，再见！”） |
  | （可选）连续两次 Ctrl+C | 退出 | 可选：第二次 Ctrl+C 视为强制退出 |

  - 结论：`Ctrl+C ≠ 退出`（改为中止当前轮次 / 忽略）；退出统一走 `/quit` 或 `Ctrl+D`。此取舍需在 PR 描述与帮助文案中显式声明。
  - 工具：无（纯分析）
  - 校验：约定表已评审通过并写入本计划。

### 步骤2：`cli/main.py` 引入 SIGINT handler 基础设施

> 设计要点：用「把本轮执行封装为可取消 `asyncio.Task` + 自定义 SIGINT handler（handler 内 `loop.call_soon_threadsafe(task.cancel)`）」实现即时中止；因 Windows 无 `loop.add_signal_handler`，统一用 `signal.signal(SIGINT, handler)`。
> 与 prompt_toolkit 的关系：提示符激活时 prompt_toolkit 处于 raw 模式（Windows 关闭 `ENABLE_PROCESSED_INPUT` / POSIX 关闭 `ISIG`），Ctrl+C 被读作按键并由 prompt_toolkit 自身抛 `KeyboardInterrupt`，**不会**触发本 handler；退出提示符后控制台模式恢复，Ctrl+C 才产生 SIGINT 并进入本 handler。

- [ ] 2.1 在 `src/miniclaw/cli/main.py` 顶部导入区新增 `import signal`（紧邻其它标准库导入）。
  - 工具：`edit_file`（`old_text: "import asyncio\nimport json\nimport os\nimport shutil"` → 追加 `import signal`）
  - 校验：`python -c "import ast,io; ast.parse(open(r'src/miniclaw/cli/main.py',encoding='utf-8').read())"` 无异常；文件仍为 4 空格缩进。
- [ ] 2.2 在 `CommandLineInteraction.__init__` 内（`self.should_exit = False` 附近）新增取消相关字段：
  ```python
  self._current_round_task = None      # 当前正在执行的可取消轮次任务
  self._abort_requested = False        # 本轮是否由用户 Ctrl+C 主动中止
  self._orig_sigint_handler = None     # 原始 SIGINT handler，用于退出时恢复
  ```
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过。
- [ ] 2.3 新增方法 `_install_sigint_handler()` / `_restore_sigint_handler()`（放在 `cleanup()` 之前）：
  ```python
  def _install_sigint_handler(self):
      """安装 SIGINT handler：执行期 Ctrl+C 取消当前轮次任务。

      注意：Windows 不支持 loop.add_signal_handler，统一用 signal.signal；
      handler 在主线程执行，用 loop.call_soon_threadsafe 调度 task.cancel。
      """
      loop = asyncio.get_event_loop()
      try:
          self._orig_sigint_handler = signal.getsignal(signal.SIGINT)
      except Exception:
          self._orig_sigint_handler = None

      def _on_sigint(signum, frame):
          task = self._current_round_task
          if task is not None and not task.done():
              self._abort_requested = True
              loop.call_soon_threadsafe(task.cancel)

      signal.signal(signal.SIGINT, _on_sigint)

  def _restore_sigint_handler(self):
      if self._orig_sigint_handler is not None:
          try:
              signal.signal(signal.SIGINT, self._orig_sigint_handler)
          except Exception:
              pass
  ```
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过。
- [ ] 2.4 新增方法 `_run_round()` 与 `_finalize_aborted_round()`：
  ```python
  async def _run_round(self, user_input: str, append_user_message: bool = True):
      """把本轮 stream() 封装为可取消 Task 并 await。"""
      task = asyncio.create_task(
          self.stream(user_input, append_user_message=append_user_message)
      )
      self._current_round_task = task
      try:
          await task
      finally:
          self._current_round_task = None

  def _finalize_aborted_round(self):
      """一轮被中止后修正历史一致性（不落盘悬空 tool_calls）。

      取消发生在「正文生成中途」或「工具执行中途」时，助手消息尚未落盘，
      历史最后一条为 user/tool；补一条纯文本占位助手消息，避免出现
      「连续 user」或「tool 无后继助手」的历史。
      注意：不调用 mark_clean_shutdown（会话仍在运行，仅进程退出才标记）。
      """
      try:
          if self.messages and self.messages[-1].get("role") != "assistant":
              self._append_message({
                  "role": "assistant",
                  "content": "（本轮已被用户中止）",
              })
      except Exception as e:
          logger.debug(f"中止轮次历史修正失败: {e}")
  ```
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过。

### 步骤3：`cli/main.py` 重写 `run()` 主循环

- [ ] 3.1 重写 `run()`：安装/恢复 handler；用 `_run_round` 包裹普通对话；区分「中止」与「真退出」；空闲 Ctrl+C 不退出。
  - 目标实现骨架：
  ```python
  async def run(self):
      """运行命令行交互界面"""
      self._install_sigint_handler()
      try:
          while True:
              try:
                  if self.should_exit:
                      break
                  user_input = await self.prompt_session.prompt_async("miniclaw> ")
                  if not user_input.strip():
                      continue
                  if user_input.startswith("/"):
                      command = user_input[1:].strip()
                      await self.command_handler(command)
                      if self.should_exit:
                          break
                      continue
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
                  await self._run_round(user_input, append_user_message=append_user)
              except asyncio.CancelledError:
                  if self._abort_requested:
                      self._abort_requested = False
                      self._finalize_aborted_round()
                      try:
                          cancel_active_shell_processes()
                      except Exception:
                          pass
                      console.print(
                          "[yellow]⏹ 已中止当前轮次，返回输入提示符"
                          "（可继续对话；/quit 或 Ctrl+D 退出）[/yellow]"
                      )
                      continue
                  raise
              except KeyboardInterrupt:
                  # 空闲提示符下的 Ctrl+C：不退出（清空输入行由 prompt_toolkit 处理）
                  console.print(
                      "[dim]（提示符处忽略 Ctrl+C；退出请用 /quit 或 Ctrl+D）[/dim]"
                  )
                  continue
              except EOFError:
                  try:
                      mark_clean_shutdown(True)
                  except Exception:
                      pass
                  await aprint("\n\n检测到结束信号，再见！")
                  break
              except Exception as e:
                  await aprint(f"\n\n发生错误: {e}")
      finally:
          self._restore_sigint_handler()
  ```
  - 说明：`cancel_active_shell_processes` 在步骤6中于 `shell.py` 定义并在此导入（`from ..agents.tools.shell import cancel_active_shell_processes`）；若步骤6未完成，可先以 `try/except ImportError` 兜底。
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过；`python -c "import miniclaw.cli.main"` 无异常。
- [ ] 3.2 在 `main.py` 顶部新增导入 `from ..agents.tools.shell import cancel_active_shell_processes`（与 `from ..agents import ...` 同区域）。
  - 工具：`edit_file`
  - 校验：`python -c "import miniclaw.cli.main"` 无异常。
- [ ] 3.3 确认 `except asyncio.CancelledError` 分支不会吞掉「外层真实取消」：仅当 `self._abort_requested` 为真才继续，否则 `raise`（已在 3.1 体现）。
  - 工具：`read_file`
  - 校验：人工确认 `raise` 分支存在。

### 步骤4：`cli/stream_runner.py` 增加 spinner 中止提示与取消清理

- [ ] 4.1 将等待 spinner 文案改为带 Ctrl+C 提示：
  - 将 `waiting_spinner = Spinner("dots", text="", style="bold blue")`
  - 改为 `waiting_spinner = Spinner("dots", text=" 生成中 · Ctrl+C 中止本轮", style="bold blue")`
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/stream_runner.py` 通过。
- [ ] 4.2 在 `run_stream_round()` 的 `with Live(...)` 块外层加 `try/except asyncio.CancelledError`（仅记录并 `raise`），确保 `Live.__exit__` 一定执行且便于排查：
  ```python
  try:
      with Live(...) as live:
          ...
  except asyncio.CancelledError:
      logger.debug(f"{log_prefix}本轮已取消（用户中止）")
      raise
  ```
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/stream_runner.py` 通过；人工确认 `raise` 保留取消语义。
> 说明：因 `Live(transient=True)` 通过上下文管理器退出清理，`CancelledError` 在 `with` 内抛出时会正常触发 `Live.stop()`，无需额外手动清理预览区。

### 步骤5：`agents/providers/litellm_provider.py` 增加异步流关闭（finally）

- [ ] 5.1 在 `LiteLLMClient.stream()` 中，把 `async for chunk in response:` 循环包裹在 `try/finally` 中，取消/异常时主动关闭底层流：
  ```python
  response = await acompletion(**params)
  try:
      async for chunk in response:
          ...
  finally:
      try:
          aclose = getattr(response, "aclose", None) or getattr(response, "close", None)
          if aclose is not None:
              res = aclose()
              if inspect.isawaitable(res):
                  await res
      except BaseException:
          pass
  ```
  并在文件顶部新增 `import inspect`（若尚未导入）。
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/agents/providers/litellm_provider.py` 通过。
> 说明：`finally` 内 `except BaseException` 仅用于清理、不吞掉外层取消（原 `CancelledError` 在 `finally` 正常结束后仍会继续传播）。

### 步骤6：`agents/tools/shell.py` 增加子进程注册表与取消时杀进程树

> 核心问题：Windows 分支 `await asyncio.to_thread(_execute_subprocess_sync, ...)`，`task.cancel()` 只取消对该线程 future 的等待，**线程内 `subprocess` 仍继续运行**（直到命令结束/超时）。需提供「取消时杀进程树」的通道。

- [ ] 6.1 在 `shell.py` 顶部导入区补充 `import threading`，并新增模块级注册表与取消函数：
  ```python
  _ACTIVE_PROCS = {}          # pid -> (proc, threading.Event)
  _ACTIVE_LOCK = threading.Lock()

  def _register_proc(pid, proc, cancel_event):
      with _ACTIVE_LOCK:
          _ACTIVE_PROCS[pid] = (proc, cancel_event)

  def _unregister_proc(pid):
      with _ACTIVE_LOCK:
          _ACTIVE_PROCS.pop(pid, None)

  def cancel_active_shell_processes():
      """中止所有在跑的 shell 子进程（供 Ctrl+C 中止轮次时调用）。"""
      with _ACTIVE_LOCK:
          items = list(_ACTIVE_PROCS.items())
      for pid, (proc, cancel_event) in items:
          try:
              cancel_event.set()
          except Exception:
              pass
          if sys.platform == "win32":
              _kill_process_tree_win32(pid)
          else:
              try:
                  os.killpg(os.getpgid(pid), signal.SIGTERM)
              except (ProcessLookupError, OSError):
                  pass
  ```
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/agents/tools/shell.py` 通过。
- [ ] 6.2 在 `_execute_subprocess_sync()` 内：新增参数 `cancel_event: "threading.Event | None" = None`；`Popen` 成功后 `_register_proc(proc.pid, proc, cancel_event or threading.Event())`；把 `proc.wait(timeout=timeout)` 改为小步轮询（如 0.3s）并在 `cancel_event.is_set()` 时 `_kill_process_tree_win32(proc.pid)` 后返回 `-1, "", "命令已被用户中止"`；`finally` 中 `_unregister_proc(proc.pid)`。
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/agents/tools/shell.py` 通过。
- [ ] 6.3 在 Windows 分支调用处传入 `cancel_event`（在 `execute_shell_command` 内构造 `threading.Event()` 传入 `asyncio.to_thread`）。
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/agents/tools/shell.py` 通过。
- [ ] 6.4 在 Linux 分支 `await asyncio.wait_for(proc.communicate(), timeout=timeout)` 外增加 `except asyncio.CancelledError:` 分支，`os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` 后 `raise`。
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/agents/tools/shell.py` 通过。

### 步骤7：可发现性文案（welcome / help）

- [ ] 7.1 修改 `CommandLineInteraction.__init__` 中的欢迎提示：在「请使用 /help 查看指令，/quit 退出」一行补充中止说明，例如：
  `console.print("\n[italic]请使用 /help 查看指令，/quit 退出；执行中按 Ctrl+C 可中止当前轮次[/italic]\n")`
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过。
- [ ] 7.2 修改 `_cmd_help()`：在打印帮助表格后补一行说明：
  `console.print("[dim]提示：执行中按 Ctrl+C 中止当前轮次（不退出）；/quit 或 Ctrl+D 退出[/dim]")`
  - 工具：`edit_file`
  - 校验：`python -m py_compile src/miniclaw/cli/main.py` 通过；运行 CLI 输入 `/help` 可见该行（随步骤9一并验证）。

### 步骤8：扩展 `.miniclaw/repro_console.py` 支持 Ctrl+C 注入

> 现状：脚本用 `WriteConsoleInput` 注入 `/quit`。Windows 下真实 `Ctrl+C`（SIGINT）需用 `GenerateConsoleCtrlEvent(CTRL_C_EVENT, 0)`；同时 harness 自身需忽略 Ctrl+C，避免被一起终止。

- [ ] 8.1 新增/改造注入函数 `send_ctrl_c()`：实现 `kernel32.GenerateConsoleCtrlEvent(1, 0)`（1 = CTRL_C_EVENT），并在发送前后用 `SetConsoleCtrlHandler(None, True/False)` 让 harness 自身忽略 Ctrl+C。
  - 工具：`edit_file`
  - 校验：`python -m py_compile .miniclaw/repro_console.py` 通过。
- [ ] 8.2 新增/改造注入函数 `send_ctrl_d()`（注入 `\x04` 或直接 `GenerateConsoleCtrlEvent` 不适用；用 `WriteConsoleInput` 注入 EOT 字符）以覆盖用例 d。
  - 工具：`edit_file`
  - 校验：`python -m py_compile .miniclaw/repro_console.py` 通过。
- [ ] 8.3 参数化场景：支持 `python repro_console.py <case>`，其中 `case ∈ {a,b,c,d,e}`，各场景编排「启动 → 等待就绪（约 9s）→ 触发动作 → 注入 Ctrl+C / Ctrl+D / /quit → 抓屏 + 保存 stderr」。
  - 工具：`edit_file`
  - 校验：`python -m py_compile .miniclaw/repro_console.py`；`python .miniclaw/repro_console.py a` 能跑通并生成 `.miniclaw/repro_console_stderr.txt`（步骤9详细判定）。

### 步骤9：用例 a~e 真机验证

> 每个用例一次命令调用。抓屏结果保存在 `.miniclaw/repro_console_stderr.txt`（或按用例命名）。

- [ ] 9.1 用例 a（生成中途中止）：让模型产出较长正文，注入 Ctrl+C。
  - 命令：`C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe .miniclaw\repro_console.py a`
  - 校验：抓屏中出现「已中止当前轮次」，随后再次出现 `miniclaw>` 提示符；进程未退出。
- [ ] 9.2 用例 b（工具执行中途中止）：让模型调用 `execute_shell_command` 执行长耗时命令（如 `ping -n 20 127.0.0.1`），执行途中注入 Ctrl+C。
  - 命令：`... python .miniclaw\repro_console.py b`
  - 校验：抓屏出现「已中止当前轮次」并回到提示符；`tasklist | findstr ping`（或等价检查）确认子进程已被杀。
- [ ] 9.3 用例 c（空闲提示符 Ctrl+C 不退出）：在提示符处注入 Ctrl+C。
  - 命令：`... python .miniclaw\repro_console.py c`
  - 校验：抓屏出现「提示符处忽略 Ctrl+C」，提示符 `miniclaw>` 仍存在，进程未退出。
- [ ] 9.4 用例 d（Ctrl+D 退出）：注入 EOF。
  - 命令：`... python .miniclaw\repro_console.py d`
  - 校验：抓屏出现「检测到结束信号，再见！」，进程退出。
- [ ] 9.5 用例 e（/quit 单条退出）：注入 `/quit`。
  - 命令：`... python .miniclaw\repro_console.py e`
  - 校验：抓屏出现「检测到退出指令，再见！」，且**不出现**「检测到中断信息，再见！」；进程退出。
- [ ] 9.6 组合用例（中止后可继续）：在一次会话中「先中止一轮 → 再输入一句话 → 正常回复 → /quit」。
  - 命令：`... python .miniclaw\repro_console.py f`（如实现）
  - 校验：抓屏显示中止后仍可继续对话并正常回复。

### 步骤10：会话历史一致性校验

- [ ] 10.1 定位本用例会话 JSONL：`<MINICLAW_MEMORY_RAW_DIR>/<session_id>.jsonl`（paths 见会话启动输出「会话历史」行）。
  - 工具：`execute_shell_command`（`dir` 列出目录）/ `read_file`
  - 校验：文件存在且包含用例消息。
- [ ] 10.2 校验无悬空 `tool_calls`：解析 JSONL，检查每条含 `tool_calls` 的 assistant 消息后都紧跟对应 `tool_call_id` 的 tool 消息。
  - 工具：`execute_shell_command`（用一小段 python 扫描）
  - 校验：脚本输出 `OK: no dangling tool_calls`（或列出 0 条违规）。
- [ ] 10.3 校验中止后历史末尾为合法序列：中止的轮次末尾为「user/tool → assistant 占位」。
  - 工具：`execute_shell_command`（打印最后 3 行 JSON） / `tail_file`
  - 校验：最后一条为 `role=assistant` 且内容为「（本轮已被用户中止）」。
- [ ] 10.4 校验 `clean_shutdown` 语义：单轮中止后 `current_session.json` 的 `clean_shutdown` 仍为 `false`；仅在 `/quit`/Ctrl+D 退出后才为 `true`。
  - 工具：`read_file`（读取 `C:\Users\zhaowei\.miniclaw\state\current_session.json`）
  - 校验：字段值与预期一致。

### 步骤11：回归验证（/quit、Ctrl+D、命令行为不变）

- [ ] 11.1 语法/导入回归：编译全部改动文件。
  - 命令：`C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe -m compileall src\miniclaw\cli\main.py src\miniclaw\cli\stream_runner.py src\miniclaw\agents\providers\litellm_provider.py src\miniclaw\agents\tools\shell.py`
  - 校验：退出码 0，无 SyntaxError。
- [ ] 11.2 `/help`、`/clear`、`/cost`、`/session-list` 等命令仍正常（任取 2~3 个）。
  - 命令：通过 `repro_console.py` 注入对应命令并抓屏
  - 校验：命令输出与改动前一致。
- [ ] 11.3 正常一轮对话（无中断）行为不变：正文落屏一次、工具轮次正常、`done_token` 处理不变。
  - 命令：`repro_console.py` 输入普通问题并抓屏
  - 校验：无重复/缺失落屏，无异常。
- [ ] 11.4 确认空闲 Ctrl+C 不再退出（与步骤9.3 一致），`Ctrl+D` 仍退出（与步骤9.4 一致）。
  - 工具：无（引用步骤9结果）
  - 校验：结论与约定表一致。

### 步骤12：风险、回滚与文档

- [ ] 12.1 汇总风险清单与缓解措施（写入 PR 描述 / README 片段，用 `append_file` 更新 `README.md` 或设计文档）：
  - 风险1：`SIGINT` handler 与 prompt_toolkit 交互——提示符激活时不触发 handler（raw 模式），已按此设计；需在 a~e 用例回归确认。
  - 风险2：`asyncio.to_thread` 子进程不可取消——由注册表 + `cancel_active_shell_processes()` + `cancel_event` 缓解；极端情况（命令内部再拉起脱离进程组的新进程）仍可能残留，需人工确认。
  - 风险3：`await task` 的 `CancelledError` 分支可能误吞外层取消——用 `_abort_requested` 布尔区分，仅中止场景 `continue`，否则 `raise`。
  - 风险4：litellm 版本差异导致 `aclose`/`close` 名称不同——用 `getattr` 兼容并在 `finally` 内 `except BaseException` 兜底。
  - 风险5：`rich.Live` 退出清理——`transient=True` 依赖上下文管理器；取消异常正常触发 `__exit__`，已用步骤4.2 的 `try/except` 加固。
  - 风险6：行为变更（Ctrl+C 不再退出）可能影响既有用户习惯——通过欢迎语/`/help` 文案显式声明，提供「连续两次 Ctrl+C 退出」可选开关。
  - 工具：`append_file`
  - 校验：文档文件包含上述 6 条风险与缓解。
- [ ] 12.2 回滚方案：所有改动集中在 4 个源码文件（`cli/main.py`、`cli/stream_runner.py`、`providers/litellm_provider.py`、`tools/shell.py`）+ 1 个验证脚本；使用 `git checkout -- <files>` 或反向 patch 即可完全回滚，不影响命令集与数据格式。
  - 工具：`append_file`
  - 校验：文档包含回滚命令。
- [ ] 12.3 （可选）实现「连续两次 Ctrl+C 强制退出」：在 `_on_sigint` 中记录时间戳，第二次在 2s 内则 `self.should_exit = True` / 触发 `KeyboardInterrupt` 退出。
  - 工具：`edit_file`
  - 校验：`py_compile` 通过；手工/用例验证第二次 Ctrl+C 退出。

---

## 附：关键实现问答（供评审）

1. **handler 安装/恢复时机**：在 `run()` 进入循环前 `_install_sigint_handler()`，在 `run()` 的 `finally` 中 `_restore_sigint_handler()`；`cli_run()` 的 `finally` 仍保留 `cleanup()`。
2. **与 prompt_toolkit raw 模式关系**：提示符激活期间控制台为 raw 模式，Ctrl+C 不产生 SIGINT，由 prompt_toolkit 抛 `KeyboardInterrupt`；此时 handler 不介入。
3. **取消语义与历史一致性**：
   - 正文生成中途取消：无 `tool_calls` 落盘，补一条纯文本占位助手消息；
   - 工具执行中途取消：`tool_calls` 与 `tool` 消息本就原子成对（无 await 间隔），不会悬空；
   - **不调用** `mark_clean_shutdown`（仅进程退出才标记）。
4. **资源清理**：`Live(transient=True)` 由上下文管理器退出清理；litellm 流由 `finally` 关闭；shell 子进程由注册表 + 取消函数杀进程树。
5. **可发现性**：spinner 文案 + 欢迎语 + `/help` 提示。
6. **验证**：扩展 `repro_console.py`，用 `GenerateConsoleCtrlEvent` 注入真实 SIGINT，覆盖用例 a~e。


---

## 实施结果（已落地）

按本方案已在代码中实现「执行期 Ctrl+C 中止当前轮次」，改动如下：

- `src/miniclaw/cli/main.py`
  - 新增 `import signal` 与运行时字段 `_round_task` / `_loop` / `_prev_sigint`。
  - 新增 `_install_sigint_handler()` / `_restore_sigint_handler()` / `_on_sigint()`：
    执行期收到 SIGINT 时用 `loop.call_soon_threadsafe(task.cancel)` 取消本轮任务；
    空闲时交回原处理器（保持既有行为）。
  - 新增 `_run_round()`：把一轮对话跑成 `asyncio.ensure_future(...)` 任务，捕获
    `asyncio.CancelledError` 后打印「⏹️ 已停止本轮生成」并回到输入提示符；`finally`
    兜底取消未完成任务，避免后台泄漏。
  - `run()`：安装/恢复 SIGINT 处理器；一轮执行改走 `_run_round()`；空闲提示符下
    按 Ctrl+C 不再退出（打印提示后 `continue`），退出统一用 `/quit` 或 `Ctrl+D`。
  - 欢迎信息追加「执行中按 Ctrl+C 可停止本轮」。
- `src/miniclaw/cli/stream_runner.py`：等待 spinner 文案增加「（生成中，按 Ctrl+C 可停止本轮）」。
- `src/miniclaw/agents/providers/litellm_provider.py`：`stream()` 增加 `finally`，
  经 `_aclose_stream_quietly()` 在正常结束/报错/被取消时统一关闭底层异步流。
- `src/miniclaw/agents/tools/shell.py`：新增 shell 子进程注册表（`_ACTIVE_PROCS`）与
  `kill_all_active_shell_procs()`；Windows `asyncio.to_thread` 分支与 Linux 分支在
  `CancelledError` 时杀掉子进程/进程组，解决线程内子进程无法被 cancel 的问题。

验证：
- `py_compile` 全通过；`pytest -q` 19 passed。
- `.miniclaw/test_stop.py`（离线假 client）：执行期触发信号 → 本轮被取消并打印停止提示 →
  回到提示符 → `/quit` 退出；会话历史仅 `['system','system','user']`，无残留 assistant 消息。
- 真实控制台（`.miniclaw/repro_stop.py`）测得：提示符态 console mode=`1008`（PROCESSED_INPUT 关闭，
  Ctrl+C 由 prompt_toolkit 处理），流式执行态 console mode=`503`（PROCESSED_INPUT 开启，
  真实 Ctrl+C 会产生 SIGINT → 触发本机制）；空闲态 Ctrl+C 不再退出；`/quit` 仍单条干净退出。
