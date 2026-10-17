"use client";

// Core SDK factory
export { createGhostCursor } from './core/SDK';
export type { GhostCursorSDK, CreateGhostCursorOptions } from './core/SDK';

// Core types
export * from './core/types';
export * from './core/dom-utils';
export * from './core/native-setter';

// Engine components
export { createCursorSvg, BRAND, CURSOR_POLYGON, CURSOR_VIEWBOX, CURSOR_WIDTH, CURSOR_HOTSPOT } from './core/cursor/assets';
export type { CursorSvgOptions } from './core/cursor/assets';
export { MIDNIGHT, DAYLIGHT, resolveMode, tokensFor, tokensToCss } from './core/theme/tokens';
export type { ThemeMode, ThemeTokens } from './core/theme/tokens';
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