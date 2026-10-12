import React, { useEffect, useRef } from 'react';
import { useAppStore } from '../../store/appStore';
import { MessageItem } from './MessageItem';
import { parseChoice } from './choice';

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

  // 判断某条「选项消息」是否已被回答：向下查找最近的一条用户消息，
  // 若其内容等于某个选项的发送内容/文案，则视为已选该项（用于历史回放禁用与高亮）。
  const answeredFor = (idx: number): string | null => {
    const m = messages[idx];
    if (m.role !== 'assistant') return null;
    const { options } = parseChoice(m.content);
    if (!options.length) return null;
    for (let j = idx + 1; j < messages.length; j++) {
      const n = messages[j];
      if (n.role === 'user') {
        const text = n.content.trim();
        const hit = options.find((o) => o.value === text || o.label === text);
        return hit ? hit.value : null;
      }
    }
    return null;
  };

  return (
    <div className="message-list" ref={containerRef} onScroll={onScroll}>
      {messages.length === 0 && <div className="empty-hint">开始与 MiniClaw 对话吧～</div>}
      {messages.map((m, i) => (
        <MessageItem key={m.id} message={m} answeredValue={answeredFor(i)} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
};
