# Mini Claw
大模型脚本手架工具

## 特性
* 提供命令行交互界面（CLI），与大模型交互以完成各项工作。
* 提供 Web 后端（FastAPI）与桌面应用（Electron + React），支持可视化聊天、会话管理、技能与设置。
* 对于复杂的任务，可以将其拆分成多个子任务，逐步完成。
* 支持记忆管理，主要是针对超长任务中的上下文压缩以最大限度节省开支。
* 支持办事员模式（子代理）处理主管交代的任务，并且可以在需要时请求主管提供更多信息。
* 支持自主推进模式（`agent`），允许大模型自行判断何时需要继续推进任务，直到任务完成；`chat` 模式为一问一答。
* 支持软件工程开发的各个环节，包括但不限于需求分析、设计、编码、测试(使用 playwright 进行B/S集成测试)、部署等。
* 支持多个大模型配置，可以即时切换生效。
* 支持联网搜索（豆包搜索）、屏幕截图、后台独立进程运行等工具。
* 支持**图片理解（多模态视觉）**：UI 可**粘贴/拖拽/选择**图片，CLI 用 `/image <图片路径>` 附加图片文件（需支持视觉的模型，如 `deepseek-flash`）。

## CLI 直接执行 Shell

使用 `/shell <命令>` 在当前进程目录执行系统命令，不调用大模型，也不将输出写入对话上下文。

* Windows：`/shell dir` 查看当前目录，`/shell dir *.md` 查看 Markdown 文档。
* Linux/macOS：`/shell ls` 查看当前目录。
* 输出包含标准输出、错误信息及失败时的退出码，默认超时 60 秒。
* 每次启动独立 Shell，`cd` 不会改变后续命令的工作目录；请仅执行可信命令，删除或修改文件会直接生效。

## 工具列表
* 文件读写：`read_file`、`write_file`、`edit_file`、`append_file`、`tail_file`
* 文件查找：`grep_search`（按内容检索）、`glob_search`（按文件名匹配）
* `SHELL` 命令：`execute_shell_command`
* 浏览器操作：`browser_use`（基于 `playwright`，对设置防火防盗防 AI 的网站操作不了！）
* 屏幕截图：`desktop_screenshot`
* 时间：`get_current_time` / `set_user_timezone`
* 联网搜索：`web_search`（豆包搜索，默认关闭，可用 `/web-search on|off` 切换）
* 独立进程运行：`launch_detached`（在后台启动一个完全独立的进程，脱离当前 Python 程序独立运行。适用于启动 Spring Boot、Node.js、执行 yarn/npm 构建等场景。路径支持 ~ 表示用户目录。）
* 办事员（子任务执行器）：`subtask_executor`（处理各项子任务，子代理默认不允许再召唤子代理）
* 任务规划者：`make_plans`（对复杂任务进行规划）

> 工具的启用/禁用可通过 `LLM_ENABLED_TOOLS`（`*` 表示启用全部）与 `LLM_DISABLED_TOOLS`（逗号分隔）配置；默认示例禁用了 `glob_search,grep_search`。

## 默认技能列表
* pdf-zh
* docx-zh
* xlsx-zh
* pptx-zh
* docling
* web-search
* markitdown

> 技能默认存放于 `~/.miniclaw/skills` 文件夹路径（可用 `MINICLAW_SKILLS_DIR` 覆盖），第三方的技能请拷贝至该文件夹。
> 启用技能的方式
> cli 模式：`/skill-list` 显示技能列表 `/skill-load <skill-name>,...`  加载技能
> ui 模式：在「技能」面板中加载技能
> 注意技能以 `SKILL.md` 全文注入用户对话（不改 system prompt），加载后无需卸载；执行 `/clear` 或新建会话会清除已加载的技能指引内容

> 大模型的连接基于统一抽象 `BaseLLMClient`，默认实现为基于 `LiteLLM` 的 `LiteLLMClient`，通过环境变量即可接入各家大模型；也可以自行实现 `BaseLLMClient` 来连接其他大模型服务。
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
* 桌面应用（`miniclaw ui`）额外需要 `Node.js`（Electron + Vite），进入 `frontend/` 执行 `npm install` 安装前端依赖

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
  # 临时设置大模型配置，多个字段以 $$$ 分隔，其中 `CUSTOM_LLM_PROVIDER` 为可选项
  miniclaw> /llm set <LLM_MODEL>$$$<LLM_BASE_URL>$$$<LLM_API_KEY>[$$$<CUSTOM_LLM_PROVIDER>]
  ```


### 运行方式
统一入口为 `python -m miniclaw`，提供三种子命令：

* `cli`（默认）：交互式命令行界面
* `server`：仅启动 FastAPI 后端
* `ui`：桌面应用（后端 + Electron 前端）

**Windows 系统**

将 `miniclaw.bat` 中的 `python.exe` 路径替换为本机路径
```cmd
@echo off
"C:\Users\zhaowei\miniconda3\envs\miniclaw311\python.exe" -m miniclaw %*
```

**Linux 系统**

编辑 `miniclaw.sh`，将 `PYTHON` 替换为本机解释器路径

**运行命令**
```bash
# 默认进入 CLI 交互模式
miniclaw.bat            # Windows
./miniclaw.sh           # Linux/macOS

# 或直接使用模块入口指定子命令
python -m miniclaw cli      # CLI 交互模式
python -m miniclaw server   # 仅后端（默认 0.0.0.0:8000，可 --host/--port/--no-reload）
python -m miniclaw ui       # 桌面应用（后端默认 7909 + Electron，--dev 开发模式 / --no-build 跳过前端构建）
```

### CLI 获取帮助
在 CLI 中输入 `/help` 可查看全部可用命令。当前命令如下：

| 命令 | 说明 | 示例 |
| --- | --- | --- |
| `/help` | 显示帮助信息 | `/help` |
| `/llm` | 显示/切换/设置大模型配置 | `/llm`；`/llm use <name>`；`/llm set <model>$$$<api_url>$$$<api_key>[$$$<custom_llm_provider>]` |
| `/agent` | 运行模式切换为代理模式 | `/agent`（自动推进任务执行） |
| `/chat` | 运行模式切换为对话模式 | `/chat`（一问一答） |
| `/web-search` | 开启/关闭联网搜索（豆包搜索） | `/web-search`；`/web-search on`；`/web-search off` |
| `/model` | 查看/设置当前模型 | `/model`；`/model <model>` |
| `/api_key` | 查看/设置当前 API KEY | `/api_key`；`/api_key <key>` |
| `/base_url` | 查看/设置当前 Base URL | `/base_url`；`/base_url <url>` |
| `/custom_llm_provider` | 查看/设置自定义模型供应商 | `/custom_llm_provider`；`/custom_llm_provider <provider>` |
| `/temperature` | 查看/设置温度（0.0~1.0） | `/temperature`；`/temperature 0.7` |
| `/max_token` | 查看/设置最大词元数 | `/max_token`；`/max_token 4096` |
| `/clear` | 清除对话上下文（同时重置已加载技能） | `/clear` |
| `/history` | 历史对话记录 | `/history N`（默认最后 3 条） |
| `/memory` | 记忆缓存 | `/memory` 精简记忆；`/memory <记忆文件名>` 提取记忆 |
| `/memory-list` | 记忆缓存列表 | `/memory-list`；`/memory-list 20` |
| `/context` | 查看上下文 token 占用与阈值状态 | `/context`；`/context shrink`；`/context window <n>`；`/context soft <ratio>`；`/context hard <ratio>`；`/context reserve <n>`；`/context reset` |
| `/cost` | 查看本次对话费用（官方口径） | `/cost` |
| `/balance` | 查询账户余额（官方） | `/balance` |
| `/session-list` | 列出最近的会话 | `/session-list N`（默认 10，`*` 标记当前会话） |
| `/session-load` | 加载指定会话到上下文（不自动接续） | `/session-load <session_id>` |
| `/session-resume` | 恢复并接续执行指定会话 | `/session-resume <session_id>` |
| `/session-export` | 导出指定会话为 Markdown | `/session-export <session_id> [path]` |
| `/skill-list` | 可用的技能列表 | `/skill-list`（扫描 `~/.miniclaw/skills`） |
| `/skill-load` | 加载技能 | `/skill-load <skill-name>,...` |
| `/image` | 附加图片文件（随下一条消息发送） | `/image <图片路径> [更多路径...]`；`/image clear`；`/image list` |
| `/quit` | 退出 MiniClaw | `/quit` |


## Web 后端与桌面应用

除 CLI 外，MiniClaw 还提供 Web 后端与桌面应用：

* **Web 后端**（`python -m miniclaw server`）：基于 FastAPI，暴露会话 / 流式聊天（SSE）/ 技能 / 配置 / 上下文等 REST 接口（路由见 `src/miniclaw/app/routers`）。除 `/api/health`、`/api/version` 外，接口通过 `Authorization: Bearer <MINICLAW_API_TOKEN>` 鉴权（未配置该环境变量时视为开发模式放行）。
* **桌面应用**（`python -m miniclaw ui`）：后端 + Electron 前端，一键启动，后端默认 `127.0.0.1:7909`（可用 `--port` 或 `MINICLAW_UI_PORT` 覆盖，端口占用时自动回退空闲端口）。
  * 开发模式：`python -m miniclaw ui --dev`（后端 `--reload` + Vite devServer）；`--no-build` 可跳过前端构建（假定 `dist/` 已存在）。
  * 前端工程位于 `frontend/`（Electron + React + TypeScript + Vite），首次使用需 `cd frontend && npm install`。
  * 关闭窗口即同步销毁后端进程；仅允许单实例运行。

## 联网搜索（豆包搜索）

* 默认关闭，CLI 中用 `/web-search on|off` 动态开关。
* API Key 推荐写入配置文件（默认 `<WORKING_DIR>/config/web_search.json`，即 `~/.miniclaw/config/web_search.json`，文件不存在时自动生成模板），也可用 `DOUBAO_SEARCH_API_KEY` / `DOUBAO_SEARCH_URL` / `DOUBAO_SEARCH_TIMEOUT` 等环境变量覆盖（详见 `.env.example`）。


## 图片理解（Vision）

支持在对话中使用图片（多模态）：

* **UI（桌面应用）**：在输入框**粘贴**剪贴板图片、**拖拽**图片、或点「🖼 图片」**选择文件**（可多张）；随消息交给模型；缩略图/消息中的图片**点击可放大预览**（灯箱，Esc 或点空白关闭）。
* **CLI**：`/image <图片路径> [更多路径...]` 附加图片（仅图片**文件**，格式 png/jpg/jpeg/gif/webp），随**下一条消息**发送；`/image clear` 清空、`/image list` 查看。

要点：

* 需要**支持视觉的模型**（如 `deepseek-flash`）；非视觉模型发图会收到明确提示。
* **多轮策略**：仅**当前轮**的图片会发送给模型（历史轮图片不发送，但会话文件保留、界面仍可回看/放大）。
* 图片落盘于 `~/.miniclaw/multimodal/uploads/<session_id>/`，历史只存**路径引用**（不内嵌 base64）；请求时转成 base64 `data:` URL，**单轮内只编码一次并缓存、轮结束即清理**。
* 受 DeepSeek 限制：单图 ≤32 MiB、请求体 ≤48 MiB、单请求 ≤600 张。
* 若经 **litellm** 接入 DeepSeek：含图请求会自动改走 **OpenAI 兼容路径**（`custom_llm_provider=openai`），因为 litellm 内置的 `deepseek/` provider 会丢弃图片内容。

## 会话推进机制（agent 模式）
* 会话推进采用**提示词驱动自主执行（agent 模式）**，不再使用裁判续跑逻辑。
  * `agent` 模式下自动注入自主执行提示词，模型在还能通过工具取得进展时持续执行，仅在任务完成或确实被阻塞时停止。
  * 安全网：单轮对话连续工具调用超过 `MINICLAW_MAX_TOOL_ITERATIONS`（默认 100000，近乎不限制）会暂停并提示；子代理嵌套层级超过 `MINICLAW_MAX_SUBAGENT_LAYER`（默认 1，即子代理不再派生子代理）会被拒绝执行。
  * `chat` 模式仍为一问一答，不自主推进。
  * `CHAT_ADVANCE_SYSTEM_PROMPT` / `CHAT_ADVANCE_USER_PROMPT` 已废弃（deprecated），已从示例配置中移除，相关函数仅为兼容保留、不再使用。

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
| `MINICLAW_MAX_TOOL_ITERATIONS` | `100000` | 单轮对话最大连续工具调用次数（安全网，近乎不限制） |
| `MINICLAW_MAX_SUBAGENT_LAYER` | `1` | 子代理最大嵌套层级（默认 1，即子代理不再派生子代理） |
| `MINICLAW_KEEP_REASONING_CONTENT` | 自动识别 | 思维链回传开关：留空按模型自动识别（DeepSeek 保留、其余剥离）；`1/0` 强制保留/剥离 |

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