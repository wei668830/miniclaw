# -*- coding: utf-8 -*-
"""Build role snapshot + refs from Playwright aria_snapshot."""

import re
from typing import Any

INTERACTIVE_ROLES = frozenset(
    {
        "button",
        "link",
        "textbox",
        "checkbox",
        "radio",
        "combobox",
        "listbox",
        "menuitem",
        "menuitemcheckbox",
        "menuitemradio",
        "option",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "treeitem",
    },
)

CONTENT_ROLES = frozenset(
    {
        "heading",
        "cell",
        "gridcell",
        "columnheader",
        "rowheader",
        "listitem",
        "article",
        "region",
        "main",
        "navigation",
    },
)

STRUCTURAL_ROLES = frozenset(
    {
        "generic",
        "group",
        "list",
        "table",
        "row",
        "rowgroup",
        "grid",
        "treegrid",
        "menu",
        "menubar",
        "toolbar",
        "tablist",
        "tree",
        "directory",
        "document",
        "application",
        "presentation",
        "none",
    },
)


def _get_indent_level(line: str) -> int:
    """根据行首缩进空格数推算快照树中的层级（每 2 个空格为 1 级）。

    :param line: aria 快照中的一行文本
    :return: 缩进层级（整数）
    """
    m = re.match(r"^(\s*)", line)
    return int(len(m.group(1)) / 2) if m else 0


def _create_tracker() -> dict[str, Any]:
    """创建跟踪各「角色:名称」重复次数的状态跟踪器。

    :return: 含 get_next_index / track_ref / get_duplicate_keys / get_key
        四个回调的字典
    """
    counts: dict[str, int] = {}
    refs_by_key: dict[str, list[str]] = {}

    def get_key(role: str, name: str | None) -> str:
        """拼接「角色:名称」作为唯一键。"""
        return f"{role}:{name or ''}"

    def get_next_index(role: str, name: str | None) -> int:
        """返回并自增该键的出现序号（从 0 开始）。"""
        key = get_key(role, name)
        current = counts.get(key, 0)
        counts[key] = current + 1
        return current

    def track_ref(role: str, name: str | None, ref: str) -> None:
        """记录某个键关联的 ref。"""
        key = get_key(role, name)
        refs_by_key.setdefault(key, []).append(ref)

    def get_duplicate_keys() -> set[str]:
        """返回出现次数大于 1 的键集合。"""
        return {k for k, refs in refs_by_key.items() if len(refs) > 1}

    return {
        "get_next_index": get_next_index,
        "track_ref": track_ref,
        "get_duplicate_keys": get_duplicate_keys,
        "get_key": get_key,
    }


def _remove_nth_from_non_duplicates(
    refs: dict[str, dict],
    tracker: dict,
) -> None:
    """清除未重复元素上的 ``nth`` 字段（仅重复元素才需要 nth 区分）。

    :param refs: ref -> 元素信息 的映射，原地修改
    :param tracker: ``_create_tracker`` 返回的状态跟踪器
    """
    dup_keys = tracker["get_duplicate_keys"]()
    for _, data in list(refs.items()):
        key = tracker["get_key"](data["role"], data.get("name"))
        if key not in dup_keys and "nth" in data:
            del data["nth"]


def _compact_tree(tree: str) -> str:
    """移除不含 ref/文本、且子树中也无 ref 的纯结构行，压缩快照。

    :param tree: 原始快照文本
    :return: 压缩后的快照文本
    """
    lines = tree.split("\n")
    result = []
    for i, line in enumerate(lines):
        if "[ref=" in line:
            result.append(line)
            continue
        if ":" in line and not line.rstrip().endswith(":"):
            result.append(line)
            continue
        current_indent = _get_indent_level(line)
        has_relevant = False
        for j in range(i + 1, len(lines)):
            if _get_indent_level(lines[j]) <= current_indent:
                break
            if "[ref=" in lines[j]:
                has_relevant = True
                break
        if has_relevant:
            result.append(line)
    return "\n".join(result)


def _process_line(  # pylint: disable=too-many-return-statements
    line: str,
    refs: dict[str, dict],
    options: dict[str, Any],
    tracker: dict,
    next_ref: Any,
) -> str | None:
    """处理单行快照：按选项过滤，并为交互/内容元素分配 ref，返回增强后的行。

    :param line: 快照单行文本
    :param refs: ref -> 元素信息 的映射，命中时写入
    :param options: 含 interactive / compact / maxDepth 的选项
    :param tracker: 状态跟踪器
    :param next_ref: 生成下一个 ref 的回调
    :return: 增强后的行文本；被过滤时返回 None
    """
    depth = _get_indent_level(line)
    max_depth_val = options.get("maxDepth")
    if max_depth_val is not None and depth > max_depth_val:
        return None

    m = re.match(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$', line)
    if not m:
        return None if options.get("interactive") else line

    prefix, role_raw, name, suffix = m.groups()
    if role_raw.startswith("/"):
        return None if options.get("interactive") else line

    role = role_raw.lower()
    is_interactive = role in INTERACTIVE_ROLES
    is_content = role in CONTENT_ROLES
    is_structural = role in STRUCTURAL_ROLES

    if options.get("interactive") and not is_interactive:
        return None
    if options.get("compact") and is_structural and not name:
        return None

    should_have_ref = is_interactive or (is_content and name)
    if not should_have_ref:
        return line

    ref = next_ref()
    nth = tracker["get_next_index"](role, name)
    tracker["track_ref"](role, name, ref)
    refs[ref] = {"role": role, "name": name, "nth": nth}

    enhanced = f"{prefix}{role_raw}"
    if name:
        enhanced += f' "{name}"'
    enhanced += f" [ref={ref}]"
    if nth is not None and nth > 0:
        enhanced += f" [nth={nth}]"
    if suffix:
        enhanced += suffix
    return enhanced


def build_role_snapshot_from_aria(
    aria_snapshot: str,
    *,
    interactive: bool = False,
    compact: bool = False,
    max_depth: int | None = None,
) -> tuple[str, dict[str, dict]]:
    """Build snapshot + refs from Playwright locator.aria_snapshot() output."""
    options = {
        "interactive": interactive,
        "compact": compact,
        "maxDepth": max_depth,
    }
    lines = aria_snapshot.split("\n")
    refs: dict[str, dict] = {}
    tracker = _create_tracker()
    counter = [0]

    def next_ref() -> str:
        """生成下一个递增的元素引用标识（如 ``e1``、``e2``）。

        :return: 形如 ``e{n}`` 的引用字符串
        """
        counter[0] += 1
        return f"e{counter[0]}"

    if options.get("interactive"):
        result_lines = []
        for line in lines:
            depth = _get_indent_level(line)
            max_d = options.get("maxDepth")
            if max_d is not None and depth > max_d:
                continue
            m = re.match(r'^(\s*-\s*)(\w+)(?:\s+"([^"]*)")?(.*)$', line)
            if not m:
                continue
            _, role_raw, name, suffix = m.groups()
            if role_raw.startswith("/"):
                continue
            role = role_raw.lower()
            if role not in INTERACTIVE_ROLES:
                continue
            ref = next_ref()
            nth = tracker["get_next_index"](role, name)
            tracker["track_ref"](role, name, ref)
            refs[ref] = {"role": role, "name": name, "nth": nth}
            enhanced = f"- {role_raw}"
            if name:
                enhanced += f' "{name}"'
            enhanced += f" [ref={ref}]"
            if nth is not None and nth > 0:
                enhanced += f" [nth={nth}]"
            if "[" in suffix:
                enhanced += suffix
            result_lines.append(enhanced)
        _remove_nth_from_non_duplicates(refs, tracker)
        snapshot = "\n".join(result_lines) or "(no interactive elements)"
        return snapshot, refs

    result_lines = []
    for line in lines:
        processed = _process_line(line, refs, options, tracker, next_ref)
        if processed is not None:
            result_lines.append(processed)
    _remove_nth_from_non_duplicates(refs, tracker)
    tree = "\n".join(result_lines) or "(empty)"
    snapshot = _compact_tree(tree) if options.get("compact") else tree
    return snapshot, refs
