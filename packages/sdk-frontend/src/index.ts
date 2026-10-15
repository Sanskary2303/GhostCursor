"use client";

// Re-export all SDK components for easy access
export { GhostCursor } from './react/GhostCursor';
export { GhostCursorProvider } from './react/GhostCursorProvider';
export type { GhostCursorProps } from './react/types';
export { createGhostCursor } from './core/SDK';
export type { GhostCursorSDK, CreateGhostCursorOptions } from './core/SDK';

// Core types
export * from './core/types';
export * from './core/dom-utils';
export * from './core/native-setter';

// Engine components
export { ElementResolver } from './core/executor/ElementResolver';
export { ActionExecutor } from './core/executor/ActionExecutor';
export { CursorEngine } from './core/engine/CursorEngine';
export { TourEngine } from './core/engine/TourEngine';

// Widget components
export { ChatWidget } from './core/chat/ChatWidget';
export { ContextProvider } from './core/context/ContextProvider';

// Utilities
export { setupEnvironment } from './utils/environment';
export { logger } from './utils/logger';

// Version info
export const SDK_VERSION = '0.1.0';
export const SDK_NAME = '@ghost-cursor/sdk';