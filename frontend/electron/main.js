// MiniClaw 桌面应用主进程
//
// 职责：
// - 单实例控制（requestSingleInstanceLock）
// - 创建窗口、加载渲染进程（dev 用 Vite devServer，prod 用 dist）
// - 后端连接信息下发（通过 preload 暴露给渲染进程）
// - 后端进程托管（形态 B：环境未提供 MINICLAW_BACKEND_URL 时自行拉起 Python 后端）
// - UI 关闭 ⇒ 后端同步销毁（覆盖所有退出路径）

const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const net = require('net');
const http = require('http');
const crypto = require('crypto');

const isDev = process.env.MINICLAW_DEV === '1';
const DEFAULT_PORT = 7909;

// 连接信息（渲染进程通过 IPC 获取）
let connection = {
  baseUrl: process.env.MINICLAW_BACKEND_URL || '',
  token: process.env.MINICLAW_API_TOKEN || '',
};

let win = null;
let backendChild = null;
let externalBackend = Boolean(process.env.MINICLAW_BACKEND_URL);

// ---------------------------------------------------------------------------
// 单实例
// ---------------------------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) {
      if (win.isMinimized()) win.restore();
      win.focus();
    }
  });
  app.whenReady().then(start);
}

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------
function pickFreePort(host = '127.0.0.1') {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.listen(0, host, () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
  });
}

function portAvailable(port, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const srv = net.createServer();
    srv.once('error', () => resolve(false));
    srv.listen(port, host, () => srv.close(() => resolve(true)));
  });
}

function waitHealthy(url, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const tick = () => {
      http
        .get(url, (res) => {
          if (res.statusCode === 200) return resolve(true);
          retry();
        })
        .on('error', retry);
    };
    const retry = () => {
      if (Date.now() > deadline) return resolve(false);
      setTimeout(tick, 300);
    };
    tick();
  });
}

function pythonExecutable() {
  return process.env.MINICLAW_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
}

// ---------------------------------------------------------------------------
// 后端托管（形态 B）
// ---------------------------------------------------------------------------
async function ensureBackend() {
  if (connection.baseUrl) return connection;

  let port = DEFAULT_PORT;
  if (!(await portAvailable(port))) {
    port = await pickFreePort();
  }
  const token = crypto.randomBytes(24).toString('hex');

  const projectRoot = path.resolve(__dirname, '..', '..');
  const env = {
    ...process.env,
    MINICLAW_API_TOKEN: token,
    MINICLAW_PARENT_PID: String(process.pid),
    PYTHONPATH: path.join(projectRoot, 'src') + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ''),
  };

  backendChild = spawn(
    pythonExecutable(),
    ['-m', 'uvicorn', 'miniclaw.app._app:app', '--host', '127.0.0.1', '--port', String(port)],
    { cwd: projectRoot, env, stdio: ['pipe', 'ignore', 'ignore'] }
  );

  connection = { baseUrl: `http://127.0.0.1:${port}`, token };
  await waitHealthy(`${connection.baseUrl}/api/health`, 30000);
  return connection;
}

function killBackend() {
  if (!backendChild) return;
  try {
    backendChild.kill('SIGTERM');
    setTimeout(() => {
      try {
        backendChild.kill('SIGKILL');
      } catch (_) {}
    }, 3000).unref();
  } catch (_) {}
  backendChild = null;
}

// ---------------------------------------------------------------------------
// 窗口
// ---------------------------------------------------------------------------
function createWindow() {
  win = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: 'MiniClaw',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 外链使用系统浏览器打开
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (isDev) {
    win.loadURL('http://localhost:5173');
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }

  win.on('closed', () => {
    win = null;
  });
}

async function start() {
  await ensureBackend();
  ipcMain.handle('conn:get', () => connection);
  ipcMain.handle('backend:info', () => ({ external: externalBackend, ...connection }));
  createWindow();
}

// ---------------------------------------------------------------------------
// 生命周期：UI 关闭 ⇒ 后端同步销毁（全路径兜底）
// ---------------------------------------------------------------------------
app.on('window-all-closed', () => {
  app.quit();
});

app.on('before-quit', () => {
  killBackend();
});

app.on('will-quit', () => {
  killBackend();
});

process.on('exit', () => {
  killBackend();
});
