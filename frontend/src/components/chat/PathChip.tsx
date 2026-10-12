import React from 'react';
import { useFilePath } from './useFilePath';
import { baseName } from './pathDetect';

/**
 * 正文路径 chip：把助手回答里出现的本地文件路径渲染为可点击元素。
 *
 * - 点击主按钮：打开该文件（非 Electron 环境降级为复制路径）；
 * - 点击 🗂：打开所在文件夹（仅 Electron）。
 */
export const PathChip: React.FC<{ path: string }> = ({ path }) => {
  const { busy, hint, absPath, isElectron, openFile, openFolder } = useFilePath(path);

  return (
    <span className="path-chip" title={hint || absPath || path}>
      <button
        type="button"
        className="path-chip-main"
        disabled={busy}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          void openFile();
        }}
      >
        📄 {baseName(path)}
      </button>
      {isElectron && (
        <button
          type="button"
          className="path-chip-folder"
          title="打开所在文件夹"
          disabled={busy}
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            void openFolder();
          }}
        >
          🗂
        </button>
      )}
    </span>
  );
};
