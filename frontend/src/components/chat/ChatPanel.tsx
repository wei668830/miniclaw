import React from 'react';
import { MessageList } from './MessageList';
import { Composer } from './Composer';

export const ChatPanel: React.FC = () => {
  return (
    <div className="chat-panel">
      <MessageList />
      <Composer />
    </div>
  );
};
