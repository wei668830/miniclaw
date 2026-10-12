# 05 · 启动流程与 `__main__.py` 集成

> 关联文档：[01-总体架构](./01-总体架构设计.md) · [04-前端工程](./04-前端Electron工程设计.md) · [06-实施计划](./06-实施计划与验收标准.md)

---

## 一、目标

在 `src/miniclaw/__main__.py` 现有 `server` / `cli` 两个子命令基础上，**新增 `ui` 子命令**，实现「一条命令拉起桌面应用」：

```bash
miniclaw ui                 # 生产：启动后端（默认端口 7909）+ Electron 窗口
miniclaw ui --dev           # 开发：后端 --reload + Electron 指向 Vite devServer
miniclaw ui --port 8123     # 覆盖后端端口（默认 7909）
miniclaw ui --no-backend    # 仅启动 Electron（后端已由别处提供）
```

> **桌面应用后端默认端口为 `7909`**（可由 `--port` / 环境变量 `MINICLAW_UI_PORT` 覆盖）。
> 该端口**独立于** `server` 子命令的 `SERVER_PORT`（`.env` 中常配置为 8000），二者互不影响。
> 若 7909 被占用，回退到自动选择的空闲端口，并将最终地址回传前端。

---

## 二、两种启动形态

| 形态 | 由谁拉起后端 | 适用 | 说明 |
|------|--------------|------|------|
| **A. Python 主导** | `__main__.py` | 一键启动（`miniclaw ui`）、一体化分发 | 先起 uvicorn → 再起 Electron，把 `baseUrl/token` 通过参数/环境变量传给 Electron |
| **B. Electron 主导** | Electron 主进程 | 用户双击 App 图标启动 | 主进程 `spawn` Python 后端（打包后为可执行），轮询 `/api/health` 就绪后再建窗 |

两种形态共用同一后端与前端；区别仅在「谁持有后端子进程句柄」。**谁拉起谁负责优雅关闭。**

### 2.1 两条硬性约束

1. **只允许一个实例**：重复启动不得产生第二个窗口/第二个后端。
2. **UI 关闭 ⇒ 后端同步销毁**：窗口关闭（或应用退出/崩溃/被强杀）后，后端进程必须在秒级内退出，**不留孤儿**。

### 2.2 单实例约束

**（1）Electron 应用级单实例锁**（`frontend/electron/main.ts`）：

```ts
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();                       // 已有实例 → 直接退出
} else {
  app.on('second-instance', () => { // 再次启动 → 聚焦已有窗口
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });
  app.whenReady().then(createWindow);
}
```

**（2）运行态锁文件** `~/.miniclaw/state/miniclaw-ui.lock`：

```jsonc
{ "pid": 12345, "port": 7909, "token": "…", "started_at": "2026-10-10T18:00:00+08:00" }
```

- 启动时读取：PID 存活 → 判定已有实例，退出（或聚焦）；PID 已死 → **陈旧锁**，清理后继续。
- 退出/崩溃恢复时清理锁文件。

**（3）后端端口判定**（默认 7909，见 2.4）：

- 7909 空闲 → 正常启动。
- 7909 被占用且探针表明是本应用后端（锁文件指向 / 健康探针特征匹配）→ 视为**孤儿后端**，先终止再启动。
- 7909 被非本应用占用 → 回退空闲端口。

### 2.3 UI 关闭 ⇒ 后端同步销毁（多路径兜底）

**A. 主进程必须覆盖所有退出路径**（`frontend/electron/main.ts`）：

```ts
let backendChild: ChildProcess | null = null;

app.on('window-all-closed', () => app.quit());        // 关窗即退出（含 macOS 也可强制退出）
app.on('before-quit', () => killBackend());           // 退出前杀后端
app.on('will-quit',  () => { killBackend(); removeLockFile(); });
process.on('exit',    () => killBackend());           // 最后兜底

function killBackend() {
  if (!backendChild) return;
  backendChild.kill('SIGTERM');
  setTimeout(() => backendChild?.kill('SIGKILL'), 3000).unref();
  backendChild = null;
}
```

**B. `miniclaw ui`（形态 A）**：`electron_proc.wait()` 返回后 `backend_proc.terminate()`，并在 `finally` 兜底（已有实现，见 3.2）。

**C. 后端看门狗（防孤儿，覆盖「UI 被强杀」等漏网情形）**：

> 后端启动时以 `MINICLAW_PARENT_PID` 传入父进程 PID，并**以管道方式启动**（父进程退出 → stdin EOF）。

```python
# app/_app.py lifespan 启动阶段
import os, threading, sys

def _watch_parent():
    parent = int(os.environ.get("MINICLAW_PARENT_PID") or 0)
    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0); return True
        except OSError:
            return False
    while True:
        if parent and not alive(parent):
            os._exit(0)                     # 父进程已消失 → 自我销毁
        # 父进程若以管道启动，stdin 读到 EOF 说明父已退出
        try:
            if not sys.stdin.isatty() and os.read(0, 1) == b"":
                os._exit(0)
        except OSError:
            os._exit(0)
        threading.Event().wait(1)

threading.Thread(target=_watch_parent, daemon=True).start()
```

> 结果：**无论 UI 是正常关闭、崩溃还是被强制结束，后端都会在秒级内自动销毁。**

### 2.4 端口与单实例的关系

- 默认端口 **7909**（可由 `--port` / `MINICLAW_UI_PORT` 覆盖；独立于 `server` 的 `SERVER_PORT`）。
- 「7909 被占用」在单实例语义下**优先判定为孤儿后端**并回收；仅当确认非本应用时才回退空闲端口。
- 回退端口需一并写入锁文件，保证后续「单实例」判定准确。

---

## 三、`__main__.py` 改造

### 3.1 新增 `ui` 子命令（解析器）

```python
# create_parser() 内追加
ui_parser = subparsers.add_parser('ui', help='启动桌面应用（Electron）')
ui_parser.add_argument('--host', default=None, help='后端监听地址（默认 127.0.0.1）')
ui_parser.add_argument('--port', type=int, default=None, help='后端监听端口（默认 7909）')
ui_parser.add_argument('--dev', action='store_true', help='开发模式（后端 reload + 前端 devServer）')
ui_parser.add_argument('--no-backend', action='store_true', help='不启动后端（复用已有后端）')
ui_parser.add_argument('--no-build', action='store_true', help='跳过前端构建（假定 dist 已存在）')
ui_parser.add_argument('--log-level', choices=['debug','info','warning','error'], default=None)
```

并在 `main()` 分派：

```python
elif args.command == 'ui':
    print("启动桌面应用...")
    run_ui(args)
```

### 3.2 `run_ui()` 实现（形态 A）

```python
import socket, secrets, subprocess, time, signal, sys
from pathlib import Path
from miniclaw.constant import EnvVarLoader

DEFAULT_UI_PORT = 7909   # 桌面应用后端默认端口

def _port_available(host: str, port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port)); return True
        except OSError:
            return False

def _pick_free_port(host: str) -> int:
    with socket.socket() as s:
        s.bind((host, 0)); return s.getsockname()[1]

def _resolve_port(host: str, preferred: int) -> int:
    """优先使用 preferred（默认 7909）；被占用时回退到空闲端口。"""
    return preferred if _port_available(host, preferred) else _pick_free_port(host)

def _project_root() -> Path:
    # src/miniclaw/__main__.py -> 项目根
    return Path(__file__).resolve().parents[2]

def run_ui(args):
    host = getattr(args, 'host', None) or "127.0.0.1"
    # 默认端口 7909（--port / MINICLAW_UI_PORT 可覆盖，独立于 server 的 SERVER_PORT）；被占用时回退到空闲端口
    port = getattr(args, 'port', None) or EnvVarLoader.get_int("MINICLAW_UI_PORT", DEFAULT_UI_PORT)
    port = _resolve_port(host, port)
    token = secrets.token_urlsafe(32)
    dev = getattr(args, 'dev', False)

    # 1) 启动后端（方式 A：由本进程托管）
    backend_proc = None
    if not getattr(args, 'no_backend', False):
        env = {**os.environ, "MINICLAW_API_TOKEN": token, "SERVER_HOST": host, "SERVER_PORT": str(port)}
        backend_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "miniclaw.app._app:app",
             "--host", host, "--port", str(port)] + (["--reload"] if dev else []),
            env=env,
        )
        _wait_healthy(f"http://{host}:{port}/api/health", timeout=30)

    # 2) 启动 Electron（前端工程位于 ./frontend）
    frontend_dir = _project_root() / "frontend"
    if not getattr(args, 'no_build', False) and not dev and not (frontend_dir / "dist").exists():
        subprocess.run(["npm", "run", "build"], cwd=frontend_dir, check=True)

    electron_env = {
        **os.environ,
        "MINICLAW_BACKEND_URL": f"http://{host}:{port}",
        "MINICLAW_API_TOKEN": token,
        "MINICLAW_DEV": "1" if dev else "0",
    }
    electron_cmd = _electron_cmd(frontend_dir, dev)  # 见下
    electron_proc = subprocess.Popen(electron_cmd, cwd=frontend_dir, env=electron_env)

    # 3) 等待 Electron 退出 → 优雅关闭后端
    try:
        electron_proc.wait()
    finally:
        if backend_proc:
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend_proc.kill()
```

其中：

```python
def _electron_cmd(frontend_dir: Path, dev: bool):
    # 优先使用本地 electron 可执行；跨平台差异在实现期处理
    exe = frontend_dir / "node_modules" / ".bin" / ("electron.cmd" if os.name == "nt" else "electron")
    return [str(exe), "."]           # 读取 frontend/package.json 的 main
```

> **不杀 Python 进程的反面用法**：这里托管是通过 `Popen` 句柄 + `terminate()` 实现，**不是** `taskkill /im python.exe`，避免误杀（与本应用自身同为 Python 进程的现实约束一致）。

### 3.3 形态 B：Electron 主进程托管后端（`frontend/electron/backend.ts`）

```ts
// 若环境变量未提供 MINICLAW_BACKEND_URL，则自行拉起后端
async function ensureBackend(): Promise<{ baseUrl: string; token: string }> {
  if (process.env.MINICLAW_BACKEND_URL) {
    return { baseUrl: process.env.MINICLAW_BACKEND_URL!, token: process.env.MINICLAW_API_TOKEN! };
  }
  const port = await resolvePort(7909);   // 默认 7909，被占用则回退空闲端口
  const token = randomToken();
  child = spawn(pythonExe(), ['-m', 'miniclaw', 'server', '--port', String(port)],
                { env: { ...process.env, MINICLAW_API_TOKEN: token } });
  await waitHealthy(`http://127.0.0.1:${port}/api/health`);
  return { baseUrl: `http://127.0.0.1:${port}`, token };
}
```

---

## 四、连接信息传递

| 变量 | 谁生成 | 传给谁 | 用途 |
|------|--------|--------|------|
| `MINICLAW_BACKEND_URL` | 启动方 | Electron 主进程 → 渲染进程 | API baseURL |
| `MINICLAW_API_TOKEN` | 启动方 | 后端 + Electron → 渲染进程 | 鉴权头 |
| `MINICLAW_DEV` | 启动方 | Electron | 决定加载 devServer 还是 dist |

- 渲染进程通过 `window.miniclaw.getConnection()`（IPC）获取 `{ baseUrl, token }`，注入到 API 客户端。
- Token 尽量**不落盘**，仅进程内传递。

---

## 五、健康检查与就绪

- 后端暴露 `GET /api/health` → `{"status":"ok"}`。
- 启动方轮询该接口（如每 300ms，最多 30s）直到就绪，再创建窗口；期间前端显示启动遮罩（`onBackendStatus`）。
- 超时则弹出错误并提供「查看日志 / 重试」。

---

## 六、优雅关闭（UI 关闭 ⇒ 后端同步销毁）

关闭路径与兜底（详见 2.3）：

1. 用户关闭窗口 → `window-all-closed` → `app.quit()` → 触发 `before-quit` / `will-quit`。
2. 若后端由 Electron 托管 → 主进程 `child.kill('SIGTERM')`，等待退出，超时 `SIGKILL`。
3. 若后端由 `__main__` 托管 → `electron_proc.wait()` 返回后，`backend_proc.terminate()`（`finally` 兜底）。
4. **清理运行态锁文件** `~/.miniclaw/state/miniclaw-ui.lock`。
5. 后端 `lifespan` 的 shutdown 分支执行清理（见 `app/_app.py`）。
6. **兜底（关键）**：后端看门狗（父进程 PID 监视 + stdin EOF）确保即便 UI 被强杀，后端也会在秒级内自我销毁，不留孤儿。

---

## 七、打包与分发（可选 · 非一期目标）

> **结论：一期不做打包。** 本应用定位为单机、单用户的本地工具，**直接以源码 + 依赖环境运行即可**（`miniclaw ui`，前置条件：本机已装 Python 与 Node）。
> 打包仅在「需要分发给不装 Python/Node 的非技术用户」时才引入，属于**可选后续能力**，实现方式如下备查。

### 7.1 后端可执行化（PyInstaller）

```bash
pyinstaller --name miniclaw-backend \
  --hidden-import uvicorn --collect-all litellm \
  src/miniclaw/__main__.py
```

- 产物放入 `frontend/resources/backend/`。
- Electron 打包时用 `extraResources` 带上，运行时用其路径替代 `python -m miniclaw`。

### 7.2 前端打包（electron-builder）

- `electron-builder.yml` 配置三平台目标（dmg / nsis / AppImage）。
- 将 `frontend/dist`（渲染进程）与 `electron` 编译产物一并打包；后端可执行放入 `extraResources`。
- 安装后双击图标即为形态 B（Electron 主导）。

### 7.3 体积与性能取舍

- Electron 体积较大（100MB+）；如需更小体积，可评估 **Tauri**（前端复用，Rust 壳）作为后续优化项。
- 首屏优化：主进程先建空窗（骨架），后端就绪后再加载会话列表。

---

## 八、CLI 兼容性

- 现有 `server` / `cli` 子命令**行为不变**（`create_parser` 仅做增量）。
- 无子命令时的默认行为保持不变（当前默认进入 CLI）。
- `--version`、`server --no-reload` 等参数维持。

---

## 九、验收点（启动集成）

- [ ] `miniclaw ui` 可一键拉起「后端 + 窗口」，窗口关闭后后端进程退出（无残留）。
- [ ] `miniclaw ui --dev` 支持前后端热更。
- [ ] `miniclaw ui` 默认使用端口 **7909**；`miniclaw ui --port 8123` 覆盖生效。
- [ ] 7909 被占用时自动回退到空闲端口，且前端能正确连接（地址由启动方回传）。
- [ ] 后端未就绪时前端展示启动状态，就绪后自动进入。
- [ ] 双击打包后的桌面图标（形态 B）可自启后端并正常工作。
- [ ] `miniclaw server` / `miniclaw cli` 回归无影响。
- [ ] 退出应用后，任务管理器无残留后端 Python 进程。
- [ ] **单实例**：应用已运行时再次启动 → 不出现第二个窗口，聚焦已有窗口。
- [ ] **单实例**：`miniclaw ui` 重复执行 → 第二次不启动新后端/新窗口。
- [ ] **同步销毁**：关闭窗口、退出应用、渲染进程崩溃三种路径下，后端均在秒级内退出。
- [ ] **防孤儿**：强制结束 UI 进程（模拟崩溃/kill）后，后端看门狗在秒级内自动销毁。
- [ ] 启动时若发现陈旧锁文件 / 孤儿后端，能自动清理并正常启动。
