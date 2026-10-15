"use client";

import React, { useEffect, useRef, forwardRef } from 'react';
import { GhostCursorProvider } from './GhostCursorProvider';
import type { GhostCursorProps } from './types';

export const GhostCursor = forwardRef<HTMLDivElement, GhostCursorProps>((props, ref) => {
  const {
    apiEndpoint = '/api/ghost-cursor',
    theme = { primaryColor: '#0052FF', cursorColor: '#FF4D4D', position: 'bottom-right' },
    requireApprovalForActions = true,
    onMessage,
    onActionsRequested,
    context,
    headers,
    selectors,
    mount,
  } = props;

  useEffect(() => {
    if (!apiEndpoint) {
      console.error('[GhostCursor] apiEndpoint is required');
    }

    // Initialize SDK
    if (typeof window !== 'undefined') {
      import('@ghost-cursor/sdk').then((SDK) => {
        const element = mount || document.createElement('div');
        element.className = 'ghost-cursor-container';

        const cleanup = SDK.createGhostCursor({
          gatewayUrl: apiEndpoint,
          page: context?.page || (() => window.location.pathname),
          targets: {}, // Customer-registered targets go here
          headers: headers || (() => ({ 'Content-Type': 'application/json' })),
          mount: element,
        });

        if (onMessage) {
          // Handle incoming messages
          console.log('[GhostCursor] SDK initialized', { SDK, cleanup });
        }
      });
    }
  }, [apiEndpoint, context, headers, mount, onMessage]);

  return (
    <GhostCursorProvider value={props}>
      <div ref={ref} className="ghost-cursor-wrapper" style={{ position: 'fixed', zIndex: 9999, ...theme }}>
        {/* Widget will be mounted here by the SDK */}
      </div>
    </GhostCursorProvider>
  );
});

GhostCursor.displayName = 'GhostCursor';