import { describe, it, expect, vi, afterEach } from 'vitest';
import { TransportManager, type Transport, type TransportEvent, type TransportEventType } from './transport/Transport';
import type { BrowserRequest, PublicResponse } from './types';

class FakeTransport implements Transport {
  listeners: Map<TransportEventType, Set<(event: TransportEvent) => void>> = new Map();
  sentRequests: BrowserRequest[] = [];

  constructor() {
    for (const t of ['open', 'close', 'error', 'message', 'status', 'delta'] as TransportEventType[]) {
      this.listeners.set(t, new Set());
    }
  }

  async connect(): Promise<void> {}
  async send(request: BrowserRequest): Promise<void> {
    this.sentRequests.push(request);
  }
  close(): void {}
  isConnected(): boolean { return true; }

  on(type: TransportEventType, listener: (event: TransportEvent) => void): () => void {
    this.listeners.get(type)?.add(listener);
    return () => this.listeners.get(type)?.delete(listener);
  }

  emit(type: TransportEventType, event: TransportEvent): void {
    const list = this.listeners.get(type);
    if (list) {
      for (const fn of [...list]) {
        fn(event);
      }
    }
  }
}

describe('TransportManager idle timeout', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('re-arms timeout on status and resolves when message arrives past 30s', async () => {
    vi.useFakeTimers();
    const fakeTransport = new FakeTransport();
    const manager = new TransportManager(fakeTransport);

    const startPromise = manager.start('Hello', { page: 'home', values: {}, availableTargets: [] });

    // Advance 25s, emit status
    await vi.advanceTimersByTimeAsync(25000);
    fakeTransport.emit('status', { type: 'status', data: 'thinking' });

    // Advance another 25s (total 50s), emit status
    await vi.advanceTimersByTimeAsync(25000);
    fakeTransport.emit('status', { type: 'status', data: 'planning' });

    // Advance another 20s (total 70s), emit message
    await vi.advanceTimersByTimeAsync(20000);
    const mockEnvelope: PublicResponse = {
      protocolVersion: '1',
      runId: 'run-1',
      revision: 0,
      status: 'completed',
      reply: 'Done!',
      actions: [],
      questions: [],
    };
    fakeTransport.emit('message', { type: 'message', data: mockEnvelope });

    const result = await startPromise;
    expect(result).toEqual(mockEnvelope);
  });

  it('rejects with Request timeout at 30s when no events arrive', async () => {
    vi.useFakeTimers();
    const fakeTransport = new FakeTransport();
    const manager = new TransportManager(fakeTransport);

    const startPromise = manager.start('Hello', { page: 'home', values: {}, availableTargets: [] });

    let error: any = null;
    startPromise.catch(err => { error = err; });

    await vi.advanceTimersByTimeAsync(30000);

    await expect(startPromise).rejects.toThrow('Request timeout');
    expect(error?.message).toBe('Request timeout');
  });
});
