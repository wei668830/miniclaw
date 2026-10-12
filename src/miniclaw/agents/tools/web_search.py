# -*- coding: utf-8 -*-
"""豆包搜索（Custom 版）联网搜索工具。

支持 web / image 两类搜索的全量参数，用于获取外部/最新资料。

API Key 从配置文件读取，配置文件默认路径为
``<WORKING_DIR>/config/web_search.json``，可通过环境变量
``MINICLAW_WEB_SEARCH_CONFIG`` 指定其它路径；文件不存在时会自动
写入一份带默认值的模板，便于用户填写 API Key。

配置项优先级：环境变量 > 配置文件 > 内置默认值。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

import httpx

from ..base_llm_client import ToolResponse, TextBlock
from ...constant import EnvVarLoader, WORKING_DIR

logger = logging.getLogger(__name__)

# 默认接口地址（API Key 接入方式）
DEFAULT_SEARCH_URL = "https://open.feedcoopapi.com/search_api/web_search"
DEFAULT_TIMEOUT = 10
DEFAULT_COUNT = 10
# image 搜索最大返回条数
IMAGE_MAX_COUNT = 5
# 配置文件相对 WORKING_DIR 的默认路径
_DEFAULT_CONFIG_RELATIVE = "config/web_search.json"


def get_config_path() -> Path:
    """返回联网搜索配置文件路径。"""
    custom = EnvVarLoader.get_str("MINICLAW_WEB_SEARCH_CONFIG")
    if custom:
        return Path(custom).expanduser().resolve()
    return (WORKING_DIR / _DEFAULT_CONFIG_RELATIVE).resolve()


def _ensure_config_file(path: Path) -> None:
    """配置文件不存在时写入一份带默认值的模板，便于用户填写 API Key。"""
    if path.exists():
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        template = {
            "api_key": "",
            "url": DEFAULT_SEARCH_URL,
            "timeout": DEFAULT_TIMEOUT,
        }
        path.write_text(
            json.dumps(template, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
    except Exception as e:  # pragma: no cover - 目录/权限异常
        logger.warning("写入联网搜索配置模板失败: %s", e, exc_info=True)


def load_search_config() -> dict:
    """读取联网搜索配置（配置文件 + 环境变量覆盖）。

    Returns:
        含 ``api_key`` / ``url`` / ``timeout`` / ``config_path`` 的字典。
    """
    path = get_config_path()
    _ensure_config_file(path)

    data: dict = {}
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
    except Exception as e:
        logger.warning("读取联网搜索配置失败(%s): %s", path, e, exc_info=True)
        data = {}

    api_key = (EnvVarLoader.get_str("DOUBAO_SEARCH_API_KEY")
               or str(data.get("api_key") or "")).strip()
    url = (EnvVarLoader.get_str("DOUBAO_SEARCH_URL")
           or str(data.get("url") or DEFAULT_SEARCH_URL)).strip()
    try:
        timeout = int(EnvVarLoader.get_str("DOUBAO_SEARCH_TIMEOUT")
                      or data.get("timeout") or DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        logger.debug("解析搜索超时配置失败，使用默认超时", exc_info=True)
        timeout = DEFAULT_TIMEOUT

    return {
        "api_key": api_key,
        "url": url or DEFAULT_SEARCH_URL,
        "timeout": timeout,
        "config_path": str(path),
    }


def _build_web_body(
    query: str,
    count: int,
    need_content: bool,
    need_url: bool,
    sites: Optional[str],
    block_hosts: Optional[str],
    auth_info_level: int,
    time_range: Optional[str],
    query_rewrite: bool,
    content_formats: str,
    industry: Optional[str],
    need_summary: bool,
) -> dict:
    """构造 web 搜索请求体（仅包含已设置的字段）。"""
    filt: dict[str, Any] = {
        "NeedContent": bool(need_content),
        "NeedUrl": bool(need_url),
    }
    if sites:
        filt["Sites"] = sites
    if block_hosts:
        filt["BlockHosts"] = block_hosts
    if auth_info_level:
        filt["AuthInfoLevel"] = auth_info_level

    body: dict[str, Any] = {
        "Query": query,
        "SearchType": "web",
        "Count": count,
        "Filter": filt,
        "NeedSummary": bool(need_summary),
        "QueryControl": {"QueryRewrite": bool(query_rewrite)},
        "ContentFormats": content_formats or "text",
    }
    if time_range:
        body["TimeRange"] = time_range
    if industry:
        body["Industry"] = industry
    return body


def _build_image_body(
    query: str,
    count: int,
    query_rewrite: bool,
    image_width_min: Optional[int],
    image_height_min: Optional[int],
    image_width_max: Optional[int],
    image_height_max: Optional[int],
    image_shapes: Optional[list[str]],
) -> dict:
    """构造 image 搜索请求体（仅包含已设置的字段）。"""
    filt: dict[str, Any] = {}
    if image_width_min is not None:
        filt["ImageWidthMin"] = image_width_min
    if image_height_min is not None:
        filt["ImageHeightMin"] = image_height_min
    if image_width_max is not None:
        filt["ImageWidthMax"] = image_width_max
    if image_height_max is not None:
        filt["ImageHeightMax"] = image_height_max
    if image_shapes:
        filt["ImageShapes"] = list(image_shapes)

    body: dict[str, Any] = {
        "Query": query,
        "SearchType": "image",
        "Count": min(count, IMAGE_MAX_COUNT),
        "QueryControl": {"QueryRewrite": bool(query_rewrite)},
    }
    if filt:
        body["Filter"] = filt
    return body


def _format_web_results(result: dict) -> str:
    """把 web 搜索结果格式化为可读文本（优先使用 Summary）。"""
    web_results = result.get("WebResults") or []
    total = result.get("ResultCount", len(web_results))
    lines = [f"豆包联网搜索（web）结果，共 {total} 条：", ""]
    if not web_results:
        lines.append("（无结果）")
        return "\n".join(lines)

    for idx, item in enumerate(web_results, 1):
        if not isinstance(item, dict):
            continue
        title = item.get("Title") or "（无标题）"
        site = item.get("SiteName") or ""
        url = item.get("Url") or ""
        publish = item.get("PublishTime") or ""
        summary = item.get("Summary") or item.get("Snippet") or ""
        lines.append(f"{idx}. {title}")
        if site or publish:
            lines.append(f"   站点：{site}    发布时间：{publish}".rstrip())
        if url:
            lines.append(f"   链接：{url}")
        if summary:
            lines.append(f"   摘要：{summary}")
        lines.append("")
    return "\n".join(lines)


def _format_image_results(result: dict) -> str:
    """把 image 搜索结果格式化为可读文本。"""
    image_results = result.get("ImageResults") or []
    total = result.get("ResultCount", len(image_results))
    lines = [f"豆包联网搜索（image）结果，共 {total} 条：", ""]
    if not image_results:
        lines.append("（无结果）")
        return "\n".join(lines)

    for idx, item in enumerate(image_results, 1):
        if not isinstance(item, dict):
            continue
        title = item.get("Title") or "（无标题）"
        site = item.get("SiteName") or ""
        page_url = item.get("Url") or ""
        image = item.get("Image") or {}
        img_url = image.get("Url") if isinstance(image, dict) else ""
        shape = image.get("Shape") if isinstance(image, dict) else ""
        width = image.get("Width") if isinstance(image, dict) else None
        height = image.get("Height") if isinstance(image, dict) else None
        lines.append(f"{idx}. {title}")
        if site:
            lines.append(f"   站点：{site}")
        if img_url:
            lines.append(f"   图片：{img_url}")
        if width or height or shape:
            lines.append(f"   规格：{width}x{height} {shape}".rstrip())
        if page_url:
            lines.append(f"   落地页：{page_url}")
        lines.append("")
    return "\n".join(lines)


async def web_search(
    query: str,
    search_type: str = "web",
    count: int = DEFAULT_COUNT,
    need_content: bool = False,
    need_url: bool = True,
    sites: Optional[str] = None,
    block_hosts: Optional[str] = None,
    auth_info_level: int = 0,
    time_range: Optional[str] = None,
    query_rewrite: bool = False,
    content_formats: str = "text",
    industry: Optional[str] = None,
    need_summary: bool = True,
    image_width_min: Optional[int] = None,
    image_height_min: Optional[int] = None,
    image_width_max: Optional[int] = None,
    image_height_max: Optional[int] = None,
    image_shapes: Optional[list[str]] = None,
) -> ToolResponse:
    """联网搜索工具（豆包搜索 Custom 版），用于获取外部/最新资料。

    Args:
        query: 搜索词，1~100 个字符（必填）。
        search_type: 搜索类型，``web``（网页）或 ``image``（图片）。
        count: 返回条数；web 最多 50，默认 10；image 最多 5。
        need_content: web 专用，是否仅返回有正文的结果。
        need_url: web 专用，是否仅返回原文链接的结果。
        sites: web 专用，指定站点范围，多个用 ``|`` 分隔，最多 20 个。
        block_hosts: web 专用，屏蔽站点，多个用 ``|`` 分隔，最多 5 个。
        auth_info_level: web 专用，1 表示仅返回「非常权威」结果，默认 0。
        time_range: web 专用，发文时间范围，如 ``OneDay`` / ``OneWeek`` /
            ``OneMonth`` / ``OneYear`` 或 ``YYYY-MM-DD..YYYY-MM-DD``。
        query_rewrite: 是否开启 Query 改写（会增加耗时）。
        content_formats: web 专用，正文格式，``text`` 或 ``markdown``。
        industry: web 专用，行业搜索，``finance`` / ``game`` / ``gov``。
        need_summary: web 专用，是否返回相关摘要 Summary（推荐用于大模型场景），默认 True。
        image_width_min / image_height_min / image_width_max /
        image_height_max: image 专用，图片尺寸过滤。
        image_shapes: image 专用，允许的形状，取值「横长方形」「竖长方形」「方形」。

    Returns:
        ``ToolResponse``：包含格式化后的搜索结果文本，或可读的错误说明。
    """

    def _err(text: str) -> ToolResponse:
        return ToolResponse(content=[TextBlock(type="text", text=text)])

    q = (query or "").strip()
    if not q:
        return _err("联网搜索失败：query 不能为空。")
    if len(q) > 100:
        q = q[:100]

    st = (search_type or "web").strip().lower()
    if st not in ("web", "image"):
        return _err(f"联网搜索失败：不支持的 search_type '{search_type}'，仅支持 web / image。")

    config = load_search_config()
    if not config["api_key"]:
        return _err(
            "联网搜索未配置 API Key。请在配置文件 "
            f"{config['config_path']} 的 \"api_key\" 字段填写豆包搜索 API Key"
            "（或设置环境变量 DOUBAO_SEARCH_API_KEY）。"
        )

    if st == "web":
        if count < 1:
            count = DEFAULT_COUNT
        count = min(count, 50)
        body = _build_web_body(
            q, count, need_content, need_url, sites, block_hosts,
            auth_info_level, time_range, query_rewrite, content_formats,
            industry, need_summary,
        )
    else:
        if count < 1:
            count = IMAGE_MAX_COUNT
        body = _build_image_body(
            q, count, query_rewrite,
            image_width_min, image_height_min, image_width_max,
            image_height_max, image_shapes,
        )

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config["timeout"]) as client:
            resp = await client.post(config["url"], headers=headers, json=body)
    except Exception as e:
        logger.exception("联网搜索请求异常")
        return _err(f"联网搜索请求失败：{e}")

    if resp.status_code != 200:
        return _err(
            f"联网搜索接口返回 HTTP {resp.status_code}：{resp.text[:500]}"
        )

    try:
        payload = resp.json()
    except Exception as e:
        logger.exception("联网搜索响应解析失败")
        return _err(f"联网搜索响应解析失败：{e}；响应内容：{resp.text[:500]}")

    meta = payload.get("ResponseMetadata") or {}
    error = meta.get("Error")
    if error:
        return _err(
            f"联网搜索接口报错：{error.get('Code')} {error.get('Message')}"
        )

    result = payload.get("Result")
    if not result:
        return _err("联网搜索无结果（Result 为空）。")

    if st == "web":
        text = _format_web_results(result)
    else:
        text = _format_image_results(result)
    return ToolResponse(content=[TextBlock(type="text", text=text)])
