import React, { useEffect } from 'react';
import { useAppStore } from './store/appStore';
import { AppShell } from './components/layout/AppShell';
import logo from './assets/logo.png';

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
        <img className="loading-logo" src={logo} alt="MiniClaw" />
        <div className="loading-title">MiniClaw</div>
        <div className="loading-text">{statusText}</div>
      </div>
    );
  }

  return <AppShell />;
};

export default App;
