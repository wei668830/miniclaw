// 预加载脚本：以最小面向上渲染进程暴露必要能力（contextIsolation 安全边界）
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('miniclaw', {
  // 获取后端连接信息 { baseUrl, token }
  getConnection: () => ipcRenderer.invoke('conn:get'),
  getBackendInfo: () => ipcRenderer.invoke('backend:info'),

  // 无框窗口（frame:false）的自定义标题栏控制
  minimizeWindow: () => ipcRenderer.invoke('window:minimize'),
  toggleMaximizeWindow: () => ipcRenderer.invoke('window:toggle-maximize'),
  closeWindow: () => ipcRenderer.invoke('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:is-maximized'),
  onMaximizedChange: (callback) => {
    const listener = (_event, value) => callback(Boolean(value));
    ipcRenderer.on('window:maximized-changed', listener);
    return () => ipcRenderer.removeListener('window:maximized-changed', listener);
  },

  // 文件快捷操作：用系统默认程序打开 / 在文件夹中定位（渲染进程先做交互，再调此处）
  openPath: (target) => ipcRenderer.invoke('shell:open-path', target),
  showItemInFolder: (target) => ipcRenderer.invoke('shell:show-item-in-folder', target),
});
