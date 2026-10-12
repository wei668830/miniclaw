import React, { useState } from 'react';
import type { UIToolCall } from '../../store/appStore';
import { FileActions } from './FileActions';

// 会产生/修改「单个文件」的工具：入参含 file_path
const FILE_TOOLS = new Set(['write_file', 'edit_file', 'append_file']);
// 计划工具：文件路径出现在结果文本中（「文件路径: …」）
const PLAN_TOOL = 'make_plans';

/**
 * 从工具调用中提取目标文件路径（用于渲染文件快捷操作）。
 *
 * 优先取入参 file_path（write/edit/append）；其次从结果文本解析（make_plans）。
 * 取不到返回 null。
 */
function extractFilePath(call: UIToolCall): string | null {
  if (FILE_TOOLS.has(call.name || '')) {
    if (call.args) {
      try {
        const obj = JSON.parse(call.args);
        const p = obj?.file_path || obj?.path;
        if (typeof p === 'string' && p.trim()) return p.trim();
      } catch {
        /* 参数非合法 JSON，忽略 */
      }
    }
  }
  const result = call.result || '';
  // make_plans 结果形如：「计划文件已生成，文件路径: D:\...\plan-xxx.md」
  const m = result.match(/文件路径[:：]\s*([^\n]+)/);
  if (m && m[1].trim()) return m[1].trim();
  return null;
}

export const ToolCallCard: React.FC<{ call: UIToolCall }> = ({ call }) => {
  const [open, setOpen] = useState(false);
  const filePath = call.status === 'done' ? extractFilePath(call) : null;
  return (
    <div className={`tool-card ${call.status}`}>
      <div className="tool-card-head" onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{call.status === 'running' ? '⏳' : call.isError ? '⚠️' : '🔧'}</span>
        <span className="tool-name">{call.name || '未知工具'}</span>
        <span className="tool-toggle">{open ? '收起' : '展开'}</span>
      </div>
      {open && (
        <div className="tool-card-body">
          <div className="tool-section-title">参数</div>
          <pre className="tool-args">{call.args || '（无）'}</pre>
          {call.result !== undefined && (
            <>
              <div className="tool-section-title">结果</div>
              <pre className="tool-result">{call.result}</pre>
            </>
          )}
        </div>
      )}
      {filePath && <FileActions path={filePath} />}
    </div>
  );
};
