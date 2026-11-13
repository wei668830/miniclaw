# MiniClaw 开发入口指南

> 本文件是工程的**入口级参考**：快速了解开发环境、工程结构、主要技术与核心模块，便于下一次开发时迅速定位资料、上手改动。
> 详细内容见 [`README.md`](./README.md) 与 [`design/`](./design) 目录。

---

## 一、项目简介

MiniClaw 是一个**大模型（LLM）脚本手架工具**：以「大模型 + 工具调用」为核心，提供
交互式 CLI、Web 后端（FastAPI）与桌面应用（Electron）三种形态。

- 核心能力：多轮工具调用、子代理（办事员）、任务规划、记忆/上下文压缩、技能（Skill）对话式加载、多模型配置切换。
- 运行模式：`agent`（自主推进，工具开启）与 `chat`（一问一答，工具关闭）。
- 三种运行形态：
  - **CLI**：交互式命令行（默认形态）。
  - **Server**：纯 FastAPI 后端。
  - **UI**：桌面应用 = 后端(FastAPI) + Electron 前端，一键拉起。

---

## 二、开发环境

| 项 | 要求 / 说明 |
| --- | --- |
| Python | `>=3.11,<4.0`（Windows 建议 miniconda，Linux 建议 conda） |
| 包管理 | **uv**（独立安装：`winget install --id=astral-sh.uv` 或 `irm https://astral.sh/uv/install.ps1 \| iex`；也可 `pip install uv`；已替代 Poetry） |
| Node.js | 前端构建/桌面应用需要（Electron + Vite） |
| 依赖安装 | `uv sync`（默认含 `dev` 依赖组；只装主依赖用 `uv sync --no-dev`） |
| 额外运行依赖 | `pip install playwright` + `playwright install`；`pip install uvicorn`；`pip install litellm[proxy]`（可选代理） |
| 配置文件 | 项目根目录 `.env`（由 `.env.example` 复制而来，`load_dotenv` 启动加载） |
| 工作目录 | 默认 `~/.miniclaw`（`MINICLAW_WORKING_DIR` 可覆盖）：技能、记忆、状态、日志、工具落盘 |

**关键路径（运行时，默认 `~/.miniclaw`）**

- `skills/`：技能目录（内置技能随包发布，第三方技能拷贝到此处）。
- `memory/raw/<session_id>.jsonl`：append-only 原始会话历史。
- `state/`：`current_session.json`、`active_plan.json`、`miniclaw-ui.lock` 等会话/单实例状态。
- `multimodal/tool_outputs/`：超长工具结果全文落盘目录。
- `logs/`：日志（`LOG_DIR`）。

**运行方式**

```bash
# 统一入口（Windows 用 miniclaw.bat / Linux、macOS、WSL 用 miniclaw.sh）
# 解释器解析顺序：MINICLAW_PYTHON 环境变量 > 工程内 .venv（uv 管理）> conda 环境 > PATH 上的 python
python -m miniclaw            # 默认进入 CLI 交互模式
python -m miniclaw cli        # CLI 交互模式
python -m miniclaw server     # 仅启动 FastAPI 后端（默认 0.0.0.0:8000，可 --host/--port/--no-reload）
python -m miniclaw ui         # 桌面应用：后端(默认 7909) + Electron（--dev 开发模式 / --no-build 跳过构建）
```

**依赖管理（uv）与「双份依赖」说明**

- 迁移结论：`pyproject.toml` 已改为 uv 友好结构（dev 依赖放 `[dependency-groups].dev`，国内镜像源放 `[[tool.uv.index]]`），锁文件由 `poetry.lock` 换成 `uv.lock`。
- 常用命令：

```bash
uv sync                          # 按 uv.lock 同步依赖（含 dev 组），首次自动创建 .venv
uv sync --no-dev                 # 只装运行依赖
uv lock --upgrade                # 升级并重算锁文件
uv add <pkg> / uv remove <pkg>   # 增删依赖（自动写回 pyproject.toml + uv.lock）
uv run python -m miniclaw cli    # 用项目环境运行，无需手动激活
uv build                         # 打包 wheel/sdist（构建后端 uv_build）
```

- 构建后端已从 `poetry-core` 换成 `uv_build`：`uv sync` 会把工程自身以 editable 方式装进环境（`miniclaw` 命令、`import miniclaw` 都依赖这一步），旧配置能跑但会额外下载 poetry-core；切换到 `uv_build` 后实测打出的 wheel 文件清单（含内置技能 `agents/skills/**` 等非 py 资源、`entry_points`）与 poetry-core 完全一致。

- **不会重复下载**：uv 使用全局缓存（已迁移到 `D:\uv-cache`，配置见 `%APPDATA%\uv\uv.toml` 的 `cache-dir`），同一个 wheel 只下载一次，`.venv`、conda 环境、其它工程共用。
- **磁盘占用**：`uv sync` 默认在工程根目录建 `.venv`，与 miniconda 的 `miniclaw311` 是两套独立环境（版本也可能不同，lock 取的是最新兼容版本）。`.venv` 逻辑大小约 216 MB，但缓存与工程同在 D 盘，安装走**硬链接**，包文件与缓存共享同一份数据，实际额外占用接近 0（可用 `fsutil hardlink list .venv\Lib\site-packages\rich\__init__.py` 验证存在两条路径）。
- 迁移/更改缓存位置后，已有 `.venv` 里的文件仍是旧方式写入，需要 `uv sync --reinstall` 才会按新缓存重建为硬链接；环境变量 `UV_CACHE_DIR` 优先级高于配置文件（曾经用过的 C 盘旧缓存 `C:\Users\zhaowei\AppData\Local\uv\cache` 已删除，可回收约 911 MB）。
- **想完全不产生第二份环境（直接复用 conda 环境）**：

```bash
set UV_PROJECT_ENVIRONMENT=C:\Users\zhaowei\miniconda3\envs\miniclaw311
uv sync --inexact      # --inexact 必需，避免删除环境里 lock 之外的包
```

  - `uv sync` 会按 lock **精确对齐**该环境（升级/降级 pydantic、aiohttp 等传递依赖）；miniclaw 正在运行时 `site-packages` 里的 `.pyd` 被占用会报 `Access denied`，必须先停进程再同步。
  - `uv sync --active` 只识别 `VIRTUAL_ENV`，conda 环境只能用 `UV_PROJECT_ENVIRONMENT`。
  - 只补装缺失、不动其它包版本：`uv pip install -e . --no-deps`。
- 启动脚本 `miniclaw.bat` / `miniclaw.sh` 已改为优先使用 `.venv`，不存在时回退 conda 环境解释器。

---

## 三、工程结构（核心）

```text
MiniClaw/
├─ pyproject.toml            # 工程定义与依赖（PEP621，uv 管理，构建后端 uv_build）
├─ uv.lock                   # 锁文件（uv，替代原 poetry.lock）
├─ .env.example              # 环境变量模板（复制为 .env 使用）
├─ miniclaw.bat / .sh        # 启动脚本（MINICLAW_PYTHON > .venv > conda > PATH python）
├─ README.md                 # 使用说明（特性/工具/技能/环境与记忆机制）
├─ entrance.md               # 本入口文件
├─ src/miniclaw/             # Python 主工程（核心）
│  ├─ __main__.py            # 统一入口：cli / server / ui 子命令
│  ├─ constant.py            # 全局常量、EnvVarLoader、记忆/上下文默认值、自主执行提示词
│  ├─ agents/                # 大模型与工具核心
│  │  ├─ base_llm_client.py  # LLM 抽象基类 + 返回结构体（LLMResponse/StreamChunk/ToolResponse）
│  │  ├─ llm_configurator.py # 从环境变量归组加载多套模型连接配置
│  │  ├─ llm_tools_manager.py# 内置工具注册/查询/执行、工具调用 JSON 容错
│  │  ├─ providers/          # 具体 LLM 实现（litellm_provider.py）
│  │  ├─ tools/              # 内置工具函数（见第五节）
│  │  └─ skills/             # 内置技能（pdf-zh/docx-zh/xlsx-zh/pptx-zh/docling/web-search/markitdown）
│  ├─ cli/                   # 命令行交互层
│  │  ├─ main.py             # CLI 主入口 cli_run / CommandLineInteraction（会话、斜杠命令、流式主循环）
│  │  ├─ actor.py            # Actor：封裝 LLM 客户端+工具+历史的执行体
│  │  ├─ clerk.py            # Clerk：子任务执行器（子代理，含层级/轮次安全网）
│  │  ├─ planner.py          # Planner：生成/恢复计划文件（make_plans 工具）
│  │  ├─ stream_runner.py    # 统一流式对话执行器（工具分发、渲染）
│  │  ├─ commands.py         # 斜杠命令定义与帮助表
│  │  ├─ console.py          # rich 控制台 / prompt session
│  │  ├─ history_store.py    # 会话历史存取（JSONL）
│  │  ├─ memory.py           # 记忆精简（map-reduce 分块）
│  │  ├─ state.py            # 活跃计划等状态
│  │  └─ session_state.py    # 当前会话元数据与异常退出恢复
│  ├─ app/                   # Web 后端（FastAPI），供 Electron 桌面端复用
│  │  ├─ _app.py             # FastAPI 应用装配（路由、CORS、健康检查、lifespan）
│  │  ├─ routers/            # REST/SSE 路由（chat/session/skill/config/context/system/llm）
│  │  ├─ runtime.py          # ChatSession：无 UI 会话核心（流式对话、技能加载）
│  │  ├─ session_manager.py  # session_id -> ChatSession 运行态容器
│  │  ├─ deps.py             # 依赖注入：会话管理单例 + Bearer Token 鉴权
│  │  └─ models.py           # 接口数据模型
│  ├─ config/                # 运行期上下文工具（当前工作目录）
│  └─ utils/                 # 通用工具：context(token 预算/裁剪)、logger、common、balance、turn_taking
├─ frontend/                 # 桌面应用前端（Electron + React + TS + Vite）
│  ├─ electron/              # 主进程 main.js + 预加载 preload.js
│  ├─ src/                   # 渲染进程：api/ store/ hooks/ components/ styles/
│  ├─ vite.config.ts / package.json / tsconfig.json
├─ design/                   # 设计方案文档（Electron GUI 方案 + 记忆/上下文/会话优化方案）
└─ tests/                    # pytest 测试
```

---

## 四、主要技术栈

**后端（Python）**

- **FastAPI + Uvicorn**：Web 后端与 REST/SSE 接口（`app/`）。
- **LiteLLM**：统一多供应商大模型调用（`agents/providers/litellm_provider.py`）。
- **Pydantic**：数据模型/校验；**loguru**：日志；**python-dotenv**：`.env` 加载；**PyYAML**：技能/记忆 frontmatter。
- **prompt-toolkit + aioconsole + rich**：CLI 交互与富文本渲染。
- **mss**：屏幕截图工具；**playwright**：浏览器操作工具（`control_browser` 类）。
- **httpx / aiofiles / shortuuid**：HTTP、异步文件、ID 生成。

**前端（桌面应用）**

- **Electron**（主进程 + preload，`contextBridge` 最小暴露）。
- **React 18 + TypeScript + Vite**：渲染进程。
- **zustand**：状态管理；**react-markdown + remark-gfm**：消息渲染。
- 前后端通信：REST + SSE（前端自解析），鉴权走 `Authorization: Bearer <MINICLAW_API_TOKEN>`。

---

## 五、核心模块导航（改动前先看这里）

| 需求 | 入口文件 |
| --- | --- |
| 新增/修改启动子命令（cli/server/ui） | `src/miniclaw/__main__.py` |
| 新增内置工具 | `src/miniclaw/agents/tools/*.py` → 在 `tools/__init__.py` 导出 → 在 `llm_tools_manager.py` 的 `BUILTIN_TOOLS` 注册定义 |
| 调整工具/子代理/规划相关常量名 | `src/miniclaw/agents/constant.py`（`subtask_executor` / `make_plans`） |
| 多模型配置读取/切换 | `src/miniclaw/agents/llm_configurator.py`、CLI `/llm` 命令 |
| CLI 交互/斜杠命令 | `src/miniclaw/cli/main.py`、`src/miniclaw/cli/commands.py` |
| 流式主循环（渲染 + 工具分发） | `src/miniclaw/cli/stream_runner.py` |
| 子代理执行逻辑 | `src/miniclaw/cli/clerk.py` |
| 计划生成与恢复（make_plans） | `src/miniclaw/cli/planner.py` |
| 记忆精简 / 上下文预算 | `src/miniclaw/cli/memory.py`、`src/miniclaw/utils/context.py` |
| Web 接口 | `src/miniclaw/app/routers/*.py`、装配在 `app/_app.py` |
| Web 会话运行时 | `src/miniclaw/app/runtime.py`、`app/session_manager.py` |
| 全局默认值/环境变量读取 | `src/miniclaw/constant.py`（`EnvVarLoader`） |
| 前端界面/组件 | `frontend/src/`（组件在 `components/`，状态在 `store/appStore.ts`） |
| 前端主进程/窗口/后端托管 | `frontend/electron/main.js` |

**内置工具清单**（`llm_tools_manager.py`）：`read_file`、`write_file`、`edit_file`、`append_file`、`tail_file`、`grep_search`、`glob_search`、`execute_shell_command`、`desktop_screenshot`、`browser_use`、`launch_detached`、`web_search`、`get_current_time`、`set_user_timezone`，以及特殊工具 `make_plans`（规划器）与 `subtask_executor`（子代理）。

**技能（Skill）机制**：技能以 `SKILL.md` 全文经**用户消息**注入（不改 system prompt），加载后本会话内不可卸载，仅「新建会话」可重置。默认目录 `~/.miniclaw/skills`；CLI 用 `/skill-list`、`/skill-load <name>,...`。

**Web 后端接口一览**（前缀 `/api`）

- `system`：`GET /system/info`、`GET /health`、`GET /version`
- `chat`：`POST /chat/stream`(SSE)、`POST /chat`、`GET /chat/cost`、`GET /chat/balance`
- `sessions`：列表/创建/详情/activate/load/resume/clear/export
- `skills`：`GET /skills`、`GET /skills/loaded`、`POST /skills/load`
- `config`：`GET|PATCH /config`、`GET /config/llms`、`POST /config/llm/use`、`POST /config/mode`、`POST /config/web-search`
- `context`：`GET /context`、`POST /context/action`
- `llm`（兼容保留）：`POST /llm/chat`、`POST /llm/stream`

---

## 六、关键环境变量速查（完整见 `.env.example`）

**模型连接（支持自定义前缀实现多套配置）**

- `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` / `CUSTOM_LLM_PROVIDER`（可加 `<NAME>_` 前缀分组）
- `LLM_TEMPERATURE`、`LLM_MAX_TOKENS`、`LLM_ENABLED_TOOLS`、`LLM_DISABLED_TOOLS`、`LLM_CLIENT_PROVIDER`

**服务与日志**：`SERVER_HOST`、`SERVER_PORT`、`MINICLAW_UI_PORT`(默认 7909)、`LOG_DIR`、`LOG_LEVEL`、`CORS_ALLOW_ORIGINS`

**记忆与上下文预算**：`MINICLAW_CONTEXT_WINDOW`(128000)、`MINICLAW_CONTEXT_SOFT_RATIO`(0.6)、`MINICLAW_CONTEXT_HARD_RATIO`(0.85)、`MINICLAW_CONTEXT_RESERVE_TOKENS`(4096)、`MINICLAW_CONTEXT_RETRY_MAX`(2)、`MINICLAW_TOOL_OUTPUT_MAX_TOKENS`(4000)、`MINICLAW_MEMORY_KEEP_RECENT`(6)、`MINICLAW_MEMORY_CHUNK_TOKENS`(20000)、`MINICLAW_STATE_DIR`

**自主执行与安全网**：`CHAT_AGENT_AUTONOMY_PROMPT`、`CHAT_CLERK_AUTONOMY_PROMPT`、`CHAT_TASK_DONE_TOKEN`(【TASK_DONE】)、`MINICLAW_MAX_TOOL_ITERATIONS`、`MINICLAW_MAX_SUBAGENT_LAYER`

**其他**：`MINICLAW_KEEP_REASONING_CONTENT`（思维链回传开关，默认按模型自动识别）、`MINICLAW_WEB_SEARCH_*` / `DOUBAO_SEARCH_*`、`MINICLAW_COST_*_PER_1M`（费用兜底单价）

---

## 七、测试与调试

- 测试：`pytest`（配置见 `pytest.ini`，测试位于 `tests/`）；异步测试用 `pytest-asyncio` 的 `@pytest.mark.asyncio`。
- 调试：在待调试处插入 `import pdb; pdb.set_trace()`。
- CLI 斜杠命令（定义于 `cli/commands.py::COMMAND_SPECS`）：`/help`、`/llm`、`/agent`、`/chat`、`/web-search`、`/model`、`/api_key`、`/base_url`、`/custom_llm_provider`、`/temperature`、`/max_token`、`/clear`、`/history`、`/memory`、`/memory-list`、`/context`、`/cost`、`/balance`、`/session-list`、`/session-load`、`/session-resume`、`/session-export`、`/skill-list`、`/skill-load`、`/image`、`/quit`。

---

## 八、参考文档索引

- 使用说明与机制详解：[`README.md`](./README.md)
- 桌面应用设计方案（架构/API/技能加载/前端/启动/实施）：[`design/electron-gui/`](./design/electron-gui)
- 会话与上下文优化方案：[`design/会话推进机制优化.md`](./design/会话推进机制优化.md)、[`design/对话上下文优化.md`](./design/对话上下文优化.md)、[`design/记忆优化.md`](./design/记忆优化.md)、[`design/cli-执行期停止对话-方案.md`](./design/cli-执行期停止对话-方案.md)
- 前端工程说明：[`frontend/README.md`](./frontend/README.md)
