import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createHistoryClient } from './history';

describe('createHistoryClient', () => {
  const origFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = origFetch;
  });

  const validUuid = '12345678-1234-1234-1234-123456789abc';

  it('bad IDs never hit the network in messages()', async () => {
    const mockFetch = vi.fn();
    global.fetch = mockFetch;

    const client = createHistoryClient('/api/ghost-cursor');

    const badIds = [
      'not-a-uuid',
      '12345',
      '../escape/path',
      '12345678-1234-1234-1234-123456789abcz',
      '',
    ];

    for (const badId of badIds) {
      const res = await client.messages(badId);
      expect(res).toEqual([]);
    }

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('messages() drops unknown roles and non-string content and caps at 6000 chars', async () => {
    const longContent = 'A'.repeat(7000);
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        messages: [
          { role: 'user', content: 'What sizes are available?' },
          { role: 'system', content: 'System instruction' },
          { role: 'tool', content: 'tool execution output' },
          { role: 'assistant', content: 42 },
          { role: 'assistant', content: null },
          { role: 'assistant', content: undefined },
          { role: 'assistant', content: { text: 'object content' } },
          { role: 'assistant', content: 'Size 10 and 11 are in stock.' },
          { role: 'user', content: longContent },
        ],
      }),
    });

    const client = createHistoryClient('/api/ghost-cursor');
    const msgs = await client.messages(validUuid);

    expect(msgs).toEqual([
      { role: 'user', content: 'What sizes are available?' },
      { role: 'assistant', content: 'Size 10 and 11 are in stock.' },
      { role: 'user', content: 'A'.repeat(6000) },
    ]);
  });

  it('create() returns null for a non-UUID response', async () => {
    const client = createHistoryClient('/api/ghost-cursor');

    // Case 1: non-UUID string
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ session_id: 'not-valid-uuid' }),
    });
    expect(await client.create()).toBeNull();

    // Case 2: empty object
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });
    expect(await client.create()).toBeNull();

    // Case 3: null
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => null,
    });
    expect(await client.create()).toBeNull();

    // Case 4: valid UUID
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ session_id: validUuid }),
    });
    expect(await client.create()).toBe(validUuid);
  });

  it('list() filters out invalid UUID sessions', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        sessions: [
          { session_id: validUuid, title: 'Chat 1', summary: 'Summary 1', updated_at: '2026-10-17T20:00:00Z' },
          { session_id: 'invalid-id', title: 'Chat 2', summary: null, updated_at: '2026-10-17T20:00:00Z' },
          { session_id: '87654321-4321-4321-4321-cba987654321', title: 'Chat 3', summary: null, updated_at: '2026-10-17T20:00:00Z' },
        ],
      }),
    });

    const client = createHistoryClient('/api/ghost-cursor');
    const sessions = await client.list();

    expect(sessions).toHaveLength(2);
    expect(sessions[0].session_id).toBe(validUuid);
    expect(sessions[1].session_id).toBe('87654321-4321-4321-4321-cba987654321');
  });

  it('forwards custom headers and credentials', async () => {
    let capturedHeaders: any = null;
    let capturedCredentials: any = null;

    global.fetch = vi.fn().mockImplementation((url, init) => {
      capturedHeaders = init?.headers;
      capturedCredentials = init?.credentials;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ sessions: [] }),
      });
    });

    const client = createHistoryClient('/api/ghost-cursor', async () => ({
      'X-Custom-Tenant': 'tenant_abc',
    }));

    await client.list();

    expect(capturedCredentials).toBe('same-origin');
    expect(capturedHeaders).toEqual({
      'Content-Type': 'application/json',
      'X-Custom-Tenant': 'tenant_abc',
    });
  });

  it('throws an error on non-ok HTTP responses', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    });

    const client = createHistoryClient('/api/ghost-cursor');
    await expect(client.list()).rejects.toThrow('HTTP 500');
  });
});

