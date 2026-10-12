import React, { useState } from 'react';
import type { UIToolCall } from '../../store/appStore';
import { FileActions } from './FileActions';
import { SearchResults } from './SearchResults';
import { parseWebSearchResults } from './webSearch';

// 会产生/修改「单个文件」的工具（入参含 file_path）
const FILE_TOOLS = new Set(['write_file', 'edit_file', 'append_file']);
const PLAN_TOOL = 'make_plans';

// 结果文本 → 绝对路径的匹配式（服务端已回传绝对路径）
const RESULT_PATH_PATTERN: Record<string, RegExp> = {
  write_file: /\bto\s+(.+?)\.\s*$/m, // Wrote N bytes to <abs>.
  append_file: /\bto\s+(.+?)\.\s*$/m, // Appended N bytes to <abs>.
  edit_file: /\bin\s+(.+?)\.\s*$/m, // Successfully replaced text in <abs>.
};

/** 归一化工具结果文本：历史回放里存的是 JSON（ToolResponse dump），实时是纯文本。 */
function normalizeResultText(result?: string): string {
  const t = (result || '').trim();
  if (!t) return '';
  if (t.startsWith('{')) {
    try {
      const obj = JSON.parse(t);
      if (Array.isArray(obj?.content)) {
        return obj.content.map((b: any) => (typeof b?.text === 'string' ? b.text : '')).join('\n');
      }
    } catch {
      /* 非 JSON，按纯文本处理 */
    }
  }
  return t;
}

/**
 * 从工具调用中提取目标文件路径（用于渲染文件快捷操作）。
 *
 * 优先使用**工具结果文本里的绝对路径**（服务端实际写入位置，最可靠）：
 * - `write_file` / `append_file`：结果形如「Wrote/Appended … to <绝对路径>.」
 * - `edit_file`：结果形如「Successfully replaced text in <绝对路径>.」
 * - `make_plans`：结果形如「文件路径: <绝对路径>」
 * 其次回退到入参 `file_path`（可能为相对路径，交后端解析）；取不到返回 null。
 */
function extractFilePath(call: UIToolCall): string | null {
  const name = call.name || '';
  const resultText = normalizeResultText(call.result);

  const pattern = RESULT_PATH_PATTERN[name];
  if (pattern) {
    const m = resultText.match(pattern);
    if (m && m[1].trim()) return m[1].trim();
  }

  if (name === PLAN_TOOL || !FILE_TOOLS.has(name)) {
    const m = resultText.match(/文件路径[:：]\s*([^\n]+)/);
    if (m && m[1].trim()) return m[1].trim();
  }

  if (FILE_TOOLS.has(name) && call.args) {
    try {
      const obj = JSON.parse(call.args);
      const p = obj?.file_path || obj?.path;
      if (typeof p === 'string' && p.trim()) return p.trim();
    } catch {
      /* 参数非合法 JSON，忽略 */
    }
  }

  return null;
}

export const ToolCallCard: React.FC<{ call: UIToolCall }> = ({ call }) => {
  const [open, setOpen] = useState(false);
  const filePath = call.status === 'done' && !call.isError ? extractFilePath(call) : null;

  const resultText = normalizeResultText(call.result);
  const search = call.name === 'web_search' ? parseWebSearchResults(resultText) : null;
  const hasSearch = !!(search && search.items.length);

  return (
    <div className={`tool-card ${call.status}`}>
      <div className="tool-card-head" onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{call.status === 'running' ? '⏳' : call.isError ? '⚠️' : '🔧'}</span>
        <span className="tool-name">{call.name || '未知工具'}</span>
        {hasSearch && <span className="search-badge">{search!.items.length} 条结果</span>}
        <span className="tool-toggle">{open ? '收起' : '展开'}</span>
      </div>

      {open && (
        <div className="tool-card-body">
          <div className="tool-section-title">参数</div>
          <pre className="tool-args">{call.args || '（无）'}</pre>
          {hasSearch ? (
            <SearchResults items={search!.items} total={search!.total} />
          ) : (
            call.result !== undefined && (
              <>
                <div className="tool-section-title">结果</div>
                <pre className="tool-result">{call.result}</pre>
              </>
            )
          )}
        </div>
      )}
      {filePath && <FileActions path={filePath} />}
    </div>
  );
};
