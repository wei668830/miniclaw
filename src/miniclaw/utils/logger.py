import os
import sys
from pathlib import Path

from loguru import logger


def _normalize_level(level: str) -> str:
    value = (level or "INFO").strip().upper()
    return value if value in {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"} else "INFO"


def setup_logger(enable_console:bool = True) -> None:
    """Configure global loguru handlers once for the whole app."""
    if getattr(setup_logger, "_configured", False):
        return

    log_level = _normalize_level(os.getenv("LOG_LEVEL", "INFO"))
    log_dir = Path(os.getenv("LOG_DIR", "logs")).expanduser().resolve()
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()

    if enable_console:
        logger.add(
            sys.stderr,
            level=log_level,
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
        )

    logger.add(
        str(log_dir / "app_{time:YYYY-MM-DD}.log"),
        level=log_level,
        rotation="00:00",
        retention="14 days",
        compression="zip",
        enqueue=True,
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {process.id}:{thread.id} | {name}:{function}:{line} - {message}",
    )

    setup_logger._configured = True
