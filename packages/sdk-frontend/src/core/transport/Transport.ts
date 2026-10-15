/**
 * Transport Layer - WebSocket and HTTP communication with the backend gateway
 * Handles connection management, reconnection, and message serialization
 */

import type { BrowserRequest, PublicResponse, ToolResult, Action } from '../types';

export interface TransportOptions {
  gatewayUrl: string;
  headers?: () => Record<string, string> | Promise<Record<string, string>>;
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

export type TransportEventType = 'open' | 'close' | 'error' | 'message';

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
      const wsUrl = this.options.gatewayUrl.replace(/^http/, 'ws');

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

  private eventListeners: Map<TransportEventType, Set<(event: TransportEvent) => void>> = new Map();

  constructor(options: TransportOptions) {
    this.options = {
      gatewayUrl: options.gatewayUrl,
      headers: options.headers || (() => ({ 'Content-Type': 'application/json' })),
      onMessage: options.onMessage || (() => {}),
      onError: options.onError || (() => {}),
      onClose: options.onClose || (() => {}),
      reconnect: false,
      reconnectInterval: 0,
      maxReconnectAttempts: 0,
    };

    for (const type of ['open', 'close', 'error', 'message'] as TransportEventType[]) {
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

  async connect(): Promise<void> {
    try {
      const response = await fetch(this.options.gatewayUrl, {
        method: 'OPTIONS',
        headers: await this.options.headers(),
      });
      if (!response.ok && response.status !== 405) {
        throw new Error(`Gateway unavailable: ${response.status}`);
      }
      this.emit('open', { type: 'open' });
    } catch (error) {
      throw new Error(`Failed to connect to gateway: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  async send(request: BrowserRequest): Promise<void> {
    if (this.isClosed) {
      throw new Error('Transport is closed');
    }

    try {
      const headers = await this.options.headers();
      const response = await fetch(this.options.gatewayUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      const data = await response.json() as PublicResponse;
      this.emit('message', { type: 'message', data });
      this.options.onMessage(data);
    } catch (error) {
      this.emit('error', { type: 'error', error: error as Error });
      this.options.onError(error as Error);
      throw error;
    }
  }

  close(): void {
    this.isClosed = true;
    this.emit('close', { type: 'close' });
  }

  isConnected(): boolean {
    return !this.isClosed;
  }
}

/**
 * Factory function to create the appropriate transport
 */
export function createTransport(options: TransportOptions): Transport {
  // Check if WebSocket is supported
  if (typeof WebSocket !== 'undefined') {
    return new WebSocketTransport(options);
  }

  // Fallback to HTTP
  return new HttpTransport(options);
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

  async start(message: string, context: any): Promise<PublicResponse> {
    const requestId = crypto.randomUUID();

    const request: BrowserRequest = {
      command: 'start',
      protocolVersion: '1',
      requestId,
      message,
      context,
    };

    this.pendingRequestId = requestId;

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Request timeout'));
      }, 30000);

      const off = this.transport.on('message', (event) => {
        if (event.data.runId) {
          this.runId = event.data.runId;
          this.revision = event.data.revision;
          clearTimeout(timeout);
          off();
          resolve(event.data);
        }
      });

      this.transport.send(request).catch(reject);
    });
  }

  async continue(kind: 'actions' | 'answer' | 'cancel', payload: any): Promise<PublicResponse> {
    if (!this.runId) {
      throw new Error('No active run');
    }

    const eventId = crypto.randomUUID();
    this.pendingRequestId = eventId;

    const request: BrowserRequest = {
      command: 'continue',
      protocolVersion: '1',
      runId: this.runId,
      eventId,
      revision: this.revision,
      kind,
      ...payload,
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Request timeout'));
      }, 30000);

      const off = this.transport.on('message', (event) => {
        if (event.data.runId === this.runId && event.data.revision === this.revision + 1) {
          this.revision = event.data.revision;
          clearTimeout(timeout);
          off();
          resolve(event.data);
        }
      });

      this.transport.send(request).catch(reject);
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