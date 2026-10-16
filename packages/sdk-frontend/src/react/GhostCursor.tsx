"use client";
/** @jsxImportSource react */

import React, { useEffect, forwardRef } from 'react';
import { GhostCursorProvider } from './GhostCursorProvider';
import type { GhostCursorProps } from './types';
import { createGhostCursor } from '../core/SDK';

const NO_TARGETS: NonNullable<GhostCursorProps['targets']> = {};

export const GhostCursor = forwardRef<HTMLDivElement, GhostCursorProps>((props, ref) => {
  const {
    apiEndpoint = '/api/ghost-cursor',
    theme = { primaryColor: '#0052FF', cursorColor: '#FF4D4D', position: 'bottom-right' },
    requireApprovalForActions = true,
    allowSemanticLookup = false,
    targets = NO_TARGETS,
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
      const sdk = createGhostCursor({
        gatewayUrl: apiEndpoint,
        page: () => {
          if (typeof context?.page === 'function') return (context.page as any)();
          if (typeof context?.page === 'string') return context.page;
          return window.location.pathname.replace(/^\//, '') || 'home';
        },
        targets,
        headers: headers || (() => ({ 'Content-Type': 'application/json' })),
        mount: mount,
        requireApprovalForActions,
        allowSemanticLookup,
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
  }, [apiEndpoint, context, headers, mount, onMessage, requireApprovalForActions, allowSemanticLookup, targets, theme]);

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