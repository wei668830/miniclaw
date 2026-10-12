import React, { useEffect } from 'react';
import { useAppStore } from './store/appStore';
import { AppShell } from './components/layout/AppShell';

const App: React.FC = () => {
  const ready = useAppStore((s) => s.ready);
  const statusText = useAppStore((s) => s.statusText);
  const init = useAppStore((s) => s.init);

  useEffect(() => {
    void init();
  }, [init]);

  if (!ready) {
    return (
      <div className="loading-screen">
        <div className="loading-title">MiniClaw</div>
        <div className="loading-text">{statusText}</div>
      </div>
    );
  }

  return <AppShell />;
};

export default App;
