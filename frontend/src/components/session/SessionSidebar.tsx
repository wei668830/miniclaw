import React, { useState } from 'react';
import { useAppStore } from '../../store/appStore';

export const SessionSidebar: React.FC = () => {
  const sessions = useAppStore((s) => s.sessions);
  const sessionsLimit = useAppStore((s) => s.sessionsLimit);
  const currentSessionId = useAppStore((s) => s.currentSessionId);
  const createSession = useAppStore((s) => s.createSession);
  const activateSession = useAppStore((s) => s.activateSession);
  const deleteSession = useAppStore((s) => s.deleteSession);
  const loadMoreSessions = useAppStore((s) => s.loadMoreSessions);
  const streaming = useAppStore((s) => s.streaming);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const doDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    setConfirmId(null);
    await deleteSession(id);
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-head">
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
          >
            <div className="session-summary">{s.summary || '(空会话)'}</div>
            <div className="session-actions" onClick={(e) => e.stopPropagation()}>
              {confirmId === s.session_id ? (
                <>
                  <button
                    className="session-btn danger"
                    title="确认删除"
                    onClick={(e) => doDelete(e, s.session_id)}
                  >
                    ✔
                  </button>
                  <button className="session-btn" title="取消" onClick={() => setConfirmId(null)}>
                    ✕
                  </button>
                </>
              ) : (
                <button
                  className="session-btn"
                  title="删除会话"
                  disabled={streaming}
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmId(s.session_id);
                  }}
                >
                  🗑
                </button>
              )}
            </div>
          </div>
        ))}
        {sessions.length === 0 && <div className="empty-hint">暂无会话</div>}
        {sessions.length >= sessionsLimit && (
          <button className="btn small load-more" onClick={() => void loadMoreSessions()}>
            加载更多
          </button>
        )}
      </div>
    </aside>
  );
};
