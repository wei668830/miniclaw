import React, { useEffect, useState } from 'react';
import logo from '../../assets/logo.png';

// 无框窗口（frame:false）的自定义标题栏：
// - 整条为可拖拽区域（.titlebar 设置 -webkit-app-region: drag）
// - 右侧窗口控制按钮（最小化 / 最大化-还原 / 关闭）走 IPC 调用主进程
// - 非 Electron 环境（如浏览器预览）不渲染，避免误触
export const TitleBar: React.FC = () => {
  const api = typeof window !== 'undefined' ? window.miniclaw : undefined;
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    if (!api?.isMaximized) return;
    void api.isMaximized().then(setMaximized).catch(() => {});
    const off = api.onMaximizedChange?.(setMaximized);
    return () => off?.();
  }, [api]);

  if (!api?.minimizeWindow) return null;

  return (
    <div className="titlebar" onDoubleClick={() => void api.toggleMaximizeWindow?.()}>
      <div className="titlebar-brand">
        <img className="titlebar-logo" src={logo} alt="MiniClaw" />
        <span>MiniClaw</span>
      </div>
      <div className="titlebar-controls" onDoubleClick={(e) => e.stopPropagation()}>
        <button className="titlebar-btn" title="最小化" onClick={() => void api.minimizeWindow?.()}>
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <rect x="0" y="4.5" width="10" height="1" fill="currentColor" />
          </svg>
        </button>
        <button
          className="titlebar-btn"
          title={maximized ? '还原' : '最大化'}
          onClick={() => void api.toggleMaximizeWindow?.()}
        >
          {maximized ? (
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <rect x="0.5" y="2.5" width="7" height="7" fill="none" stroke="currentColor" />
              <rect x="2.5" y="0.5" width="7" height="7" fill="none" stroke="currentColor" />
            </svg>
          ) : (
            <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
              <rect x="0.5" y="0.5" width="9" height="9" fill="none" stroke="currentColor" />
            </svg>
          )}
        </button>
        <button className="titlebar-btn close" title="关闭" onClick={() => void api.closeWindow?.()}>
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true">
            <path d="M0.5 0.5 L9.5 9.5 M9.5 0.5 L0.5 9.5" stroke="currentColor" />
          </svg>
        </button>
      </div>
    </div>
  );
};
