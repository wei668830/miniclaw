---
name: docling
description: "当用户需要转换 PDF、Word、PPT、Excel、HTML、图像等格式文件为 Markdown 文档时，使用此技能。Docling 支持本地文件和网络 URL 来源，能够高质量地保留文档结构、表格、图像等内容。"
license: Proprietary. LICENSE.txt has complete terms
metadata:
  builtin_skill_version: "0.1"
---

> **重要:** 所有 `scripts/` 路径均相对于本技能目录。
> 运行方式: `cd {this_skill_dir} && python scripts/...`
> 或使用 `execute_shell_command` 的 `cwd` 参数。

# Docling 文档转换工具

## 前置依赖

- **docling** (`pip install docling`): 安装 Docling 文档转换库

## 概述

Docling 是一个强大的文档解析和转换工具，专为 AI 应用场景设计。它能够将 PDF、Office 文档（Word、Excel、PowerPoint）、HTML、图像等多种格式高质量地转换为 Markdown 格式。Docling 不仅保留文档的结构信息（标题、列表、表格），还能处理复杂的布局和格式，非常适合用于文档分析、知识提取和 RAG（检索增强生成）等场景。

**主要特性:**
- 支持多种文档格式（PDF、DOCX、PPTX、XLSX、HTML、图像等）
- 支持本地文件和网络 URL 来源
- 高质量保留文档结构和内容
- 智能表格识别和转换
- 自动布局分析

## 快速参考

| 任务         | 方法                                                    |
|------------|-------------------------------------------------------|
| 转换本地文件     | `python scripts/converter.py input.pdf output.md`     |
| 转换网络文件     | `python scripts/converter.py https://example.com/doc.pdf output.md` |

## 用法

### 脚本使用

使用 `converter.py` 脚本进行文档转换：

**转换本地文件:**
```bash
python scripts/converter.py document.pdf output.md
python scripts/converter.py report.docx result.md
```

**转换网络文件:**
```bash
python scripts/converter.py https://arxiv.org/pdf/2206.01062 paper.md
```

**参数说明:**
- `source`: 源文件路径或 URL（支持 http:// 和 https://）
- `target`: 目标 Markdown 文件路径（自动创建所需目录）

### Python API

**基本用法:**
```python
from docling.document_converter import DocumentConverter

# 转换本地文件
source = "document.pdf"
converter = DocumentConverter()
doc = converter.convert(source).document
markdown_content = doc.export_to_markdown()

# 保存结果
with open("output.md", "w", encoding="utf-8") as f:
    f.write(markdown_content)
```

**转换网络文件:**
```python
from docling.document_converter import DocumentConverter

# 转换网络 URL
source = "https://arxiv.org/pdf/2408.09869"
converter = DocumentConverter()
doc = converter.convert(source).document
markdown_content = doc.export_to_markdown()

print(markdown_content)
```

**批量转换:**
```python
from docling.document_converter import DocumentConverter

files = ["file1.pdf", "file2.docx", "file3.pptx"]
converter = DocumentConverter()

for file in files:
    doc = converter.convert(file).document
    output_file = file.rsplit(".", 1)[0] + ".md"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(doc.export_to_markdown())
```
