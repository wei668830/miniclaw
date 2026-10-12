import React, { useState } from 'react';
import { SessionSidebar } from '../session/SessionSidebar';
import { ChatPanel } from '../chat/ChatPanel';
import { SkillPanel } from '../skill/SkillPanel';
import { SettingsDialog } from '../settings/SettingsDialog';
import { StatusBar } from '../common/StatusBar';

export const AppShell: React.FC = () => {
  const [rightOpen, setRightOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="app-shell">
      <div className="app-body">
        <SessionSidebar />
        <main className="main-area">
          <div className="topbar">
            <div className="topbar-title">对话</div>
            <div className="topbar-actions">
              <button className="btn small" onClick={() => setRightOpen((v) => !v)}>
                {rightOpen ? '隐藏技能' : '显示技能'}
              </button>
              <button className="btn small" onClick={() => setSettingsOpen(true)}>
                设置
              </button>
            </div>
          </div>
          <ChatPanel />
        </main>
        {rightOpen && (
          <aside className="right-panel">
            <div className="topbar">
              <div className="topbar-title">技能</div>
            </div>
            <SkillPanel />
          </aside>
        )}
      </div>
      <StatusBar />
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
};
