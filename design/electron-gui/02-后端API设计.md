# 02 · 后端 API 设计（`src/miniclaw/app` 重构）

> 关联文档：[01-总体架构](./01-总体架构设计.md) · [03-技能机制](./03-技能对话式加载机制.md) · [05-启动流程](./05-启动流程与__main__集成.md)

---

## 一、重构目标

现有 `app/` 只有两个无状态接口（`/api/llm/chat`、`/api/llm/stream`），每次请求都要求前端自己维护 `messages` 全量历史，**无法承载**：会话、技能、配置、上下文预算等 CLI 已有能力。

本次将其升级为**「会话化 + 有状态后端」**：

1. 新增 **会话运行时（SessionManager）**：为每个会话持有 messages / 技能 / 配置 / 预算。
2. 新增 REST 路由：sessions / skills / config / context。
3. 改造聊天路由：以 `session_id` 取代裸 `messages`，并支持**技能对话式注入**。
4. 保持既有 `/api/llm/chat`、`/api/llm/stream` 作**兼容层**（可选，标注 deprecated）。

---

## 二、模块结构（目标态）

```
src/miniclaw/app/
├─ _app.py                # 应用装配：注册路由、CORS、鉴权依赖、lifespan
├─ deps.py                # ★ 新增：Token 鉴权、SessionManager 依赖注入
├─ session_manager.py     # ★ 新增：会话运行时容器与生命周期
├─ runtime.py             # ★ 新增（推荐）：ChatSession 运行时（从 CLI 抽取）
├─ llm_chat_context.py    # 消息持久层（保留原样）
├─ models.py              # ★ 新增：Pydantic 请求/响应模型
└─ routers/
   ├─ __init__.py
   ├─ system_router.py    # ★ 新增：/version /health /system/info
   ├─ llm_router.py       # 改造：/chat /chat/stream（会话化）
   ├─ session_router.py   # ★ 新增
   ├─ skill_router.py     # ★ 新增
   ├─ config_router.py    # ★ 新增
   └─ context_router.py   # ★ 新增
```

### 2.1 ChatSession（会话运行时）

> 建议：**从 `cli/main.py::CommandLineInteraction` 抽取「无 UI」核心**为 `ChatSession`，CLI 与 API 共用。若暂不重构 CLI，则先在 `app/runtime.py` 做等价薄封装（复用 `agents`、`cli/stream_runner.py::run_stream_round`、`cli/history_store.py`、`cli/memory.py`）。

字段定义：

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | `str` | 形如 `s{uuid}`，与 CLI 一致 |
| `messages` | `list[dict]` | 含两条 system（短指令 + PID 自保护），首条用户消息合并完整系统提示词 |
| `skills_preload` | `list[tuple]` | 待注入技能 `(name, description, dir)`，注入后清空 |
| `skills_loaded` | `list[tuple]` | 已加载技能，会话内**只增不减** |
| `llm` | `object` | `provider/model/api_key/base_url/custom_llm_provider/temperature/max_tokens` |
| `runtime_mode` | `str` | `agent` / `chat` |
| `web_search_enabled` | `bool` | 联网搜索开关 |
| `history_store` | `HistoryStore` | JSONL 原始历史 |
| `memory` | `Memory` | 记忆文件 |
| `active_plan_path` | `str \| None` | 活跃计划 |
| `tools` | `list` | 工具 schema（由 `llm_tools_manager` 提供） |

关键方法（语义与 CLI 对齐）：

```python
class ChatSession:
    def append_user_message(self, user_input: str) -> None: ...
        # ★ 技能注入点：把 skills_preload 中每个 SKILL.md 全文拼进本条用户消息
        #   然后 skills_preload.clear()，并把加载记录追加到 skills_loaded
    async def ensure_context(self) -> None: ...      # 复用 utils/context
    async def stream(self, user_input: str) -> AsyncIterator[Event]: ...
        # 复用 cli/stream_runner.run_stream_round 的多轮工具回路
```

### 2.2 SessionManager

- 持有 `dict[session_id -> ChatSession]` 与「当前活跃 session_id」。
- 提供 `create() / get(sid) / activate(sid) / list() / resume(sid)`。
- 进程内缓存，配合 `~/.miniclaw` 落盘（会话历史、记忆、chat_context）。
- **新建会话 = 新的 ChatSession（skills_loaded 为空）→ 满足「仅新会话重置技能」的语义。**

---

## 三、接口总览

统一前缀 `/api`。除 `/api/version`、`/api/health` 外，**均需鉴权头**：

```
Authorization: Bearer <token>
```

| 分组 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 系统 | GET | `/api/version` | 版本号 |
| 系统 | GET | `/api/health` | 健康检查 |
| 系统 | GET | `/api/system/info` | 模型/工作目录/当前会话等 |
| 会话 | GET | `/api/sessions` | 会话列表 |
| 会话 | POST | `/api/sessions` | **新建会话**（重置技能） |
| 会话 | GET | `/api/sessions/{sid}` | 会话详情（消息 + 已加载技能） |
| 会话 | POST | `/api/sessions/{sid}/activate` | 设为当前会话 |
| 会话 | POST | `/api/sessions/{sid}/resume` | 恢复并接续 |
| 会话 | POST | `/api/sessions/{sid}/load` | 加载到上下文（不接续） |
| 会话 | GET | `/api/sessions/{sid}/export` | 导出 Markdown |
| 聊天 | POST | `/api/chat/stream` | **SSE 流式对话**（核心） |
| 聊天 | POST | `/api/chat` | 非流式对话 |
| 技能 | GET | `/api/skills` | 技能列表（扫描） |
| 技能 | GET | `/api/skills/loaded` | 当前会话已加载技能 |
| 技能 | POST | `/api/skills/load` | **加载技能（对话式）** |
| 配置 | GET | `/api/config` | 当前配置 |
| 配置 | PATCH | `/api/config` | 更新配置 |
| 配置 | GET | `/api/config/llms` | 大模型配置列表 |
| 配置 | POST | `/api/config/llm/use` | 切换大模型配置 |
| 配置 | POST | `/api/config/mode` | 切换 agent/chat |
| 配置 | POST | `/api/config/web-search` | 开关联网搜索 |
| 上下文 | GET | `/api/context` | token 占用与阈值 |
| 上下文 | POST | `/api/context/action` | shrink/window/soft/hard/reset |

---

## 四、核心接口定义

### 4.1 新建会话

`POST /api/sessions`

```jsonc
// 请求（均为可选）
{ "activate": true }
// 响应
{ "session_id": "sxxxx", "created_at": "2026-10-10T18:00:00+08:00",
  "model": "deepseek/deepseek-chat", "runtime_mode": "agent",
  "skills_loaded": [] }
```

> 语义：创建全新的 `ChatSession`，`skills_loaded` 为空 —— 这是 UI 上「重置技能」的**唯一手段**。

### 4.2 流式对话（核心）

`POST /api/chat/stream`，`Content-Type: application/json`，响应 `text/event-stream`。

```jsonc
// 请求
{
  "session_id": "sxxxx",
  "message": "帮我搜索武汉天气",     // 纯用户输入；技能由后端注入
  "model": null,                     // 可选覆盖
  "temperature": null,
  "max_tokens": null,
  "mode": null                       // 可选覆盖 agent/chat
}
```

**SSE 事件协议：**

| event | data | 说明 |
|-------|------|------|
| `meta` | `{session_id, model, runtime_mode}` | 流开始，回传生效参数 |
| `reasoning` | `{delta}` | 思考过程增量（`reasoning_content`） |
| `chunk` | `{delta}` | 正式回答增量 |
| `tool_call` | `{id, function:{name, arguments}}` | 发起工具调用 |
| `tool_result` | `{tool_call_id, name, content, is_error}` | 工具执行结果（截断展示） |
| `done` | `{finish_reason, prompt_tokens, completion_tokens, total_tokens, cost_usd}` | 结束 |
| `error` | `{error}` | 异常 |

> 后端在一次 `stream` 请求内**串联多轮工具回路**（复用 `run_stream_round`），前端只需顺序消费事件。
> 是否开启工具依赖 `runtime_mode == agent`（与 CLI 一致）。

**前端消费示例（伪代码）：**

```ts
const es = new EventSourcePolyfill(`/api/chat/stream`, {method:'POST', body, headers});
es.on('chunk',  e => appendAssistant(e.delta));
es.on('reasoning', e => appendReasoning(e.delta));
es.on('tool_call', e => upsertToolCard(e));
es.on('tool_result', e => fillToolCard(e));
es.on('done',  e => setUsage(e));
es.on('error', e => showError(e));
```

> 实现建议：由于浏览器原生 `EventSource` 不支持 POST，前端使用 **`fetch` + ReadableStream** 解析 SSE（现有 `chat_stream.html` 已有参考实现，可复用其解析逻辑）。

### 4.3 技能加载（对话式）

`POST /api/skills/load`

```jsonc
// 请求
{ "session_id": "sxxxx", "names": ["web-search", "pdf-zh"] }
// 响应
{
  "pending": ["web-search"],         // 本次排入 skills_preload，将在下一条消息注入
  "already_loaded": ["pdf-zh"],      // 本会话已加载，忽略
  "skills_loaded": ["pdf-zh"]        // 当前已加载集合
}
```

**关键语义（与 CLI 完全一致，见文档 03）：**

- 加载 = 把技能排入 `skills_preload`；**真正的注入发生在下一条用户消息**，`SKILL.md` 全文拼接进该用户消息文本。
- 已加载技能写入 `skills_loaded`，**本会话内不可卸载**；重复加载返回 `already_loaded`。
- **重置方式唯一**：`POST /api/sessions`（新建会话）。

### 4.4 技能列表

```jsonc
// GET /api/skills
{ "skills": [ { "name": "web-search", "description": "联网搜索……", "path": "/Users/x/.miniclaw/skills/web-search" }, ... ] }
// GET /api/skills/loaded?session_id=sxxxx
{ "skills_loaded": [ { "name": "pdf-zh", "description": "..." } ] }
```

> 扫描逻辑复用 `cli/main.py::_reload_skills`，抽取为 `utils/common.py::scan_skills(skills_dir)`（首次自动从 `agents/skills` 复制到 `~/.miniclaw/skills`）。

### 4.5 配置

```jsonc
// GET /api/config
{
  "provider": "litellm",
  "model": "deepseek/deepseek-chat",
  "api_key_masked": "sk-****abcd",
  "base_url": "https://...",
  "custom_llm_provider": null,
  "temperature": null, "max_tokens": null,
  "runtime_mode": "agent",
  "web_search_enabled": false,
  "current_llm_name": "default"
}
// PATCH /api/config   body: 上述可写字段的子集
// POST /api/config/mode        { "mode": "chat" }
// POST /api/config/web-search  { "enabled": true }
// GET  /api/config/llms        { "llms": [{ "name": "default", "model": "...", "*": true }] }
// POST /api/config/llm/use     { "name": "fast" }
```

> API Key：前端**只读掩码**，写入用 `PATCH`（`api_key` 明文仅在后端流转）。

### 4.6 上下文

```jsonc
// GET /api/context?session_id=sxxxx
{ "used_tokens": 34210, "window": 128000, "soft": 0.6, "hard": 0.85, "reserve": 4096, "overrides": {} }
// POST /api/context/action  { "session_id": "sxxxx", "action": "window", "value": 1000000 }
```

---

## 五、CLI ↔ API 对照表（语义一致性）

| CLI 命令（`cli/commands.py`） | 后端 API | 备注 |
|-------------------------------|----------|------|
| `/skill-list` | `GET /api/skills` | 同一扫描逻辑 |
| `/skill-load a,b` | `POST /api/skills/load` | 均走 `skills_preload` 对话注入 |
| `/session-list` | `GET /api/sessions` | |
| `/session-load <id>` | `POST /api/sessions/{sid}/load` | |
| `/session-resume <id>` | `POST /api/sessions/{sid}/resume` | |
| `/session-export <id>` | `GET /api/sessions/{sid}/export` | |
| `/llm` `/llm use` | `GET /api/config/llms` · `POST /api/config/llm/use` | |
| `/model` `/api_key` `/base_url` | `PATCH /api/config` | |
| `/temperature` `/max_token` | `PATCH /api/config` | |
| `/agent` `/chat` | `POST /api/config/mode` | |
| `/web-search on|off` | `POST /api/config/web-search` | |
| `/context ...` | `GET/POST /api/context*` | |
| `/clear` | `POST /api/sessions/{sid}/clear`（新增） | 清空上下文 |
| `/history` | `GET /api/sessions/{sid}` | 取 messages |

---

## 六、鉴权与依赖注入

`deps.py`：

```python
from fastapi import Header, HTTPException, Depends

def require_token(authorization: str | None = Header(default=None)):
    token = app_state.auth_token          # 启动时生成
    if not authorization or authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="unauthorized")

def get_session_manager() -> SessionManager: ...
```

- `auth_token` 由启动方生成并经环境变量 `MINICLAW_API_TOKEN` 注入后端，同时下发给前端。
- 开发模式（`--dev`）可放宽鉴权，便于调试。

## 七、CORS 与静态资源

- 生产：`allow_origins` 收敛到 Electron 渲染进程来源（`file://` 或 `app://`）。
- 开发：允许 `http://localhost:*`。
- 可选用 `StaticFiles` 托管前端 `dist/`（`miniclaw server --serve-ui`），作为**不打包 Electron 时的降级形态**。

---

## 八、兼容与迁移

- 保留 `/api/llm/chat`、`/api/llm/stream` 行为不变，标注 `deprecated=True`，内部委托给 `SessionManager`（用每请求临时会话）。
- 现有 `chat_stream.html` 原型改用新接口后即可保留为「网页降级版」。

---

## 九、错误模型

统一返回：

```jsonc
{ "detail": "人类可读错误信息", "code": "SKILL_NOT_FOUND" }
```

常见状态码：`400` 参数错误 / `401` 鉴权失败 / `404` 会话或技能不存在 / `409` 会话状态冲突 / `500` 服务异常。
SSE 场景错误通过 `event: error` 下发，不改变 HTTP 状态。
