# -*- coding: utf-8 -*-
# flake8: noqa: E501
# pylint: disable=line-too-long
"""The shell command tool."""

import asyncio
import locale
import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from ..base_llm_client import ToolResponse, TextBlock
from ...constant import WORKING_DIR
from ...config.context import get_current_workspace_dir

def _kill_process_tree_win32(pid: int) -> None:
    """Kill a process and all its descendants on Windows via taskkill.

    Uses ``taskkill /F /T`` which forcefully terminates the entire process
    tree, including grandchild processes that ``Popen.kill()`` would miss.
    """
    try:
        subprocess.call(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        logger.opt(exception=True).debug('终止 Windows 进程树失败')


# 正在执行的 shell 子进程注册表：供「本轮被 Ctrl+C 中止」时杀掉仍在运行的子进程树。
_ACTIVE_PROCS: dict[int, subprocess.Popen] = {}
_ACTIVE_PROCS_LOCK = threading.Lock()


def _register_process(proc: subprocess.Popen) -> None:
    with _ACTIVE_PROCS_LOCK:
        _ACTIVE_PROCS[proc.pid] = proc


def _unregister_process(pid: int) -> None:
    with _ACTIVE_PROCS_LOCK:
        _ACTIVE_PROCS.pop(pid, None)


def kill_all_active_shell_procs() -> None:
    """终止所有仍在运行的 shell 子进程（及其子进程树）。

    供 :func:`execute_shell_command` 在协程被取消（用户 Ctrl+C 中止本轮）时调用：
    Windows 分支用 ``asyncio.to_thread`` 包裹同步子进程，线程内的 ``proc.wait()``
    无法被 asyncio 取消打断，只能显式杀掉对应进程树。
    """
    with _ACTIVE_PROCS_LOCK:
        procs = list(_ACTIVE_PROCS.items())
    for pid, proc in procs:
        try:
            if proc.poll() is not None:
                continue
            if sys.platform == "win32":
                _kill_process_tree_win32(pid)
            else:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            logger.opt(exception=True).debug('查询或终止 shell 子进程失败')
        except Exception:
            logger.opt(exception=True).debug('终止 shell 子进程时发生异常')


def _sanitize_win_cmd(cmd: str) -> str:
    """Fix common LLM escaping artefacts for Windows ``cmd.exe``.

    LLMs sometimes produce commands with backslash-escaped double quotes
    (``\\"``) — valid in bash/JSON but meaningless to ``cmd.exe``.  When
    *every* double-quote in the command is preceded by a backslash, it is
    almost certainly a double-escape artefact, so we strip them.
    """
    if '\\"' in cmd and '"' not in cmd.replace('\\"', ""):
        return cmd.replace('\\"', '"')
    return cmd


def _read_temp_file(path: str) -> str:
    """Read a temporary output file and return its decoded content."""
    try:
        with open(path, "rb") as f:
            return smart_decode(f.read())
    except OSError:
        logger.opt(exception=True).debug('读取临时输出文件失败，返回空字符串')
        return ""


# pylint: disable=too-many-branches, too-many-statements
def _execute_subprocess_sync(
    cmd: str,
    cwd: str,
    timeout: int,
    env: dict | None = None,
) -> tuple[int, str, str]:
    """Execute subprocess synchronously in a thread.

    This function runs in a separate thread to avoid Windows asyncio
    subprocess limitations.

    stdout/stderr are redirected to temporary files instead of pipes.
    On Windows, child processes inherit pipe handles and keep them open
    even after the parent exits, which causes ``communicate()`` to block
    until *all* holders close (e.g. a Chrome process launched via
    ``Start-Process``).  With temp-file redirection, ``proc.wait()``
    only waits for the direct child (``cmd.exe``) to exit, so commands
    that spawn background processes return immediately.

    Args:
        cmd (`str`):
            The shell command to execute.
        cwd (`str`):
            The working directory for the command execution.
        timeout (`int`):
            The maximum time (in seconds) allowed for the command to run.
        env (`dict | None`):
            Environment variables for the subprocess.

    Returns:
        `tuple[int, str, str]`:
            A tuple containing the return code, standard output, and
            standard error of the executed command. If timeout occurs, the
            return code will be -1 and stderr will contain timeout information.
    """
    stdout_path: str | None = None
    stderr_path: str | None = None
    stdout_file = None
    stderr_file = None
    proc: subprocess.Popen | None = None

    try:
        cmd = _sanitize_win_cmd(cmd)
        wrapped = f'cmd /D /S /C "{cmd}"'

        stdout_fd, stdout_path = tempfile.mkstemp(prefix="miniclaw_out_")
        stderr_fd, stderr_path = tempfile.mkstemp(prefix="miniclaw_err_")
        stdout_file = os.fdopen(stdout_fd, "wb")
        stderr_file = os.fdopen(stderr_fd, "wb")

        proc = subprocess.Popen(  # pylint: disable=consider-using-with
            wrapped,
            shell=False,
            stdout=stdout_file,
            stderr=stderr_file,
            text=False,
            cwd=cwd,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        _register_process(proc)

        # Parent copies are no longer needed — the child inherited its own
        # handles via CreateProcess.  Closing here avoids holding the files
        # open longer than necessary.
        stdout_file.close()
        stdout_file = None
        stderr_file.close()
        stderr_file = None

        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.opt(exception=True).debug('子进程执行超时，准备终止进程树')
            timed_out = True
            _kill_process_tree_win32(proc.pid)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.opt(exception=True).debug('子进程超时后仍未退出，尝试直接 kill')
                try:
                    proc.kill()
                except OSError:
                    logger.opt(exception=True).debug('超时后 kill 子进程失败')

        stdout_str = _read_temp_file(stdout_path)
        stderr_str = _read_temp_file(stderr_path)

        if timed_out:
            timeout_msg = (
                f"Command execution exceeded the timeout of {timeout} seconds."
            )
            if stderr_str:
                stderr_str = f"{stderr_str}\n{timeout_msg}"
            else:
                stderr_str = timeout_msg
            return -1, stdout_str, stderr_str

        returncode = proc.returncode if proc.returncode is not None else -1
        return returncode, stdout_str, stderr_str

    except Exception as e:
        logger.exception("执行子进程失败")
        return -1, "", str(e)
    finally:
        if proc is not None:
            _unregister_process(proc.pid)
        for f in (stdout_file, stderr_file):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    logger.opt(exception=True).debug('关闭临时文件句柄失败')
        for path in (stdout_path, stderr_path):
            if path is not None:
                try:
                    os.unlink(path)
                except OSError:
                    logger.opt(exception=True).debug('删除临时文件失败')


# pylint: disable=too-many-branches, too-many-statements
async def execute_shell_command(
    command: str,
    timeout: int = 60,
    cwd: Optional[Path] = None,
) -> ToolResponse:
    """Execute a shell command and return its output.

    Platform shells: Windows uses cmd.exe; Linux/macOS use /bin/sh or /bin/bash.

    IMPORTANT: Always consider the operating system before choosing commands.

    Args:
        command (`str`):
            The shell command to execute.
        timeout (`int`, defaults to `60`):
            The maximum time (in seconds) allowed for the command to run.
            Default is 60 seconds.
        cwd (`Optional[Path]`, defaults to `None`):
            The working directory for the command execution.
            If None, defaults to WORKING_DIR.

    Returns:
        `ToolResponse`:
            The tool response containing the return code, standard output, and
            standard error of the executed command. If timeout occurs, the
            return code will be -1 and stderr will contain timeout information.
    """

    cmd = (command or "").strip()

    # Use current workspace_dir from context, fallback to WORKING_DIR
    if cwd is not None:
        working_dir = cwd
    else:
        working_dir = get_current_workspace_dir() or WORKING_DIR

    # Ensure the venv Python is on PATH for subprocesses
    env = os.environ.copy()
    python_bin_dir = str(Path(sys.executable).parent)
    existing_path = env.get("PATH", "")
    if existing_path:
        env["PATH"] = python_bin_dir + os.pathsep + existing_path
    else:
        env["PATH"] = python_bin_dir

    try:
        # 安全检查：禁止执行可能导致自杀式操作的命令（如批量杀死 Python 进程）
        _check_kill_yourself_command(cmd)
        if sys.platform == "win32":
            # Windows: use thread pool to avoid asyncio subprocess limitations
            try:
                returncode, stdout_str, stderr_str = await asyncio.to_thread(
                    _execute_subprocess_sync,
                    cmd,
                    str(working_dir),
                    timeout,
                    env,
                )
            except asyncio.CancelledError:
                # 本轮被 Ctrl+C 中止：to_thread 中的子进程无法被 cancel 打断，显式杀进程树
                kill_all_active_shell_procs()
                raise
        else:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                bufsize=0,
                cwd=str(working_dir),
                env=env,
                start_new_session=True,
            )

            try:
                # Apply timeout to communicate directly; wait()+communicate()
                # can hang if descendants keep stdout/stderr pipes open.
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
                stdout_str = smart_decode(stdout)
                stderr_str = smart_decode(stderr)
                returncode = proc.returncode

            except asyncio.CancelledError:
                # 本轮被 Ctrl+C 中止：杀掉整个进程组，避免残留子进程
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    logger.opt(exception=True).debug('取消时终止进程组失败')
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except BaseException:
                    logger.opt(exception=True).debug('取消时等待子进程结束失败')
                raise

            except asyncio.TimeoutError:
                logger.opt(exception=True).debug('命令执行超时，尝试终止整个进程组')
                stderr_suffix = (
                    f"⚠️ TimeoutError: The command execution exceeded "
                    f"the timeout of {timeout} seconds. "
                    f"Please consider increasing the timeout value if this command "
                    f"requires more time to complete."
                )
                returncode = -1
                try:
                    # Kill the entire process group so that child processes
                    # spawned by the shell are also terminated.
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGTERM)
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2)
                    except asyncio.TimeoutError:
                        logger.opt(exception=True).debug('等待子进程退出超时，强制发送 SIGKILL')
                        os.killpg(pgid, signal.SIGKILL)
                        await asyncio.wait_for(proc.wait(), timeout=2)

                    # Drain remaining output.
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(),
                            timeout=1,
                        )
                    except asyncio.TimeoutError:
                        logger.opt(exception=True).debug('读取子进程剩余输出超时')
                        stdout, stderr = b"", b""
                    stdout_str = smart_decode(stdout)
                    stderr_str = smart_decode(stderr)
                    if stderr_str:
                        stderr_str += f"\n{stderr_suffix}"
                    else:
                        stderr_str = stderr_suffix
                except (ProcessLookupError, OSError):
                    # Process already gone or pgid lookup failed — fall back
                    # to direct kill on the process itself.
                    logger.opt(exception=True).debug('终止进程组失败，回退到直接 kill 子进程')
                    try:
                        proc.kill()
                        await proc.wait()
                    except (ProcessLookupError, OSError):
                        logger.opt(exception=True).debug('回退 kill 子进程失败')
                    stdout_str = ""
                    stderr_str = stderr_suffix

        if returncode == 0:
            if stdout_str:
                response_text = stdout_str
            else:
                response_text = "Command executed successfully (no output)."
            if stderr_str:
                response_text += f"\n[stderr]\n{stderr_str}"
        else:
            response_parts = [f"Command failed with exit code {returncode}."]
            if stdout_str:
                response_parts.append(f"\n[stdout]\n{stdout_str}")
            if stderr_str:
                response_parts.append(f"\n[stderr]\n{stderr_str}")
            response_text = "".join(response_parts)

        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=response_text,
                ),
            ],
        )

    except Exception as e:
        logger.exception("Shell 命令执行失败")
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: Shell command execution failed due to \n{e}",
                ),
            ],
        )


def smart_decode(data: bytes) -> str:
    try:
        decoded_str = data.decode("utf-8")
    except UnicodeDecodeError:
        logger.opt(exception=True).debug('UTF-8 解码失败，尝试使用本地编码')
        encoding = locale.getpreferredencoding(False) or "utf-8"
        decoded_str = data.decode(encoding, errors="replace")

    return decoded_str.strip("\n")


def _check_kill_yourself_command(cmd: str):
    """Check if the command is a self-termination command."""
    # 统一转为小写，防止用户通过大小写绕过（比如 TASKKILL, Python.Exe）
    cmd_lower = cmd.lower()

    if sys.platform == "win32":
        # --- Windows 平台 ---

        # 1. 传统的 CMD taskkill 命令
        # 补充了 /FI (过滤器) 的绕过情况
        if "taskkill" in cmd_lower and "python.exe" in cmd_lower:
            raise Exception("Killing all python.exe processes is not allowed as this will also stop the application.")

        # 2. PowerShell 的 Stop-Process 命令
        # 补充了别名 kill/spps 以及单引号的绕过情况
        if ("stop-process" in cmd_lower or " kill " in cmd_lower or " spps " in cmd_lower) and \
                ("python" in cmd_lower) and ("-name" in cmd_lower or "-id" in cmd_lower):
            raise Exception("Killing all python.exe processes is not allowed as this will also stop the application.")

    else:
        # --- Linux / macOS 平台 ---

        # 1. killall 命令 (例如: killall -9 python)
        if "killall" in cmd_lower and "python" in cmd_lower:
            raise Exception("Killing all python processes is not allowed as this will also stop the application.")

        # 2. pkill 命令 (例如: pkill -f python)
        if "pkill" in cmd_lower and "python" in cmd_lower:
            raise Exception("Killing all python processes is not allowed as this will also stop the application.")

        # 3. ps + grep + kill 组合拳 (例如: ps -ef | grep python | awk ... | xargs kill)
        # 只要命令里同时包含 kill、grep 和 python，极大概率是在进行批量查杀
        if "kill" in cmd_lower and "grep" in cmd_lower and "python" in cmd_lower:
            raise Exception("Killing all python processes is not allowed as this will also stop the application.")



