const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export interface SessionSummary {
  session_id: string;
  title: string;
  summary: string | null;
  updated_at: string;
}

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
}

export function createHistoryClient(
  gatewayUrl: string,
  headers?: () => Record<string, string> | Promise<Record<string, string>>
) {
  const base = gatewayUrl.replace(/\/+$/, '');
  const call = async (path: string, init?: RequestInit) => {
    const extraHeaders = headers ? await headers() : {};
    const res = await fetch(`${base}${path}`, {
      ...init,
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        ...extraHeaders,
      },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };
  return {
    list: async (): Promise<SessionSummary[]> =>
      ((await call('/sessions')).sessions ?? []).filter((s: SessionSummary) => UUID.test(s.session_id)),
    create: async (): Promise<string | null> => {
      const s = await call('/sessions', { method: 'POST', body: '{}' });
      return UUID.test(s?.session_id) ? s.session_id : null;
    },
    messages: async (id: string): Promise<HistoryMessage[]> => {
      if (!UUID.test(id)) return [];
      const data = await call(`/sessions/${encodeURIComponent(id)}/messages`);
      return (data.messages ?? [])
        .filter((m: any) => (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string')
        .map((m: any) => ({ role: m.role, content: m.content.slice(0, 6000) }));
    },
  };
}

export type HistoryClient = ReturnType<typeof createHistoryClient>;

