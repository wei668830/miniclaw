# 04 · 前端 Electron 工程设计（`./frontend`）

> 关联文档：[01-总体架构](./01-总体架构设计.md) · [02-后端API设计](./02-后端API设计.md) · [05-启动流程](./05-启动流程与__main__集成.md)

---

## 一、技术栈

| 层 | 选型 | 说明 |
|----|------|------|
| 桌面壳 | **Electron**（最新稳定版） | 主进程 + 渲染进程 |
| 构建 | **Vite** + `electron-vite`（或 vite-plugin-electron） | 一套配置同时构建主/预加载/渲染 |
| 语言 | **TypeScript** | 主进程与渲染进程共享类型 |
| UI 框架 | **React 18** | 组件生态成熟 |
| 状态管理 | **Zustand** | 轻量，适合会话/技能/配置状态 |
| 样式 | **TailwindCSS** + CSS 变量主题 | 快速落地；可换 Ant Design |
| Markdown | `react-markdown` + `remark-gfm` + `highlight.js`/`shiki` | 代码高亮 |
| 图标 | `lucide-react` | 轻量图标 |
| SSE | `fetch + ReadableStream` 自解析（可选用 `@microsoft/fetch-event-source` 封装） | 原生 `EventSource` 只支持 GET（无法传 POST body / 自定义头） |
| 打包（可选） | electron-builder | 仅分发场景启用，非一期目标 |

---

## 二、工程目录结构

```
frontend/
├─ package.json
├─ tsconfig.json
├─ vite.config.ts
├─ electron-builder.yml
├─ index.html
├─ resources/                     # 图标等静态资源
├─ electron/                      # 主进程侧
│  ├─ main.ts                     # 应用入口：创建窗口、生命周期
│  ├─ backend.ts                  # 后端进程托管（方式 B：由主进程拉起 Python）
│  ├─ ipc.ts                      # IPC 通道注册
│  └─ preload.ts                  # contextBridge 暴露安全 API
└─ src/                           # 渲染进程（React）
   ├─ main.tsx
   ├─ App.tsx
   ├─ api/
   │  ├─ client.ts                # fetch 封装（baseURL + Token）
   │  ├─ sse.ts                   # SSE 解析器（POST + stream）
   │  └─ endpoints.ts             # 各接口函数
   ├─ store/
   │  ├─ chatStore.ts             # 消息流/流式状态
   │  ├─ sessionStore.ts          # 会话列表/当前会话
   │  ├─ skillStore.ts            # 技能列表/已加载
   │  └─ configStore.ts           # 模型/模式/联网开关
   ├─ components/
   │  ├─ layout/AppShell.tsx      # 三栏布局
   │  ├─ session/SessionSidebar.tsx
   │  ├─ chat/ChatPanel.tsx
   │  ├─ chat/MessageList.tsx
   │  ├─ chat/MessageItem.tsx     # 含 Markdown / reasoning / tool 卡片
   │  ├─ chat/ToolCallCard.tsx
   │  ├─ chat/Composer.tsx        # 输入框 + 斜杠命令 + 停止
   │  ├─ skill/SkillPanel.tsx
   │  ├─ settings/SettingsDialog.tsx
   │  └─ common/StatusBar.tsx     # 模型 / token / 上下文
   ├─ hooks/
   │  ├─ useChatStream.ts
   │  └─ useSlashCommands.ts
   └─ styles/
      └─ index.css
```

---

## 三、主进程（`electron/main.ts`）

职责：

1. **单实例控制**：`app.requestSingleInstanceLock()`，未获得锁则退出；`second-instance` 聚焦已有窗口。
2. **创建窗口**：`BrowserWindow`（默认 1200×800），加载渲染进程（dev 用 Vite devServer，prod 用 `dist/index.html`）。
3. **后端托管**：调用 `backend.ts`，按 [`05-启动流程`](./05-启动流程与__main__集成.md) 决定是「复用外部后端」还是「自行 spawn Python 后端」。
4. **连接信息下发**：把 `backendUrl`、`authToken` 通过 `preload` 暴露给渲染进程。
5. **安全**：`contextIsolation: true`、`nodeIntegration: false`、`sandbox: true`。
6. **生命周期强绑定**：`window-all-closed` / `before-quit` / `will-quit` / `process.on('exit')` 全路径销毁后端子进程并清理锁文件；渲染进程崩溃时按策略退出（退出必带后端）。
7. 菜单/托盘/快捷键（可选）：新建会话、清空上下文、切换模式。

关键代码骨架：

```ts
const win = new BrowserWindow({
  width: 1200, height: 800,
  webPreferences: {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true, nodeIntegration: false, sandbox: true,
  },
});
```

---

## 四、预加载（`electron/preload.ts`）

仅暴露**必要**能力，禁止把 Node 能力直通渲染进程：

```ts
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('miniclaw', {
  getConnection: () => ipcRenderer.invoke('conn:get'),   // { baseUrl, token }
  newSession:     () => ipcRenderer.invoke('session:new'),
  restartBackend: () => ipcRenderer.invoke('backend:restart'),
  onBackendStatus:(cb) => ipcRenderer.on('backend:status', (_e, s) => cb(s)),
});
```

- `getConnection()`：渲染进程启动时获取 `baseUrl` + `token`，用于后续 REST/SSE。
- `onBackendStatus`：后端启动中/就绪/异常的订阅，用于展示启动遮罩。

---

## 五、渲染进程（React）

### 5.1 布局（三栏）

```
┌───────────┬──────────────────────────────────────────┬───────────────┐
│ 会话侧栏   │               聊天主区                     │ 技能/设置面板   │
│           │  ┌────────────────────────────────────┐   │               │
│ + 新建会话 │  │ MessageList（Markdown/思考/工具卡片）│   │ 技能列表       │
│ 会话列表   │  │                                    │   │ [已加载]徽标   │
│           │  └────────────────────────────────────┘   │ ─────────     │
│           │  ┌────────────────────────────────────┐   │ 模型/参数      │
│           │  │ Composer（输入 + 斜杠命令 + 停止）    │   │ 运行模式       │
│           │  └────────────────────────────────────┘   │ 联网开关       │
├───────────┴──────────────────────────────────────────┴───────────────┤
│ StatusBar：模型 · 运行模式 · 上下文 token/阈值 · 后端状态              │
└──────────────────────────────────────────────────────────────────────┘
```

> 右侧「技能面板」**默认隐藏**，通过主区顶部「显示技能」按钮展开；设置以弹窗呈现。

### 5.2 状态管理（Zustand）

| Store | 关键状态 |
|-------|----------|
| `sessionStore` | `sessions[]`、`currentSessionId`、`createSession()`、`activate()` |
| `chatStore` | `messages[]`、`streaming`、`usage`、`appendChunk()`、`abort()` |
| `skillStore` | `available[]`、`loaded[]`、`loadSkills(names)` |
| `configStore` | `model`、`mode`、`webSearch`、`temperature`、`context` |

### 5.3 聊天流式消费（`hooks/useChatStream.ts`）

- 使用 `fetch` POST `/api/chat/stream`，读取 `response.body`（ReadableStream），按 `\n\n` 切帧、解析 `event:`/`data:`。
- 事件分派：
  - `meta` → 记录 `injected_skills`（做透明标签）、生效模型；
  - `reasoning` → 折叠式「思考中…」块；
  - `chunk` → 追加到当前助手气泡；
  - `tool_call` → 新建工具卡片（工具名 + 参数，可折叠）；
  - `tool_result` → 回填卡片结果（截断展示，长文本可展开）；
  - `done` → 写入 `usage`，结束流，允许再次发送；
  - `error` → 气泡内红色错误 + 重试按钮。
- **停止**：`AbortController.abort()` 中断 fetch（后端随连接断开结束生成器）。
- **任务完成标记**：若助手文本包含 `【TASK_DONE】`，渲染为「✅ 任务完成」徽标（不在正文重复显示标记本身）。

> 解析逻辑可参考现有 `chat_stream.html` 的 `parseSseFrames/parseFrame`（已可用，直接移植为 TS）。

**SSE 实现选型说明（结论：采用 POST + SSE）**

- 主流方案有三类：① 原生 `EventSource`（**仅 GET**，不能传 body / 自定义头）；② `fetch + ReadableStream` 自解析；③ 封装库（`@microsoft/fetch-event-source` 及其衍生 `modern-fetch-stream` / `sse-wire` 等）。
- 因聊天接口需 **POST**（`session_id`/`message`/`model` 放 body）并携带 `Authorization` 头，**不可用原生 `EventSource`**（MDN 明确其构造函数仅接受 `url` 与 `withCredentials`）。
- 选型共识：**GET 接口 → `EventSource`；POST 接口 → fetch-based SSE**。AI 流式对话属后者，业界普遍如此。
- 本项目采用 **② `fetch + ReadableStream` 自解析**（复用 `chat_stream.html`）；如需省事可换 **③ `@microsoft/fetch-event-source`**（注意其为回调 API，且 POST 默认不自动重连——正契合「一次生成」语义）。

### 5.4 斜杠命令（`hooks/useSlashCommands.ts`）

- 在 `Composer` 中，输入以 `/` 开头时弹出命令浮层（数据源镜像 `cli/commands.py::COMMAND_SPECS`）。
- 支持的命令（映射到 API）：
  - `/skill-list`、`/skill-load a,b`
  - `/session-list`、`/session-load`、`/session-resume`、`/session-export`
  - `/llm`、`/model`、`/temperature`、`/max_token`、`/api_key`、`/base_url`
  - `/agent`、`/chat`、`/web-search on|off`、`/context`、`/clear`、`/help`
- **命令 vs 普通消息**：`/` 开头 → 本地派发到对应 API，并以「系统气泡」展示结果，**不进 LLM 上下文**；否则作为普通用户消息发送。

### 5.5 技能面板（`components/skill/SkillPanel.tsx`）

- 分区一「本会话已加载」：只读列表 + 「本会话内不可卸载」徽标。
- 分区二「可用技能」：`name` / `description` / `[加载]` 按钮（已加载置灰）。
- 交互：点「加载」→ `POST /api/skills/load` → Toast「已加载，将在下一条消息生效」。
- **无卸载按钮**（刻意）；若用户尝试，提示「请新建会话重置」。

### 5.6 设置（`components/settings/SettingsDialog.tsx`）

- 大模型配置（列表切换 / 临时设置 model+base_url+api_key）。
- 采样参数（temperature / max_token）。
- 运行模式（Agent / Chat 切换）。
- 联网搜索开关。
- 上下文预算（查看 + 运行期覆盖 window/soft/hard/reserve/reset）。
- API Key 仅显示掩码。

### 5.7 消息渲染（`MessageItem.tsx`）

- 用户气泡：仅显示**用户原始输入**（`cleanUserText` 剥离注入的完整系统提示词与技能注入块）+ 「已注入技能：xxx」标签（来自 `meta.injected_skills`）。**系统提示词不在对话中展示。**
- 助手气泡：Markdown 渲染、代码高亮、可折叠 reasoning、工具卡片、任务完成徽标。
- 系统气泡：斜杠命令/接口操作的结果。

---

## 六、类型与契约共享

- 后端 Pydantic 模型（`app/models.py`）与前端 TS 类型（`src/api/types.ts`）保持字段一致。
- 建议：由后端导出 OpenAPI（FastAPI 自带 `/openapi.json`），前端用 `openapi-typescript` 生成类型，杜绝手写漂移。

---

## 七、样式与主题

- 使用 CSS 变量定义 `--bg / --fg / --accent / --border`，内置浅色/深色两套主题。
- 跟随系统主题（`prefers-color-scheme`）+ 手动切换。
- 聊天区滚动：新消息自动吸底；用户手动上滑时暂停吸底并显示「回到底部」。

---

## 八、打包与分发（可选 · 非一期目标）

> 一期以「源码 + 依赖环境」运行（`miniclaw ui`），**不做打包**（前置：本机已装 Python 与 Node）。仅当需要面向不装 Python/Node 的用户分发时，才引入 electron-builder：
- 目标产物：macOS `.dmg`、Windows `.exe(nsis)`、Linux `AppImage`。
- `extraResources` 打入后端可执行（PyInstaller 产物）或 Python 运行时。
- 详见 [05-启动流程与__main__集成](./05-启动流程与__main__集成.md) 的打包章节。

---

## 九、开发与调试

| 场景 | 命令（建议） | 说明 |
|------|--------------|------|
| 前端热更 | `cd frontend && npm run dev` | 起 Vite devServer + Electron |
| 仅后端 | `python -m miniclaw server --no-reload` | 供前端联调 |
| 一体化 | `python -m miniclaw ui --dev` | 后端 + Electron（dev 模式） |
| 构建 | `cd frontend && npm run build` | 产出 `dist/` 与主进程产物 |

---

## 十、验收点（前端）

- [ ] 三栏布局可用，窗口可缩放，主题可切换。
- [ ] 流式对话：逐字输出、思考块、工具卡片、完成徽标正确。
- [ ] 斜杠命令浮层与派发正确，且不进上下文。
- [ ] 技能面板可加载、显示已加载徽标、无卸载入口。
- [ ] 新建会话后，聊天区清空、已加载技能清空。
- [ ] 停止按钮可中断流；错误可重试。
- [ ] 设置项改动即时生效（模型、模式、联网、上下文覆盖）。
- [ ] 单实例：应用已运行时再次启动只聚焦已有窗口。
- [ ] 关闭窗口/退出应用后后端进程同步销毁（无残留）。
