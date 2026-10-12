import React, { useEffect, useState } from 'react';
import { apiGet } from '../../api/client';
import { copyText } from '../chat/clipboard';

/**
 * 「打开工作目录」按钮：用系统文件管理器打开**命令执行所在的文件夹**
 * （后端进程工作目录，即 `_resolve_file_path('.')` / shell 的 cwd）。
 *
 * - Electron 环境：经 IPC `shell.openPath` 打开；
 * - 非 Electron（浏览器调试）：降级为复制路径。
 */
export const WorkingDirButton: React.FC = () => {
  const [dir, setDir] = useState('');
  const [busy, setBusy] = useState(false);
  const isElectron = typeof window !== 'undefined' && !!window.miniclaw?.openPath;

  const fetchDir = async (): Promise<string> => {
    try {
      const r = await apiGet<{ abs_path: string }>('/api/system/resolve-path?path=.');
      const p = r?.abs_path || '';
      if (p) setDir(p);
      return p;
    } catch {
      return '';
    }
  };

  useEffect(() => {
    void fetchDir();
  }, []);

  const onClick = async () => {
    setBusy(true);
    try {
      const target = dir || (await fetchDir());
      if (!target) return;
      if (isElectron) {
        await window.miniclaw!.openPath!(target);
      } else {
        await copyText(target);
      }
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      className="btn small"
      onClick={onClick}
      disabled={busy}
      title={dir ? `打开当前工作目录：${dir}` : '打开当前工作目录（命令执行所在文件夹）'}
    >
      📂 工作目录
    </button>
  );
};
