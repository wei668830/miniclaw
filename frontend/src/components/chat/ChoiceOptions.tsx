import React from 'react';
import type { ChoiceOption } from './choice';

/**
 * 交互确认选项按钮组：点击即以该选项内容作为用户消息发送。
 *
 * @param options       选项列表
 * @param disabled      是否禁用全部（如流式进行中）
 * @param answeredValue 已回答的选项 value；非空表示该轮已作答，全部禁用并高亮命中项
 * @param onChoose      点击回调，参数为该选项的发送内容
 */
export const ChoiceOptions: React.FC<{
  options: ChoiceOption[];
  disabled?: boolean;
  answeredValue?: string | null;
  onChoose: (value: string) => void;
}> = ({ options, disabled, answeredValue, onChoose }) => {
  if (!options.length) return null;
  const answered = answeredValue != null;
  return (
    <div className="choice-options">
      {options.map((o, i) => {
        const hit = answered && answeredValue === o.value;
        return (
          <button
            key={i}
            className={`btn choice ${hit ? 'answered' : ''}`}
            disabled={disabled || answered}
            title={o.value}
            onClick={() => onChoose(o.value)}
          >
            {hit ? `✓ ${o.label}` : o.label}
          </button>
        );
      })}
    </div>
  );
};
