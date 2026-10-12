import { useState } from 'react';
import { apiGet } from '../../api/client';
import { copyText } from './clipboard';

interface ResolveResult {
  input: string;
  abs_path: string;
  exists: boolean;
  is_dir: boolean;
}

/**
 * 文件路径操作 Hook：解析路径 + 打开文件 / 打开所在文件夹 / 复制路径。
 * 供 FileActions（工具卡片）与 PathChip（正文路径）复用。
 */
export function useFilePath(path: string) {
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState('');
  const [absPath, setAbsPath] = useState('');

  const isElectron = typeof window !== 'undefined' && !!window.miniclaw?.openPath;

  const resolve = async (): Promise<ResolveResult | null> => {
    try {
      const r = await apiGet<ResolveResult>(`/api/system/resolve-path?path=${encodeURIComponent(path)}`);
      if (r?.abs_path) setAbsPath(r.abs_path);
      return r;
    } catch (e: any) {
      setHint(`解析路径失败：${e?.message || e}`);
      return null;
    }
  };

  const copyOnly = async () => {
    const r = await resolve();
    const target = r?.abs_path || absPath || path;
    const ok = await copyText(target);
    setHint(ok ? '已复制路径' : '复制失败');
  };

  const openFile = async () => {
    setHint('');
    setBusy(true);
    try {
      if (!isElectron) {
        await copyOnly();
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
        await copyOnly();
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
      await copyOnly();
    } finally {
      setBusy(false);
    }
  };

  return { busy, hint, absPath, isElectron, openFile, openFolder, copy };
}
