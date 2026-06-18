---
name: web-search
description: "当用户需要通过搜索引擎收集公开网页信息、定位资料来源、抓取页面内容、整理为 Markdown/HTML/JSON 等结构化文档时，使用此技能。适用于资料调研、公开文本汇总、目录生成、搜索页结果解析和网页内容落地保存。"
license: Proprietary. LICENSE.txt has complete terms
metadata:
    builtin_skill_version: "0.1"
---

> **重要:** 所有临时脚本建议放在当前工作目录的 `.miniclaw/` 文件夹中。
> 使用网络搜索时优先通过 `execute_shell_command` 运行脚本或命令完成。
> 若搜索页需要浏览器渲染或反爬校验，可使用浏览器工具打开搜索结果页并读取页面快照。

# Web Search 网络信息收集方法

## 概述

本技能用于将“搜索引擎检索 -> 结果页定位 -> 目标页面抓取 -> 内容解析 -> 结构化输出”的流程标准化。典型场景包括：从 Bing 检索公开资料，提取可用来源链接，访问目标网页，解析标题、作者、正文、来源 URL 等字段，最后生成 HTML、Markdown、JSON 或其他文档。

**主要特性:**
- 使用 `https://cn.bing.com/` 执行公开网页检索
- 保存搜索结果页作为溯源材料
- 从搜索结果中筛选高质量来源页面
- 批量抓取目标页面并提取正文内容
- 输出带目录、搜索功能和来源链接的 HTML 页面
- 支持同时保存中间 JSON，便于后续复用和校验

## 适用场景

- 收集公开古诗文、百科资料、公开文档、网页文章等内容
- 将搜索到的资料整理为本地 HTML/Markdown 文档
- 为页面生成目录、搜索框、来源链接
- 对多个网页进行批量抓取、去重、清洗和归档
- 需要保留搜索过程和来源证据的资料整理任务

## 快速参考

| 任务 | 方法 |
| --- | --- |
| 搜索 Bing | 请求 `https://cn.bing.com/search?q={关键词}`，必要时使用 `control_browser` 打开搜索页 |
| 保存搜索页 | 将搜索结果 HTML 保存到 `.miniclaw/search_result.html` |
| 浏览器确认结果 | 使用 `control_browser` 的 `open`、`snapshot` 获取真实搜索结果标题、摘要和 URL |
| 提取结果链接 | 用正则、HTML 解析器或浏览器快照提取搜索结果中的 URL |
| 抓取目标页 | 使用 `urllib.request` 或浏览器工具访问目标页面 |
| 结构化内容 | 提取标题、作者、正文、来源 URL 等字段 |
| 输出文档 | 写入 HTML/Markdown/JSON 文件 |

## 标准流程

### 1. 明确检索关键词

根据用户目标构造搜索关键词，优先包含主题词、全集/目录/原文/官方来源等限定词。

示例：
```text
唐诗三百首 全集
唐诗三百首 原文 古诗文网
公开政策 文件 PDF
```

### 2. 使用 Bing 获取搜索结果

通过 Python 请求 Bing 搜索页，并保存 HTML 作为检索记录。

```python
import urllib.parse
import urllib.request
from pathlib import Path

work = Path('.miniclaw')
work.mkdir(exist_ok=True)

query = urllib.parse.quote('唐诗三百首 全集')
url = f'https://cn.bing.com/search?q={query}'
request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
html = urllib.request.urlopen(request, timeout=30).read().decode('utf-8', 'ignore')

(work / 'bing_result.html').write_text(html, encoding='utf-8')
```

### 3. 使用 control_browser 确认搜索结果

当 Bing 搜索页由 JavaScript 渲染、命令行请求无法稳定提取链接，或需要确认真实排名与摘要时，使用 `control_browser` 打开搜索页并读取页面快照。

推荐操作顺序：
1. `control_browser.start`: 启动浏览器。
2. `control_browser.open`: 打开 Bing 搜索 URL。
3. `control_browser.snapshot`: 获取页面结构化快照。
4. 从快照中读取搜索结果标题、摘要、URL，选择可信来源。

示例流程：
```text
control_browser.start(headed=false)
control_browser.open(url="https://cn.bing.com/search?q=唐诗三百首%20全集")
control_browser.snapshot()
```

快照中重点关注：
- 搜索结果标题
- 搜索结果 URL
- 摘要中是否包含目标内容
- 来源站点是否公开、稳定、可信

### 4. 解析搜索结果链接

优先筛选搜索结果中可信、结构稳定、内容完整的公开页面。若普通 HTTP 请求无法稳定解析 Bing 结果，可使用 `control_browser` 打开 Bing 页面并读取快照，直接从快照中获取结果标题、摘要和 URL。

```python
import html
import re

content = Path('.miniclaw/bing_result.html').read_text(encoding='utf-8')
links = re.findall(r'<a href="(https?://[^"]+)"', content)
links = [html.unescape(link) for link in links]
```

### 5. 抓取目标网页内容

对目标站点逐页请求，保存原始页面，便于排查解析问题和保留来源。

```python
import urllib.request
from pathlib import Path

url = 'https://www.example.com/page.html'
request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
page_html = urllib.request.urlopen(request, timeout=30).read().decode('utf-8', 'ignore')

Path('.miniclaw/source_page.html').write_text(page_html, encoding='utf-8')
```

### 6. 清洗并结构化内容

将 HTML 标签、换行、实体字符清理为可用文本。根据目标网页结构提取标题、作者、正文、来源 URL 等字段。

```python
import html
import re


def clean_text(value):
    value = re.sub(r'<br\s*/?>', '\n', value, flags=re.I)
    value = re.sub(r'<.*?>', '', value, flags=re.S)
    value = html.unescape(value)
    value = re.sub(r'\r', '', value)
    value = re.sub(r'\n\s*\n+', '\n', value)
    return value.strip()
```

### 7. 输出结构化文档

输出时建议同时生成：
- `JSON`: 保存结构化数据，便于复用
- `HTML`: 面向用户阅读，带目录和搜索功能
- `Markdown`: 面向知识库或二次编辑

HTML 输出应包含：
- 标题和说明
- 目录导航
- 搜索输入框
- 正文卡片/章节
- 来源链接
- 无搜索结果提示

## HTML 搜索功能模板

```html
<input id="searchInput" type="search" placeholder="搜索标题、作者或正文">
<p>当前显示：<span id="count"></span></p>
<div id="emptyTip" style="display:none;">没有找到匹配内容。</div>

<script>
    const items = Array.from(document.querySelectorAll('.item'));
    const searchInput = document.getElementById('searchInput');
    const count = document.getElementById('count');
    const emptyTip = document.getElementById('emptyTip');

    function filterItems() {
        const keyword = searchInput.value.trim().toLowerCase();
        const visible = [];

        items.forEach((item) => {
            const matched = !keyword || item.textContent.toLowerCase().includes(keyword);
            item.style.display = matched ? '' : 'none';
            if (matched) {
                visible.push(item);
            }
        });

        count.textContent = visible.length;
        emptyTip.style.display = visible.length ? 'none' : 'block';
    }

    searchInput.addEventListener('input', filterItems);
    filterItems();
</script>
```

## 推荐脚本结构

```text
.miniclaw/
    collect_web_info.py        # 主采集脚本
    bing_result.html           # Bing 搜索结果页
    source_page.html           # 目标页面原始 HTML
    collected_data.json        # 结构化结果
```

## 命令执行示例

```bash
python .miniclaw/collect_web_info.py
```

在工具中执行时，使用 `execute_shell_command`，并将 `cwd` 设置为用户当前工作目录。

## 质量检查

- 检查抓取数量是否符合预期
- 检查标题、作者、正文是否为空
- 检查是否有重复 URL 或重复条目
- 检查 HTML 是否可在浏览器中打开
- 检查搜索框是否能按标题、作者、正文过滤
- 检查每条内容是否保留来源链接

## 注意事项

- 仅收集公开网页中可访问的信息，避免绕过登录、付费墙或访问控制。
- 对来源页面结构要做容错处理，避免单个页面失败导致整体任务中断。
- 请求网络时设置合理 `User-Agent`、超时时间和重试策略。
- 批量抓取时建议加入短暂间隔，避免对目标网站造成压力。
- 对版权不确定的现代内容，应优先摘要、引用来源或征得用户确认。
- 若 Bing 返回内容不易解析，使用浏览器工具查看搜索结果快照，再提取可信链接。

## 典型案例

用户要求：“使用 https://cn.bing.com/ 收集唐诗三百首，并输出至 tangsong.html”。

执行方式：
1. 使用 Bing 搜索“唐诗三百首 全集”。
2. 从搜索结果中选择公开古诗文页面作为来源。
3. 抓取目录页，提取每首诗的详情页链接。
4. 批量访问详情页，解析标题、作者、正文和来源 URL。
5. 保存中间 JSON。
6. 生成 `tangsong.html`，包含目录、全文搜索、正文和来源链接。
