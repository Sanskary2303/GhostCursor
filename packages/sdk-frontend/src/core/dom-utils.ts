/**
 * Element Targeting Cascade - Deterministic DOM element resolution
 * Priority order:
 * 1. data-ghost-id (explicit logical ID)
 * 2. data-testid (automated test ID)
 * 3. id (standard DOM ID)
 * 4. ARIA labels (accessibility labels)
 * 5. Semantic text/visible value matching
 */

import type { Target } from './types';

const registry = new Map<string, Target>();

/**
 * Registers a custom target with the SDK
 */
export function registerTarget(id: string, target: Target): void {
  registry.set(id, target);
}

/**
 * Retrieves a registered target by its ID
 */
export function getRegisteredTarget(id: string): Target | undefined {
  return registry.get(id);
}

/**
 * Clears the target registry (useful for tests or teardown)
 */
export function clearTargetRegistry(): void {
  registry.clear();
}

export interface ResolutionOptions {
  timeout?: number;
  pollInterval?: number;
  allowHidden?: boolean;
  allowDisabled?: boolean;
  allowSensitive?: boolean;
  allowSemanticLookup?: boolean;
}

export interface ResolutionResult {
  element: HTMLElement | null;
  level: number;
  selector: string;
  matched: boolean;
}

const DEFAULT_OPTIONS: Required<ResolutionOptions> = {
  timeout: 8000,
  pollInterval: 100,
  allowHidden: false,
  allowDisabled: false,
  allowSensitive: false,
  allowSemanticLookup: false,
};

// Sensitive input types that should never be targeted
const SENSITIVE_INPUT_TYPES = new Set(['password', 'file', 'hidden']);
const SENSITIVE_ATTRIBUTES = new Set(['autocomplete', 'data-sensitive', 'data-pii']);

/**
 * Checks if an element is sensitive (password, file, hidden, or marked as PII)
 */
function isSensitiveElement(element: HTMLElement): boolean {
  if (element instanceof HTMLInputElement) {
    if (SENSITIVE_INPUT_TYPES.has(element.type)) return true;
    // Check for sensitive autocomplete values
    const autocomplete = element.getAttribute('autocomplete');
    if (autocomplete && (autocomplete.includes('cc-') || autocomplete.includes('password'))) return true;
  }
  // Check for explicit sensitive markers
  for (const attr of SENSITIVE_ATTRIBUTES) {
    if (element.hasAttribute(attr)) return true;
  }
  return false;
}

/**
 * Checks if an element is interactable (visible, enabled, not inert)
 */
function isInteractable(element: HTMLElement, options: Required<ResolutionOptions>): boolean {
  if (!options.allowHidden) {
    const style = window.getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
    // Check if element has zero dimensions
    const rect = element.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
  }

  if (!options.allowDisabled) {
    if (element instanceof HTMLInputElement || element instanceof HTMLButtonElement ||
        element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
      if (element.disabled) return false;
    }
    if (element.getAttribute('aria-disabled') === 'true') return false;
    if (element.closest('[aria-disabled="true"]')) return false;
  }

  if (!options.allowSensitive && isSensitiveElement(element)) {
    return false;
  }

  // Check for inert attribute
  if (element.hasAttribute('inert') || element.closest('[inert]')) return false;

  // Check if disconnected from DOM
  if (!document.body.contains(element)) return false;

  return true;
}

/**
 * Level 1: Explicit Logical ID - data-ghost-id
 */
function resolveByGhostId(targetId: string): HTMLElement | null {
  const selector = `[data-ghost-id="${escapeSelector(targetId)}"]`;
  return document.querySelector<HTMLElement>(selector) || null;
}

/**
 * Level 2: Automated Test ID - data-testid
 */
function resolveByTestId(targetId: string): HTMLElement | null {
  const selector = `[data-testid="${escapeSelector(targetId)}"]`;
  return document.querySelector<HTMLElement>(selector) || null;
}

/**
 * Level 3: Standard DOM ID - id
 */
function resolveById(targetId: string): HTMLElement | null {
  return document.getElementById(targetId) || null;
}

/**
 * Level 4: ARIA Accessibility Labels
 */
function resolveByAria(targetId: string): HTMLElement | null {
  // Try aria-label
  let selector = `[aria-label="${escapeSelector(targetId)}"]`;
  let element = document.querySelector<HTMLElement>(selector);
  if (element) return element;

  // Try aria-labelledby pointing to an element with matching id
  const labelledbyElements = document.querySelectorAll(`[aria-labelledby]`);
  for (const el of labelledbyElements) {
    const labelledBy = el.getAttribute('aria-labelledby')?.split(' ') || [];
    for (const id of labelledBy) {
      const labelEl = document.getElementById(id);
      if (labelEl && (labelEl.textContent?.trim() === targetId || labelEl.id === targetId)) {
        return el as HTMLElement;
      }
    }
  }

  // Try role-based lookup with matching text
  const roleSelectors = [
    '[role="button"]',
    '[role="link"]',
    '[role="menuitem"]',
    '[role="tab"]',
    '[role="checkbox"]',
    '[role="radio"]',
    '[role="switch"]',
    '[role="textbox"]',
    '[role="combobox"]',
    '[role="slider"]',
  ];

  for (const roleSelector of roleSelectors) {
    const elements = document.querySelectorAll<HTMLElement>(roleSelector);
    for (const el of elements) {
      if (el.textContent?.trim() === targetId ||
          el.getAttribute('aria-label') === targetId) {
        return el;
      }
    }
  }

  return null;
}

/**
 * Level 5: Semantic Text & Visible Value Matching (fuzzy)
 */
function resolveByText(targetId: string): HTMLElement | null {
  // Interactive elements to search
  const interactiveSelectors = [
    'button',
    'a[href]',
    'input[type="button"]',
    'input[type="submit"]',
    'input[type="checkbox"]',
    'input[type="radio"]',
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
  ];

  const wanted = targetId.toLowerCase().trim();
  if (!wanted) return null;
  const matches: HTMLElement[] = [];
  for (const el of document.querySelectorAll<HTMLElement>(interactiveSelectors.join(','))) {
    if (isSensitiveElement(el)) continue;
    const sources = [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')]
      .map(s => (s ?? '').trim().toLowerCase()).filter(Boolean);
    if (sources.includes(wanted)) matches.push(el);
  }
  return matches.length === 1 ? matches[0] : null;
}

/**
 * Escapes a string for use in a CSS selector
 */
function escapeSelector(str: string): string {
  return CSS.escape(str);
}

/**
 * Main resolution function implementing the Element Targeting Cascade
 */
export async function resolveTargetWithCascade(
  targetId: string,
  options: ResolutionOptions = {}
): Promise<ResolutionResult> {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const startTime = Date.now();
  const registered = getRegisteredTarget(targetId);

  while (Date.now() - startTime < opts.timeout) {
    if (registered) {
      const element = registered.resolve();
      if (element && isInteractable(element, opts)) {
        return { element, level: 0, selector: 'registered', matched: true };
      }
    } else {
      const levels = [
        { level: 1, name: 'data-ghost-id', fn: resolveByGhostId },
        { level: 2, name: 'data-testid', fn: resolveByTestId },
        { level: 3, name: 'id', fn: resolveById },
      ];
      if (opts.allowSemanticLookup) {
        levels.push(
          { level: 4, name: 'aria', fn: resolveByAria },
          { level: 5, name: 'text', fn: resolveByText }
        );
      }
      for (const level of levels) {
        const element = level.fn(targetId);
        if (element && isInteractable(element, opts)) {
          return { element, level: level.level, selector: level.name, matched: true };
        }
      }
    }
    await new Promise(resolve => setTimeout(resolve, opts.pollInterval));
  }

  // No element found after all levels and timeout
  return {
    element: null,
    level: 0,
    selector: '',
    matched: false,
  };
}

/**
 * Re-resolves immediately before acting to eliminate stale references
 */
export function reResolveElement(targetId: string, options: ResolutionOptions = {}): HTMLElement | null {
  const opts = { ...DEFAULT_OPTIONS, ...options };
  const registered = getRegisteredTarget(targetId);
  if (registered) {
    const el = registered.resolve();
    return el && isInteractable(el, opts) ? el : null;
  }
  let candidate = resolveByGhostId(targetId) ||
                  resolveByTestId(targetId) ||
                  resolveById(targetId);
  if (!candidate && opts.allowSemanticLookup) {
    candidate = resolveByAria(targetId) || resolveByText(targetId);
  }
  if (candidate && isInteractable(candidate, opts)) {
    return candidate;
  }
  return null;
}

/**
 * Creates a target from a simple selector for basic use cases
 */
export function createSimpleTarget(
  page: string | 'global',
  selector: string,
  operations: Target['operations'] = ['click', 'fill']
): Target {
  return {
    page,
    resolve: () => document.querySelector<HTMLElement>(selector),
    operations,
  };
}