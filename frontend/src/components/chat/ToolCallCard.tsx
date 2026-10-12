import React, { useState } from 'react';
import type { UIToolCall } from '../../store/appStore';

export const ToolCallCard: React.FC<{ call: UIToolCall }> = ({ call }) => {
  const [open, setOpen] = useState(false);
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
    </div>
  );
};
