import React from 'react';
import { CodeBlock } from './CodeBlock';
import { PathChip } from './PathChip';
import { looksLikeLocalPath } from './pathDetect';
import { nodeToText } from './reactText';

/**
 * 内联代码渲染：
 * - 若内容看起来是本地文件路径，则渲染为可点击的 PathChip（打开文件 / 打开所在文件夹）；
 * - 否则保持普通 `<code>`。
 *
 * 说明：代码块（fenced）由 `pre`(CodeBlock) 接管，不会走到这里。
 */
const InlineCode: React.FC<any> = ({ node, className, children }) => {
  const text = nodeToText(children);
  if (looksLikeLocalPath(text)) {
    return <PathChip path={text.trim()} />;
  }
  return <code className={className}>{children}</code>;
};

/** ReactMarkdown 自定义组件表：代码块复制 + 正文路径可点击。 */
export const markdownComponents = {
  pre: CodeBlock,
  code: InlineCode,
};
