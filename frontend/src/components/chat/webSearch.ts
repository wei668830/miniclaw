// 解析 web_search 工具的文本结果（格式见 src/miniclaw/agents/tools/web_search.py）。
//
// web 结果形如：
//   豆包联网搜索（web）结果，共 N 条：
//
//   1. 标题
//      站点：<Site>    发布时间：<Publish>
//      链接：<URL>
//      摘要：<Summary>

export interface WebResultItem {
  title: string;
  site?: string;
  publish?: string;
  url?: string;
  summary?: string;
}

export interface WebSearchParsed {
  total?: string;
  items: WebResultItem[];
}

/**
 * 解析 web 搜索结果文本；非 web 结果（如 image / 错误文本）返回 null。
 *
 * @param text 工具结果文本（实时为纯文本，历史为 JSON 时请先归一化）
 */
export function parseWebSearchResults(text: string): WebSearchParsed | null {
  const raw = text || '';
  const isWeb = /（web）/.test(raw) || raw.includes('链接：');
  if (!isWeb) return null;

  const items: WebResultItem[] = [];
  let cur: WebResultItem | null = null;
  let total: string | undefined;
  const tm = raw.match(/共\s*(\d+)\s*条/);
  if (tm) total = tm[1];

  for (const rawLine of raw.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) continue;

    const mi = line.match(/^(\d+)[.、]\s+(.*)$/);
    if (mi) {
      if (cur) items.push(cur);
      cur = { title: mi[2].trim() };
      continue;
    }
    if (!cur) continue;

    if (line.includes('发布时间：')) {
      const idx = line.indexOf('发布时间：');
      const left = line.slice(0, idx).replace(/^站点：/, '').trim();
      const right = line.slice(idx + '发布时间：'.length).trim();
      if (left) cur.site = left;
      if (right) cur.publish = right;
      continue;
    }
    if (line.startsWith('站点：')) {
      const v = line.slice(3).trim();
      if (v) cur.site = v;
      continue;
    }
    if (line.startsWith('链接：')) {
      cur.url = line.slice(3).trim();
      continue;
    }
    if (line.startsWith('摘要：')) {
      cur.summary = line.slice(3).trim();
      continue;
    }
    // 其它续行并入摘要（少见）
    cur.summary = cur.summary ? `${cur.summary} ${line}` : line;
  }
  if (cur) items.push(cur);

  return { total, items };
}
