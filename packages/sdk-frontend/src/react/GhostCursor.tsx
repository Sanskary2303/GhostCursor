"use client";
/** @jsxImportSource react */

import React, { useEffect, forwardRef } from 'react';
import { GhostCursorProvider } from './GhostCursorProvider';
import type { GhostCursorProps } from './types';
import { createGhostCursor } from '../core/SDK';

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

    if (typeof window !== 'undefined') {
      const element = mount || document.createElement('div');
      element.className = 'ghost-cursor-container';

      const sdk = createGhostCursor({
        gatewayUrl: apiEndpoint,
        page: () => {
          if (typeof context?.page === 'function') return (context.page as any)();
          if (typeof context?.page === 'string') return context.page;
          return window.location.pathname.replace(/^\//, '') || 'home';
        },
        targets: {},
        headers: headers || (() => ({ 'Content-Type': 'application/json' })),
        mount: element,
        requireApprovalForActions,
        theme: {
          primaryColor: theme?.primaryColor,
          cursorColor: theme?.cursorColor,
          position: theme?.position,
        },
      });

      return () => {
        sdk.dispose();
      };
    }
  }, [apiEndpoint, context, headers, mount, onMessage, requireApprovalForActions, theme]);

  return React.createElement(
    GhostCursorProvider,
    { value: props },
    React.createElement('div', {
      ref,
      className: 'ghost-cursor-wrapper',
      style: { position: 'fixed', zIndex: 9999, ...theme },
    })
  );
});

GhostCursor.displayName = 'GhostCursor';