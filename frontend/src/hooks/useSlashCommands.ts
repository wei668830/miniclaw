import { useAppStore } from '../store/appStore';

export interface SlashCommand {
  name: string;
  summary: string;
  example: string;
}

// 与后端 CLI（src/miniclaw/cli/commands.py）语义对齐的常用命令子集
export const SLASH_COMMANDS: SlashCommand[] = [
  { name: 'help', summary: '显示帮助信息', example: '/help' },
  { name: 'new', summary: '新建会话（唯一可重置技能的方式）', example: '/new' },
  { name: 'skill-list', summary: '列出可用技能', example: '/skill-list' },
  { name: 'skill-load', summary: '加载技能（对话式，下条消息生效）', example: '/skill-load web-search' },
  { name: 'session-list', summary: '列出最近会话', example: '/session-list' },
  { name: 'agent', summary: '切换为代理模式', example: '/agent' },
  { name: 'chat', summary: '切换为对话模式', example: '/chat' },
  { name: 'web-search', summary: '联网搜索开关', example: '/web-search on' },
  { name: 'cost', summary: '查看本次对话费用（官方口径）', example: '/cost' },
  { name: 'balance', summary: '查询账户余额（官方）', example: '/balance' },
  { name: 'clear', summary: '清空当前会话上下文', example: '/clear' },
];

function helpText(): string {
  const lines = ['可用命令：', ''];
  for (const c of SLASH_COMMANDS) lines.push(`/${c.name}  —  ${c.summary}   例：${c.example}`);
  return lines.join('\n');
}

export function useSlashCommands() {
  const pushSystem = useAppStore((s) => s.pushSystem);

  async function run(raw: string): Promise<boolean> {
    const text = raw.trim();
    if (!text.startsWith('/')) return false;
    const parts = text.slice(1).split(/\s+/);
    const cmd = (parts.shift() || '').toLowerCase();
    const arg = parts.join(' ');
    const store = useAppStore.getState();

    switch (cmd) {
      case 'help':
        pushSystem(helpText());
        return true;
      case 'new':
        await store.createSession();
        pushSystem('已新建会话，技能加载状态已重置。');
        return true;
      case 'skill-list': {
        const { skills } = store;
        pushSystem(
          '可用技能：\n' +
            (skills.length
              ? skills.map((s) => `- ${s.name}：${s.description}`).join('\n')
              : '（未发现技能）')
        );
        return true;
      }
      case 'skill-load': {
        if (!arg) {
          pushSystem('用法：/skill-load <skill-name>[,<skill-name>...]');
          return true;
        }
        const names = arg.split(',').map((s) => s.trim()).filter(Boolean);
        const res = await store.loadSkills(names);
        const parts2: string[] = [];
        if (res.pending.length) parts2.push(`已加载：${res.pending.join('，')}（将在下一条消息中生效）`);
        if (res.already_loaded.length) parts2.push(`已加载过（忽略）：${res.already_loaded.join('，')}`);
        pushSystem(parts2.join('\n') || '未匹配到技能');
        return true;
      }
      case 'session-list': {
        await store.refreshSessions();
        const { sessions } = useAppStore.getState();
        pushSystem(
          '会话列表：\n' +
            sessions
              .map((s) => `${s.current ? '*' : ' '} ${s.session_id}  ${s.summary || '(空)'}`)
              .join('\n')
        );
        return true;
      }
      case 'agent':
        await store.setMode('agent');
        pushSystem('已切换为代理模式。');
        return true;
      case 'chat':
        await store.setMode('chat');
        pushSystem('已切换为对话模式。');
        return true;
      case 'web-search': {
        const on = arg.trim().toLowerCase() === 'on';
        await store.setWebSearch(on);
        pushSystem(`联网搜索已${on ? '开启' : '关闭'}。`);
        return true;
      }
      case 'cost': {
        await Promise.all([store.refreshUsage(), store.refreshBalance()]);
        const s = useAppStore.getState();
        const b = s.balance;
        const u = s.usage;
        const lines: string[] = [];
        if (b && b.ok) {
          lines.push(`会话官方花费：${b.session_spent} ${b.currency}（余额差值，含缓存命中折扣）`);
          lines.push(`当前余额：${b.total_balance} ${b.currency}`);
        } else if (b) {
          lines.push(`官方花费查询失败：${b.error || '未知错误'}`);
        }
        if (u) {
          lines.push(
            `累计 tokens：${u.total_tokens}（输入 ${u.prompt_tokens} / 输出 ${u.completion_tokens}，共 ${u.turns} 次调用）`
          );
        }
        pushSystem(lines.join('\n') || '暂无数据。');
        return true;
      }
      case 'balance': {
        await store.refreshBalance();
        const b = useAppStore.getState().balance;
        if (!b || !b.ok) {
          pushSystem(`余额查询失败：${b?.error || '未知错误'}`);
        } else {
          pushSystem(
            `账户余额（${b.currency}）：${b.total_balance}\n` +
              `- 赠金：${b.granted_balance}\n` +
              `- 充值：${b.topped_up_balance}\n` +
              `- 可用：${b.is_available}`
          );
        }
        return true;
      }
      case 'clear':
        pushSystem('清空上下文请通过「新建会话」或后端 /clear（UI 暂以新建会话实现）。');
        return true;
      default:
        pushSystem(`未识别的命令：/${cmd}（输入 /help 查看帮助）`);
        return true;
    }
  }

  return { run, commands: SLASH_COMMANDS };
}
