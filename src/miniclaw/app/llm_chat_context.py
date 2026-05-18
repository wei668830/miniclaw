from pathlib import Path
import json
from typing import List, Optional

from loguru import logger

from miniclaw.constant import EnvVarLoader


def _get_cid_file(cid: str) -> str:
    """根据 CID 获取文件路径（无后缀）"""
    _dir = Path(EnvVarLoader.get_str("MINICLAW_CHAT_CONTEXT_DIR", "~/.miniclaw/chat_context")).expanduser().resolve()
    if not _dir.exists():
        _dir.mkdir(parents=True)

    return str(_dir / f"cid_{cid}")  # 移除 .json 后缀


async def store_chat_context(
        cid: str,
        message: dict
):
    """存储聊天上下文，每行存储一个 JSON 对象"""
    try:
        cid_file = _get_cid_file(cid)
        # 使用 "a" 模式追加，每行写入一个 JSON 对象
        with open(cid_file, "a", encoding="utf-8") as f:
            # 确保 message 包含 role 和 content
            # 格式: {"role": "user", "content": "..."}
            json.dump(message, f, ensure_ascii=False)
            f.write('\n')  # 每条记录后添加换行符
    except Exception as e:
        logger.error(f"Error storing chat context for CID {cid}: {e}")


async def fetch_chat_context(cid: str) -> List[dict]:
    """根据 CID 获取聊天上下文，按行读取返回列表"""
    try:
        cid_file = _get_cid_file(cid)
        if Path(cid_file).exists():
            messages = []
            with open(cid_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:  # 跳过空行
                        try:
                            message = json.loads(line)
                            messages.append(message)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Failed to parse line in {cid_file}: {e}")
            return messages
    except Exception as e:
        logger.error(f"Error fetching chat context for CID {cid}: {e}")

    return []


__all__ = ["store_chat_context", "fetch_chat_context"]