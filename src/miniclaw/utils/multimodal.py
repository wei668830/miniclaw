"""多模态（图片）辅助：存储、读取与「OpenAI 兼容 content 块」构造。

内部表示（消息字典）：
    {"role": "user", "content": "<文本>", "images": [{"path": "<绝对路径>", "mime": "image/png"}]}

仅在**构造请求**时，才把 images 转成 OpenAI 兼容的块数组（base64 内联 data URL）。

约定：图片一律落盘为文件（`<工作目录>/multimodal/uploads/<session_id>/`），
历史只存路径引用，避免把 base64 写进 JSONL。
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

from ..constant import WORKING_DIR

# 支持的图片格式（与 DeepSeek 一致：JPEG/PNG/GIF/WebP）
_SUPPORTED_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


def uploads_dir(session_id: str) -> Path:
    """返回某会话的图片上传目录（并确保存在）。"""
    d = (WORKING_DIR / "multimodal" / "uploads" / session_id).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_mime(mime: Optional[str], name: Optional[str] = None) -> str:
    """归一化图片 MIME（缺省时按文件名推断，仍缺省则按 png）。"""
    if mime and mime.lower() in _SUPPORTED_MIME:
        return "image/jpeg" if mime.lower() == "image/jpg" else mime.lower()
    if name:
        guessed, _ = mimetypes.guess_type(name)
        if guessed and guessed.lower() in _SUPPORTED_MIME:
            return guessed.lower()
    return "image/png"


def save_image_base64(session_id: str, data_base64: str, mime: Optional[str] = None,
                      name: Optional[str] = None, uid: Optional[str] = None,
                      cache: Optional[dict] = None) -> Optional[Tuple[str, str]]:
    """把 base64 图片落盘，返回 (绝对路径, mime)；失败返回 None。

    :param cache: 可选单轮图片缓存；命中写入时顺带「预热」，避免本轮首次读盘编码。
    """
    try:
        raw = base64.b64decode(data_base64)
    except Exception:
        logger.opt(exception=True).warning("图片 base64 解码失败")
        return None
    mime = normalize_mime(mime, name)
    ext = _SUPPORTED_MIME.get(mime, ".png")
    fname = f"{uid or _short_id()}{ext}"
    path = uploads_dir(session_id) / fname
    try:
        path.write_bytes(raw)
    except Exception:
        logger.opt(exception=True).warning("图片写入失败")
        return None
    # 预热缓存（用规范的 base64，避免与文件内容不一致）
    prime_cache(cache, str(path), base64.b64encode(raw).decode("ascii"), mime)
    return str(path), mime


def _cache_key(path: str):
    """返回图片缓存键 ``(绝对路径, mtime_ns, size)``；无法 stat 时返回 None。"""
    try:
        p = Path(path)
        st = p.stat()
        return (str(p.resolve()), st.st_mtime_ns, st.st_size)
    except OSError:
        return None


def image_path_to_data_url(path: str, mime: Optional[str] = None, cache: Optional[dict] = None) -> Optional[str]:
    """把本地图片文件转成 `data:<mime>;base64,<b64>`；失败返回 None。

    :param cache: 可选「单轮缓存」字典（键 = :func:`_cache_key`，值 = data URL）。
        命中则直接返回，避免重复读盘 + base64 编码。
    """
    key = _cache_key(path) if cache is not None else None
    if key is not None:
        hit = cache.get(key)
        if hit is not None:
            return hit
    try:
        p = Path(path)
        if not p.is_file():
            return None
        m = mime or _EXT_TO_MIME.get(p.suffix.lower()) or (mimetypes.guess_type(str(p))[0]) or "image/png"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        data_url = f"data:{m};base64,{b64}"
    except Exception:
        logger.opt(exception=True).warning(f"读取图片失败: {path}")
        return None
    if key is not None:
        cache[key] = data_url
    return data_url


def prime_cache(cache: Optional[dict], path: str, data_base64: str, mime: Optional[str] = None) -> None:
    """用已知的 base64 预热缓存，避免刚写完文件又读盘编码。

    :param cache: 单轮缓存字典（None 则忽略）
    :param path: 刚写入的图片文件路径
    :param data_base64: 图片 base64（不含 data URL 前缀）
    :param mime: 图片 MIME
    """
    if cache is None:
        return
    key = _cache_key(path)
    if key is None:
        return
    m = normalize_mime(mime)
    cache[key] = f"data:{m};base64,{data_base64}"


def build_user_content(text: str, images: List[dict], detail: str = "auto", cache: Optional[dict] = None) -> List[dict]:
    """把文本 + 内部图片项构造成 OpenAI 兼容的 content 块数组。

    :param text: 用户文本
    :param images: [{"path":..., "mime":...}]
    :param detail: 图片 detail（low/high/original/auto）
    :param cache: 可选单轮图片缓存（见 :func:`image_path_to_data_url`）
    :return: content 块数组（text 块 + image_url 块）
    """
    blocks: List[dict] = []
    if text is not None and str(text).strip():
        blocks.append({"type": "text", "text": str(text)})
    for img in images or []:
        data_url = image_path_to_data_url(img.get("path", ""), img.get("mime"), cache=cache)
        if data_url:
            blocks.append({"type": "image_url", "image_url": {"url": data_url, "detail": detail}})
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    return blocks


def images_for_snapshot(images: List[dict]) -> List[dict]:
    """把内部图片项转成给前端展示的 {mime, data_url} 列表（供历史回放显示）。"""
    out: List[dict] = []
    for img in images or []:
        data_url = image_path_to_data_url(img.get("path", ""), img.get("mime"))
        if data_url:
            out.append({"mime": img.get("mime") or "image/png", "data_url": data_url})
    return out


def _short_id() -> str:
    """生成短随机 ID（用于图片文件名）。"""
    import uuid

    return uuid.uuid4().hex[:16]


__all__ = [
    "uploads_dir",
    "save_image_base64",
    "image_path_to_data_url",
    "prime_cache",
    "build_user_content",
    "images_for_snapshot",
    "normalize_mime",
]
