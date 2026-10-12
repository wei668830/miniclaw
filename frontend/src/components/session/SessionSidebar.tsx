import React from 'react';
import { useAppStore } from '../../store/appStore';

export const SessionSidebar: React.FC = () => {
  const sessions = useAppStore((s) => s.sessions);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const createSession = useAppStore((s) => s.createSession);
  const activateSession = useAppStore((s) => s.activateSession);
  const streaming = useAppStore((s) => s.streaming);

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
        <span className="brand">MiniClaw</span>
        <button className="btn primary small" onClick={createSession} disabled={streaming}>
          ＋ 新建会话
        </button>
      </div>
      <div className="session-list">
        {sessions.map((s) => (
          <div
            key={s.session_id}
            className={`session-item ${s.session_id === currentSessionId ? 'active' : ''}`}
            onClick={() => !streaming && activateSession(s.session_id)}
            title={s.session_id}
          >
            <div className="session-summary">{s.summary || '(空会话)'}</div>
            <div className="session-meta">
              {s.session_id.slice(0, 14)}… · {s.messages} 条
            </div>
          </div>
        ))}
        {sessions.length === 0 && <div className="empty-hint">暂无会话</div>}
      </div>
    </aside>
  );
};
