import React, { useState } from 'react';
import { copyText } from './clipboard';
import { nodeToText } from './reactText';

/**
 * Markdown 代码块渲染：在代码块右上角提供「复制」按钮。
 *
 * 作为 `ReactMarkdown` 的 `pre` 组件使用；从子 `<code>` 元素取回原始文本用于复制，
 * 自身渲染 `<pre><code>`（不渲染子元素，从而避免内联 code 组件被误用于代码块）。
 */
export const CodeBlock: React.FC<any> = ({ children }) => {
  const [copied, setCopied] = useState(false);

  const child: any = React.isValidElement(children) ? children : null;
  const className: string = (child?.props?.className as string) || '';
  const lang = className.match(/language-([\w-]+)/)?.[1] || '';
  const code = nodeToText(child ? (child.props as any)?.children : children);

  const onCopy = async () => {
    const ok = await copyText(code);
    if (ok) {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <div className="code-block">
      <div className="code-block-head">
        <span className="code-lang">{lang || 'code'}</span>
        <button type="button" className="code-copy" onClick={onCopy}>
          {copied ? '✓ 已复制' : '复制'}
        </button>
      </div>
      <pre className="code-block-pre">
        <code className={className}>{code}</code>
      </pre>
    </div>
  );
};
