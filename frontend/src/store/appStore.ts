import { create } from 'zustand';
import { apiGet, apiPost, apiPatch, streamChat } from '../api/client';
import type { BalanceInfo, ChatStreamEvent, ConfigPayload, ContextInfo, SessionInfo, SkillItem, UsageInfo } from '../api/types';

export interface UIToolCall {
  id?: string;
  name?: string;
  args?: string;
  result?: string;
  isError?: boolean;
  status: 'running' | 'done';
}

export interface UIMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  reasoning?: string;
  toolCalls?: UIToolCall[];
  injectedSkills?: string[];
  streaming?: boolean;
  error?: string;
}

let seq = 0;
const uid = () => `m${Date.now()}-${seq++}`;

interface AppState {
  ready: boolean;
  statusText: string;
  sessions: SessionInfo[];
  currentSessionId: string | null;
  messages: UIMessage[];
  streaming: boolean;
  skills: SkillItem[];
  loadedSkills: { name: string; description: string }[];
  config: ConfigPayload | null;
  context: ContextInfo | null;
  usage: UsageInfo | null;
  balance: BalanceInfo | null;
  abortController: AbortController | null;

  init: () => Promise<void>;
  refreshSessions: () => Promise<void>;
  refreshSkills: () => Promise<void>;
  refreshConfig: () => Promise<void>;
  refreshContext: () => Promise<void>;
  refreshUsage: () => Promise<void>;
  refreshBalance: () => Promise<void>;
  createSession: () => Promise<void>;
  activateSession: (id: string) => Promise<void>;
  loadSkills: (names: string[]) => Promise<{ pending: string[]; already_loaded: string[] }>;
  sendMessage: (text: string) => Promise<void>;
  stopStream: () => void;
  setMode: (mode: 'agent' | 'chat') => Promise<void>;
  setWebSearch: (enabled: boolean) => Promise<void>;
  updateConfig: (patch: Partial<ConfigPayload> & { api_key?: string }) => Promise<void>;
  pushSystem: (text: string) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  ready: false,
  statusText: '就绪',
  sessions: [],
  currentSessionId: null,
  messages: [],
  streaming: false,
  skills: [],
  loadedSkills: [],
  config: null,
  context: null,
  usage: null,
  balance: null,
  abortController: null,

  init: async () => {
    try {
      set({ statusText: '正在载入会话与技能...' });
      await get().refreshSessions();
      let current = get().currentSessionId;
      if (!current) {
        await get().createSession();
      } else {
        const snapshot = await apiGet<{ messages: any[] }>(`/api/sessions/${current}`);
        set({ messages: mapHistory(snapshot.messages || []) });
      }
      await get().refreshSkills();
      await get().refreshConfig();
      await get().refreshContext();
      await get().refreshUsage();
      await get().refreshBalance();
      set({ ready: true, statusText: '就绪' });
    } catch (e: any) {
      set({ statusText: `初始化失败: ${e?.message || e}` });
    }
  },

  refreshSessions: async () => {
    const data = await apiGet<{ sessions: SessionInfo[]; current_session_id: string | null }>('/api/sessions');
    set({ sessions: data.sessions, currentSessionId: data.current_session_id });
  },

  refreshSkills: async () => {
    const { currentSessionId } = get();
    const data = await apiGet<{ skills: SkillItem[] }>('/api/skills');
    let loaded: { name: string; description: string }[] = [];
    if (currentSessionId) {
      const l = await apiGet<{ skills_loaded: { name: string; description: string }[] }>(
        `/api/skills/loaded?session_id=${currentSessionId}`
      );
      loaded = l.skills_loaded;
    }
    set({ skills: data.skills, loadedSkills: loaded });
  },

  refreshConfig: async () => {
    const config = await apiGet<ConfigPayload>('/api/config');
    set({ config });
  },

  refreshContext: async () => {
    const { currentSessionId } = get();
    if (!currentSessionId) return;
    const context = await apiGet<ContextInfo>(`/api/context?session_id=${currentSessionId}`);
    set({ context });
  },

  refreshUsage: async () => {
    const { currentSessionId } = get();
    if (!currentSessionId) return;
    try {
      const usage = await apiGet<UsageInfo>(`/api/chat/cost?session_id=${currentSessionId}`);
      set({ usage });
    } catch {
      /* ignore */
    }
  },

  refreshBalance: async () => {
    const { currentSessionId } = get();
    if (!currentSessionId) return;
    try {
      const balance = await apiGet<BalanceInfo>(`/api/chat/balance?session_id=${currentSessionId}`);
      set({ balance });
    } catch {
      /* ignore */
    }
  },

  createSession: async () => {
    const data = await apiPost<{ session_id: string; skills_loaded: any[] }>('/api/sessions', { activate: true });
    set({
      currentSessionId: data.session_id,
      messages: [],
      loadedSkills: [],
      usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, cost_usd: 0, turns: 0 },
      balance: null,
    });
    await get().refreshSessions();
    await get().refreshSkills();
    await get().refreshContext();
    await get().refreshUsage();
    await get().refreshBalance();
  },

  activateSession: async (id: string) => {
    if (get().streaming) return;
    await apiPost(`/api/sessions/${id}/activate`);
    const snapshot = await apiGet<{ messages: any[]; skills_loaded: any[] }>(`/api/sessions/${id}`);
    set({
      currentSessionId: id,
      messages: mapHistory(snapshot.messages || []),
      loadedSkills: snapshot.skills_loaded || [],
    });
    await get().refreshSessions();
    await get().refreshUsage();
    await get().refreshBalance();
  },

  loadSkills: async (names: string[]) => {
    const { currentSessionId } = get();
    if (!currentSessionId) return { pending: [], already_loaded: [] };
    const res = await apiPost<{ pending: string[]; already_loaded: string[]; skills_loaded: any[] }>(
      '/api/skills/load',
      { session_id: currentSessionId, names }
    );
    await get().refreshSkills();
    return { pending: res.pending, already_loaded: res.already_loaded };
  },

  sendMessage: async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || get().streaming) return;
    const { currentSessionId } = get();
    if (!currentSessionId) return;

    const userMsg: UIMessage = { id: uid(), role: 'user', content: trimmed };
    const assistantId = uid();
    const assistantMsg: UIMessage = { id: assistantId, role: 'assistant', content: '', streaming: true, toolCalls: [] };
    set({ messages: [...get().messages, userMsg, assistantMsg], streaming: true, statusText: '生成中...' });

    const controller = new AbortController();
    set({ abortController: controller });

    const update = (patch: Partial<UIMessage>) => {
      set({
        messages: get().messages.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)),
      });
    };
    const getAssistant = () => get().messages.find((m) => m.id === assistantId)!;

    try {
      await streamChat(
        { session_id: currentSessionId, message: trimmed, mode: get().config?.runtime_mode },
        {
          onEvent: (evt: ChatStreamEvent) => {
            const a = getAssistant();
            switch (evt.event) {
              case 'meta':
                if (evt.data.injected_skills?.length) update({ injectedSkills: evt.data.injected_skills });
                break;
              case 'reasoning':
                update({ reasoning: (a.reasoning || '') + evt.data.delta });
                break;
              case 'chunk':
                update({ content: a.content + evt.data.delta });
                break;
              case 'tool_call': {
                const fn = evt.data.function || {};
                const calls = [...(a.toolCalls || []), {
                  id: evt.data.id,
                  name: fn.name,
                  args: typeof fn.arguments === 'string' ? fn.arguments : JSON.stringify(fn.arguments, null, 2),
                  status: 'running' as const,
                }];
                update({ toolCalls: calls });
                break;
              }
              case 'tool_result': {
                const calls = (a.toolCalls || []).map((tc) =>
                  tc.id === evt.data.tool_call_id
                    ? { ...tc, result: evt.data.content, isError: evt.data.is_error, status: 'done' as const }
                    : tc
                );
                update({ toolCalls: calls });
                break;
              }
              case 'done': {
                const d = evt.data as any;
                if (d.session_cost_usd !== undefined) {
                  set({
                    usage: {
                      cost_usd: d.session_cost_usd,
                      total_tokens: d.session_total_tokens,
                      prompt_tokens: d.session_prompt_tokens,
                      completion_tokens: d.session_completion_tokens,
                      turns: d.session_turns,
                    },
                  });
                }
                update({ streaming: false });
                break;
              }
              case 'error':
                update({ error: evt.data.error, streaming: false });
                break;
            }
          },
        },
        controller.signal
      );
    } catch (e: any) {
      if (e?.name === 'AbortError') {
        update({ streaming: false, content: getAssistant().content + '\n\n[已停止]' });
      } else {
        update({ error: e?.message || String(e), streaming: false });
      }
    } finally {
      set({ streaming: false, abortController: null, statusText: '就绪' });
      try {
        await Promise.all([
          get().refreshContext(),
          get().refreshSessions(),
          get().refreshSkills(),
          get().refreshBalance(),
        ]);
      } catch {
        /* ignore */
      }
    }
  },

  stopStream: () => {
    const c = get().abortController;
    if (c) c.abort();
  },

  setMode: async (mode) => {
    await apiPost('/api/config/mode', { mode });
    await get().refreshConfig();
  },

  setWebSearch: async (enabled) => {
    await apiPost('/api/config/web-search', { enabled });
    await get().refreshConfig();
  },

  updateConfig: async (patch) => {
    await apiPatch('/api/config', patch);
    await get().refreshConfig();
  },

  pushSystem: (text: string) => {
    set({ messages: [...get().messages, { id: uid(), role: 'system', content: text }] });
  },
}));

// 去掉注入的用户消息中的「完整系统提示词」前缀与「技能注入块」，仅保留用户原始输入
export function cleanUserText(content: string): string {
  let text = content || '';
  const marker = '【用户最新输入】';
  if (text.includes(marker)) text = text.split(marker).pop() || '';
  const skillMarker = '**【技能名称：';
  if (text.includes(skillMarker)) text = text.split(skillMarker)[0];
  return text.trim();
}

// 把后端历史消息映射为 UI 消息（过滤 system、合并 reasoning/tool）
function mapHistory(messages: any[]): UIMessage[] {
  const out: UIMessage[] = [];
  for (const m of messages) {
    const role = m.role;
    if (role === 'system') continue;
    if (role === 'user') {
      const text = cleanUserText(typeof m.content === 'string' ? m.content : '');
      if (text) out.push({ id: uid(), role: 'user', content: text });
      continue;
    }
    if (role === 'assistant') {
      if (m.tool_calls) {
        out.push({
          id: uid(),
          role: 'assistant',
          content: m.content || '',
          toolCalls: (m.tool_calls || []).map((tc: any) => ({
            id: tc.id,
            name: tc.function?.name,
            args: tc.function?.arguments,
            status: 'done' as const,
          })),
        });
      } else if (typeof m.content === 'string' && m.content) {
        out.push({ id: uid(), role: 'assistant', content: m.content, reasoning: m.reasoning_content });
      }
      continue;
    }
    if (role === 'tool') {
      const last = out[out.length - 1];
      if (last && last.role === 'assistant' && last.toolCalls?.length) {
        const tc = last.toolCalls.find((t) => t.status === 'done' && t.result === undefined) || last.toolCalls[last.toolCalls.length - 1];
        if (tc) tc.result = typeof m.content === 'string' ? m.content : JSON.stringify(m.content);
      }
    }
  }
  return out;
}
