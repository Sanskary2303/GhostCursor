"use client";

import { useEffect, useRef, FC } from 'react';
import { createGhostCursor, type GhostCursorSDK } from '@ghost-cursor/sdk';
import type { GhostCursorProps } from './types.js';

const NO_TARGETS: NonNullable<GhostCursorProps['targets']> = {};

export const GhostCursor: FC<GhostCursorProps> = (props) => {
  const propsRef = useRef<GhostCursorProps>(props);
  propsRef.current = props;

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const initialProps = propsRef.current;
    if (!initialProps.apiEndpoint) {
      console.error('[GhostCursor] apiEndpoint is required');
    }

    const sdk: GhostCursorSDK = createGhostCursor({
      gatewayUrl: initialProps.apiEndpoint || '/api/ghost-cursor',
      page: () => {
        const ctxPage = propsRef.current.context?.page;
        if (typeof ctxPage === 'function') return ctxPage();
        if (typeof ctxPage === 'string') return ctxPage;
        return window.location.pathname.replace(/^\//, '') || 'home';
      },
      targets: propsRef.current.targets || NO_TARGETS,
      headers: () => {
        const h = propsRef.current.headers;
        if (typeof h === 'function') return h();
        return { 'Content-Type': 'application/json' };
      },
      mount: propsRef.current.mount,
      requireApprovalForActions: propsRef.current.requireApprovalForActions ?? true,
      allowSemanticLookup: propsRef.current.allowSemanticLookup ?? false,
      theme: {
        primaryColor: propsRef.current.theme?.primaryColor,
        cursorColor: propsRef.current.theme?.cursorColor,
        position: propsRef.current.theme?.position,
        mode: propsRef.current.theme?.mode,
      },
      onMessage: (msg: any) => propsRef.current.onMessage?.(msg),
      onActionsRequested: (acts: any) => propsRef.current.onActionsRequested?.(acts),
    });

    return () => {
      sdk.dispose();
    };
  }, []);

  return null;
};

GhostCursor.displayName = 'GhostCursor';
