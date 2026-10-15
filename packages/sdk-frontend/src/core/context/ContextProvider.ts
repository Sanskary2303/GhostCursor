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
    'button',
    'a[href]',
    'input:not([type="hidden"]):not([type="password"]):not([type="file"])',
    'select',
    'textarea',
    '[role="button"]',
    '[role="link"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="tab"]',
    '[role="menuitem"]',
    '[role="option"]',
    '[tabindex]:not([tabindex="-1"])',
    '[data-ghost-id]',
    '[data-testid]',
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

interface ObservedElement {
  element: Element;
  targetId: string;
  lastValue: string;
}

export class ContextProvider {
  private options: Required<ContextProviderOptions>;
  private mutationObserver: MutationObserver | null = null;
  private intersectionObserver: IntersectionObserver | null = null;
  private debounceTimer: ReturnType<typeof setTimeout> | null = null;
  private observedElements: Map<string, ObservedElement> = new Map();
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

    this.observedElements.clear();
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

    // Capture from registered value selectors
    for (const [key, selector] of Object.entries(this.options.valueSelectors)) {
      const element = document.querySelector(selector);
      if (element) {
        if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {
          values[key] = element.value;
        } else if (element instanceof HTMLInputElement && element.type === 'checkbox') {
          values[key] = element.checked;
        } else {
          values[key] = element.textContent?.trim() || '';
        }
      }
    }

    // Capture from observed elements
    for (const [targetId, observed] of this.observedElements) {
      if (observed.element instanceof HTMLInputElement || observed.element instanceof HTMLTextAreaElement || observed.element instanceof HTMLSelectElement) {
        const value = observed.element.value;
        if (value !== observed.lastValue) {
          values[targetId] = value;
          observed.lastValue = value;
        }
      } else if (observed.element instanceof HTMLInputElement && observed.element.type === 'checkbox') {
        const value = observed.element.checked;
        if (value !== observed.lastValue) {
          values[targetId] = value;
          observed.lastValue = String(value);
        }
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
    // Priority order matching Element Targeting Cascade
    const ghostId = element.getAttribute('data-ghost-id');
    if (ghostId) return ghostId;

    const testId = element.getAttribute('data-testid');
    if (testId) return testId;

    const id = element.id;
    if (id) return id;

    const ariaLabel = element.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel;

    // For form elements, use name attribute
    const name = element.getAttribute('name');
    if (name && (element.tagName === 'INPUT' || element.tagName === 'SELECT' || element.tagName === 'TEXTAREA')) {
      return name;
    }

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
    if (element instanceof HTMLInputElement) {
      if (element.type === 'password' || element.type === 'file' || element.type === 'hidden') return true;
      const autocomplete = element.getAttribute('autocomplete');
      if (autocomplete && (autocomplete.includes('cc-') || autocomplete.includes('password') || autocomplete.includes('secret'))) return true;
    }

    if (element.hasAttribute('data-sensitive') || element.hasAttribute('data-pii')) return true;

    return false;
  }

  /**
   * Observe elements for value changes
   */
  private observeElements(): void {
    const selector = this.options.targetSelectors.join(',');
    const elements = document.querySelectorAll<HTMLElement>(selector);

    for (const element of elements) {
      if (this.isExcluded(element) || this.isSensitive(element)) continue;

      const targetId = this.getTargetId(element);
      if (!targetId) continue;

      // Track initial value
      let lastValue = '';
      if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement || element instanceof HTMLSelectElement) {
        lastValue = element.value;
      } else if (element instanceof HTMLInputElement && element.type === 'checkbox') {
        lastValue = String(element.checked);
      }

      this.observedElements.set(targetId, { element, targetId, lastValue });

      // Observe for intersection (visibility)
      if (this.intersectionObserver) {
        this.intersectionObserver.observe(element);
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
      // Check if mutation affects observed elements
      if (mutation.type === 'attributes') {
        const target = mutation.target as Element;
        const targetId = this.getTargetId(target as HTMLElement);
        if (targetId && this.observedElements.has(targetId)) {
          shouldRecapture = true;
          break;
        }
      }

      // Check for added/removed nodes that might be interactive
      if (mutation.type === 'childList') {
        for (const node of mutation.addedNodes) {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node as HTMLElement;
            if (this.matchesTargetSelectors(el) && !this.isExcluded(el) && !this.isSensitive(el)) {
              shouldRecapture = true;
              break;
            }
            // Check descendants
            const descendants = el.querySelectorAll(this.options.targetSelectors.join(','));
            for (const desc of descendants) {
              if (!this.isExcluded(desc) && !this.isSensitive(desc)) {
                shouldRecapture = true;
                break;
              }
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
      const target = entry.target as HTMLElement;
      const targetId = this.getTargetId(target);
      if (targetId && this.observedElements.has(targetId)) {
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