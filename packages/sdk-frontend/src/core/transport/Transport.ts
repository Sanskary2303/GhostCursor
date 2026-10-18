/**
 * Transport Layer - WebSocket and HTTP communication with the backend gateway
 * Handles connection management, reconnection, and message serialization
 */

import type { BrowserRequest, PublicResponse, ToolResult, Action } from '../types';

export interface TransportOptions {
  gatewayUrl: string;
  headers?: () => Record<string, string> | Promise<Record<string, string>>;
  streaming?: boolean;
  onStatus?: (status: string) => void;
  onDelta?: (delta: string) => void;
  onMessage?: (response: PublicResponse) => void;
  onError?: (error: Error) => void;
  onClose?: () => void;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

export interface Transport {
  connect(): Promise<void>;
  send(request: BrowserRequest): Promise<void>;
  close(): void;
  isConnected(): boolean;
  on(type: TransportEventType, listener: (event: TransportEvent) => void): () => void;
  off?(type: TransportEventType, listener: (event: TransportEvent) => void): void;
}

export type TransportEventType = 'open' | 'close' | 'error' | 'message' | 'status' | 'delta';

export interface TransportEvent {
  type: TransportEventType;
  data?: any;
  error?: Error;
}

/**
 * WebSocket Transport Implementation
 */
export class WebSocketTransport implements Transport {
  private options: Required<TransportOptions>;
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private messageQueue: BrowserRequest[] = [];
  private eventListeners: Map<TransportEventType, Set<(event: TransportEvent) => void>> = new Map();
  private isConnecting = false;
  private isClosed = false;

  constructor(options: TransportOptions) {
    this.options = {
      gatewayUrl: options.gatewayUrl,
      headers: options.headers || (() => ({ 'Content-Type': 'application/json' })),
      streaming: options.streaming ?? false,
      onStatus: options.onStatus || (() => {}),
      onDelta: options.onDelta || (() => {}),
      onMessage: options.onMessage || (() => {}),
      onError: options.onError || (() => {}),
      onClose: options.onClose || (() => {}),
      reconnect: options.reconnect ?? true,
      reconnectInterval: options.reconnectInterval ?? 3000,
      maxReconnectAttempts: options.maxReconnectAttempts ?? 10,
    };

    // Initialize event listener map
    for (const type of ['open', 'close', 'error', 'message'] as TransportEventType[]) {
      this.eventListeners.set(type, new Set());
    }
  }

  async connect(): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;

    try {
      // Convert HTTP URL to WebSocket URL
      let wsUrl = this.options.gatewayUrl;
      if (wsUrl.startsWith('http://')) {
        wsUrl = wsUrl.replace(/^http:\/\//, 'ws://');
      } else if (wsUrl.startsWith('https://')) {
        wsUrl = wsUrl.replace(/^https:\/\//, 'wss://');
      } else if (!wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
        if (typeof window === 'undefined' || !window.location.host) {
          throw new Error('WebSocket transport needs a browser');
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        wsUrl = `${protocol}//${host}${wsUrl.startsWith('/') ? '' : '/'}${wsUrl}`;
      }

      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = async () => {
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.emit('open', { type: 'open' });

        // Send queued messages
        for (const msg of this.messageQueue) {
          this.sendInternal(msg);
        }
        this.messageQueue = [];
      };

      this.ws.onmessage = async (event) => {
        try {
          const response = JSON.parse(event.data) as PublicResponse;
          this.emit('message', { type: 'message', data: response });
          this.options.onMessage(response);
        } catch (error) {
          console.error('[WebSocketTransport] Failed to parse message:', error);
          this.emit('error', { type: 'error', error: error as Error });
        }
      };

      this.ws.onerror = (event) => {
        this.isConnecting = false;
        const error = new Error('WebSocket error');
        this.emit('error', { type: 'error', error });
        this.options.onError(error);
      };

      this.ws.onclose = () => {
        this.isConnecting = false;
        this.emit('close', { type: 'close' });
        this.options.onClose();

        if (this.options.reconnect && !this.isClosed && this.reconnectAttempts < this.options.maxReconnectAttempts) {
          this.scheduleReconnect();
        }
      };
    } catch (error) {
      this.isConnecting = false;
      throw error;
    }
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts++;
    const delay = this.options.reconnectInterval * Math.min(this.reconnectAttempts, 5); // Cap at 5x

    this.reconnectTimer = setTimeout(() => {
      this.connect().catch(err => {
        console.error('[WebSocketTransport] Reconnection failed:', err);
      });
    }, delay);
  }

  async send(request: BrowserRequest): Promise<void> {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendInternal(request);
    } else {
      // Queue message for when connection is established
      this.messageQueue.push(request);
      if (!this.isConnecting && !this.isClosed) {
        await this.connect();
      }
    }
  }

  private sendInternal(request: BrowserRequest): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const headers = this.options.headers();
      const payload = { ...request, headers };
      this.ws.send(JSON.stringify(payload));
    }
  }

  close(): void {
    this.isClosed = true;

    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.messageQueue = [];
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Event emitter methods
   */
  on(type: TransportEventType, listener: (event: TransportEvent) => void): () => void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      listeners.add(listener);
    }
    return () => this.off(type, listener);
  }

  off(type: TransportEventType, listener: (event: TransportEvent) => void): void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      listeners.delete(listener);
    }
  }

  private emit(type: TransportEventType, event: TransportEvent): void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      for (const listener of listeners) {
        try {
          listener(event);
        } catch (error) {
          console.error(`[WebSocketTransport] Listener error for ${type}:`, error);
        }
      }
    }
  }
}

/**
 * HTTP Transport Implementation (fallback for environments without WebSocket support)
 */
export class HttpTransport implements Transport {
  private options: Required<TransportOptions>;
  private isClosed = false;
  private abortControllers: Set<AbortController> = new Set();

  private eventListeners: Map<TransportEventType, Set<(event: TransportEvent) => void>> = new Map();

  constructor(options: TransportOptions) {
    this.options = {
      gatewayUrl: options.gatewayUrl,
      headers: options.headers || (() => ({ 'Content-Type': 'application/json' })),
      streaming: options.streaming ?? false,
      onStatus: options.onStatus || (() => {}),
      onDelta: options.onDelta || (() => {}),
      onMessage: options.onMessage || (() => {}),
      onError: options.onError || (() => {}),
      onClose: options.onClose || (() => {}),
      reconnect: false,
      reconnectInterval: 0,
      maxReconnectAttempts: 0,
    };

    for (const type of ['open', 'close', 'error', 'message', 'status', 'delta'] as TransportEventType[]) {
      this.eventListeners.set(type, new Set());
    }
  }

  on(type: TransportEventType, listener: (event: TransportEvent) => void): () => void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      listeners.add(listener);
    }
    return () => this.off(type, listener);
  }

  off(type: TransportEventType, listener: (event: TransportEvent) => void): void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      listeners.delete(listener);
    }
  }

  private emit(type: TransportEventType, event: TransportEvent): void {
    const listeners = this.eventListeners.get(type);
    if (listeners) {
      for (const listener of listeners) {
        try {
          listener(event);
        } catch (error) {
          console.error(`[HttpTransport] Listener error for ${type}:`, error);
        }
      }
    }
  }

  async connect(): Promise<void> { this.emit('open', { type: 'open' }); }

  private async readEventStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let finalEnvelope: PublicResponse | null = null;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const trimmed = part.trim();
          if (!trimmed) continue;

          let eventType = 'message';
          let dataStr = '';

          for (const line of trimmed.split('\n')) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              dataStr = line.slice(5).trim();
            }
          }

          if (eventType === 'status') {
            try {
              const parsed = JSON.parse(dataStr);
              const st = typeof parsed === 'string' ? parsed : (parsed.status || parsed.text);
              if (st) {
                this.emit('status', { type: 'status', data: st, status: st } as any);
                this.options.onStatus?.(st);
              }
            } catch {
              this.emit('status', { type: 'status', data: dataStr, status: dataStr } as any);
              this.options.onStatus?.(dataStr);
            }
          } else if (eventType === 'delta') {
            try {
              const parsed = JSON.parse(dataStr);
              const delta = typeof parsed === 'string' ? parsed : (parsed.delta ?? parsed.text);
              if (delta) {
                this.emit('delta', { type: 'delta', data: delta, delta } as any);
                this.options.onDelta?.(delta);
              }
            } catch {
              this.emit('delta', { type: 'delta', data: dataStr, delta: dataStr } as any);
              this.options.onDelta?.(dataStr);
            }
          } else if (eventType === 'envelope') {
            const data = JSON.parse(dataStr) as PublicResponse;
            finalEnvelope = data;
            this.emit('message', { type: 'message', data });
            this.options.onMessage(data);
          } else if (eventType === 'error') {
            let errMsg = 'streaming_error';
            try {
              const parsed = JSON.parse(dataStr);
              errMsg = parsed.error || errMsg;
            } catch {
              errMsg = dataStr || errMsg;
            }
            throw new Error(errMsg);
          }
        }
      }

      if (buffer.trim()) {
        const trimmed = buffer.trim();
        let eventType = 'message';
        let dataStr = '';
        for (const line of trimmed.split('\n')) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim();
          else if (line.startsWith('data:')) dataStr = line.slice(5).trim();
        }
        if (eventType === 'envelope' && dataStr) {
          finalEnvelope = JSON.parse(dataStr) as PublicResponse;
          this.emit('message', { type: 'message', data: finalEnvelope });
          this.options.onMessage(finalEnvelope);
        } else if (eventType === 'error') {
          throw new Error(dataStr || 'streaming_error');
        }
      }
    } finally {
      reader.releaseLock();
    }

    if (!finalEnvelope) {
      throw new Error('Stream closed without envelope');
    }
  }

  async send(request: BrowserRequest): Promise<void> {
    if (this.isClosed) {
      throw new Error('Transport is closed');
    }

    const controller = new AbortController();
    this.abortControllers.add(controller);

    try {
      const customHeaders = await this.options.headers();
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...customHeaders,
      };
      if (this.options.streaming) {
        headers['Accept'] = 'text/event-stream';
      }

      const response = await fetch(this.options.gatewayUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      if (!response.ok) {
        let code = `HTTP ${response.status}`;
        try { const body = await response.json(); if (typeof body?.error === 'string') code = body.error; } catch { /* not JSON */ }
        throw new Error(code);
      }

      const contentType = (response.headers && typeof response.headers.get === 'function')
        ? (response.headers.get('content-type') || '')
        : '';
      if (contentType.includes('text/event-stream') && response.body) {
        await this.readEventStream(response.body);
      } else {
        const data = await response.json() as PublicResponse;
        this.emit('message', { type: 'message', data });
        this.options.onMessage(data);
      }
    } catch (error) {
      this.emit('error', { type: 'error', error: error as Error });
      this.options.onError(error as Error);
      throw error;
    } finally {
      this.abortControllers.delete(controller);
    }
  }

  close(): void {
    this.isClosed = true;
    for (const controller of this.abortControllers) {
      try {
        controller.abort();
      } catch {
        // ignore
      }
    }
    this.abortControllers.clear();
    this.emit('close', { type: 'close' });
  }

  isConnected(): boolean {
    return !this.isClosed;
  }
}

/**
 * Factory function to create the appropriate transport
 */
export function createTransport(options: TransportOptions, kind: 'http' | 'websocket' = 'http'): Transport {
  return kind === 'websocket' ? new WebSocketTransport(options) : new HttpTransport(options);
}

/**
 * Higher-level transport manager that handles protocol logic
 */
export class TransportManager {
  private transport: Transport;
  private runId: string | null = null;
  private revision = -1;
  private pendingRequestId: string | null = null;

  constructor(transport: Transport) {
    this.transport = transport;

    this.transport.on('message', (event) => {
      this.handleResponse(event.data);
    });
  }

  async start(
    message: string,
    context: any,
    sessionId?: string,
    callbacks?: { onStatus?: (status: string) => void; onDelta?: (delta: string) => void }
  ): Promise<PublicResponse> {
    const requestId = crypto.randomUUID();

    const request: BrowserRequest = {
      command: 'start',
      protocolVersion: '1.1',
      requestId,
      message,
      context,
      ...(sessionId ? { sessionId } : {}),
    };

    this.pendingRequestId = requestId;

    return new Promise((resolve, reject) => {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      const arm = () => {
        if (timeout) clearTimeout(timeout);
        timeout = setTimeout(() => {
          cleanup();
          reject(new Error('Request timeout'));
        }, 30000);
      };
      arm();

      const offStatus = this.transport.on('status', (e) => { arm(); callbacks?.onStatus?.(e.data); });
      const offDelta = this.transport.on('delta', (e) => { arm(); callbacks?.onDelta?.(e.data); });

      const offMessage = this.transport.on('message', (event) => {
        if (event.data.runId) {
          this.runId = event.data.runId;
          this.revision = event.data.revision;
          clearTimeout(timeout);
          cleanup();
          resolve(event.data);
        }
      });

      const offError = this.transport.on('error', (event) => {
        clearTimeout(timeout);
        cleanup();
        reject(event.error || new Error('Transport error'));
      });

      const cleanup = () => {
        if (timeout) clearTimeout(timeout);
        offStatus();
        offDelta();
        offMessage();
        offError();
      };

      this.transport.send(request).catch((err) => {
        clearTimeout(timeout);
        cleanup();
        reject(err);
      });
    });
  }

  async continue(
    kind: 'actions' | 'answer' | 'cancel',
    payload: any,
    callbacks?: { onStatus?: (status: string) => void; onDelta?: (delta: string) => void }
  ): Promise<PublicResponse> {
    if (!this.runId) {
      throw new Error('No active run');
    }

    const eventId = crypto.randomUUID();
    this.pendingRequestId = eventId;

    const request: BrowserRequest = {
      command: 'continue',
      protocolVersion: '1.1',
      runId: this.runId,
      eventId,
      revision: this.revision,
      kind,
      ...payload,
    };

    return new Promise((resolve, reject) => {
      let timeout: ReturnType<typeof setTimeout> | undefined;
      const arm = () => {
        if (timeout) clearTimeout(timeout);
        timeout = setTimeout(() => {
          cleanup();
          reject(new Error('Request timeout'));
        }, 30000);
      };
      arm();

      const offStatus = this.transport.on('status', (e) => { arm(); callbacks?.onStatus?.(e.data); });
      const offDelta = this.transport.on('delta', (e) => { arm(); callbacks?.onDelta?.(e.data); });

      const offMessage = this.transport.on('message', (event) => {
        if (event.data.runId === this.runId && event.data.revision > this.revision) {
          this.revision = event.data.revision;
          clearTimeout(timeout);
          cleanup();
          resolve(event.data);
        }
      });

      const offError = this.transport.on('error', (event) => {
        clearTimeout(timeout);
        cleanup();
        reject(event.error || new Error('Transport error'));
      });

      const cleanup = () => {
        if (timeout) clearTimeout(timeout);
        offStatus();
        offDelta();
        offMessage();
        offError();
      };

      this.transport.send(request).catch((err) => {
        clearTimeout(timeout);
        cleanup();
        reject(err);
      });
    });
  }

  private handleResponse(response: PublicResponse): void {
    // Response handling is done via promises in start/continue
    // This is for any async messages from server
  }

  getRunId(): string | null {
    return this.runId;
  }

  getRevision(): number {
    return this.revision;
  }

  close(): void {
    this.transport.close();
  }
}