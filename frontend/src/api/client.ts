import type { ChatStreamEvent } from './types';

declare global {
  interface Window {
    miniclaw?: {
      getConnection: () => Promise<{ baseUrl: string; token: string }>;
      getBackendInfo: () => Promise<{ baseUrl: string; token: string; external: boolean }>;
    };
  }
}

interface Connection {
  baseUrl: string;
  token: string;
}

let conn: Connection | null = null;

export async function getConnection(): Promise<Connection> {
  if (conn) return conn;
  try {
    if (window.miniclaw?.getConnection) {
      conn = await window.miniclaw.getConnection();
    }
  } catch (e) {
    // ignore
  }
  if (!conn || !conn.baseUrl) {
    conn = { baseUrl: 'http://127.0.0.1:7909', token: '' };
  }
  return conn;
}

function headers(token: string, json = true): Record<string, string> {
  const h: Record<string, string> = {};
  if (json) h['Content-Type'] = 'application/json';
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

export async function apiGet<T>(path: string): Promise<T> {
  const { baseUrl, token } = await getConnection();
  const res = await fetch(`${baseUrl}${path}`, { headers: headers(token, false) });
  if (!res.ok) throw new Error(`GET ${path} -> HTTP ${res.status}`);
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const { baseUrl, token } = await getConnection();
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: headers(token),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} -> HTTP ${res.status}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

export async function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  const { baseUrl, token } = await getConnection();
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'PATCH',
    headers: headers(token),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} -> HTTP ${res.status}`);
  const text = await res.text();
  return (text ? JSON.parse(text) : {}) as T;
}

// ---------------------------------------------------------------------------
// SSE：fetch + ReadableStream 自解析（原生 EventSource 仅支持 GET）
// ---------------------------------------------------------------------------
function parseFrame(frame: string): ChatStreamEvent | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  let data: unknown = {};
  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch {
    data = { raw: dataLines.join('\n') };
  }
  return { event, data } as ChatStreamEvent;
}

export interface StreamHandlers {
  onEvent: (evt: ChatStreamEvent) => void;
}

export async function streamChat(
  body: { session_id: string; message: string; model?: string | null; mode?: string | null },
  handlers: StreamHandlers,
  signal?: AbortSignal
): Promise<void> {
  const { baseUrl, token } = await getConnection();
  const res = await fetch(`${baseUrl}/api/chat/stream`, {
    method: 'POST',
    headers: { ...headers(token), Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(`chat stream -> HTTP ${res.status}`);
  if (!res.body) throw new Error('响应体为空，无法读取流');

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      if (!frame.trim()) continue;
      const evt = parseFrame(frame);
      if (evt) handlers.onEvent(evt);
    }
  }
}
