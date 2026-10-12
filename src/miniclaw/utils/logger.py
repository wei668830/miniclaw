"""全局日志配置模块。

统一的日志初始化入口，负责：

* 控制台输出（可开关，带颜色与级别对齐）；
* 全量日志文件 ``app_{date}.log``（含进程 / 线程 / 模块 / 函数 / 行号）；
* 独立错误日志文件 ``error_{date}.log``（仅 ERROR 及以上），便于快速排查；
* 接管标准库 ``logging``（uvicorn / litellm / httpx 等第三方日志统一进 loguru）；
* 安装全局异常钩子（``sys.excepthook`` / ``threading.excepthook`` /
  ``sys.unraisablehook`` / asyncio 事件循环异常处理器），保证未捕获异常
  也能携带完整堆栈落盘；
* 提供 :func:`get_logger` / :func:`log_exception` 等便捷辅助函数。

所有行为均可通过环境变量覆盖，具体见 :func:`setup_logger`。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

__all__ = [
    "logger",
    "setup_logger",
    "get_logger",
    "log_exception",
    "install_global_exception_hooks",
    "install_asyncio_exception_handler",
    "InterceptHandler",
]

_VALID_LEVELS = {
    "TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL",
}

# 控制台日志格式（带颜色，级别左对齐 8 字符）
_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

# 文件日志格式（无颜色，含进程 / 线程 / 位置信息）
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
    "{level: <8} | "
    "{process.id}:{thread.name} | "
    "{name}:{function}:{line} - "
    "{message}"
)

# 需要接管的标准库 logger（第三方库）
_INTERCEPT_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "uvicorn.asgi",
    "litellm",
    "LiteLLM",
    "httpx",
    "httpcore",
    "openai",
    "openai._base_client",
    "asyncio",
    "watchfiles",
    "watchfiles.main",
)


def _env_bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量，未设置时返回默认值。"""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _normalize_level(level: str) -> str:
    """归一化日志级别为 loguru 合法级别，非法或空值回退为 ``INFO``。

    :param level: 原始级别字符串
    :return: 大写且合法的级别名
    """
    value = (level or "INFO").strip().upper()
    return value if value in _VALID_LEVELS else "INFO"


class InterceptHandler(logging.Handler):
    """将标准库 ``logging`` 记录转发到 loguru 的处理器。"""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        """将一条标准库 ``logging`` 记录转发到 loguru 输出。

        :param record: 标准库日志记录
        """
        # 将标准库 level 映射到 loguru level
        try:
            level: str | int = logger.level(record.levelname).name
        except (ValueError, KeyError):
            level = record.levelno

        # 用标准库记录自带的定位信息（模块 / 函数 / 行号）覆写 loguru 记录，
        # 以避免因调用栈深度差异导致定位到 logging 内部帧。
        logger.opt(exception=record.exc_info).patch(
            lambda r: r.update(
                name=record.name,
                function=record.funcName,
                line=record.lineno,
            )
        ).log(level, record.getMessage())


def _install_intercept_handler() -> None:
    """接管标准库 logging：根 logger + 常见第三方 logger。"""
    intercept = InterceptHandler()
    # 根 logger：捕获未单独配置的记录
    logging.basicConfig(handlers=[intercept], level=0, force=True)

    for name in _INTERCEPT_LOGGERS:
        std_logger = logging.getLogger(name)
        std_logger.handlers = [intercept]
        std_logger.propagate = False
        if std_logger.level in (logging.NOTSET, 0):
            std_logger.setLevel(logging.INFO)


def install_asyncio_exception_handler(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """为事件循环安装异常处理器，让未处理的 asyncio 异常带堆栈落盘。"""
    try:
        target = loop or asyncio.get_event_loop()
    except RuntimeError:
        return
    if target is None:
        return
    target.set_exception_handler(_asyncio_exception_handler)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
    """asyncio 事件循环的默认异常处理器，将未处理异常带堆栈记录下来。

    :param loop: 事件循环
    :param context: asyncio 提供的异常上下文字典
    """
    exc = context.get("exception")
    message = context.get("message", "未处理的 asyncio 异常")
    if exc is not None:
        logger.opt(exception=exc).error("未处理的 asyncio 异常: {}", message)
    else:
        logger.error("未处理的 asyncio 异常: {} | context={}", message, context)


def _excepthook(exc_type, exc_value, exc_tb) -> None:
    """主线程未捕获异常钩子。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.opt(exception=(exc_type, exc_value, exc_tb)).critical(
        "未捕获的异常（主线程），进程即将退出"
    )


def _threading_excepthook(args: "threading.ExceptHookArgs") -> None:
    """子线程未捕获异常钩子。"""
    if issubclass(args.exc_type, KeyboardInterrupt):
        return
    thread_name = args.thread.name if args.thread is not None else "unknown"
    logger.opt(
        exception=(args.exc_type, args.exc_value, args.exc_traceback)
    ).critical("未捕获的异常（线程 {}），线程即将退出", thread_name)


def _unraisablehook(unraisable) -> None:
    """无法传播的异常钩子（如 ``__del__`` 中抛出）。"""
    exc_value = unraisable.exc_value
    if exc_value is not None and issubclass(type(exc_value), KeyboardInterrupt):
        return
    logger.opt(
        exception=(unraisable.exc_type, unraisable.exc_value, unraisable.exc_traceback)
    ).error(
        "未处理的不可传播异常（unraisable）| object={!r}",
        unraisable.object,
    )


def install_global_exception_hooks() -> None:
    """安装进程级异常钩子（主线程 / 线程 / unraisable / asyncio）。"""
    sys.excepthook = _excepthook

    if hasattr(threading, "excepthook"):
        threading.excepthook = _threading_excepthook

    if hasattr(sys, "unraisablehook"):
        sys.unraisablehook = _unraisablehook

    # 若当前已有运行中的事件循环，则立即安装 asyncio 异常处理器
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is not None:
        install_asyncio_exception_handler(running)


def setup_logger(enable_console: bool = True) -> None:
    """为整个应用配置日志处理器（幂等，仅首次调用生效）。

    支持的环境变量：

    * ``LOG_LEVEL``       日志级别，默认 ``INFO``；
    * ``LOG_DIR``         日志目录，默认 ``logs``；
    * ``LOG_CONSOLE``     是否输出到控制台，默认 ``True``（受 ``enable_console`` 影响）；
    * ``LOG_FILE``        是否写入日志文件，默认 ``True``；
    * ``LOG_BACKTRACE``   异常回溯是否展开调试信息，默认 ``True``；
    * ``LOG_DIAGNOSE``    异常是否显示变量值诊断，默认 ``False``（生产环境性能更佳）；
    * ``LOG_ROTATION``    轮转策略，默认 ``00:00``；
    * ``LOG_RETENTION``   保留策略，默认 ``14 days``；
    * ``LOG_COMPRESSION`` 压缩格式，默认 ``zip``；
    * ``LOG_COLORIZE``    控制台是否着色，默认自动检测。
    """
    if getattr(setup_logger, "_configured", False):
        return

    log_level = _normalize_level(os.getenv("LOG_LEVEL", "INFO"))
    log_dir = Path(os.getenv("LOG_DIR", "logs")).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    console_enabled = enable_console and _env_bool("LOG_CONSOLE", True)
    file_enabled = _env_bool("LOG_FILE", True)
    backtrace = _env_bool("LOG_BACKTRACE", True)
    diagnose = _env_bool("LOG_DIAGNOSE", False)
    rotation = os.getenv("LOG_ROTATION", "00:00")
    retention = os.getenv("LOG_RETENTION", "14 days")
    compression = os.getenv("LOG_COMPRESSION", "zip")

    colorize_env = os.getenv("LOG_COLORIZE")
    colorize = (
        _env_bool("LOG_COLORIZE", sys.stderr.isatty())
        if colorize_env is not None
        else sys.stderr.isatty()
    )

    # 移除 loguru 默认处理器，避免重复输出
    logger.remove()

    if console_enabled:
        logger.add(
            sys.stderr,
            level=log_level,
            format=_CONSOLE_FORMAT,
            colorize=bool(colorize),
            enqueue=True,
            backtrace=backtrace,
            diagnose=diagnose,
            catch=True,
        )

    if file_enabled:
        # 全量日志
        logger.add(
            str(log_dir / "app_{time:YYYY-MM-DD}.log"),
            level=log_level,
            format=_FILE_FORMAT,
            rotation=rotation,
            retention=retention,
            compression=compression,
            enqueue=True,
            encoding="utf-8",
            backtrace=backtrace,
            diagnose=diagnose,
            catch=True,
        )
        # 错误日志（仅 ERROR 及以上），单独成文件便于排查
        logger.add(
            str(log_dir / "error_{time:YYYY-MM-DD}.log"),
            level="ERROR",
            format=_FILE_FORMAT,
            rotation=rotation,
            retention=retention,
            compression=compression,
            enqueue=True,
            encoding="utf-8",
            backtrace=True,
            diagnose=diagnose,
            catch=True,
        )

    if _env_bool("LOG_INTERCEPT", True):
        _install_intercept_handler()

    install_global_exception_hooks()

    logger.debug(
        "日志系统已初始化 | level={} dir={} console={} file={}",
        log_level,
        log_dir,
        console_enabled,
        file_enabled,
    )

    setup_logger._configured = True


def get_logger(name: Optional[str] = None):
    """获取带模块名绑定的 logger。

    便于在调用处区分来源，可在日志格式中通过 ``{extra[logger_name]}`` 引用。
    """
    if name is None:
        return logger
    return logger.bind(logger_name=name)


def log_exception(message: str = "发生未处理异常", *, level: str = "ERROR") -> None:
    """在当前异常上下文中记录日志并附带完整堆栈。"""
    logger.opt(exception=True).log(_normalize_level(level), message)
