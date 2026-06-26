# Mini Claw
大模型脚本手架工具

## 特性
* 提供一个交互式的命令行界面，与大模型交互以完成各项工作。
* 对于复杂的任务，可以将其拆分成多个子任务，逐步完成。
* 支持记忆管理，主要是针对超长任务中的上下文压缩以最大限度节省开支。
* 支持办事员模式处理主管交代的任务，并且可以在需要时请求主管提供更多信息。
* 支持无限推进模式，允许大模型自行判断何时需要继续推进任务，直到任务完成。
* 支持软件工程开发的各个环节，包括但不限于需求分析、设计、编码、测试(使用 playwright 进行B/S集成测试)、部署等。
* 支持多个大模型配置，可以即时切换生效。

## 工具列表
* 文件读写
* 文件查找
* `SHELL`命令
* 浏览器操作（基于`playwright`对于设置防火防盗防AI的网站操作不了！）
* 屏幕截图
* 独立进程运行（在后台启动一个完全独立的进程，脱离当前Python程序独立运行。适用于启动 Spring Boot、Node.js、执行yarn/npm 构建等场景。路径支持~表示用户目录。）
* 办事员（办事员处理各项子任务，不允许办事员再召唤办事员要不然你会发现地狱不止十八层！）
* 任务规划者（对于复杂任务进行规划）

## 默认技能列表
* pdf-zh
* docx-zh
* xlsx-zh
* pptx-zh
* docling
* web-search
* markitdown

> 技能默认存放于 `~/.miniclaw/skills` 文件夹路径，第三方的技能请拷贝至该文件夹。
> 启用技能的方式
> cli 模式：`/skill-list` 显示技能列表 `/skill-load <skill-name>,...`  加载技能
> 注意技能加载后不需要卸载（因为技能指引内容在用户对话里），若执行 `/clear` 会清除技能指引的内容

> 大模型的连接方式是基于 `LLM` 抽象类的，默认提供了 `DeepSeek` 的实现，用户也可以根据需要实现自己的 `LLM` 类来连接其他大模型服务。
> LiteLLM 支持的大模型以及连接方式参考文档：https://docs.litellm.ai/docs/providers

## 环境配置
* `python 3.11+`
  * `Windows` 系统建议安装 `miniconda`
  * `Linux` 系统建议安装 `Conda`
* 需要安装 `poetry` 包管理工具
  * `pip install poetry`
* 安装依赖
  * `poetry install`
  * `poetry install --group dev` (安装开发依赖)
* 运行依赖（额外的）
  * `pip install playwright`
  * `playwright install` (安装浏览器)
  * `pip install uvicorn` (安装服务器)
  * `pip install litellm[proxy]` (安装 LiteLLM 代理)

## 运行配置

### 运行配置
* 需要在项目根目录下创建 `.env` 文件，可以直接将 `.env.example` 文件复制一份并重命名为 `.env`，例如：
  * LLM_MODEL=deepseek/deepseek-v4-flash
  * LLM_API_KEY=<your_api_key>
  * LLM_BASE_URL=https://api.deepseek.com
  * CUSTOM_LLM_PROVIDER=openai # 若需要自定义调用大模型的供应商时填写该项，填写该项后 LLM_MODEL=deepseek-v4-flash 此时不需要在大模型名称处指定供应商
* 多个大模型配置：在 `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, `CUSTOM_LLM_PROVIDER` 属性前添加自定义前缀名称，切换时指定该名称。
  * <CUSTOM_NAME>_LLM_MODEL=deepseek/deepseek-v4-flash
  * <CUSTOM_NAME>_LLM_API_KEY=<your_api_key>
  * <CUSTOM_NAME>_LLM_BASE_URL=https://api.deepseek.com
  * <CUSTOM_NAME>_CUSTOM_LLM_PROVIDER=openai # 若需要自定义调用大模型的供应商时填写该项，填写该项后 LLM_MODEL=deepseek-v4-flash 此时不需要在大模型名称处指定供应商
  * 使用方式：
  ```bash
  # 显示大模型配置列表
  miniclaw> /llm
  # 切换大模型配置（不分大小写）
  miniclaw> /llm use <custom_name>
  # 临时设置大模型配置，以冒号分隔，其中 `CUSTOM_LLM_PROVIDER` 为可选项
  miniclaw> /llm set <LLM_MODEL>:<LLM_BASE_URL>:<LLM_API_KEY>[:<CUSTOM_LLM_PROVIDER>]
  ```


### 运行方式
**Windows 系统**

将 `miniclaw.bat` 中的 `python.exe` 路径替换为本机路径
```cmd
@echo off
"C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe" -m miniclaw %*
```

**Linux 系统**

同上

**运行命令**
```bash
# 在 Commander/Power Shell 或者 Shell 中运行 `miniclaw` 命令，进入交互式命令行界面。

miniclaw.bat
```

### CLI 获取帮助
```bash
miniclaw> /help
                                                        可用命令
┏━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ 命令         ┃ 说明                     ┃ 示例                                                                       ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ /help        │ 显示帮助信息             │ /help                                                                      │
│ /llm         │ 显示/切换/设置大模型配置 │ /llm 显示大模型列表*号标记正在使用的大模型配置                             │
│              │                          │ /llm use <model> 切换大模型配置                                            │
│              │                          │ /llm set <model>:<api_url>:<api_key>[:<custom_llm_provider>]               │
│              │                          │ 设置临时大模型配置                                                         │
│ /agent       │ 运行模式切换为代理模式   │ /agent 代理模式下大模型将尽量自动推进任务执行                              │
│ /chat        │ 运行模式切切换为对话模式 │ /chat 对话模式下大模型将采用一问一答的方式                                 │
│ /clear       │ 清除对话上下文           │ /clear                                                                     │
│ /history     │ 历史对话记录             │ /history N 最近N条历史对话记录，若不指定N默认看最后3条记录                 │
│ /memory      │ 记忆缓存                 │ /memory 精简记忆  /memory <记忆缓存> 提取记忆                              │
│ /memory-list │ 记忆缓存列表             │ /memory-list 查看记忆缓存列表(默认最新的前10个记忆)                        │
│              │                          │ /memory-list 20 查看最新的前20个记忆                                       │
│ /skill-list  │ 可用的技能列表           │ /skill-list 扫描 '~/code-agent/skills' 目录下的技能列表                    │
│ /skill-load  │ 加载技能                 │ /skill-load <skill-name>,... 同时加载多个技能以逗号分隔                    │
│ /quit        │ 退出 MiniClaw            │ /quit                                                                      │
└──────────────┴──────────────────────────┴────────────────────────────────────────────────────────────────────────────┘
```


## 调试说明
* 若需要在控制台运行时调试，请将下面的语句在待调试的地方拷贝
  * `import pdb; pdb.set_trace()`

## 测试说明

### 异步测试
* 需要安装 `pytest-asyncio` 包
  * `poetry add --group dev pytest-asyncio`
* 在测试文件中引入 `pytest-asyncio`，并使用 `@pytest.mark.asyncio` 装饰器标记异步测试函数
  ```python
  import pytest
  
  @pytest.mark.asyncio
  async def test_async_function():
      # 测试代码
      pass
  ```