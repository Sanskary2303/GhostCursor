import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HttpTransport } from './transport/Transport';
import type { BrowserStartRequest } from './types';

describe('HttpTransport', () => {
  const origFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = origFetch;
  });

  const sampleRequest: BrowserStartRequest = {
    command: 'start',
    protocolVersion: '1',
    requestId: 'req-1',
    message: 'Hello',
    context: { page: 'home', values: {}, availableTargets: [] },
  };

  it('maps JSON error payload to Error with error code string', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ error: 'unauthorized_tenant' }),
    });

    const onError = vi.fn();
    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      onError,
    });

    await expect(transport.send(sampleRequest)).rejects.toThrow('unauthorized_tenant');
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'unauthorized_tenant' }));
  });

  it('maps non-JSON error to Error with HTTP status code', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => {
        throw new Error('Not JSON');
      },
    });

    const onError = vi.fn();
    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      onError,
    });

    await expect(transport.send(sampleRequest)).rejects.toThrow('HTTP 502');
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'HTTP 502' }));
  });

  it('successfully delivers PublicResponse on 200 OK', async () => {
    const mockResponse = {
      protocolVersion: '1',
      runId: 'run-123',
      revision: 1,
      status: 'awaiting_answer',
      reply: 'How can I help?',
      actions: [],
      questions: [],
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockResponse,
    });

    const onMessage = vi.fn();
    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      onMessage,
    });

    await transport.send(sampleRequest);
    expect(onMessage).toHaveBeenCalledWith(mockResponse);
  });

  it('emits error and rejects when fetch throws network error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));

    const onError = vi.fn();
    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      onError,
    });

    await expect(transport.send(sampleRequest)).rejects.toThrow('Failed to fetch');
    expect(onError).toHaveBeenCalled();
  });

  it('handles SSE stream with status, deltas, and envelope', async () => {
    const sseText =
      'event: status\ndata: {"status": "thinking"}\n\n' +
      'event: delta\ndata: {"delta": "Hello "}\n\n' +
      'event: delta\ndata: {"delta": "world!"}\n\n' +
      'event: envelope\ndata: {"protocolVersion": "1", "runId": "run-1", "revision": 1, "status": "completed", "reply": "Hello world!", "actions": [], "questions": []}\n\n';

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(sseText));
        controller.close();
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: (h: string) => (h.toLowerCase() === 'content-type' ? 'text/event-stream' : null),
      },
      body: stream,
    });

    const onMessage = vi.fn();
    const statuses: string[] = [];
    const deltas: string[] = [];

    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      streaming: true,
      onMessage,
    });

    transport.on('status', (e: any) => statuses.push(e.status));
    transport.on('delta', (e: any) => deltas.push(e.delta));

    await transport.send(sampleRequest);

    expect(global.fetch).toHaveBeenCalledWith(
      '/api/ghost',
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'text/event-stream',
        }),
      })
    );
    expect(statuses).toEqual(['thinking']);
    expect(deltas).toEqual(['Hello ', 'world!']);
    expect(onMessage).toHaveBeenCalledWith(
      expect.objectContaining({ reply: 'Hello world!' })
    );
  });

  it('rejects when SSE stream emits error event', async () => {
    const sseText = 'event: error\ndata: {"error": "disclosure_blocked"}\n\n';

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(sseText));
        controller.close();
      },
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: {
        get: (h: string) => (h.toLowerCase() === 'content-type' ? 'text/event-stream' : null),
      },
      body: stream,
    });

    const transport = new HttpTransport({
      gatewayUrl: '/api/ghost',
      streaming: true,
    });

    await expect(transport.send(sampleRequest)).rejects.toThrow('disclosure_blocked');
  });
});

