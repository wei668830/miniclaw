import React, { useEffect, useRef } from 'react';
import { useAppStore } from '../../store/appStore';
import { MessageItem } from './MessageItem';

export const MessageList: React.FC = () => {
  const messages = useAppStore((s) => s.messages);
  const bottomRef = useRef<HTMLDivElement>(null);
  const autoScroll = useRef(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    autoScroll.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
  };

  return (
    <div className="message-list" ref={containerRef} onScroll={onScroll}>
      {messages.length === 0 && <div className="empty-hint">开始与 MiniClaw 对话吧～</div>}
      {messages.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
};
