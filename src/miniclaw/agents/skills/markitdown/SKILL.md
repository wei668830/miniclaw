---
name: markitdown
description: "当用户需要转换 PDF, WORD, PPTX, XLSX, XLS, HTML, CSV, JSON, XML 格式文件为 MARKDOWN 文件时，使用此技能。触发场景包括提到转换为 MARKDOWN 文档也应使用此技能。"
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "0.1"
---

> **重要:** 所有 `scripts/` 路径均相对于本技能目录。
> 运行方式: `cd {this_skill_dir} && python scripts/...`
> 或使用 `execute_shell_command` 的 `cwd` 参数。

# 转换为 MARKDOWN 文档

## 前置依赖

- **markitdown** (`pip install 'markitdown[pptx,docx,xlsx,xls,pdf]'`): 安装 MarkItDown

## 概述

MarkItDown 是一个轻量级的 Python 工具，用于将各种文件转换为 Markdown 格式，以便在 LLM 和相关文本分析流程中使用。在这方面，它与textract最为相似，但更侧重于保留文档的重要结构和内容（包括标题、列表、表格、链接等）。虽然输出结果通常相当美观且易于阅读，但它主要面向文本分析工具，对于需要高保真度文档转换以供人阅读的用户而言，可能并非最佳选择。

## 快速参考

| 任务     | 方法                                           |
|--------|----------------------------------------------|
| 转换     | `markitdown path-to-file.pdf -o document.md` |

## 用法

### 命令行
`python -m markitdown path-to-file.pdf > document.md`

或者使用-o以下方式指定输出文件：

`python -m markitdown path-to-file.pdf -o document.md`

### Python API

Python API
Python 中的基本用法：
```python
from markitdown import MarkItDown

md = MarkItDown(enable_plugins=False) # Set to True to enable plugins
result = md.convert("test.xlsx")
print(result.text_content)
```
Python中的文档智能转换：
```python
from markitdown import MarkItDown

md = MarkItDown(docintel_endpoint="<document_intelligence_endpoint>")
result = md.convert("test.pdf")
print(result.text_content)
```
要使用大型语言模型进行图像描述（目前仅支持 pptx 和图像文件），请提供llm_client以下信息llm_model：
```python
from markitdown import MarkItDown
from openai import OpenAI

client = OpenAI()
md = MarkItDown(llm_client=client, llm_model="gpt-4o", llm_prompt="optional custom prompt")
result = md.convert("example.jpg")
print(result.text_content)
```

