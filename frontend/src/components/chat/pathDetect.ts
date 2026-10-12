// 判断一段文本是否为「本地文件路径」（用于将正文中的内联代码渲染为可点击 chip）。
//
// 判定偏严格（宁可不判定，也不误判）：必须是带**文件名 + 后缀**的完整路径，
// 覆盖以下根：
//   - Windows 盘符：C:\dir\file.ext  /  C:/dir/file.ext
//   - UNC：\\server\share\file.ext
//   - 主目录：~/dir/file.ext  /  ~\dir\file.ext
//   - POSIX 绝对：/dir/file.ext
// 明确排除：`c:\.`、`c:\..`、`c:\...`、`~`、`/api/xxx`（无后缀）、相对路径、含空白者。

// 后缀：一个点 + 1~10 位字母数字
const RE_WIN = /^[A-Za-z]:[\\/](?:[^\\/:*?"<>|\s]+[\\/])*[^\\/:*?"<>|\s]+\.[A-Za-z0-9]{1,10}$/;
const RE_UNC = /^\\\\[^\\/\s]+[\\/](?:[^\\/:*?"<>|\s]+[\\/])*[^\\/:*?"<>|\s]+\.[A-Za-z0-9]{1,10}$/;
const RE_HOME = /^~[\\/](?:[^\\/\s]+[\\/])*[^\\/\s]+\.[A-Za-z0-9]{1,10}$/;
const RE_POSIX = /^\/(?:[^/\s]+\/)*[^/\s]+\.[A-Za-z0-9]{1,10}$/;

const MAX_LEN = 260;

/**
 * 是否为「完整的本地文件路径」（文件名 + 后缀）。
 *
 * @param raw 待判定的文本
 * @returns 命中任一完整路径规则返回 true
 */
export function looksLikeLocalPath(raw: string): boolean {
  const s = (raw || '').trim();
  if (!s || s.length > MAX_LEN) return false;
  if (/\s/.test(s)) return false; // 含空白一律不判定（路径带空格属极少数，宁可漏判）
  return RE_WIN.test(s) || RE_UNC.test(s) || RE_HOME.test(s) || RE_POSIX.test(s);
}

/** 取路径最后一段作为显示名（兼容 Windows / POSIX 分隔符）。 */
export function baseName(p: string): string {
  const s = (p || '').replace(/[\\/]+$/, '');
  const idx = Math.max(s.lastIndexOf('/'), s.lastIndexOf('\\'));
  return idx >= 0 ? s.slice(idx + 1) : s;
}
