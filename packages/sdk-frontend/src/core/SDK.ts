import { h, render } from 'preact';
import type { PageContext, Action, ToolResult, Target, PublicResponse } from './types';
import { ContextProvider } from './context/ContextProvider';
import { createTransport, TransportManager, Transport } from './transport/Transport';
import { ActionExecutor, type ExecutionResult } from './executor/ActionExecutor';
import { CursorController, type CursorOutcome, type RingHandle } from './cursor/CursorController';
import { createBridge, INITIAL_WIDGET_STATE, type WidgetBridgeState } from './bridge';
import { TourEngine } from './engine/TourEngine';
import { ChatWidget, Message } from './chat/ChatWidget';
import { resolveTargetWithCascade, registerTarget } from './dom-utils';
import { BRAND } from './cursor/assets';
import type { ThemeMode } from './theme/tokens';
import { describeAction } from './chat/describe';
import { createHistoryClient } from './history';
import { defineGhostCursorElement } from './element';
import { initXray } from './xray';

const SESSION_STORAGE_KEY = 'ghost-cursor.session';
const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function getStoredSessionId(): string | null {
  try {
    if (typeof sessionStorage !== 'undefined') {
      const id = sessionStorage.getItem(SESSION_STORAGE_KEY);
      return id && UUID_REGEX.test(id) ? id : null;
    }
  } catch {}
  return null;
}

function setStoredSessionId(id: string | null): void {
  try {
    if (typeof sessionStorage !== 'undefined') {
      if (id) {
        sessionStorage.setItem(SESSION_STORAGE_KEY, id);
      } else {
        sessionStorage.removeItem(SESSION_STORAGE_KEY);
      }
    }
  } catch {}
}

export interface GhostCursorSDK {
  readonly host?: HTMLElement;
  dispose(): void;
  sendMessage(message: string): Promise<void>;
  executeActions(actions: Action[], token?: string, stepByStep?: boolean): Promise<PublicResponse | null>;
  startTour(steps: any[]): Promise<void>;
  updateContext(context: Partial<PageContext>): void;
  getContext(): PageContext | null;
  registerTarget(id: string, target: Target): void;
}

export interface CreateGhostCursorOptions {
  gatewayUrl: string;
  page: () => string;
  targets: Record<string, Target>;
  headers?: () => Record<string, string> | Promise<Record<string, string>>;
  mount?: HTMLElement;
  theme?: {
    primaryColor?: string;
    cursorColor?: string;
    position?: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
    mode?: ThemeMode;
  };
  requireApprovalForActions?: boolean;
  transport?: 'http' | 'websocket';
  allowSemanticLookup?: boolean;
  streaming?: boolean;
  xray?: boolean;
  allowXrayParam?: boolean;
  onMessage?: (message: Message) => void;
  onActionsRequested?: (actions: Action[]) => void;
  onContextChange?: (context: PageContext) => void;
}

function createDefaultHeaders(): Record<string, string> {
  return {
    'Content-Type': 'application/json',
    'X-Ghost-SDK-Version': '0.1.0',
  };
}

/**
 * Main SDK factory function
 */
export function createGhostCursor(options: CreateGhostCursorOptions): GhostCursorSDK {
  const {
    gatewayUrl,
    page: getPage,
    targets,
    headers = createDefaultHeaders,
    mount,
    theme = {},
    requireApprovalForActions = true,
    allowSemanticLookup = false,
    onMessage,
    onActionsRequested,
    onContextChange,
  } = options;

  const isStreaming = options.streaming ?? (typeof window !== 'undefined' && Boolean((window as any).__GC_STREAMING));

  // Drop undefined values so wrappers that forward every key don't erase the defaults.
  const definedTheme = Object.fromEntries(
    Object.entries(theme).filter(([, value]) => value !== undefined)
  ) as NonNullable<CreateGhostCursorOptions['theme']>;
  const mergedTheme = {
    primaryColor: BRAND.blue as string,
    cursorColor: BRAND.blue as string,
    position: 'bottom-right' as NonNullable<CreateGhostCursorOptions['theme']>['position'],
    mode: 'midnight' as ThemeMode,
    ...definedTheme,
  } as Required<NonNullable<CreateGhostCursorOptions['theme']>>;

  // Initialize components
  const contextProvider = new ContextProvider({
    pageSelector: getPage,
    valueSelectors: {},
    targetSelectors: ['[data-ghost-id]'],
    excludeSelectors: [
      '.sensitive-data',
      '#credit-card-form',
      '[data-sensitive]',
      '[data-pii]',
      '[autocomplete="cc-*"]',
      '[autocomplete*="password"]',
    ],
    debounceMs: 300,
    onContextChange: (ctx) => onContextChange?.(ctx),
  });

  const transport = createTransport({
    gatewayUrl,
    headers,
    streaming: isStreaming,
    onMessage: handleResponse,
    onError: (error) => console.error('[GhostCursor] Transport error:', error),
    onClose: () => console.log('[GhostCursor] Connection closed'),
    reconnect: true,
  }, options.transport ?? 'http');

  const transportManager = new TransportManager(transport);

  // Mount widget
  defineGhostCursorElement();
  let widgetContainer: HTMLElement;
  if (mount) {
    widgetContainer = mount;
    if (!document.body.contains(widgetContainer)) {
      widgetContainer.id = widgetContainer.id || 'ghost-cursor-widget-container';
      document.body.appendChild(widgetContainer);
    }
  } else {
    const existing = document.getElementById('ghost-cursor-widget-container');
    if (existing) {
      widgetContainer = existing;
    } else {
      const tag = typeof customElements !== 'undefined' ? 'ghost-cursor-widget' : 'div';
      widgetContainer = document.createElement(tag);
      widgetContainer.id = 'ghost-cursor-widget-container';
      document.body.appendChild(widgetContainer);
    }
  }

  // Create shadow root for widget isolation (reuse if already present)
  const shadowRoot = widgetContainer.shadowRoot || widgetContainer.attachShadow({ mode: 'open' });

  const widgetBridge = createBridge<WidgetBridgeState>({ ...INITIAL_WIDGET_STATE });
  // Created now, mounted lazily on the first undock().
  const cursor = new CursorController({
    accent: mergedTheme.cursorColor,
    getDockRect: () => {
      const dock = shadowRoot.getElementById('gc-dock') ?? shadowRoot.getElementById('gc-launcher');
      return dock ? dock.getBoundingClientRect() : null;
    },
    getDockElement: () => shadowRoot.getElementById('gc-dock') ?? shadowRoot.getElementById('gc-launcher'),
    onStateChange: (state) => {
      const away = state !== 'docked';
      if (widgetBridge.get().cursorAway !== away) widgetBridge.set({ cursorAway: away });
    },
    onDocked: (outcome) => {
      widgetBridge.set({ outcome, step: null, status: '' });
      if (outcome !== 'error') {
        setTimeout(() => {
          if (widgetBridge.get().outcome === outcome) widgetBridge.set({ outcome: 'none' });
        }, 2500);
      }
    },
  });

  let activeRing: RingHandle | null = null;
  const actionExecutor = new ActionExecutor({
    timeout: 8000,
    requireApproval: requireApprovalForActions,
    allowSemanticLookup,
    onProgress: (step, status) => console.log(`[GhostCursor] ${step}: ${status}`),
    onStepApproval: async (_element, info) => {
      cursor.setCaption('Approve this step?');
      return new Promise<boolean>((resolve) => {
        let settled = false;
        const cleanUp = () => {
          widgetBridge.set({ awaitingNextStep: false, onNextStep: null });
          info.signal.removeEventListener('abort', onAbort);
        };
        const onAbort = () => {
          if (settled) return;
          settled = true;
          cleanUp();
          resolve(false);
        };
        const onNext = () => {
          if (settled) return;
          settled = true;
          cleanUp();
          cursor.setCaption(`${info.index + 1}/${info.total} • ${describeAction(info.action)}`);
          resolve(true);
        };
        info.signal.addEventListener('abort', onAbort);
        widgetBridge.set({
          awaitingNextStep: true,
          onNextStep: onNext,
        });
      });
    },
    onAim: async (element, info) => {
      await keepTargetVisible(element);
      activeRing?.remove();
      activeRing = null;
      await cursor.flyTo(element);
      if (info.signal.aborted) return;
      if (info.tour) {
        cursor.setCaption(`Tour ${info.tour.index + 1}/${info.tour.total}`);
        return; // the tour draws its own spotlight, so no ring
      }
      activeRing = cursor.highlight(element);
      if (info.risk === 'never') {
        cursor.setCaption("You'll need to click this yourself");
      } else {
        cursor.setCaption(`${info.index + 1}/${info.total} • ${describeAction(info.action)}`);
      }
    },
    onBeforeAct: async (element, info) => {
      if (info.action.type === 'fill_input') {
        await cursor.typeOverlay(element, String(info.action.value ?? ''), info.signal);
      } else {
        await cursor.press();
      }
    },
    onStepEnd: (info, result) => {
      if (info.risk === 'never') {
        setTimeout(() => cursor.setCaption(null), 3000);
      } else {
        cursor.setCaption(null);
      }
      const ring = activeRing;
      activeRing = null;
      if (!ring) return;
      ring.setTone(result.ok ? 'success' : 'error');
      setTimeout(() => ring.remove(), result.ok ? 350 : (info.risk === 'never' ? 3000 : 900));
    },
    onStepStart: (info) => {
      widgetBridge.set({
        step: { index: info.index + 1, total: info.total },
        status: `${info.index + 1}/${info.total} • ${describeAction(info.action)}`,
      });
    },
    onWait: (waiting) => cursor.wait(waiting),
  });

  const tourEngine = new TourEngine({
    onStepChange: (index, step) => console.log(`[GhostCursor] Tour step ${index + 1}:`, step),
    onComplete: () => console.log('[GhostCursor] Tour completed'),
    onSkip: () => console.log('[GhostCursor] Tour skipped'),
  });

  const nextFrame = () => new Promise<void>((resolve) => {
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(() => resolve());
    else setTimeout(resolve, 16);
  });

  function overlaps(a: DOMRect, b: DOMRect, pad = 12): boolean {
    return a.left < b.right + pad && a.right > b.left - pad && a.top < b.bottom + pad && a.bottom > b.top - pad;
  }

  /** If the widget covers the target, move the widget to the other side first. */
  async function keepTargetVisible(element: HTMLElement): Promise<void> {
    const widget = shadowRoot.getElementById('ghost-cursor-widget');
    if (!widget || !overlaps(element.getBoundingClientRect(), widget.getBoundingClientRect())) return;
    widgetBridge.set({ flipSide: !widgetBridge.get().flipSide });
    await nextFrame();
    await nextFrame();
  }

  /** Clean up the step visuals, put the widget back, then fly home (not awaited by callers). */
  async function finishRun(outcome: CursorOutcome): Promise<void> {
    activeRing?.remove();
    activeRing = null;
    cursor.setCaption(null);
    widgetBridge.set({ awaitingNextStep: false, onNextStep: null });
    if (widgetBridge.get().flipSide) {
      widgetBridge.set({ flipSide: false });
      await nextFrame();
    }
    await cursor.dock(outcome);
  }

  // State
  let isDisposed = false;
  let currentRunId: string | null = null;
  const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);
  let lastStatus: string | null = null;
  function rememberStatus(res: { runId: string; status: string }): void {
    lastStatus = res.status;
    currentRunId = TERMINAL_STATUSES.has(res.status) ? null : res.runId;
  }

  const historyClient = createHistoryClient(gatewayUrl, headers);
  let currentSessionId: string | null = getStoredSessionId();

  async function ensureSession(): Promise<string | null> {
    if (currentSessionId) return currentSessionId;
    try {
      const newId = await historyClient.create();
      if (newId) {
        currentSessionId = newId;
        setStoredSessionId(newId);
      }
    } catch (err) {
      console.warn('[GhostCursor] Failed to create session:', err);
    }
    return currentSessionId;
  }

  // Render Preact ChatWidget into shadow root
  render(
    h(ChatWidget, {
      apiEndpoint: gatewayUrl,
      theme: mergedTheme,
      bridge: widgetBridge,
      requireApprovalForActions,
      getPage,
      initialContext: { page: getPage(), values: {}, availableTargets: [] },
      history: {
        list: () => historyClient.list(),
        create: () => historyClient.create(),
        messages: (id: string) => historyClient.messages(id),
        current: () => currentSessionId,
        select: (id: string | null) => {
          currentSessionId = id;
          setStoredSessionId(id);
          currentRunId = null;
          lastStatus = null;
        },
      },
      onSendMessage: async (msg: string, ctx: any, callbacks?: any) => {
        const rawCtx = contextProvider.captureContext();
        const pageContext = {
          page: rawCtx?.page ?? getPage(),
          values: rawCtx?.values ?? {},
          availableTargets: rawCtx?.availableTargets ?? [],
        };
        let res: PublicResponse;
        if (currentRunId && lastStatus === 'awaiting_answer') {
          res = await transportManager.continue('answer', { answer: msg }, callbacks);
        } else {
          const sid = await ensureSession();
          res = await transportManager.start(msg, pageContext, sid ?? undefined, callbacks);
        }
        rememberStatus(res);
        return res;
      },
      onActionApproval: (actions: any[], token?: string, stepByStep?: boolean) => executeActions(actions, token, stepByStep),
      onCancelApproval: async () => {
        if (!currentRunId) return null;
        const res = await transportManager.continue('cancel', {});
        rememberStatus(res);
        return res;
      },
      onStop: () => {
        actionExecutor.stop();
        cursor.cancel();
      },
      onShowMe: (steps: { targetId: string; label: string }[]) => {
        void startTour(steps.map(s => ({ target_id: s.targetId, message: `Here: ${s.label}`, spotlight: true })));
      },
      onPreview: (targets: HTMLElement[]) => cursor.showPreview(targets),
      onClearPreview: () => cursor.clearPreview(),
    }),
    shadowRoot
  );

  // Register customer targets
  for (const [id, target] of Object.entries(targets)) {
    registerTarget(id, target);
  }

  /**
   * Handle response from backend
   */
  async function handleResponse(response: any): Promise<void> {
    if (isDisposed) return;

    rememberStatus(response);

    // Handle different response types
    if (response.reply) {
      onMessage?.({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.reply,
        timestamp: new Date(),
      } as Message);
    }

    if (response.questions && response.questions.length > 0) {
      // Questions are handled by the widget UI
      onMessage?.({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: response.reply || '',
        timestamp: new Date(),
        questions: response.questions,
      } as Message);
    }

    if (response.actions && response.actions.length > 0) {
      onActionsRequested?.(response.actions);

      if (requireApprovalForActions) {
        // Widget will show approval UI
        onMessage?.({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: response.reply || 'I have a plan. Please approve to execute.',
          timestamp: new Date(),
          actions: response.actions,
        } as Message);
      }
    }

    if (response.status === 'completed') {
      console.log('[GhostCursor] Run completed');
    } else if (response.status === 'failed') {
      console.error('[GhostCursor] Run failed:', response.reply);
    }
  }

  /**
   * Send a message to the backend
   */
  async function sendMessage(message: string): Promise<void> {
    if (isDisposed) throw new Error('SDK is disposed');

    const rawCtx = contextProvider.captureContext();

    const pageContext = {
      page: rawCtx?.page ?? getPage(),
      values: rawCtx?.values ?? {},
      availableTargets: rawCtx?.availableTargets ?? [],
    };

    let res: PublicResponse;
    if (currentRunId && lastStatus === 'awaiting_answer') {
      res = await transportManager.continue('answer', { answer: message });
    } else {
      const sid = await ensureSession();
      res = await transportManager.start(message, pageContext, sid ?? undefined);
    }
    rememberStatus(res);
  }

  /**
   * Execute approved actions
   */
  async function executeActions(actions: Action[], token?: string, stepByStep = false): Promise<PublicResponse | null> {
    const currentToken = `${transportManager.getRunId()}:${transportManager.getRevision()}`;
    if (isDisposed || !currentRunId || lastStatus !== 'awaiting_actions' || (token && token !== currentToken)) {
      throw new Error('This plan is out of date.');
    }
    const execution = await runWithCursor(actions, stepByStep);
    const res = await transportManager.continue('actions', { results: execution.results });
    rememberStatus(res);
    return res;
  }

  async function runWithCursor(actions: Action[], stepByStep = false): Promise<ExecutionResult> {
    const startedAt = Date.now();
    await nextFrame(); // let the widget collapse into the mission bar first
    await cursor.undock();
    let execution: ExecutionResult;
    try {
      execution = await actionExecutor.execute(actions, { stepByStep });
    } catch (error) {
      widgetBridge.set({
        lastRun: {
          results: [{ ok: false, error: error instanceof Error ? error.message : String(error) }],
          ms: Date.now() - startedAt,
        },
      });
      void finishRun('error');
      throw error;
    }
    const outcome: CursorOutcome = execution.success ? 'success' : execution.error === 'cancelled' ? 'stopped' : 'error';
    widgetBridge.set({
      lastRun: {
        results: execution.results.map(r => ({ ok: r.ok, error: r.error })),
        ms: Date.now() - startedAt,
      },
    });
    void finishRun(outcome);
    return execution;
  }

  /**
   * Start a guided tour
   */
  async function startTour(steps: any[]): Promise<void> {
    const hostElement = document.body; // Tour operates on host DOM
    await tourEngine.start(steps, hostElement);
  }

  /**
   * Update context manually
   */
  function updateContext(context: Partial<PageContext>): void {
    contextProvider.captureContext();
  }

  /**
   * Get current context
   */
  function getContext(): PageContext | null {
    return contextProvider.getContext();
  }

  /**
   * Register a new target
   */
  function registerTargetFn(id: string, target: Target): void {
    registerTarget(id, target);
  }

  /**
   * Dispose of all resources
   */
  function dispose(): void {
    if (isDisposed) return;
    isDisposed = true;

    xrayInstance?.dispose();
    contextProvider.destroy();
    transportManager.close();
    actionExecutor.dispose();
    cursor.dispose();
    render(null, shadowRoot);

    if (widgetContainer.parentNode && !mount) {
      widgetContainer.parentNode.removeChild(widgetContainer);
    }

    console.log('[GhostCursor] SDK disposed');
  }

  // Initialize
  const xrayInstance = initXray({
    xray: options.xray,
    allowXrayParam: options.allowXrayParam,
    targets,
  });
  contextProvider.start();
  transport.connect().catch(err => console.error('[GhostCursor] Initial connection failed:', err));

  return {
    host: widgetContainer,
    dispose,
    sendMessage,
    executeActions,
    startTour,
    updateContext,
    getContext,
    registerTarget: registerTargetFn,
  };
}

// Re-export types for consumers
export * from './types';
export * from './native-setter';
export * from './dom-utils';
export * from './executor/ActionExecutor';
export * from './engine/CursorEngine';
export * from './engine/TourEngine';
export * from './chat/ChatWidget';
export * from './context/ContextProvider';
export * from './transport/Transport';
export * from './element';
export * from './xray';