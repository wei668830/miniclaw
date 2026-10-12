import React from 'react';
import { useAppStore } from '../../store/appStore';

export const StatusBar: React.FC = () => {
  const config = useAppStore((s) => s.config);
  const context = useAppStore((s) => s.context);
  const usage = useAppStore((s) => s.usage);
  const balance = useAppStore((s) => s.balance);
  const statusText = useAppStore((s) => s.statusText);
  const currentSessionId = useAppStore((s) => s.currentSessionId);

  return (
    <footer className="status-bar">
      <span className="status-item">模型：{config?.model || '-'}</span>
      <span className="status-item">模式：{config?.runtime_mode || '-'}</span>
      <span className="status-item">联网：{config?.web_search_enabled ? '开' : '关'}</span>
      {context && (
        <span className="status-item">
          上下文：{context.used_tokens} / {context.hard} tok
        </span>
      )}
      {balance && balance.ok && balance.total_balance != null && (
        <span
          className="status-item status-cost"
          title={
            `余额 ${balance.total_balance} ${balance.currency}` +
            (balance.session_spent != null ? `；本会话花费（余额差值）${balance.session_spent} ${balance.currency}` : '')
          }
        >
          余额：{balance.total_balance} {balance.currency}
          {balance.session_spent != null && ` · 本会话：${balance.session_spent} ${balance.currency}`}
        </span>
      )}
      {usage && (
        <span className="status-item" title={`输入 ${usage.prompt_tokens} / 输出 ${usage.completion_tokens} tokens，共 ${usage.turns} 次调用`}>
          {usage.total_tokens} tok
        </span>
      )}
      <span className="status-item">会话：{currentSessionId?.slice(0, 16) || '-'}</span>
      <span className="status-spacer" />
      <span className="status-item status-text">{statusText}</span>
    </footer>
  );
};
