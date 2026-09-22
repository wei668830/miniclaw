"""持久化会话历史（外部记忆）。

以 append-only JSONL 形式将会话消息落盘，与内存上下文窗口解耦，
任何时候都能重建完整历史用于重新精简。文件路径：
``<MINICLAW_MEMORY_RAW_DIR>/<session_id>.jsonl``。
"""

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from ..constant import DEFAULT_MEMORY_RAW_DIR, EnvVarLoader


class HistoryStore:
    """append-only JSONL 会话历史存储。"""

    def __init__(self, session_id: str, base_dir: str | None = None):
        self.session_id = session_id
        if base_dir is None:
            base_dir = EnvVarLoader.get_str(
                "MINICLAW_MEMORY_RAW_DIR", DEFAULT_MEMORY_RAW_DIR
            )
        self.base_dir = Path(base_dir).expanduser()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.base_dir / f"{session_id}.jsonl"

    def append(self, msg: dict) -> None:
        """追加一条消息为单行 JSON；异常时记录 warning 不中断主流程。"""
        try:
            line = json.dumps(msg, ensure_ascii=False)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
        except Exception as e:
            logger.warning(f"会话历史写入失败 session={self.session_id}: {e}")

    def load_all(self) -> list[dict]:
        """读取全部消息；跳过损坏行并计数告警。"""
        messages: list[dict] = []
        if not self.path.exists():
            return messages
        bad = 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        bad += 1
        except Exception as e:
            logger.warning(f"会话历史读取失败 session={self.session_id}: {e}")
        if bad:
            logger.warning(
                f"会话历史 {self.path} 存在 {bad} 行损坏数据，已跳过"
            )
        return messages

    def tail(self, n: int) -> list[dict]:
        """返回最后 n 条消息。"""
        if n <= 0:
            return []
        messages = self.load_all()
        return messages[-n:]

    def stats(self) -> dict:
        """返回会话统计信息；文件不存在时返回零值。"""
        if not self.path.exists():
            return {
                "session_id": self.session_id,
                "path": str(self.path),
                "messages": 0,
                "bytes": 0,
                "updated_at": None,
            }
        try:
            size = self.path.stat().st_size
            mtime = self.path.stat().st_mtime
            updated_at = datetime.fromtimestamp(mtime).isoformat(timespec="seconds")
        except Exception as e:
            logger.warning(f"会话历史 stat 失败 session={self.session_id}: {e}")
            size = 0
            updated_at = None
        return {
            "session_id": self.session_id,
            "path": str(self.path),
            "messages": len(self.load_all()),
            "bytes": size,
            "updated_at": updated_at,
        }
