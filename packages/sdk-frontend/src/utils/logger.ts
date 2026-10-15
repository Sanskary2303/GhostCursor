export const logger = {
  log: (...args: any[]) => console.log('[GhostCursor]', ...args),
  warn: (...args: any[]) => console.warn('[GhostCursor]', ...args),
  error: (...args: any[]) => console.error('[GhostCursor]', ...args),
  info: (...args: any[]) => console.info('[GhostCursor]', ...args),
  debug: (...args: any[]) => console.debug('[GhostCursor]', ...args),
};

