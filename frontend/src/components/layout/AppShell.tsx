import React, { useState } from 'react';
import { SessionSidebar } from '../session/SessionSidebar';
import { ChatPanel } from '../chat/ChatPanel';
import { SkillPanel } from '../skill/SkillPanel';
import { SettingsDialog } from '../settings/SettingsDialog';
import { StatusBar } from '../common/StatusBar';
import { WorkingDirButton } from '../common/WorkingDirButton';
import { ImageLightbox } from '../common/ImageLightbox';
import { TitleBar } from './TitleBar';

export const AppShell: React.FC = () => {
  const [rightOpen, setRightOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="app-shell">
      <TitleBar onOpenSettings={() => setSettingsOpen(true)} />
      <div className="app-body">
        <SessionSidebar />
        <main className="main-area">
          <div className="topbar">
            <div className="topbar-title">对话</div>
            <div className="topbar-actions">
              <WorkingDirButton />
              <button className="btn small" onClick={() => setRightOpen((v) => !v)}>
                {rightOpen ? '隐藏技能' : '显示技能'}
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
      <ImageLightbox />
    </div>
  );
};
