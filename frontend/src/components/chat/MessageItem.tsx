import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { cleanUserText, useAppStore } from '../../store/appStore';
import type { UIMessage } from '../../store/appStore';
import { ToolCallCard } from './ToolCallCard';
import { ChoiceOptions } from './ChoiceOptions';
import { parseChoice } from './choice';

const TASK_DONE_TOKEN = '【TASK_DONE】';

export const MessageItem: React.FC<{ message: UIMessage; answeredValue?: string | null }> = ({
  message,
  answeredValue = null,
}) => {
  const { role } = message;
  const sendMessage = useAppStore((s) => s.sendMessage);
  const streaming = useAppStore((s) => s.streaming);

  if (role === 'system') {
    return <div className="msg system">{message.content}</div>;
  }

  if (role === 'user') {
    return (
      <div className="msg-row user">
        <div className="bubble user">
          <div className="content">{cleanUserText(message.content)}</div>
          {message.injectedSkills && message.injectedSkills.length > 0 && (
            <div className="injected-skills">已注入技能：{message.injectedSkills.join('，')}</div>
          )}
        </div>
      </div>
    );
  }

  const done = message.content.includes(TASK_DONE_TOKEN);
  const withoutToken = message.content.replace(TASK_DONE_TOKEN, '').trim();
  const { text: content, options } = parseChoice(withoutToken);

  return (
    <div className="msg-row assistant">
      <div className="bubble assistant">
        {message.reasoning && <details className="reasoning"><summary>思考过程</summary><div>{message.reasoning}</div></details>}
        {message.toolCalls?.map((tc, i) => <ToolCallCard key={i} call={tc} />)}
        {content && (
          <div className="content markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
        {options.length > 0 && (
          <ChoiceOptions
            options={options}
            disabled={streaming}
            answeredValue={answeredValue}
            onChoose={(value) => sendMessage(value)}
          />
        )}
        {message.streaming && !content && (!message.toolCalls || message.toolCalls.length === 0) && (
          <div className="typing">思考中…</div>
        )}
        {done && <div className="task-done">✅ 任务完成</div>}
        {message.error && <div className="error">错误：{message.error}</div>}
      </div>
    </div>
  );
};
