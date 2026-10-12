import React from 'react';

/** 递归提取 React 子节点的纯文本（用于从 <code> 子元素取回原始代码文本）。 */
export function nodeToText(node: any): string {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(nodeToText).join('');
  if (React.isValidElement(node)) return nodeToText((node.props as any)?.children);
  return '';
}
