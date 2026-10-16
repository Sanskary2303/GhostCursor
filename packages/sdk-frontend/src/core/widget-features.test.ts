import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { HttpTransport } from './transport/Transport';
import { ActionExecutor } from './executor/ActionExecutor';
import { CursorEngine } from './engine/CursorEngine';
import { createGhostCursor } from './SDK';
import type { BrowserRequest } from './types';

// Setup DOM mocks for node environment
const setupMockDOM = () => {
  const origWindow = (global as any).window;
  const origDocument = (global as any).document;
  const origMutationObserver = (global as any).MutationObserver;
  const origIntersectionObserver = (global as any).IntersectionObserver;

  (global as any).MutationObserver = class {
    observe = vi.fn();
    disconnect = vi.fn();
  };

  (global as any).IntersectionObserver = class {
    observe = vi.fn();
    unobserve = vi.fn();
    disconnect = vi.fn();
  };

  (global as any).window = {
    matchMedia: vi.fn().mockImplementation((query: string) => ({
      matches: query === '(prefers-reduced-motion: reduce)',
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
    devicePixelRatio: 1,
    innerWidth: 1024,
    innerHeight: 768,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    requestAnimationFrame: (cb: Function) => setTimeout(cb, 16),
    cancelAnimationFrame: (id: any) => clearTimeout(id),
  };

  const mockCanvasCtx = {
    scale: vi.fn(),
    clearRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    arc: vi.fn(),
    moveTo: vi.fn(),
    quadraticCurveTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    translate: vi.fn(),
  };

  const createMockElement = (tag: string) => {
    const el: any = {
      tagName: tag.toUpperCase(),
      nodeName: tag.toUpperCase(),
      nodeType: 1,
      id: '',
      style: {},
      setAttribute: vi.fn(),
      removeAttribute: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      getContext: () => mockCanvasCtx,
      attachShadow: () => createMockElement('div'),
      getBoundingClientRect: () => ({ left: 100, top: 200, width: 50, height: 50 }),
      childNodes: [],
      firstChild: null,
      lastChild: null,
      nextSibling: null,
      parentNode: null,
      appendChild: vi.fn((child: any) => {
        child.parentNode = el;
        el.childNodes.push(child);
        return child;
      }),
      removeChild: vi.fn(),
      insertBefore: vi.fn(),
    };
    return el;
  };

  (global as any).document = {
    body: createMockElement('body'),
    createElement: (tag: string) => createMockElement(tag),
    createElementNS: (_ns: string, tag: string) => createMockElement(tag),
    createTextNode: (text: string) => ({
      nodeType: 3,
      nodeName: '#text',
      data: text,
      parentNode: null,
      nextSibling: null,
    }),
    getElementById: () => null,
    querySelector: () => null,
    querySelectorAll: () => [],
  };

  return () => {
    (global as any).window = origWindow;
    (global as any).document = origDocument;
    (global as any).MutationObserver = origMutationObserver;
    (global as any).IntersectionObserver = origIntersectionObserver;
  };
};

describe('Widget Features and Hardening (Step 29)', () => {
  describe('HttpTransport in-flight abort on close()', () => {
    it('aborts all pending in-flight requests when close() is called', async () => {
      let abortedSignal: AbortSignal | null = null;
      const originalFetch = global.fetch;

      global.fetch = vi.fn().mockImplementation((_url, init) => {
        abortedSignal = init.signal;
        return new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const err = new Error('The operation was aborted');
            err.name = 'AbortError';
            reject(err);
          });
        });
      });

      const transport = new HttpTransport({
        gatewayUrl: 'http://localhost:8080/api/ghost-cursor',
      });

      const req: BrowserRequest = {
        command: 'start',
        protocolVersion: '1',
        requestId: 'req-1',
        message: 'Hello',
        context: { page: 'home', values: {}, availableTargets: [] },
      };

      const sendPromise = transport.send(req);
      await new Promise(r => setTimeout(r, 10));

      expect(abortedSignal).not.toBeNull();
      expect((abortedSignal as any)?.aborted).toBe(false);

      transport.close();
      expect((abortedSignal as any)?.aborted).toBe(true);

      await expect(sendPromise).rejects.toThrow();
      global.fetch = originalFetch;
    });
  });

  describe('ActionExecutor stop()', () => {
    it('marks remaining actions as cancelled by user when stopped', async () => {
      const executor = new ActionExecutor({ timeout: 500 });

      // Stop before execution
      executor.stop();

      const res = await executor.execute([
        { id: 'step-1', type: 'navigate', target_page: 'products' },
        { id: 'step-2', type: 'click', target_id: 'btn' },
      ]);

      expect(res.success).toBe(false);
      expect(res.error).toBe('cancelled');
      expect(res.results).toHaveLength(2);
      expect(res.results[0].error).toBe('cancelled by user');
      expect(res.results[1].error).toBe('cancelled by user');
    });
  });

  describe('CursorEngine reduced motion', () => {
    let cleanupDOM: () => void;

    beforeEach(() => {
      cleanupDOM = setupMockDOM();
    });

    afterEach(() => {
      cleanupDOM();
    });

    it('jumps cursor immediately without animation frames when prefers-reduced-motion is active', async () => {
      const engine = new CursorEngine();
      const el = {
        getBoundingClientRect: () => ({
          left: 100,
          top: 200,
          width: 50,
          height: 50,
        }),
      } as any;

      await engine.moveTo(el);
      // Immediately arrived at center: 100 + 25 = 125, 200 + 25 = 225
      expect((engine as any).currentPosition).toEqual({ x: 125, y: 225 });
      expect((engine as any).trail).toEqual([]);
      engine.dispose();
    });
  });

  describe('Approval Token in SDK executeActions', () => {
    let cleanupDOM: () => void;

    beforeEach(() => {
      cleanupDOM = setupMockDOM();
    });

    afterEach(() => {
      cleanupDOM();
    });

    it('refuses to execute with "This plan is out of date." when token does not match', async () => {
      const sdk = createGhostCursor({
        gatewayUrl: 'http://localhost:8080/api/ghost-cursor',
        page: () => 'home',
        targets: {},
      });

      await expect(
        sdk.executeActions(
          [{ id: '1', type: 'click', target_id: 'btn' }],
          'run-123:5'
        )
      ).rejects.toThrow('This plan is out of date.');

      sdk.dispose();
    });
  });
});
