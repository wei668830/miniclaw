// 「交互确认选项块」解析（约定见 design/electron-gui/07-界面优化.md 9.4.1）
//
// 模型在需要用户确认/选择时，于回复末尾输出语言标记为 choice 的代码块：
//
// ```choice
// 继续 :: 确认，请按当前方案继续
// 取消 :: 先不执行
// ```
//
// 每行一个选项；行文本既是按钮文案，也是点击后发送的内容；
// 支持 `标签 :: 发送内容` 以区分短标签与较长回复。

export interface ChoiceOption {
  label: string;
  value: string;
}

// 匹配 ```choice ... ``` 代码块（允许缩进与 CRLF）
const CHOICE_BLOCK_RE = /```choice[ \t]*\r?\n([\s\S]*?)```/;

/** 从 assistant 文本中解析出选项，并返回剥离选项块后的正文。 */
export function parseChoice(content: string): { text: string; options: ChoiceOption[] } {
  if (!content || !content.includes('```choice')) return { text: content || '', options: [] };

  const match = content.match(CHOICE_BLOCK_RE);
  if (!match) return { text: content, options: [] };

  const options: ChoiceOption[] = [];
  for (const raw of match[1].split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    const sep = line.indexOf('::');
    if (sep >= 0) {
      const label = line.slice(0, sep).trim();
      const value = line.slice(sep + 2).trim();
      options.push({ label: label || value, value: value || label });
    } else {
      options.push({ label: line, value: line });
    }
  }

  const text = content.replace(CHOICE_BLOCK_RE, '').trim();
  return { text, options };
}
