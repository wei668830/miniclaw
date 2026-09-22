"""会话状态管理：活跃计划路径登记与读取。

用于将「当前活跃任务锚点（计划文件）」持久化到
``<MINICLAW_STATE_DIR>/active_plan.json``，便于上下文超限或会话恢复时
重新定位并继续执行任务。
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..constant import DEFAULT_STATE_DIR, EnvVarLoader


STATE_DIR = Path(
    EnvVarLoader.get_str("MINICLAW_STATE_DIR", DEFAULT_STATE_DIR)
).expanduser().resolve()
ACTIVE_PLAN_FILE = STATE_DIR / "active_plan.json"


def save_active_plan(plan_path: str, session_id: str | None = None, title: str | None = None) -> None:
    """写入（刷新）活跃计划登记信息。"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "plan_path": plan_path,
        "session_id": session_id,
        "title": title,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with open(ACTIVE_PLAN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"活跃计划登记写入失败 {ACTIVE_PLAN_FILE}: {e}")


def load_active_plan() -> str | None:
    """读取活跃计划路径；文件不存在、损坏或对应计划文件不存在时返回 None。"""
    if not ACTIVE_PLAN_FILE.exists():
        return None
    try:
        with open(ACTIVE_PLAN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning(f"活跃计划登记读取失败 {ACTIVE_PLAN_FILE}: {e}")
        return None

    plan_path = data.get("plan_path") if isinstance(data, dict) else None
    if not plan_path:
        logger.warning(f"活跃计划登记缺少 plan_path: {ACTIVE_PLAN_FILE}")
        return None
    if not Path(plan_path).exists():
        logger.warning(f"活跃计划文件不存在: {plan_path}")
        return None
    return plan_path


def clear_active_plan() -> None:
    """清除活跃计划登记。"""
    try:
        if ACTIVE_PLAN_FILE.exists():
            ACTIVE_PLAN_FILE.unlink()
    except Exception as e:
        logger.warning(f"活跃计划登记清除失败 {ACTIVE_PLAN_FILE}: {e}")
