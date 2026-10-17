import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { defineGhostCursorElement } from './element';
import { createGhostCursor } from './SDK';

describe('defineGhostCursorElement', () => {
  beforeEach(() => {
    if (typeof (global as any).IntersectionObserver === 'undefined') {
      (global as any).IntersectionObserver = class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      };
    }
    const existing = document.getElementById('ghost-cursor-widget-container');
    if (existing?.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  });

  afterEach(() => {
    const existing = document.getElementById('ghost-cursor-widget-container');
    if (existing?.parentNode) {
      existing.parentNode.removeChild(existing);
    }
  });

  it('is idempotent and registers ghost-cursor-widget', () => {
    expect(() => {
      defineGhostCursorElement();
      defineGhostCursorElement();
      defineGhostCursorElement();
    }).not.toThrow();

    expect(customElements.get('ghost-cursor-widget')).toBeDefined();
  });

  it('SDK host tagName is GHOST-CURSOR-WIDGET', () => {
    defineGhostCursorElement();

    const sdk = createGhostCursor({
      gatewayUrl: '/api/ghost-cursor',
      page: () => 'home',
      targets: {},
    });

    try {
      const host = document.getElementById('ghost-cursor-widget-container');
      expect(host).not.toBeNull();
      expect(host?.tagName).toBe('GHOST-CURSOR-WIDGET');
      expect(sdk.host?.tagName).toBe('GHOST-CURSOR-WIDGET');
      expect(sdk.host).toBe(host);
    } finally {
      sdk.dispose();
    }
  });
});
