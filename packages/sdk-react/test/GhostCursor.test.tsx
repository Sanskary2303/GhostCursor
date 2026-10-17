import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import * as SDK from '@ghost-cursor/sdk';
import { GhostCursor } from '../src/GhostCursor.js';
import { GhostCursorProvider, useGhostCursor } from '../src/GhostCursorProvider.js';

vi.mock('@ghost-cursor/sdk', () => ({
  createGhostCursor: vi.fn(),
}));

describe('@ghost-cursor/sdk-react', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('GhostCursor component is a function with displayName', () => {
    expect(typeof GhostCursor).toBe('function');
    expect(GhostCursor.displayName).toBe('GhostCursor');
  });

  it('useGhostCursor throws when used outside GhostCursorProvider', () => {
    const origDispatcher = (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current;
    (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = {
      useContext: () => null,
    };
    try {
      expect(() => useGhostCursor()).toThrow('useGhostCursor must be used within a GhostCursorProvider');
    } finally {
      (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = origDispatcher;
    }
  });

  it('simulates GhostCursor mount-once logic, null return, dynamic prop access via useRef, and disposal', () => {
    const mockSdk = { dispose: vi.fn() };
    (SDK.createGhostCursor as any).mockReturnValue(mockSdk);

    (global as any).window = {
      location: { pathname: '/checkout' },
    };

    let effectFn: (() => (() => void) | void) | null = null;
    let refValue: any = null;

    const mockDispatcher = {
      useRef: (val: any) => {
        if (!refValue) refValue = { current: val };
        return refValue;
      },
      useEffect: (fn: any, deps: any[]) => {
        expect(deps).toEqual([]);
        effectFn = fn;
      },
    };

    const origDispatcher = (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current;
    (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = mockDispatcher;

    try {
      const props1 = {
        apiEndpoint: '/api/ghost',
        context: { page: () => 'initial-page' },
        targets: { myTarget: {} as any },
      };
      const result = GhostCursor(props1);
      expect(result).toBeNull();
      expect(effectFn).not.toBeNull();

      // Trigger effect (mount)
      const cleanup = effectFn!();
      expect(SDK.createGhostCursor).toHaveBeenCalledTimes(1);

      const options = (SDK.createGhostCursor as any).mock.calls[0][0];
      expect(options.gatewayUrl).toBe('/api/ghost');
      expect(options.page()).toBe('initial-page');

      // Update props (simulating re-render)
      const props2 = {
        apiEndpoint: '/api/ghost',
        context: { page: () => 'updated-page' },
        targets: { myTarget: {} as any },
      };
      GhostCursor(props2);

      // SDK factory was NOT called again (mount-once!)
      expect(SDK.createGhostCursor).toHaveBeenCalledTimes(1);

      // Dynamic page getter reads latest props from useRef
      expect(options.page()).toBe('updated-page');

      // Unmount cleanup
      cleanup!();
      expect(mockSdk.dispose).toHaveBeenCalledTimes(1);
    } finally {
      (React as any).__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentDispatcher.current = origDispatcher;
      delete (global as any).window;
    }
  });

  it('resolves @ghost-cursor/sdk-react/dist/index.css export', async () => {
    const { createRequire } = await import('module');
    const require = createRequire(import.meta.url);
    const resolved = require.resolve('@ghost-cursor/sdk-react/dist/index.css');
    expect(resolved).toContain('packages/sdk-react/dist/index.css');
  });
});

