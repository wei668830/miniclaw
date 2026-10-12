// MiniClaw 桌面应用主进程
//
// 职责：
// - 单实例控制（requestSingleInstanceLock）
// - 创建窗口、加载渲染进程（dev 用 Vite devServer，prod 用 dist）
// - 后端连接信息下发（通过 preload 暴露给渲染进程）
// - 后端进程托管（形态 B：环境未提供 MINICLAW_BACKEND_URL 时自行拉起 Python 后端）
// - UI 关闭 ⇒ 后端同步销毁（覆盖所有退出路径）

const { app, BrowserWindow, ipcMain, shell, Menu } = require('electron');
const path = require('path');
const fs = require('fs');
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
// 窗口图标
// ---------------------------------------------------------------------------
// 未做打包时，窗口/任务栏图标由此处的 icon 决定。
// 约定：将图标放到 frontend/build/ 下（Windows 优先 icon.ico，其次 icon.png）。
function resolveWindowIcon() {
  const candidates = [
    path.join(__dirname, '..', 'build', 'icon.ico'),
    path.join(__dirname, '..', 'build', 'icon.png'),
  ];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) return p;
    } catch (_) {}
  }
  return undefined; // 未提供时回退 Electron 默认图标
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
    icon: resolveWindowIcon(),
    frame: false,
    autoHideMenuBar: true,
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

  // 通知渲染进程最大化状态变化，用于切换自定义标题栏的按钮图标
  const sendMaximized = () => {
    if (win) win.webContents.send('window:maximized-changed', win.isMaximized());
  };
  win.on('maximize', sendMaximized);
  win.on('unmaximize', sendMaximized);

  win.on('closed', () => {
    win = null;
  });
}

async function start() {
  // 移除 Electron 默认应用菜单栏（File/Edit/View/Window/Help）
  Menu.setApplicationMenu(null);
  await ensureBackend();
  ipcMain.handle('conn:get', () => connection);
  ipcMain.handle('backend:info', () => ({ external: externalBackend, ...connection }));
  // 无框窗口（frame:false）的窗口控制，由渲染进程的自定义标题栏调用
  ipcMain.handle('window:minimize', () => {
    win?.minimize();
  });
  ipcMain.handle('window:toggle-maximize', () => {
    if (!win) return false;
    if (win.isMaximized()) win.unmaximize();
    else win.maximize();
    return win.isMaximized();
  });
  ipcMain.handle('window:close', () => {
    win?.close();
  });
  ipcMain.handle('window:is-maximized', () => Boolean(win?.isMaximized()));
  // 用系统默认程序打开文件 / 打开所在文件夹并定位（供对话窗口的「文件快捷操作」使用）
  ipcMain.handle('shell:open-path', async (_e, target) => {
    if (typeof target !== 'string' || !target) return { ok: false, error: 'invalid path' };
    const err = await shell.openPath(target);
    return { ok: !err, error: err || null };
  });
  ipcMain.handle('shell:show-item-in-folder', (_e, target) => {
    if (typeof target !== 'string' || !target) return { ok: false, error: 'invalid path' };
    shell.showItemInFolder(target);
    return { ok: true };
  });
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
