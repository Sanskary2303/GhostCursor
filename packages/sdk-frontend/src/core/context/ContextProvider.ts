/**
 * Context Provider - Scans DOM and provides page context to the backend
 * Uses MutationObserver and IntersectionObserver for efficient reactive tracking
 */

import type { PageContext, ContextSnapshot } from '../types';

export interface ContextProviderOptions {
  pageSelector?: () => string;
  valueSelectors?: Record<string, string>;
  targetSelectors?: string[];
  excludeSelectors?: string[];
  debounceMs?: number;
  onContextChange?: (context: ContextSnapshot) => void;
}

const DEFAULT_OPTIONS: Required<ContextProviderOptions> = {
  pageSelector: () => window.location.pathname,
  valueSelectors: {},
  targetSelectors: [
    '[data-ghost-id]',
  ],
  excludeSelectors: [
    '.sensitive-data',
    '#credit-card-form',
    '[data-sensitive]',
    '[data-pii]',
    '[autocomplete="cc-*"]',
    '[autocomplete*="password"]',
  ],
  debounceMs: 300,
  onContextChange: () => {},
};

export class ContextProvider {
  private options: Required<ContextProviderOptions>;
  private mutationObserver: MutationObserver | null = null;
  private intersectionObserver: IntersectionObserver | null = null;
  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private observedTargets: Set<Element> = new Set();
  private currentContext: ContextSnapshot | null = null;
  private isDestroyed = false;

  constructor(options: ContextProviderOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
  }

  /**
   * Start observing the DOM for context changes
   */
  start(): void {
    if (this.isDestroyed) return;

    // Initial context capture
    this.captureContext();

    // Set up MutationObserver for DOM changes
    this.mutationObserver = new MutationObserver(this.handleMutations.bind(this));
    this.mutationObserver.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['value', 'checked', 'selected', 'disabled', 'aria-hidden', 'style', 'class'],
      characterData: true,
    });

    // Set up IntersectionObserver for visibility changes
    this.intersectionObserver = new IntersectionObserver(this.handleIntersection.bind(this), {
      root: null,
      rootMargin: '0px',
      threshold: [0, 0.1, 0.5, 1],
    });

    // Observe initial elements
    this.observeElements();
  }

  /**
   * Stop observing and cleanup
   */
  destroy(): void {
    this.isDestroyed = true;

    if (this.mutationObserver) {
      this.mutationObserver.disconnect();
      this.mutationObserver = null;
    }

    if (this.intersectionObserver) {
      this.intersectionObserver.disconnect();
      this.intersectionObserver = null;
    }

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }

    this.observedTargets.clear();
  }

  /**
   * Get current context snapshot
   */
  getContext(): ContextSnapshot | null {
    return this.currentContext;
  }

  /**
   * Force a context capture
   */
  captureContext(): ContextSnapshot {
    const page = this.options.pageSelector();
    const values = this.captureValues();
    const availableTargets = this.captureAvailableTargets();

    const snapshot: ContextSnapshot = {
      page,
      values,
      availableTargets,
      timestamp: Date.now(),
    };

    this.currentContext = snapshot;
    this.options.onContextChange(snapshot);

    return snapshot;
  }

  /**
   * Capture form values and control states
   */
  private captureValues(): Record<string, string | number | boolean> {
    const values: Record<string, string | number | boolean> = {};

    const elements = Array.from(
      document.querySelectorAll<HTMLElement>('[data-ghost-id][data-ghost-observe]')
    ).slice(0, 50);

    for (const element of elements) {
      if (this.isSensitive(element)) continue;
      const targetId = element.getAttribute('data-ghost-id');
      if (!targetId) continue;

      if (element instanceof HTMLInputElement && (element.type === 'checkbox' || element.type === 'radio')) {
        values[targetId] = element.checked;
      } else if (
        element instanceof HTMLInputElement ||
        element instanceof HTMLTextAreaElement ||
        element instanceof HTMLSelectElement
      ) {
        values[targetId] = (element.value || '').slice(0, 2000);
      } else {
        values[targetId] = (element.textContent || '').trim().slice(0, 200);
      }
    }

    return values;
  }

  /**
   * Capture available interactive targets on the page
   */
  private captureAvailableTargets(): string[] {
    const targets = new Set<string>();

    // Get elements matching target selectors
    const selector = this.options.targetSelectors.join(',');
    const elements = document.querySelectorAll<HTMLElement>(selector);

    for (const element of elements) {
      // Skip excluded elements
      if (this.isExcluded(element)) continue;

      // Skip sensitive elements
      if (this.isSensitive(element)) continue;

      // Get target ID from various attributes
      const targetId = this.getTargetId(element);
      if (targetId) {
        targets.add(targetId);
      }
    }

    return Array.from(targets).slice(0, 100); // Limit to 100 targets
  }

  /**
   * Get a stable target ID for an element
   */
  private getTargetId(element: HTMLElement): string | null {
    const ghostId = element.getAttribute('data-ghost-id');
    if (ghostId) return ghostId;
    return null;
  }

  /**
   * Check if element should be excluded
   */
  private isExcluded(element: Element): boolean {
    for (const selector of this.options.excludeSelectors) {
      if (element.matches(selector) || element.closest(selector)) {
        return true;
      }
    }
    return false;
  }

  /**
   * Check if element is sensitive (password, credit card, etc.)
   */
  private isSensitive(element: Element): boolean {
    const sensitivePattern = /card|cvv|cvc|ssn|password|secret|token/i;
    const name = element.getAttribute('name') || '';
    const id = element.id || '';
    if (sensitivePattern.test(name) || sensitivePattern.test(id)) {
      return true;
    }

    if (element instanceof HTMLInputElement) {
      if (element.type === 'password' || element.type === 'file' || element.type === 'hidden') return true;
      const autocomplete = element.getAttribute('autocomplete');
      if (
        autocomplete &&
        (autocomplete.includes('cc-') ||
          autocomplete.includes('password') ||
          autocomplete.includes('secret'))
      ) {
        return true;
      }
    }

    if (element.hasAttribute('data-sensitive') || element.hasAttribute('data-pii')) return true;

    return false;
  }

  /**
   * Observe elements for intersection (visibility)
   */
  private observeElements(): void {
    if (!this.intersectionObserver) return;
    const selector = this.options.targetSelectors.join(',');
    const elements = document.querySelectorAll<HTMLElement>(selector);

    for (const element of elements) {
      if (this.isExcluded(element) || this.isSensitive(element)) continue;
      if (!this.observedTargets.has(element)) {
        this.intersectionObserver.observe(element);
        this.observedTargets.add(element);
      }
    }
  }

  /**
   * Handle DOM mutations
   */
  private handleMutations(mutations: MutationRecord[]): void {
    if (this.isDestroyed) return;

    let shouldRecapture = false;

    for (const mutation of mutations) {
      if (mutation.type === 'attributes') {
        const target = mutation.target as Element;
        if (target.hasAttribute && (target.hasAttribute('data-ghost-id') || target.hasAttribute('data-ghost-observe'))) {
          shouldRecapture = true;
          break;
        }
      }

      if (mutation.type === 'childList') {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node as HTMLElement;
            if (this.matchesTargetSelectors(el) && !this.isExcluded(el) && !this.isSensitive(el)) {
              shouldRecapture = true;
              break;
            }
            const descendants = el.querySelectorAll?.(this.options.targetSelectors.join(','));
            if (descendants && descendants.length > 0) {
              shouldRecapture = true;
              break;
            }
          }
        }
        if (shouldRecapture) break;
      }
    }

    if (shouldRecapture) {
      this.scheduleContextUpdate();
    }
  }

  /**
   * Handle intersection changes (visibility)
   */
  private handleIntersection(entries: IntersectionObserverEntry[]): void {
    let shouldRecapture = false;

    for (const entry of entries) {
      if (entry.isIntersecting) {
        shouldRecapture = true;
        break;
      }
    }

    if (shouldRecapture) {
      this.scheduleContextUpdate();
    }
  }

  /**
   * Check if element matches target selectors
   */
  private matchesTargetSelectors(element: HTMLElement): boolean {
    return this.options.targetSelectors.some(selector => element.matches(selector));
  }

  /**
   * Schedule a debounced context update
   */
  private scheduleContextUpdate(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }

    this.debounceTimer = setTimeout(() => {
      this.captureContext();
      this.observeElements(); // Re-observe for new elements
    }, this.options.debounceMs);
  }
}

/**
 * Create a context provider for a specific page
 */
export function createPageContextProvider(
  pageId: string,
  options: Partial<ContextProviderOptions> = {}
): ContextProvider {
  return new ContextProvider({
    pageSelector: () => pageId,
    ...options,
  });
}

/**
 * Global context provider instance
 */
let globalContextProvider: ContextProvider | null = null;

export function getGlobalContextProvider(): ContextProvider {
  if (!globalContextProvider) {
    globalContextProvider = new ContextProvider();
  }
  return globalContextProvider;
}

export function initGlobalContextProvider(options: ContextProviderOptions): ContextProvider {
  if (globalContextProvider) {
    globalContextProvider.destroy();
  }
  globalContextProvider = new ContextProvider(options);
  return globalContextProvider;
}