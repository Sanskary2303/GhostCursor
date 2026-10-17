import {
  ActionExecutor,
  registerTarget,
  getRegisteredTarget,
  clearTargetRegistry,
  resolveTargetWithCascade,
  reResolveElement,
} from '@ghost-cursor/sdk';

export function installE2EHooks(): void {
  if (typeof window !== 'undefined') {
    (window as any).__GHOST_CURSOR_SDK__ = {
      ActionExecutor,
      registerTarget,
      getRegisteredTarget,
      clearTargetRegistry,
      resolveTargetWithCascade,
      reResolveElement,
    };
  }
}

