// 与后端 Pydantic 模型对应的类型（src/miniclaw/app/models.py）

export interface SessionInfo {
  session_id: string;
  created_at?: string | null;
  updated_at?: string | null;
  messages: number;
  summary: string;
  current: boolean;
}

export interface SkillItem {
  name: string;
  description: string;
  path?: string;
}

export interface ConfigPayload {
  provider: string;
  model: string | null;
  api_key_masked: string;
  base_url: string | null;
  custom_llm_provider: string | null;
  temperature: number | null;
  max_tokens: number | null;
  runtime_mode: 'agent' | 'chat';
  web_search_enabled: boolean;
}

export interface BalanceInfo {
  ok: boolean;
  error: string | null;
  is_available: boolean | null;
  currency: string | null;
  total_balance: number | null;
  granted_balance: number | null;
  topped_up_balance: number | null;
  baseline_balance: number | null;
  session_spent: number | null;
}

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
  turns: number;
}

export interface ContextInfo {
  used_tokens: number;
  window: number;
  soft: number;
  hard: number;
  overrides: Record<string, number>;
}

export type ChatRole = 'user' | 'assistant' | 'system' | 'tool';

export interface ToolCallInfo {
  id?: string;
  function?: { name?: string; arguments?: string | Record<string, unknown> };
}

export type ChatStreamEvent =
  | { event: 'meta'; data: { session_id: string; model: string; runtime_mode: string; injected_skills: string[] } }
  | { event: 'reasoning'; data: { delta: string } }
  | { event: 'chunk'; data: { delta: string } }
  | { event: 'tool_call'; data: ToolCallInfo }
  | { event: 'tool_result'; data: { tool_call_id?: string; name?: string; content: string; is_error: boolean } }
  | { event: 'done'; data: { finish_reason: string; prompt_tokens?: number; completion_tokens?: number; total_tokens?: number; cost_usd?: number } }
  | { event: 'error'; data: { error: string } };
