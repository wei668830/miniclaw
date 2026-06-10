import re
import uuid
from datetime import datetime
from pathlib import Path

import yaml


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


def extract_yaml_frontmatter(content):
    """提取 SKILL.md 文件开头的 YAML frontmatter"""
    # 匹配 --- 开头和结尾的 YAML 内容
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    if match:
        yaml_content = match.group(1)
        try:
            return yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            return None
    return None


if __name__ == "__main__":
    skills_dir = Path("~/.miniclaw/skills").expanduser().resolve()
    src_skills_dir = Path(__file__).parent.parent / "agents" / "skills"
    print(src_skills_dir)
    # if not os.path.exists(skills_dir):
    #     shutil.copytree(skills_dir, skills_dir, dirs_exist_ok=True)