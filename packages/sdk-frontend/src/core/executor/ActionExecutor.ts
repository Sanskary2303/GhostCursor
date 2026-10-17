/**
 * Action Executor - Deterministic execution of frontend actions
 * Receives tool calls from the backend and executes them against the DOM
 */

import type { Action, ToolResult } from '../types';
import { setNativeValue, setNativeSelectValue, setNativeCheckboxState, verifyValueRetained } from '../native-setter';
import { resolveTargetWithCascade, reResolveElement, ResolutionOptions, getRegisteredTarget } from '../dom-utils';
import { TourEngine } from '../engine/TourEngine';

export interface StepInfo {
  action: Action;
  /** 0-based index in the plan. */
  index: number;
  total: number;
  /** Aborted when the user presses Stop. */
  signal: AbortSignal;
}

export interface ExecutionOptions {
  timeout?: number;
  requireApproval?: boolean;
  onProgress?: (step: string, status: 'pending' | 'executing' | 'completed' | 'failed') => void;
  /** @deprecated Use onAim. Still called, but not awaited. */
  onCursorMove?: (element: HTMLElement) => void;
  /** Called and awaited once the target is on screen, before acting. Fly the cursor here. */
  onAim?: (element: HTMLElement, info: StepInfo) => Promise<void> | void;
  /** Called and awaited right before the DOM is changed (press / typing animations). */
  onBeforeAct?: (element: HTMLElement, info: StepInfo) => Promise<void> | void;
  /** Called after each step completes (success or failure). */
  onStepEnd?: (info: StepInfo, result: ToolResult) => void;
  /** Called before each step starts. */
  onStepStart?: (info: StepInfo) => void;
  /** Called with true while waiting for an element or a route change, then false. */
  onWait?: (waiting: boolean, info: StepInfo) => void;
  allowSemanticLookup?: boolean;
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
  onAim: () => {},
  onBeforeAct: () => {},
  onStepEnd: () => {},
  onStepStart: () => {},
  onWait: () => {},
  allowSemanticLookup: false,
};

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** Waits until the element stops moving (smooth scroll finished), at most maxMs. */
async function waitForScrollSettle(element: HTMLElement, maxMs: number): Promise<void> {
  if (maxMs <= 0 || typeof requestAnimationFrame !== 'function') return;
  const start = Date.now();
  let last = element.getBoundingClientRect();
  let stableFrames = 0;
  while (Date.now() - start < maxMs) {
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    const now = element.getBoundingClientRect();
    if (Math.abs(now.top - last.top) < 0.5 && Math.abs(now.left - last.left) < 0.5) {
      stableFrames += 1;
      if (stableFrames >= 2) return;
    } else {
      stableFrames = 0;
    }
    last = now;
  }
}

/** Scrolls the target into view, lets it settle, then lets the cursor fly to it (awaited). */
async function animateCursorTo(element: HTMLElement, options: Required<ExecutionOptions>, info: StepInfo): Promise<void> {
  const reduced = prefersReducedMotion();
  if (typeof element.scrollIntoView === 'function') {
    element.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center', inline: 'center' });
  }
  await waitForScrollSettle(element, reduced ? 0 : 600);
  if (info.signal.aborted) return;
  options.onCursorMove(element);
  await options.onAim(element, info);
}

function cancelledResult(): ToolResult {
  return { id: crypto.randomUUID(), ok: false, error: 'cancelled by user' };
}

/** Flies the cursor to the element, then plays the "about to act" animation. False when stopped. */
async function prepareToAct(element: HTMLElement, options: Required<ExecutionOptions>, info: StepInfo): Promise<boolean> {
  await animateCursorTo(element, options, info);
  if (info.signal.aborted) return false;
  await options.onBeforeAct(element, info);
  return !info.signal.aborted;
}

const TARGET_ID_PATTERN = /^[a-zA-Z0-9_.:-]{1,120}$/;
const OP_MAP: Record<string, string> = {
  click: 'click',
  fill_input: 'fill',
  select_option: 'select',
  toggle_switch: 'toggle',
};

/**
 * Executes a single action
 */
async function executeAction(
  action: Action,
  options: Required<ExecutionOptions>,
  info: StepInfo
): Promise<ToolResult> {
  const { target_id, value, target_page, explanation, state, steps } = action;

  try {
    if (action.type in OP_MAP) {
      if (!target_id || !TARGET_ID_PATTERN.test(target_id)) {
        return {
          id: action.id ?? crypto.randomUUID(),
          ok: false,
          error: 'invalid target id',
        };
      }
      const registered = getRegisteredTarget(target_id);
      const requiredOp = OP_MAP[action.type];
      if (registered && (!registered.operations || !registered.operations.includes(requiredOp as any))) {
        return {
          id: action.id ?? crypto.randomUUID(),
          ok: false,
          error: 'operation not allowed',
        };
      }
    }

    switch (action.type) {
      case 'navigate':
        return await executeNavigate(target_page!, options, info);

      case 'click':
        return await executeClick(target_id!, options, info);

      case 'fill_input':
        return await executeFillInput(target_id!, value!, options, info);

      case 'select_option':
        return await executeSelectOption(target_id!, action.option ?? value!, options, info);

      case 'toggle_switch':
        return await executeToggleSwitch(target_id!, state!, options, info);

      case 'guided_tour':
        return await executeGuidedTour(steps || [], options, info.signal);

      case 'ask_clarification':
        return await executeAskClarification(action.question!, action.options!, options);

      default:
        return {
          id: action.id ?? crypto.randomUUID(),
          ok: false,
          error: `Unknown action type: ${(action as Action).type}`,
        };
    }
  } catch (error) {
    return {
      id: action.id ?? crypto.randomUUID(),
      ok: false,
      error: error instanceof Error ? error.message : 'Unknown execution error',
    };
  }
}

/**
 * Navigate to a page within the SPA
 */
async function executeNavigate(targetPage: string, options: Required<ExecutionOptions>, info: StepInfo): Promise<ToolResult> {
  options.onProgress(`navigate:${targetPage}`, 'executing');

  if (/^[a-z][a-z0-9+.-]*:/i.test(targetPage) || targetPage.startsWith('//')) {
    return { id: crypto.randomUUID(), ok: false, error: 'blocked: only in-app pages are allowed' };
  }

  const path = '/' + targetPage.replace(/^\/+/, '');

  const link = document.querySelector<HTMLElement>(`[data-ghost-nav="${CSS.escape(targetPage)}"], [data-ghost-nav="${CSS.escape(path)}"]`);
  if (link) {
    if (!(await prepareToAct(link, options, info))) return cancelledResult();
    link.click();
  } else {
    window.history.pushState({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }

  options.onWait(true, info);
  let reached = false;
  try {
    reached = await waitForNavigation(path);
  } finally {
    options.onWait(false, info);
  }
  if (!reached) {
    return { id: crypto.randomUUID(), ok: false, error: `navigation did not reach ${path}` };
  }

  options.onProgress(`navigate:${targetPage}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { navigated: path } };
}

/**
 * Click an element
 */
async function executeClick(targetId: string, options: Required<ExecutionOptions>, info: StepInfo): Promise<ToolResult> {
  options.onProgress(`click:${targetId}`, 'executing');

  options.onWait(true, info);
  let resolution: Awaited<ReturnType<typeof resolveTargetWithCascade>>;
  try {
    resolution = await resolveTargetWithCascade(targetId, {
      timeout: options.timeout,
      allowSemanticLookup: options.allowSemanticLookup,
    });
  } finally {
    options.onWait(false, info);
  }
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  // Re-resolve immediately before acting (stale reference protection)
  const freshElement = reResolveElement(targetId, {
    allowSemanticLookup: options.allowSemanticLookup,
  });
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(await prepareToAct(freshElement, options, info))) return cancelledResult();
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
  options: Required<ExecutionOptions>,
  info: StepInfo
): Promise<ToolResult> {
  options.onProgress(`fill:${targetId}`, 'executing');

  options.onWait(true, info);
  let resolution: Awaited<ReturnType<typeof resolveTargetWithCascade>>;
  try {
    resolution = await resolveTargetWithCascade(targetId, {
      timeout: options.timeout,
      allowSemanticLookup: options.allowSemanticLookup,
    });
  } finally {
    options.onWait(false, info);
  }
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  // Re-resolve immediately before acting
  const freshElement = reResolveElement(targetId, {
    allowSemanticLookup: options.allowSemanticLookup,
  });
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLInputElement) && !(freshElement instanceof HTMLTextAreaElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not an input or textarea: ${targetId}` };
  }

  if (!(await prepareToAct(freshElement, options, info))) return cancelledResult();

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
  options: Required<ExecutionOptions>,
  info: StepInfo
): Promise<ToolResult> {
  options.onProgress(`select:${targetId}`, 'executing');

  options.onWait(true, info);
  let resolution: Awaited<ReturnType<typeof resolveTargetWithCascade>>;
  try {
    resolution = await resolveTargetWithCascade(targetId, {
      timeout: options.timeout,
      allowSemanticLookup: options.allowSemanticLookup,
    });
  } finally {
    options.onWait(false, info);
  }
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  const freshElement = reResolveElement(targetId, {
    allowSemanticLookup: options.allowSemanticLookup,
  });
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLSelectElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not a select element: ${targetId}` };
  }

  if (!(await prepareToAct(freshElement, options, info))) return cancelledResult();

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
  options: Required<ExecutionOptions>,
  info: StepInfo
): Promise<ToolResult> {
  options.onProgress(`toggle:${targetId}`, 'executing');

  options.onWait(true, info);
  let resolution: Awaited<ReturnType<typeof resolveTargetWithCascade>>;
  try {
    resolution = await resolveTargetWithCascade(targetId, {
      timeout: options.timeout,
      allowSemanticLookup: options.allowSemanticLookup,
    });
  } finally {
    options.onWait(false, info);
  }
  if (!resolution.element) {
    return { id: crypto.randomUUID(), ok: false, error: `Element not found or not interactable: ${targetId}` };
  }

  const { element } = resolution;

  const freshElement = reResolveElement(targetId, {
    allowSemanticLookup: options.allowSemanticLookup,
  });
  if (!freshElement || !document.body.contains(freshElement)) {
    return { id: crypto.randomUUID(), ok: false, error: `Element became stale: ${targetId}` };
  }

  if (!(freshElement instanceof HTMLInputElement) || (freshElement.type !== 'checkbox' && freshElement.type !== 'radio')) {
    return { id: crypto.randomUUID(), ok: false, error: `Target is not a checkbox or radio: ${targetId}` };
  }

  if (!(await prepareToAct(freshElement, options, info))) return cancelledResult();

  setNativeCheckboxState(freshElement, state);
  await new Promise(resolve => setTimeout(resolve, 0));
  const after = document.body.contains(freshElement)
    ? freshElement
    : reResolveElement(targetId, { allowSemanticLookup: options.allowSemanticLookup });
  if (!(after instanceof HTMLInputElement) || after.checked !== state) {
    return { id: crypto.randomUUID(), ok: false, error: `Switch did not change: ${targetId}` };
  }

  options.onProgress(`toggle:${targetId}`, 'completed');
  return { id: crypto.randomUUID(), ok: true, output: { toggled: targetId, state } };
}

/**
 * Execute a guided tour
 */
async function executeGuidedTour(
  steps: any[],
  options: Required<ExecutionOptions>,
  signal?: AbortSignal
): Promise<ToolResult> {
  options.onProgress('guided_tour', 'executing');

  if (typeof document === 'undefined' || !document.body) {
    options.onProgress('guided_tour', 'failed');
    return { id: crypto.randomUUID(), ok: false, error: 'Document body not available for guided tour' };
  }

  return new Promise<ToolResult>((resolve) => {
    let resolved = false;
    const finish = (completed: boolean) => {
      if (resolved) return;
      resolved = true;
      options.onProgress('guided_tour', 'completed');
      resolve({ id: crypto.randomUUID(), ok: true, output: { completed } });
    };

    const tour = new TourEngine({
      onComplete: () => finish(true),
      onSkip: () => finish(false),
    });

    if (signal) {
      if (signal.aborted) {
        tour.stop().catch(() => {});
        finish(false);
        return;
      }
      signal.addEventListener(
        'abort',
        () => {
          tour.stop().catch(() => {});
          finish(false);
        },
        { once: true }
      );
    }

    tour.start(steps, document.body).catch((err) => {
      if (resolved) return;
      resolved = true;
      options.onProgress('guided_tour', 'failed');
      resolve({ id: crypto.randomUUID(), ok: false, error: String(err) });
    });
  });
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
async function waitForNavigation(expectedPath: string, timeoutMs = 3000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (window.location.pathname === expectedPath) {
      await new Promise(r => requestAnimationFrame(() => setTimeout(r, 100)));
      return true;
    }
    await new Promise(r => setTimeout(r, 50));
  }
  return false;
}

/**
 * Main executor that runs a sequence of actions
 */
export class ActionExecutor {
  private options: Required<ExecutionOptions>;
  private abortController: AbortController | null = null;
  private isStopped = false;

  constructor(options: ExecutionOptions = {}) {
    this.options = { ...DEFAULT_EXECUTION_OPTIONS, ...options };
  }

  /**
   * Execute an array of actions sequentially
   */
  async execute(actions: Action[]): Promise<ExecutionResult> {
    this.isStopped = false;
    this.abortController = new AbortController();
    const results: ToolResult[] = [];
    const skipRest = (from: number, reason: string) => {
      for (const rest of actions.slice(from)) results.push({ id: rest.id ?? crypto.randomUUID(), ok: false, error: reason });
    };
    for (let i = 0; i < actions.length; i++) {
      if (this.abortController.signal.aborted || this.isStopped) {
        skipRest(i, 'cancelled by user');
        this.isStopped = false;
        return { success: false, results, error: 'cancelled' };
      }
      const info: StepInfo = { action: actions[i], index: i, total: actions.length, signal: this.abortController.signal };
      this.options.onStepStart(info);
      const result = await executeAction(actions[i], this.options, info);
      result.id = actions[i].id ?? result.id;
      results.push(result);
      try {
        this.options.onStepEnd(info, result);
      } catch (hookError) {
        console.warn('[GhostCursor] onStepEnd hook failed:', hookError);
      }
      if (this.abortController.signal.aborted || this.isStopped) {
        skipRest(i + 1, 'cancelled by user');
        this.isStopped = false;
        return { success: false, results, error: 'cancelled' };
      }
      if (!result.ok) {
        skipRest(i + 1, 'skipped: an earlier step failed');
        return { success: false, results, error: result.error };
      }
    }
    return { success: true, results };
  }

  /**
   * Stop execution
   */
  stop(): void {
    this.isStopped = true;
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