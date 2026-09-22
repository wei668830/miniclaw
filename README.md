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


## 会话推进机制（agent 模式）
* 会话推进采用**提示词驱动自主执行（agent 模式）**，不再使用裁判续跑逻辑。
  * `agent` 模式下自动注入自主执行提示词，模型在还能通过工具取得进展时持续执行，仅在任务完成或确实被阻塞时停止。
  * 安全网：单轮对话连续工具调用超过 `MINICLAW_MAX_TOOL_ITERATIONS`（默认 50）会暂停并提示；子代理嵌套层级超过 `MINICLAW_MAX_SUBAGENT_LAYER`（默认 5）会被拒绝执行。
  * `chat` 模式仍为一问一答，不自主推进。
  * `CHAT_ADVANCE_SYSTEM_PROMPT` / `CHAT_ADVANCE_USER_PROMPT` 已废弃（deprecated），保留仅为兼容。

## 记忆（Memory）与上下文溢出恢复

当整个会话上下文（`self.messages`）接近模型上下文窗口限度时，MiniClaw 会通过记忆机制自动精简并重建上下文，最大限度保证任务不中断。

### 触发阈值
* 软阈值：`MINICLAW_CONTEXT_WINDOW * MINICLAW_CONTEXT_SOFT_RATIO`（默认 128000 × 0.6），超过则对较早消息做轻量裁剪。
* 硬阈值：`MINICLAW_CONTEXT_WINDOW * MINICLAW_CONTEXT_HARD_RATIO`（默认 128000 × 0.85，且不超过 `window - MINICLAW_CONTEXT_RESERVE_TOKENS`），超过则强制精简记忆并重建上下文。
* 当 LLM 返回上下文超限错误时，会强制精简并重建后重试，最多 `MINICLAW_CONTEXT_RETRY_MAX`（默认 2）次。

### 常用命令
* `/memory`：立即精简当前上下文为结构化记忆，并在下一轮输入时重建上下文继续执行。
* `/memory <file>`：切换记忆缓存文件（原有语义不变）。
* `/memory-list`：列出记忆缓存文件（原有语义不变）。
* `/context`：查看当前 token 估算占用、预算 soft/hard/window、消息条数与会话历史统计。
* `/context shrink`：立即对当前上下文裁剪较早的工具输出（不调用 LLM）。

### 记忆文件 frontmatter
记忆文件以 YAML frontmatter 开头，字段包括：
* `type`：固定为 `memory`。
* `created_at`：生成时间。
* `session_id`：所属会话 ID。
* `message_range`：被精简的原消息索引范围 `[start, end]`。
* `token_before` / `token_after`：精简前后 token 估算。
* `chunk_count`：分块数量。
* `active_plan`：活跃计划文件路径（若有）。
* `keep_recent`：保留的最近轮次数。

### 原始会话历史（外部记忆）
* `~/.miniclaw/memory/raw/<session_id>.jsonl`：append-only 的单行 JSON 会话历史，与内存窗口解耦。
* 任何时候都能从该文件还原完整原始历史（条数与内存一致），用于重新精简或人工核对。

### 任务锚点与恢复流程
* 复杂任务通过 `make_plans` 生成计划文件，计划文件包含 YAML frontmatter 与固定的「## 进度摘要」章节，未完成步骤以 `[ ]` 标注。
* 活跃计划路径登记于 `~/.miniclaw/state/active_plan.json`，记忆精简时会保留该锚点。
* 上下文重建后会自动注入「记忆摘要 + 活跃计划路径 + 继续执行指令 + 最近对话原文」，驱动模型从 `[ ]` 未完成步骤继续执行。

### 会话元数据与异常退出恢复
* `~/.miniclaw/state/current_session.json`：记录当前会话 ID、历史文件、记忆文件、活跃计划、`clean_shutdown` 等元数据。
* 正常退出（`/quit`、`Ctrl-C`、EOF）会置 `clean_shutdown=true`；若上次为异常退出（`false`），启动时会给出恢复提示。
* 会话恢复命令：
  * `/session-list [N]`：列出最近 N 个会话（默认 10，`*` 标记当前会话）。
  * `/session-load <session_id>`：加载指定会话到上下文（不自动接续）。
  * `/session-resume <session_id>`：加载后自动精简并接续执行未完成步骤。
  * `/session-export <session_id> [path]`：导出会话为可读 Markdown。

### 可调环境变量
| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MINICLAW_CONTEXT_WINDOW` | `128000` | 模型上下文窗口 token 数（保守值） |
| `MINICLAW_CONTEXT_SOFT_RATIO` | `0.6` | 软阈值比例，超过则自动精简 |
| `MINICLAW_CONTEXT_HARD_RATIO` | `0.85` | 硬阈值比例，超过则强制精简 |
| `MINICLAW_CONTEXT_RESERVE_TOKENS` | `4096` | 为模型回复预留的 token |
| `MINICLAW_CONTEXT_DEBUG` | `false` | 是否打印预算判定调试日志 |
| `MINICLAW_CONTEXT_RETRY_MAX` | `2` | 上下文超限后的最大重试次数 |
| `MINICLAW_TOOL_OUTPUT_MAX_TOKENS` | `4000` | 单条工具结果超过则落盘裁剪 |
| `MINICLAW_TOOL_OUTPUT_DIR` | `~/.miniclaw/multimodal/tool_outputs` | 工具输出全文落盘目录 |
| `MINICLAW_MEMORY_RAW_DIR` | `~/.miniclaw/memory/raw` | JSONL 原始历史目录 |
| `MINICLAW_MEMORY_KEEP_RECENT` | `6` | 精简时保留的最近轮次数（tail） |
| `MINICLAW_MEMORY_CHUNK_TOKENS` | `20000` | 分块 map-reduce 的单块 token 上限 |
| `MINICLAW_STATE_DIR` | `~/.miniclaw/state` | 会话状态目录 |
| `CHAT_AGENT_AUTONOMY_PROMPT` | 内置默认文案 | agent 模式自主执行提示词 |
| `CHAT_CLERK_AUTONOMY_PROMPT` | 内置默认文案 | 子代理自主执行提示词 |
| `CHAT_TASK_DONE_TOKEN` | `【TASK_DONE】` | 任务完成哨兵标记 |
| `MINICLAW_MAX_TOOL_ITERATIONS` | `50` | 单轮对话最大连续工具调用次数（安全网） |
| `MINICLAW_MAX_SUBAGENT_LAYER` | `5` | 子代理最大嵌套层级 |

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