"""账户余额查询（官方接口）。

DeepSeek 提供只读的余额查询接口：``GET {base_url}/user/balance``，
需 ``Authorization: Bearer <API_KEY>``。返回示例：::

    {
      "is_available": true,
      "balance_infos": [
        {"currency": "CNY", "total_balance": "110.00",
         "granted_balance": "10.00", "topped_up_balance": "100.00"}
      ]
    }

由于余额接口**不是**逐次计费/用量接口，本模块只负责「查余额」；
会话级「官方花费」由余额差值（baseline - current）推导，天然包含缓存命中折扣。
"""

from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger


def _to_float(value) -> Optional[float]:
    """将余额字段安全转换为 float，转换失败时返回 None。

    :param value: 待转换的原始值
    :return: 转换后的浮点数，无法解析时为 None
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.opt(exception=True).debug('余额数值解析失败，返回 None')
        return None


async def fetch_balance(base_url: str, api_key: str, timeout: float = 10.0) -> dict:
    """查询账户余额。

    返回统一结构::

        {
          "ok": true/false,
          "is_available": bool | None,
          "currency": "CNY" | "USD" | None,
          "total_balance": float | None,
          "granted_balance": float | None,
          "topped_up_balance": float | None,
          "raw": <原始响应>,
          "error": str | None
        }
    """
    if not base_url or not api_key:
        return {"ok": False, "error": "缺少 base_url 或 api_key"}

    url = base_url.rstrip("/") + "/user/balance"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                url,
                headers={"Accept": "application/json", "Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
    except Exception as e:
        logger.opt(exception=True).debug(f'余额查询失败: {e}')
        return {"ok": False, "error": str(e)}

    infos = data.get("balance_infos") or []
    info = infos[0] if infos else {}
    return {
        "ok": True,
        "is_available": data.get("is_available"),
        "currency": info.get("currency"),
        "total_balance": _to_float(info.get("total_balance")),
        "granted_balance": _to_float(info.get("granted_balance")),
        "topped_up_balance": _to_float(info.get("topped_up_balance")),
        "raw": data,
        "error": None,
    }


__all__ = ["fetch_balance"]
