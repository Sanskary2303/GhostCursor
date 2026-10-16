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
});

