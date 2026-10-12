import React, { useState } from 'react';
import { apiGet } from '../../api/client';

interface ResolveResult {
  input: string;
  abs_path: string;
  exists: boolean;
  is_dir: boolean;
}

/**
 * 文件快捷操作条：对生成/修改的文件提供「打开文件 / 打开所在文件夹 / 复制路径」。
 *
 * 路径解析走后端 `/api/system/resolve-path`（相对路径 → 绝对路径，与后端工具一致）；
 * 打开动作经 Electron IPC（`window.miniclaw`）调系统默认程序 / 资源管理器。
 * 非 Electron 环境（浏览器调试）隐藏打开类按钮，降级为「复制路径」。
 */
export const FileActions: React.FC<{ path: string }> = ({ path }) => {
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState('');
  const [absPath, setAbsPath] = useState('');

  const isElectron = typeof window !== 'undefined' && !!window.miniclaw?.openPath;

  const resolve = async (): Promise<ResolveResult | null> => {
    try {
      const r = await apiGet<ResolveResult>(
        `/api/system/resolve-path?path=${encodeURIComponent(path)}`
      );
      if (r?.abs_path) setAbsPath(r.abs_path);
      return r;
    } catch (e: any) {
      setHint(`解析路径失败：${e?.message || e}`);
      return null;
    }
  };

  const openFile = async () => {
    setHint('');
    setBusy(true);
    try {
      if (!isElectron) {
        await copy();
        return;
      }
      const r = await resolve();
      if (!r) return;
      if (!r.exists) {
        setHint('文件不存在');
        return;
      }
      const res = await window.miniclaw!.openPath!(r.abs_path);
      if (res && res.ok === false) setHint(res.error || '打开失败');
    } finally {
      setBusy(false);
    }
  };

  const openFolder = async () => {
    setHint('');
    setBusy(true);
    try {
      if (!isElectron) {
        await copy();
        return;
      }
      const r = await resolve();
      if (!r) return;
      if (!r.exists) {
        setHint('文件不存在');
        return;
      }
      const res = r.is_dir
        ? await window.miniclaw!.openPath!(r.abs_path)
        : await window.miniclaw!.showItemInFolder!(r.abs_path);
      if (res && res.ok === false) setHint(res.error || '打开失败');
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    setHint('');
    setBusy(true);
    try {
      const r = await resolve();
      const target = r?.abs_path || absPath || path;
      await navigator.clipboard.writeText(target);
      setHint('已复制路径');
    } catch {
      setHint('复制失败');
    } finally {
      setBusy(false);
    }
  };

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
