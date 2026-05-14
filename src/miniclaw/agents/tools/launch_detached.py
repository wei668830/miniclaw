# -*- coding: utf-8 -*-
"""独立执行的命令 - 生产级实现（定期清理版）"""

import os
import subprocess
import sys
import uuid
import asyncio
import tempfile
import atexit
import shutil
import time
import threading
from typing import Dict, Optional, List
from pathlib import Path
from datetime import datetime, timedelta

from loguru import logger
from .file_io import _resolve_file_path
from ..base_llm_client import ToolResponse, TextBlock


# ==================== 临时文件管理器（定期清理） ====================

class TempScriptManager:
    """临时脚本管理器 - 定期清理"""

    def __init__(self):
        self.temp_dir = None
        self.initialized = False
        self.cleanup_interval_hours = 1  # 每小时清理一次
        self.cleanup_thread = None
        self._stop_cleanup = False

    def init(self):
        """初始化临时目录"""
        if self.initialized:
            return

        # 在系统临时目录下创建专属目录
        base_temp = tempfile.gettempdir()
        self.temp_dir = os.path.join(base_temp, "miniclaw_launch_scripts")
        os.makedirs(self.temp_dir, exist_ok=True)

        # 注册退出清理
        atexit.register(self.cleanup_on_exit)

        # 启动定期清理线程
        self._start_cleanup_thread()

        # 启动时清理一次过期文件（超过24小时）
        self.cleanup_expired(hours=24)

        self.initialized = True
        logger.info(f"临时脚本目录初始化: {self.temp_dir}")
        logger.info(f"定期清理任务已启动（间隔: {self.cleanup_interval_hours}小时）")

    def _start_cleanup_thread(self):
        """启动后台清理线程"""

        def cleanup_worker():
            while not self._stop_cleanup:
                time.sleep(self.cleanup_interval_hours * 3600)
                if not self._stop_cleanup:
                    self.cleanup_expired(hours=24)
                    logger.debug("执行定期清理")

        self.cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self.cleanup_thread.start()

    def get_script_path(self, suffix: str = ".bat") -> str:
        """获取临时脚本路径"""
        if not self.initialized:
            self.init()

        script_id = uuid.uuid4().hex[:12]
        filename = f"launch_{script_id}{suffix}"
        return os.path.join(self.temp_dir, filename)

    def cleanup_expired(self, hours: int = 24):
        """
        清理过期的临时文件

        Args:
            hours: 超过多少小时的文件将被删除
        """
        try:
            if not self.temp_dir or not os.path.exists(self.temp_dir):
                return

            now = time.time()
            expired_time = now - (hours * 3600)
            deleted_count = 0

            for filename in os.listdir(self.temp_dir):
                filepath = os.path.join(self.temp_dir, filename)
                try:
                    if os.path.isfile(filepath):
                        mtime = os.path.getmtime(filepath)
                        if mtime < expired_time:
                            os.remove(filepath)
                            deleted_count += 1
                            logger.debug(f"删除过期脚本: {filepath}")
                except Exception as e:
                    logger.warning(f"删除文件失败 {filepath}: {e}")

            if deleted_count > 0:
                logger.info(f"清理过期脚本: 共删除 {deleted_count} 个文件")

        except Exception as e:
            logger.warning(f"清理过期脚本失败: {e}")

    def cleanup_all(self):
        """清理所有临时文件"""
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                files = os.listdir(self.temp_dir)
                for filename in files:
                    filepath = os.path.join(self.temp_dir, filename)
                    try:
                        if os.path.isfile(filepath):
                            os.remove(filepath)
                    except Exception as e:
                        logger.warning(f"删除文件失败 {filepath}: {e}")
                logger.info(f"已清理所有临时脚本，共 {len(files)} 个文件")
        except Exception as e:
            logger.warning(f"清理临时目录失败: {e}")

    def cleanup_on_exit(self):
        """程序退出时清理"""
        self._stop_cleanup = True
        # 可选：退出时是否清理所有文件
        # self.cleanup_all()
        logger.debug("临时脚本管理器已停止")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            'temp_dir': self.temp_dir,
            'file_count': 0,
            'total_size_mb': 0,
            'oldest_file': None,
            'newest_file': None
        }

        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                files = []
                for filename in os.listdir(self.temp_dir):
                    filepath = os.path.join(self.temp_dir, filename)
                    if os.path.isfile(filepath):
                        mtime = os.path.getmtime(filepath)
                        size = os.path.getsize(filepath)
                        files.append((filepath, mtime, size))

                if files:
                    stats['file_count'] = len(files)
                    stats['total_size_mb'] = sum(s for _, _, s in files) / (1024 * 1024)

                    oldest = min(files, key=lambda x: x[1])
                    newest = max(files, key=lambda x: x[1])

                    stats['oldest_file'] = {
                        'name': os.path.basename(oldest[0]),
                        'age_hours': (time.time() - oldest[1]) / 3600
                    }
                    stats['newest_file'] = {
                        'name': os.path.basename(newest[0]),
                        'age_hours': (time.time() - newest[1]) / 3600
                    }
        except Exception as e:
            logger.warning(f"获取统计信息失败: {e}")

        return stats


# 全局临时脚本管理器
_temp_script_manager = TempScriptManager()


# ==================== 辅助清理函数（供外部调用） ====================

async def cleanup_temp_scripts(age_hours: int = 24) -> Dict:
    """
    手动清理临时脚本

    Args:
        age_hours: 清理超过指定小时的脚本

    Returns:
        清理统计信息
    """
    _temp_script_manager.init()

    before_stats = _temp_script_manager.get_stats()
    _temp_script_manager.cleanup_expired(hours=age_hours)
    after_stats = _temp_script_manager.get_stats()

    return {
        'before': before_stats,
        'after': after_stats,
        'deleted_count': before_stats['file_count'] - after_stats['file_count']
    }


async def get_temp_scripts_info() -> Dict:
    """
    获取临时脚本信息

    Returns:
        临时脚本统计信息
    """
    _temp_script_manager.init()
    return _temp_script_manager.get_stats()


# ==================== 核心函数 ====================

async def launch_detached(
        cmd: str,
        cwd: str,
        log_file: str,
        env: Optional[Dict[str, str]] = None,
        timeout_seconds: int = 30
) -> ToolResponse:
    """
    启动一个完全独立的进程，脱离 Python 进程，输出重定向到日志文件

    Args:
        cmd: 要执行的命令
        cwd: 工作目录
        log_file: 日志文件路径
        env: 额外的环境变量
        timeout_seconds: 启动超时时间（秒）

    Returns:
        ToolResponse: 包含启动信息的响应
    """
    # 初始化临时脚本管理器
    _temp_script_manager.init()

    # 处理路径
    cwd = _resolve_file_path(cwd)
    log_file = _resolve_file_path(log_file)

    # 验证工作目录
    if not os.path.exists(cwd):
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: 工作目录不存在: {cwd}",
                ),
            ],
        )

    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 合并环境变量
    env_dict = os.environ.copy()
    if env:
        env_dict.update(env)

    logger.info(f"启动独立进程 | 命令: {cmd} | 工作目录: {cwd} | 日志: {log_file}")

    try:
        if sys.platform == 'win32':
            return await _launch_windows(cmd, cwd, log_file, env_dict, timeout_seconds)
        else:
            return await _launch_unix(cmd, cwd, log_file, env_dict, timeout_seconds)

    except Exception as e:
        logger.exception(f"独立进程启动失败: {e}")
        return ToolResponse(
            content=[
                TextBlock(
                    type="text",
                    text=f"Error: 独立进程启动失败\n{str(e)}",
                ),
            ],
        )


async def _launch_windows(
        cmd: str,
        cwd: str,
        log_file: str,
        env_dict: Dict[str, str],
        timeout_seconds: int
) -> ToolResponse:
    """Windows 平台实现"""

    # 创建临时批处理文件（不自删除）
    bat_file = _temp_script_manager.get_script_path(".bat")

    # 转义日志路径中的反斜杠（用于批处理）
    log_file_escaped = log_file.replace('\\', '\\\\')
    cwd_escaped = cwd.replace('\\', '\\\\')

    # 批处理内容（不删除自身）
    bat_content = f'''@echo off
chcp 65001 > nul
cd /d "{cwd_escaped}"
echo [%date% %time%] ========== 进程启动 ========== >> "{log_file_escaped}"
echo [%date% %time%] 命令: {cmd} >> "{log_file_escaped}"
echo [%date% %time%] 工作目录: {cwd_escaped} >> "{log_file_escaped}"
echo [%date% %time%] 脚本文件: {bat_file} >> "{log_file_escaped}"
{cmd} >> "{log_file_escaped}" 2>&1
set EXIT_CODE=%errorlevel%
echo [%date% %time%] ========== 进程退出 ========== >> "{log_file_escaped}"
echo [%date% %time%] 退出码: %EXIT_CODE% >> "{log_file_escaped}"
if %EXIT_CODE% neq 0 (
    echo [%date% %time%] 错误: 进程异常退出 >> "{log_file_escaped}"
)
exit /b %EXIT_CODE%
'''

    # 写入批处理文件
    with open(bat_file, 'w', encoding='utf-8') as f:
        f.write(bat_content)

    logger.debug(f"创建临时脚本: {bat_file}")

    # 配置启动参数
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0  # 不显示窗口

    # 启动进程
    process = subprocess.Popen(
        f'start /min cmd /c "{bat_file}"',
        shell=True,
        cwd=cwd,
        env=env_dict,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
        startupinfo=startupinfo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL
    )

    shell_pid = process.pid
    logger.info(f"进程已启动 | Shell PID: {shell_pid} | 脚本: {os.path.basename(bat_file)}")

    # 等待进程启动
    await asyncio.sleep(2)

    # 查找实际启动的进程 PID
    actual_pids = await _find_actual_processes(cwd)

    # 构建返回信息
    info_lines = [
        "✅ 独立进程已启动",
        f"📁 工作目录: {cwd}",
        f"📄 日志文件: {log_file}",
        f"🆔 Shell PID: {shell_pid}",
        f"📝 临时脚本: {os.path.basename(bat_file)} (将自动清理)",
    ]

    if actual_pids:
        info_lines.append(f"🎯 实际进程 PID: {', '.join(actual_pids)}")
        info_lines.append(f"📊 查看进程: tasklist | findstr \"{actual_pids[0]}\"")
        info_lines.append(f"🛑 停止进程: taskkill /F /PID {actual_pids[0]}")

    info_lines.extend([
        f"🗑️  清理临时脚本: 系统将自动清理超过24小时的文件",
    ])

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="\n".join(info_lines),
            ),
        ],
    )


async def _launch_unix(
        cmd: str,
        cwd: str,
        log_file: str,
        env_dict: Dict[str, str],
        timeout_seconds: int
) -> ToolResponse:
    """Linux/Mac 平台实现"""

    # 创建临时 Shell 脚本（不自删除）
    script_file = _temp_script_manager.get_script_path(".sh")

    # Shell 脚本内容
    script_content = f'''#!/bin/bash
cd "{cwd}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========== 进程启动 ==========" >> "{log_file}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 命令: {cmd}" >> "{log_file}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 工作目录: {cwd}" >> "{log_file}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 脚本文件: {script_file}" >> "{log_file}"
{cmd} >> "{log_file}" 2>&1
EXIT_CODE=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ========== 进程退出 ==========" >> "{log_file}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 退出码: $EXIT_CODE" >> "{log_file}"
if [ $EXIT_CODE -ne 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 错误: 进程异常退出" >> "{log_file}"
fi
'''

    # 写入脚本文件
    with open(script_file, 'w', encoding='utf-8') as f:
        f.write(script_content)

    # 添加执行权限
    os.chmod(script_file, 0o755)

    logger.debug(f"创建临时脚本: {script_file}")

    # 启动进程
    process = subprocess.Popen(
        f'nohup "{script_file}" > /dev/null 2>&1 &',
        shell=True,
        cwd=cwd,
        env=env_dict,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        preexec_fn=os.setsid if hasattr(os, 'setsid') else None
    )

    shell_pid = process.pid
    logger.info(f"进程已启动 | Shell PID: {shell_pid} | 脚本: {os.path.basename(script_file)}")

    # 等待进程启动
    await asyncio.sleep(1)

    # 构建返回信息
    info_lines = [
        "✅ 独立进程已启动",
        f"📁 工作目录: {cwd}",
        f"📄 日志文件: {log_file}",
        f"🆔 Shell PID: {shell_pid}",
        f"📝 临时脚本: {os.path.basename(script_file)} (将自动清理)",
        f"🗑️  清理临时脚本: 系统将自动清理超过24小时的文件",
        f"📊 查看进程: ps aux | grep {shell_pid}",
        f"🛑 停止进程: kill -9 {shell_pid}",
    ]

    return ToolResponse(
        content=[
            TextBlock(
                type="text",
                text="\n".join(info_lines),
            ),
        ],
    )


async def _find_actual_processes(cwd: str) -> List[str]:
    """
    查找实际启动的进程 PID（通过工作目录和进程名）

    Args:
        cwd: 工作目录

    Returns:
        实际进程 PID 列表
    """
    actual_pids = []

    try:
        if sys.platform != 'win32':
            return actual_pids

        # 获取当前所有 Java 进程的详细信息（包括命令行）
        result = await asyncio.create_subprocess_shell(
            'wmic process where "name=\'java.exe\'" get processid,commandline /FORMAT:CSV',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, _ = await result.communicate()
        output = stdout.decode('gbk', errors='ignore')

        # 解析输出，找到工作目录匹配的进程
        for line in output.strip().split('\n'):
            if line and 'java.exe' in line.lower():
                parts = line.split(',')
                if len(parts) >= 2:
                    # 命令行在最后，PID 在倒数第二个
                    command_line = parts[-1] if len(parts) > 1 else ''
                    pid = parts[-2] if len(parts) > 1 else ''

                    # 检查是否包含目标工作目录
                    if cwd.lower() in command_line.lower() and pid.strip().isdigit():
                        actual_pids.append(pid.strip())

        # 如果没有找到，回退到简单查找
        if not actual_pids:
            result = await asyncio.create_subprocess_shell(
                'tasklist /FI "IMAGENAME eq java.exe" /FO CSV /NH',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, _ = await result.communicate()
            output = stdout.decode('gbk', errors='ignore')

            for line in output.strip().split('\n'):
                if line:
                    parts = line.replace('"', '').split(',')
                    if len(parts) >= 2 and parts[0].lower() == 'java.exe':
                        pid = parts[1].strip()
                        if pid and pid.isdigit():
                            actual_pids.append(pid)

        # 返回最新的几个（去重）
        unique_pids = list(dict.fromkeys(actual_pids))
        return unique_pids[-3:] if unique_pids else []

    except Exception as e:
        logger.debug(f"查找实际进程失败: {e}")
        return []


# ==================== 辅助工具函数 ====================

async def check_process_running(pid: int) -> bool:
    """
    检查进程是否在运行

    Args:
        pid: 进程 ID

    Returns:
        bool: True 表示进程在运行
    """
    try:
        if sys.platform == 'win32':
            result = await asyncio.create_subprocess_shell(
                f'tasklist /FI "PID eq {pid}" /NH',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            output = stdout.decode('gbk', errors='ignore')
            return str(pid) in output and "INFO" not in output
        else:
            os.kill(pid, 0)
            return True
    except (OSError, ProcessLookupError):
        return False
    except Exception as e:
        logger.error(f"检查进程失败: {e}")
        return False


async def stop_process(pid: int, force: bool = False) -> bool:
    """
    停止进程

    Args:
        pid: 进程 ID
        force: 是否强制终止

    Returns:
        bool: True 表示成功停止
    """
    try:
        if sys.platform == 'win32':
            cmd = f'taskkill /{"F" if force else ""} /PID {pid} /T'
        else:
            signal = '9' if force else '15'
            cmd = f'kill -{signal} {pid}'

        result = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await result.wait()

        if result.returncode == 0:
            logger.info(f"成功停止进程: {pid}")
            return True
        else:
            logger.warning(f"停止进程失败: {pid}")
            return False

    except Exception as e:
        logger.error(f"停止进程失败: {e}")
        return False


async def get_process_info(pid: int) -> Optional[Dict]:
    """
    获取进程详细信息

    Args:
        pid: 进程 ID

    Returns:
        进程信息字典
    """
    try:
        if sys.platform == 'win32':
            result = await asyncio.create_subprocess_shell(
                f'wmic process where "processid={pid}" get processid,name,commandline /FORMAT:CSV',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            output = stdout.decode('gbk', errors='ignore')

            lines = output.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split(',')
                if len(parts) >= 3:
                    return {
                        'pid': pid,
                        'name': parts[1] if len(parts) > 1 else '',
                        'command_line': parts[2] if len(parts) > 2 else ''
                    }
        else:
            # Linux/Mac 实现
            result = await asyncio.create_subprocess_shell(
                f'ps -p {pid} -o pid,comm,args --no-headers',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await result.communicate()
            output = stdout.decode('utf-8', errors='ignore').strip()

            if output:
                parts = output.split(None, 2)
                if len(parts) >= 2:
                    return {
                        'pid': pid,
                        'name': parts[1],
                        'command_line': parts[2] if len(parts) > 2 else ''
                    }
        return None

    except Exception as e:
        logger.debug(f"获取进程信息失败: {e}")
        return None