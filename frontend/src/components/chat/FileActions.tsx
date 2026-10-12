import React from 'react';
import { useFilePath } from './useFilePath';

/**
 * 文件快捷操作条：对生成/修改的文件提供「打开文件 / 打开所在文件夹 / 复制路径」。
 *
 * 路径解析走后端 `/api/system/resolve-path`（相对路径 → 绝对路径，与后端工具一致）；
 * 打开动作经 Electron IPC（`window.miniclaw`）调系统默认程序 / 资源管理器。
 * 非 Electron 环境（浏览器调试）隐藏打开类按钮，降级为「复制路径」。
 */
export const FileActions: React.FC<{ path: string }> = ({ path }) => {
  const { busy, hint, absPath, isElectron, openFile, openFolder, copy } = useFilePath(path);

  return (
    <div className="file-actions">
      <div className="file-actions-buttons">
        {isElectron && (
          <>
            <button className="btn tiny" onClick={openFile} disabled={busy}>
              📂 打开文件
            </button>
            <button className="btn tiny" onClick={openFolder} disabled={busy}>
              🗂 打开所在文件夹
            </button>
          </>
        )}
        <button className="btn tiny" onClick={copy} disabled={busy}>
          📋 复制路径
        </button>
      </div>
      <span className="file-actions-path" title={absPath || path}>
        {absPath || path}
      </span>
      {hint && <span className="file-actions-hint">{hint}</span>}
    </div>
  );
};
