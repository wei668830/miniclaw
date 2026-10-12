// 预加载脚本：以最小面向上渲染进程暴露必要能力（contextIsolation 安全边界）
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('miniclaw', {
  // 获取后端连接信息 { baseUrl, token }
  getConnection: () => ipcRenderer.invoke('conn:get'),
  getBackendInfo: () => ipcRenderer.invoke('backend:info'),
});
