import {
  resolveTargetWithCascade,
  reResolveElement,
  registerTarget,
  createSimpleTarget,
  type ResolutionOptions,
  type ResolutionResult,
} from '../dom-utils';
import type { Target } from '../types';

export class ElementResolver {
  resolve(targetId: string, options?: ResolutionOptions): Promise<ResolutionResult> {
    return resolveTargetWithCascade(targetId, options);
  }

  reResolve(targetId: string, options?: ResolutionOptions): HTMLElement | null {
    return reResolveElement(targetId, options);
  }

  register(id: string, target: Target): void {
    registerTarget(id, target);
  }

  createSimple(page: string | 'global', selector: string, operations?: Target['operations']): Target {
    return createSimpleTarget(page, selector, operations);
  }
}

