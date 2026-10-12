import React, { useMemo, useState } from 'react';
import { useAppStore } from '../../store/appStore';
import { SLASH_COMMANDS, useSlashCommands } from '../../hooks/useSlashCommands';

export const Composer: React.FC = () => {
  const [text, setText] = useState('');
  const streaming = useAppStore((s) => s.streaming);
  const sendMessage = useAppStore((s) => s.sendMessage);
  const stopStream = useAppStore((s) => s.stopStream);
  const { run } = useSlashCommands();

  const showCommands = text.startsWith('/') && !text.includes(' ');
  const matches = useMemo(
    () => SLASH_COMMANDS.filter((c) => c.name.startsWith(text.slice(1).toLowerCase())),
    [text]
  );

  const submit = async () => {
    const value = text.trim();
    if (!value || streaming) return;
    setText('');
    if (value.startsWith('/')) {
      await run(value);
    } else {
      await sendMessage(value);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div className="composer">
      {showCommands && matches.length > 0 && (
        <div className="command-popover">
          {matches.map((c) => (
            <div key={c.name} className="command-item" onClick={() => setText(`/${c.name} `)}>
              <span className="command-name">/{c.name}</span>
              <span className="command-summary">{c.summary}</span>
            </div>
          ))}
        </div>
      )}
      <textarea
        value={text}
        placeholder="输入消息，Enter 发送，Shift+Enter 换行；以 / 开头可执行命令"
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="composer-actions">
        {streaming ? (
          <button className="btn stop" onClick={stopStream}>
            停止
          </button>
        ) : (
          <button className="btn send" onClick={submit} disabled={!text.trim()}>
            发送
          </button>
        )}
      </div>
    </div>
  );
};
