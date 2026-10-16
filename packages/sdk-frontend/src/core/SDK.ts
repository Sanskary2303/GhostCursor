import { h, render } from 'preact';
import type { PageContext, Action, ToolResult, Target, PublicResponse } from './types';
import { ContextProvider } from './context/ContextProvider';
import { createTransport, TransportManager, Transport } from './transport/Transport';
import { ActionExecutor, ExecutionOptions } from './executor/ActionExecutor';
import { CursorEngine, getCursorEngine, disposeCursorEngine } from './engine/CursorEngine';
import { TourEngine } from './engine/TourEngine';
import { ChatWidget, Message } from './chat/ChatWidget';
import { resolveTargetWithCascade, registerTarget } from './dom-utils';

export interface GhostCursorSDK {
  dispose(): void;
  sendMessage(message: string): Promise<void>;
  executeActions(actions: Action[], token?: string): Promise<PublicResponse | null>;
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
  };
  requireApprovalForActions?: boolean;
  transport?: 'http' | 'websocket';
  allowSemanticLookup?: boolean;
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

  // Merge theme with defaults
  const mergedTheme = {
    primaryColor: '#0052FF',
    cursorColor: '#FF4D4D',
    position: 'bottom-right' as const,
    ...theme,
  };

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
    onMessage: handleResponse,
    onError: (error) => console.error('[GhostCursor] Transport error:', error),
    onClose: () => console.log('[GhostCursor] Connection closed'),
    reconnect: true,
  }, options.transport ?? 'http');

  const transportManager = new TransportManager(transport);

  const actionExecutor = new ActionExecutor({
    timeout: 5000,
    requireApproval: requireApprovalForActions,
    allowSemanticLookup,
    onProgress: (step, status) => console.log(`[GhostCursor] ${step}: ${status}`),
    onCursorMove: (element) => cursorEngine.moveTo(element),
  });

  const cursorEngine = getCursorEngine({
    color: mergedTheme.cursorColor,
    size: 24,
    animationDuration: 500,
  });

  const tourEngine = new TourEngine({
    onStepChange: (index, step) => console.log(`[GhostCursor] Tour step ${index + 1}:`, step),
    onComplete: () => console.log('[GhostCursor] Tour completed'),
    onSkip: () => console.log('[GhostCursor] Tour skipped'),
  });

  // Mount widget
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
      widgetContainer = document.createElement('div');
      widgetContainer.id = 'ghost-cursor-widget-container';
      document.body.appendChild(widgetContainer);
    }
  }

  // Create shadow root for widget isolation (reuse if already present)
  const shadowRoot = widgetContainer.shadowRoot || widgetContainer.attachShadow({ mode: 'open' });

  // State
  let isDisposed = false;
  let currentRunId: string | null = null;
  const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled']);
  let lastStatus: string | null = null;
  function rememberStatus(res: { runId: string; status: string }): void {
    lastStatus = res.status;
    currentRunId = TERMINAL_STATUSES.has(res.status) ? null : res.runId;
  }

  // Render Preact ChatWidget into shadow root
  render(
    h(ChatWidget, {
      apiEndpoint: gatewayUrl,
      theme: mergedTheme,
      requireApprovalForActions,
      initialContext: { page: getPage(), values: {}, availableTargets: [] },
      onSendMessage: async (msg: string, ctx: any) => {
        const rawCtx = contextProvider.captureContext();
        const pageContext = {
          page: rawCtx?.page ?? getPage(),
          values: rawCtx?.values ?? {},
          availableTargets: rawCtx?.availableTargets ?? [],
        };
        const res = currentRunId && lastStatus === 'awaiting_answer'
          ? await transportManager.continue('answer', { answer: msg })
          : await transportManager.start(msg, pageContext);
        rememberStatus(res);
        return res;
      },
      onActionApproval: (actions: any[], token?: string) => executeActions(actions, token),
      onCancelApproval: async () => {
        if (!currentRunId) return null;
        const res = await transportManager.continue('cancel', {});
        rememberStatus(res);
        return res;
      },
      onStop: () => {
        actionExecutor.stop();
      },
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

    const res = currentRunId && lastStatus === 'awaiting_answer'
      ? await transportManager.continue('answer', { answer: message })
      : await transportManager.start(message, pageContext);
    rememberStatus(res);
  }

  /**
   * Execute approved actions
   */
  async function executeActions(actions: Action[], token?: string): Promise<PublicResponse | null> {
    const currentToken = `${transportManager.getRunId()}:${transportManager.getRevision()}`;
    if (isDisposed || !currentRunId || lastStatus !== 'awaiting_actions' || (token && token !== currentToken)) {
      throw new Error('This plan is out of date.');
    }
    const execution = await actionExecutor.execute(actions);
    const res = await transportManager.continue('actions', { results: execution.results });
    rememberStatus(res);
    return res;
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

    contextProvider.destroy();
    transportManager.close();
    actionExecutor.dispose();
    disposeCursorEngine();
    render(null, shadowRoot);

    if (widgetContainer.parentNode && !mount) {
      widgetContainer.parentNode.removeChild(widgetContainer);
    }

    console.log('[GhostCursor] SDK disposed');
  }

  // Initialize
  contextProvider.start();
  transport.connect().catch(err => console.error('[GhostCursor] Initial connection failed:', err));

  return {
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