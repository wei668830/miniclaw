# MiniClaw 桌面应用（前端）

Electron + React + TypeScript + Vite 实现的 MiniClaw 桌面界面。

## 目录结构

```
frontend/
├─ electron/           # 主进程与预加载脚本（CommonJS，无需编译）
│  ├─ main.js          # 单实例锁、窗口、后端托管、生命周期
│  └─ preload.js       # contextBridge 暴露最小能力
├─ src/                # 渲染进程（React + TS）
│  ├─ api/             # 后端客户端（REST + SSE 自解析）
│  ├─ store/           # zustand 状态
│  ├─ hooks/           # 斜杠命令
│  ├─ components/      # 会话/聊天/技能/设置/状态栏
│  ├─ styles/
│  ├─ App.tsx
│  └─ main.tsx
├─ index.html
├─ vite.config.ts
└─ package.json
```

## 依赖安装

```bash
cd frontend
npm install
```

> 若 Electron 二进制下载失败（ECONNRESET/404），使用镜像重装：
> ```bash
> set "ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/"
> node node_modules\electron\install.js
> ```

## 开发 / 构建

```bash
npm run dev      # 仅启动 Vite devServer（配合 MINICLAW_DEV=1 的 Electron）
npm run build    # 构建渲染进程到 dist/
npm start        # 直接用 Electron 启动（需已构建 dist 或 MINICLAW_DEV=1）
```

## 启动方式

推荐从项目根目录用统一入口启动（自动拉起后端 + Electron）：

```bash
python -m miniclaw ui            # 默认端口 7909
python -m miniclaw ui --dev      # 开发模式
```

Electron 通过环境变量获取连接信息：

- `MINICLAW_BACKEND_URL`：后端地址（未设置时主进程会自行拉起 Python 后端）
- `MINICLAW_API_TOKEN`：鉴权 Token
- `MINICLAW_DEV`：`1` 时加载 Vite devServer（http://localhost:5173），否则加载 `dist/`
