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
| 包管理 | **Poetry**（`pip install poetry`） |
| Node.js | 前端构建/桌面应用需要（Electron + Vite） |
| 依赖安装 | `poetry install`（含 dev 依赖；`poetry install --group dev`） |
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
# 统一入口（Windows 用 miniclaw.bat / Linux 用 miniclaw.sh，脚本内指定 python 解释器路径）
python -m miniclaw            # 默认进入 CLI 交互模式
python -m miniclaw cli        # CLI 交互模式
python -m miniclaw server     # 仅启动 FastAPI 后端（默认 0.0.0.0:8000，可 --host/--port/--no-reload）
python -m miniclaw ui         # 桌面应用：后端(默认 7909) + Electron（--dev 开发模式 / --no-build 跳过构建）
```

---

## 三、工程结构（核心）

```text
MiniClaw/
├─ pyproject.toml            # Poetry 工程定义与依赖
├─ poetry.lock               # 锁文件
├─ .env.example              # 环境变量模板（复制为 .env 使用）
├─ miniclaw.bat / .sh        # 启动脚本（指定 python 解释器）
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
