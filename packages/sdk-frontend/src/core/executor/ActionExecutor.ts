/**
 * Action Executor - Deterministic execution of frontend actions
 * Receives tool calls from the backend and executes them against the DOM
 */

import type { Action, ToolResult } from '../types';
import { setNativeValue, setNativeSelectValue, setNativeCheckboxState, verifyValueRetained } from '../native-setter';
import { resolveTargetWithCascade, reResolveElement, ResolutionOptions } from '../dom-utils';

export interface ExecutionOptions {
  timeout?: number;
  requireApproval?: boolean;
  onProgress?: (step: string, status: 'pending' | 'executing' | 'completed' | 'failed') => void;
  onCursorMove?: (element: HTMLElement) => void;
}

export interface ExecutionResult {
  success: boolean;
  results: ToolResult[];
  error?: string;
}

const DEFAULT_EXECUTION_OPTIONS: Required<ExecutionOptions> = {
  timeout: 5000,
  requireApproval: true,
  onProgress: () => {},
  onCursorMove: () => {},
};

/**
 * Animates the ghost cursor to a target element
 */
async function animateCursorTo(element: HTMLElement, onCursorMove: (el: HTMLElement) => void): Promise<void> {
  // Scroll element into view
  element.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });

  // Wait for scroll to complete
  await new Promise(resolve => setTimeout(resolve, 300));

  // Trigger cursor animation callback
  onCursorMove(element);

  // Small delay for visual effect
  await new Promise(resolve => setTimeout(resolve, 200));
}

/**
 * Executes a single action
 */
async function executeAction(
  action: Action,
  options: Required<ExecutionOptions>
): Promise<ToolResult> {
  const { target_id, value, target_page, explanation, state, steps } = action;

  try {
    switch (action.type) {
      case 'navigate':
        return await executeNavigate(target_page!, options);

      case 'click':
        return await executeClick(target_id!, options);

      case 'fill_input':
        return await executeFillInput(target_id!, value!, options);

      case 'select_option':
        return await executeSelectOption(target_id!, value!, options);

      case 'toggle_switch':
        return await executeToggleSwitch(target_id!, state!, options);

      case 'guided_tour':
        return await executeGuidedTour(steps!, options);

      case 'ask_clarification':
        return await executeAskClarification(action.question!, action.options!, options);

      default:
        return {
          id: crypto.randomUUID(),
          ok: false,
          error: `Unknown action type: ${(action as Action).type}`,
        };
    }
  } catch (error) {
    return {
      id: crypto.randomUUID(),
      ok: false,
      error: error instanceof Error ? error.message : 'Unknown execution error',
    };
  }
}

/**
 * Navigate to a page within the SPA
 */
async function executeNavigate(targetPage: string, options: Required<ExecutionOptions>): Promise<ToolResult> {
  options.onProgress(`navigate:${targetPage}`, 'executing');

  // Try to find a navigation link with data-ghost-nav
  const link = document.querySelector<HTMLElement>(`[data-ghost-nav="${targetPage}"]`);
  if (link) {
    await animateCursorTo(link, options.onCursorMove);
    link.click();

    // Wait for navigation to complete
    await waitForNavigation(targetPage);

    options.onProgress(`navigate:${targetPage}`, 'completed');
    return { id: crypto.randomUUID(), ok: true, output: { navigated: targetPage } };
  }

  // Fallback: push state for SPA
  const path = targetPage.startsWith('/') ? targetPage : `/${targetPage}`;
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));

  // Wait for route to settle
  await waitForNavigation(path);

  options.onProgress(`navigate:${targetPage}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { navigated: path } };
}

/**
 * Click an element
 */
async function executeClick(targetId: string, options: Required<ExecutionOptions>): Promise<ToolResult> {
  options.onProgress(`click:${targetId}`, 'executing');

  const resolution = await resolveTargetWithCascade(targetId, { timeout: options.timeout });
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  // Re-resolve immediately before acting (stale reference protection)
  const freshElement = reResolveElement(targetId);
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  await animateCursorTo(freshElement, options.onCursorMove);
  freshElement.click();

  options.onProgress(`click:${targetId}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { clicked: targetId, level: resolution.level } };
}

/**
 * Fill an input/textarea element
 */
async function executeFillInput(
  targetId: string,
  value: string | number | boolean,
  options: Required<ExecutionOptions>
): Promise<ToolResult> {
  options.onProgress(`fill:${targetId}`, 'executing');

  const resolution = await resolveTargetWithCascade(targetId, { timeout: options.timeout });
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  // Re-resolve immediately before acting
  const freshElement = reResolveElement(targetId);
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLInputElement) && !(freshElement instanceof HTMLTextAreaElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not an input or textarea: ${targetId}` };
  }

  await animateCursorTo(freshElement, options.onCursorMove);

  const stringValue = String(value);
  setNativeValue(freshElement, stringValue, { commitEvent: 'input' });

  // Verify value was retained
  const verification = verifyValueRetained(freshElement, stringValue);
  if (!verification.retained) {
    return { id: crypto.randomUUID(), ok: false, error: `Value not retained after input: expected '${stringValue}', got '${verification.actualValue}'` };
  }

  options.onProgress(`fill:${targetId}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { filled: targetId, value: stringValue } };
}

/**
 * Select an option from a select element
 */
async function executeSelectOption(
  targetId: string,
  value: string | number | boolean,
  options: Required<ExecutionOptions>
): Promise<ToolResult> {
  options.onProgress(`select:${targetId}`, 'executing');

  const resolution = await resolveTargetWithCascade(targetId, { timeout: options.timeout });
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  const freshElement = reResolveElement(targetId);
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLSelectElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not a select element: ${targetId}` };
  }

  await animateCursorTo(freshElement, options.onCursorMove);

  const stringValue = String(value);
  const success = setNativeSelectValue(freshElement, stringValue);

  if (!success) {
    return { id: crypto.randomUUID(), ok: false, error: `Option not found or disabled: ${stringValue}` };
  }

  options.onProgress(`select:${targetId}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { selected: targetId, value: stringValue } };
}

/**
 * Toggle a checkbox or switch
 */
async function executeToggleSwitch(
  targetId: string,
  state: boolean,
  options: Required<ExecutionOptions>
): Promise<ToolResult> {
  options.onProgress(`toggle:${targetId}`, 'executing');

  const resolution = await resolveTargetWithCascade(targetId, { timeout: options.timeout });
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  const freshElement = reResolveElement(targetId);
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLInputElement) || (freshElement.type !== 'checkbox' && freshElement.type !== 'radio')) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not a checkbox or radio: ${targetId}` };
  }

  await animateCursorTo(freshElement, options.onCursorMove);

  setNativeCheckboxState(freshElement, state);

  options.onProgress(`toggle:${targetId}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { toggled: targetId, state } };
}

/**
 * Execute a guided tour
 */
async function executeGuidedTour(steps: any[], options: Required<ExecutionOptions>): Promise<ToolResult> {
  options.onProgress('guided_tour', 'executing');

  // This would typically delegate to a TourEngine
  // For now, we'll execute each step sequentially
  const results = [];

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    options.onProgress(`tour:step:${i + 1}`, 'executing');

    if (step.target_id) {
      const resolution = await resolveTargetWithCascade(step.target_id, { timeout: options.timeout });
      if (resolution.element) {
        await animateCursorTo(resolution.element, options.onCursorMove);

        // Highlight element (could be done via TourEngine)
        highlightElement(resolution.element);
        await new Promise(resolve => setTimeout(resolve, 1000));
        removeHighlight(resolution.element);
      }
    }

    options.onProgress(`tour:step:${i + 1}`, 'completed');
    results.push({ step: i + 1, target: step.target_id });
  }

  options.onProgress('guided_tour', 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { tour: 'completed', steps: results } };
}

/**
 * Ask a clarifying question (this is handled by the UI, not executed here)
 */
async function executeAskClarification(question: string, options: string[], _options: Required<ExecutionOptions>): Promise<ToolResult> {
  // This action type signals the UI to show a clarification dialog
  return { id: crypto.randomUUID(), ok: true, output: { clarify: { question, options } } };
}

/**
 * Waits for SPA navigation to complete
 */
async function waitForNavigation(expectedPath: string): Promise<void> {
  return new Promise(resolve => {
    const timeout = setTimeout(resolve, 2000); // Max 2s wait

    const checkNavigation = () => {
      if (window.location.pathname === expectedPath || window.location.pathname.endsWith(expectedPath)) {
        clearTimeout(timeout);
        resolve();
      }
    };

    // Check immediately
    checkNavigation();

    // Listen for popstate (back/forward navigation)
    window.addEventListener('popstate', checkNavigation, { once: true });

    // Also check periodically for hash-based routing
    const interval = setInterval(() => {
      checkNavigation();
    }, 100);

    // Clean up
    setTimeout(() => {
      clearInterval(interval);
      window.removeEventListener('popstate', checkNavigation);
    }, 2000);
  });
}

/**
 * Highlights an element for tour
 */
function highlightElement(element: HTMLElement): void {
  element.style.outline = '3px solid #FF4D4D';
  element.style.outlineOffset = '2px';
  element.style.boxShadow = '0 0 0 4px rgba(255, 77, 77, 0.3)';
  element.setAttribute('data-ghost-highlight', 'true');
}

/**
 * Removes highlight from an element
 */
function removeHighlight(element: HTMLElement): void {
  element.style.outline = '';
  element.style.outlineOffset = '';
  element.style.boxShadow = '';
  element.removeAttribute('data-ghost-highlight');
}

/**
 * Main executor that runs a sequence of actions
 */
export class ActionExecutor {
  private options: Required<ExecutionOptions>;
  private abortController: AbortController | null = null;

  constructor(options: ExecutionOptions = {}) {
    this.options = { ...DEFAULT_EXECUTION_OPTIONS, ...options };
  }

  /**
   * Execute an array of actions sequentially
   */
  async execute(actions: Action[]): Promise<ExecutionResult> {
    this.abortController = new AbortController();
    const results: ToolResult[] = [];
    const skipRest = (from: number, reason: string) => {
      for (const rest of actions.slice(from)) results.push({ id: rest.id ?? crypto.randomUUID(), ok: false, error: reason });
    };
    for (let i = 0; i < actions.length; i++) {
      if (this.abortController.signal.aborted) { skipRest(i, 'cancelled by user'); return { success: false, results, error: 'cancelled' }; }
      const result = await executeAction(actions[i], this.options);
      result.id = actions[i].id ?? result.id;
      results.push(result);
      if (!result.ok) { skipRest(i + 1, 'skipped: an earlier step failed'); return { success: false, results, error: result.error }; }
    }
    return { success: true, results };
  }

  /**
   * Stop execution
   */
  stop(): void {
    if (this.abortController) {
      this.abortController.abort();
    }
  }

  /**
   * Dispose of resources
   */
  dispose(): void {
    this.stop();
  }
}