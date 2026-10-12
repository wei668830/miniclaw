"""会话轻量索引（方案 B）。

为「历史会话列表」提供 O(1) 的元数据读取：**不整读 JSONL**，只维护
``sid -> {created_at, updated_at, summary}`` 的索引；由 ``HistoryStore.append`` 写透更新，
首次/按需用目录对账（:meth:`SessionIndex.reconcile`）补齐历史遗留文件。

索引文件：``<MINICLAW_MEMORY_RAW_DIR>/index.json``（默认 ``~/.miniclaw/memory/raw/index.json``）。
JSONL 首行即该会话第一条用户消息（系统提示词不落盘），故 summary 取自首条 user 消息。
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

from ..constant import DEFAULT_MEMORY_RAW_DIR, EnvVarLoader

INDEX_FILENAME = "index.json"
_SUMMARY_MAX_LEN = 60
_USER_MARKER = "【用户最新输入】"


def extract_summary(content: str) -> str:
    """从消息内容提取会话摘要（首条用户消息正文，去除注入前缀并截断）。

    :param content: 用户消息内容（可能含技能注入块与「【用户最新输入】」前缀）
    :return: 裁剪后的摘要文本
    """
    text = content or ""
    if _USER_MARKER in text:
        text = text.split(_USER_MARKER, 1)[1]
    return text.strip().replace("\n", " ")[:_SUMMARY_MAX_LEN]


def _now() -> str:
    """返回当前时间的秒级 ISO 字符串。"""
    return datetime.now().isoformat(timespec="seconds")


class SessionIndex:
    """会话元数据索引（线程安全、原子写）。"""

    def __init__(self, base_dir: Optional[str | Path] = None) -> None:
        """初始化索引。

        :param base_dir: 索引所在目录（默认取 MINICLAW_MEMORY_RAW_DIR）
        """
        self._base_dir = Path(base_dir) if base_dir is not None else None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 路径
    # ------------------------------------------------------------------
    def raw_dir(self) -> Path:
        """返回历史 JSONL 所在目录（索引与其同目录）。"""
        if self._base_dir is not None:
            return self._base_dir
        base = EnvVarLoader.get_str("MINICLAW_MEMORY_RAW_DIR", DEFAULT_MEMORY_RAW_DIR)
        return Path(base).expanduser()

    def index_path(self) -> Path:
        """返回索引文件路径。"""
        return self.raw_dir() / INDEX_FILENAME

    # ------------------------------------------------------------------
    # 读写
    # ------------------------------------------------------------------
    def _read(self) -> Dict[str, dict]:
        """读取索引（不存在或损坏时返回空字典）。"""
        path = self.index_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.opt(exception=True).warning("会话索引读取失败，按空处理")
            return {}

    def _write(self, data: Dict[str, dict]) -> None:
        """原子写入索引（临时文件 + os.replace）。"""
        path = self.index_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            logger.opt(exception=True).warning("会话索引写入失败")

    # ------------------------------------------------------------------
    # 变更
    # ------------------------------------------------------------------
    def update_on_append(self, session_id: str, msg: dict) -> None:
        """追加消息时写透更新索引（由 ``HistoryStore.append`` 调用）。

        - 新会话：创建条目，记录 created_at/updated_at，并以首条 user 消息生成 summary；
        - 已有会话：刷新 updated_at，首个 user 消息前确定 summary。

        :param session_id: 会话 ID
        :param msg: 本次追加的消息
        """
        with self._lock:
            data = self._read()
            now = _now()
            entry = data.get(session_id)
            if entry is None:
                entry = {"created_at": now, "updated_at": now, "summary": ""}
            entry["updated_at"] = now
            if msg.get("role") == "user" and not entry.get("summary"):
                content = msg.get("content")
                if isinstance(content, str):
                    entry["summary"] = extract_summary(content)
            data[session_id] = entry
            self._write(data)

    def remove(self, session_id: str) -> None:
        """移除索引条目。

        :param session_id: 会话 ID
        """
        with self._lock:
            data = self._read()
            if session_id in data:
                data.pop(session_id, None)
                self._write(data)

    def all(self) -> Dict[str, dict]:
        """返回全部索引条目（浅拷贝）。"""
        with self._lock:
            return dict(self._read())

    # ------------------------------------------------------------------
    # 对账
    # ------------------------------------------------------------------
    def reconcile(self, raw_dir: Optional[Path] = None) -> Dict[str, dict]:
        """用目录中的 ``s*.jsonl`` 对账索引。

        - 补齐缺失条目（status 由文件 mtime 推导，summary 只读首行）；
        - 补齐缺 summary 的条目；
        - 文件比索引新时回填 updated_at（覆盖 CLI 等外部写入）；
        - 清理文件已删除的条目。

        :param raw_dir: 历史目录（默认取 :meth:`raw_dir`）
        :return: 对账后的索引字典
        """
        rdir = raw_dir or self.raw_dir()
        with self._lock:
            data = self._read()
            changed = False

            files: Dict[str, Path] = {}
            if rdir.exists():
                for jsonl in rdir.glob("s*.jsonl"):
                    files[jsonl.stem] = jsonl

            # 清理已删除文件对应的条目
            for sid in list(data.keys()):
                if sid not in files:
                    data.pop(sid, None)
                    changed = True

            # 补齐/刷新剩余条目（仅读首行）
            for sid, path in files.items():
                try:
                    mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
                except Exception:
                    mtime = None

                entry = data.get(sid)
                if entry is None:
                    data[sid] = {
                        "created_at": mtime,
                        "updated_at": mtime,
                        "summary": self._first_summary(path),
                    }
                    changed = True
                    continue
                if not entry.get("summary"):
                    entry["summary"] = self._first_summary(path)
                    changed = True
                if mtime and (not entry.get("updated_at") or entry["updated_at"] < mtime):
                    entry["updated_at"] = mtime
                    changed = True

            if changed:
                self._write(data)
            return dict(data)

    @staticmethod
    def _first_summary(path: Path) -> str:
        """仅读取文件前若干行，取首条 user 消息生成 summary（避免整读）。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for _ in range(50):
                    line = f.readline()
                    if not line:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if msg.get("role") == "user":
                        content = msg.get("content")
                        return extract_summary(content) if isinstance(content, str) else ""
        except Exception:
            logger.opt(exception=True).debug("读取会话首行失败")
        return ""


session_index = SessionIndex()

__all__ = ["session_index", "SessionIndex", "extract_summary"]
