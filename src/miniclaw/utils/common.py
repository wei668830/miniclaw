from datetime import datetime
import uuid
from typing import Optional

def clip(s: str, max_len: int = 30) -> str:
    """Clip a string to a maximum length, adding ellipsis if truncated."""
    return s if len(s) <= max_len else s[:max_len] + '...'





def dt_uuid(include_microseconds: bool = False) -> str:
    """
    生成时间戳 + UUID4前7位的唯一ID

    Args:
        include_microseconds: 是否包含微秒（默认False，精确到秒）

    Returns:
        唯一ID字符串
    """
    if include_microseconds:
        # 精确到微秒：YYYYMMDDHHMMSSffffff
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
    else:
        # 精确到秒：YYYYMMDDHHMMSS
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')

    uuid_part = uuid.uuid4().hex[:7]
    return f"{timestamp}-{uuid_part}"

