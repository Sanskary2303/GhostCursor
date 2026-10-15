"use client";

import React, { createContext, useContext, ReactNode } from 'react';
import type { GhostCursorProps } from './types';

export interface GhostCursorContextType extends GhostCursorProps {
  isInitialized: boolean;
  error?: Error;
}

const GhostCursorContext = createContext<GhostCursorContextType | null>(null);

export const GhostCursorProvider: React.FC<{
  children: ReactNode;
  value: GhostCursorProps;
}> = ({ children, value }) => {
  const contextValue: GhostCursorContextType = {
    ...value,
    isInitialized: true,
    error: undefined,
  };

  return (
    <GhostCursorContext.Provider value={contextValue}>
      {children}
    </GhostCursorContext.Provider>
  );
};

export const useGhostCursor = () => {
  const context = useContext(GhostCursorContext);
  if (!context) {
    throw new Error('useGhostCursor must be used within a GhostCursorProvider');
  }
  return context;
};