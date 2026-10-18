/**
 * Chat Widget - Preact-based UI component rendered in Shadow DOM
 * Fully style-isolated from host application
 */

import { h, Component, createRef } from 'preact';
import type { ThemeMode, ThemeTokens } from '../theme/tokens';
import { BrandCursor } from './BrandCursor';
import { WIDGET_CSS } from './widgetStyles';
import { BRAND } from '../cursor/assets';
import { prefersDarkScheme, resolveMode, tokensFor, tokensToCss } from '../theme/tokens';
import { ACTION_ICONS, describeAction } from './describe';
import type { Action } from '../types';
import { INITIAL_WIDGET_STATE } from '../bridge';
import type { Bridge, WidgetBridgeState } from '../bridge';
import type { SessionSummary, HistoryMessage } from '../history';

export interface HistoryProp {
  list: () => Promise<SessionSummary[]>;
  create: () => Promise<string | null>;
  messages: (id: string) => Promise<HistoryMessage[]>;
  current: () => string | null;
  select: (id: string | null) => void;
}

export interface RunCardStep {
  label: string;
  status: 'done' | 'failed' | 'skipped';
  targetId?: string;
  error?: string;
}

export interface RunCard {
  kind: 'receipt' | 'recovery';
  steps: RunCardStep[];
  seconds: number;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  actions?: any[];
  questions?: { question: string; options: string[] }[];
  isStreaming?: boolean;
  card?: RunCard;
}

export interface ChatWidgetProps {
  apiEndpoint: string;
  theme: {
    primaryColor: string;
    cursorColor: string;
    position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
    mode?: ThemeMode;
  };
  bridge?: Bridge<WidgetBridgeState>;
  requireApprovalForActions: boolean;
  onSendMessage: (message: string, context: any, callbacks?: { onStatus?: (status: string) => void; onDelta?: (delta: string) => void }) => Promise<any>;
  onActionApproval: (actions: any[], token?: string, stepByStep?: boolean) => Promise<any>;
  onCancelApproval?: () => Promise<any>;
  onStop?: () => void;
  onShowMe?: (steps: { targetId: string; label: string }[]) => void;
  onTour?: () => Promise<void> | void;
  history?: HistoryProp;
  initialContext: any;
}

export interface ChatWidgetState {
  isOpen: boolean;
  messages: Message[];
  inputValue: string;
  isLoading: boolean;
  isExecutingActions: boolean;
  showActionApproval: boolean;
  pendingActions: any[];
  approvalToken: string | null;
  unreadCount: number;
  context: any;
  error: string | null;
  ui: WidgetBridgeState;
  drawerOpen: boolean;
  sessions: SessionSummary[];
  query: string;
  hasRehydrated?: boolean;
  askBubble: { text: string; top: number; left: number } | null;
  showSlashMenu: boolean;
  streamingStatus?: string | null;
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = Date.now();
  const diffSec = Math.floor((now - date.getTime()) / 1000);
  if (isNaN(diffSec) || diffSec < 0) return 'Just now';
  if (diffSec < 60) return 'Just now';
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 30) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

export class ChatWidget extends Component<ChatWidgetProps, ChatWidgetState> {
  state: ChatWidgetState = {
    isOpen: false,
    messages: [] as Message[],
    inputValue: '',
    isLoading: false,
    isExecutingActions: false,
    showActionApproval: false,
    pendingActions: [] as any[],
    approvalToken: null,
    unreadCount: 0,
    context: this.props.initialContext,
    error: null as string | null,
    ui: this.props.bridge?.get() ?? INITIAL_WIDGET_STATE,
    drawerOpen: false,
    sessions: [] as SessionSummary[],
    query: '',
    hasRehydrated: false,
    askBubble: null,
    showSlashMenu: false,
  };

  private messagesEndRef = createRef<HTMLDivElement>();
  private inputRef = createRef<HTMLTextAreaElement>();
  private abortController: AbortController | null = null;
  private isStoppedByUser = false;
  private lastRequest = '';
  private unsubscribeBridge: (() => void) | null = null;
  private tokens: ThemeTokens = tokensFor(
    resolveMode(this.props.theme.mode, prefersDarkScheme()),
    this.props.theme.primaryColor,
  );
  private css = tokensToCss(this.tokens) + WIDGET_CSS;

  componentDidMount() {
    this.scrollToBottom();
    this.setupResizeListener();
    window.addEventListener('keydown', this.handleKeyDown);
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('selectionchange', this.handleSelectionChange);
      document.addEventListener('mousedown', this.handleDocumentMouseDown);
    }
    this.unsubscribeBridge = this.props.bridge?.subscribe(ui => this.setState({ ui })) ?? null;
    if (this.props.history) {
      const storedId = this.props.history.current();
      if (storedId) {
        void this.loadSession(storedId);
      }
    }
  }

  componentWillUnmount() {
    this.cleanup();
  }

  componentDidUpdate(_prevProps: ChatWidgetProps, prevState: ChatWidgetState) {
    if (!prevState.isOpen && this.state.isOpen) {
      if (this.state.unreadCount > 0) {
        this.setState({ unreadCount: 0 });
      }
      setTimeout(() => {
        this.inputRef.current?.focus();
      }, 50);
    }
  }

  private setupResizeListener() {
    window.addEventListener('resize', this.handleResize);
  }

  private handleResize = () => {
    this.forceUpdate();
  };

  private handleKeyDown = (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      const active = typeof document !== 'undefined' ? document.activeElement : null;
      if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || (active as HTMLElement).isContentEditable)) {
        const host = typeof document !== 'undefined' ? document.getElementById('ghost-cursor-widget-container') : null;
        if (host && !host.contains(active)) {
          return;
        }
      }
      e.preventDefault();
      this.setState({ isOpen: true }, () => {
        setTimeout(() => this.inputRef.current?.focus(), 50);
      });
      return;
    }

    if (e.key !== 'Escape') return;
    if (this.state.drawerOpen) {
      this.setState({ drawerOpen: false, query: '' });
    } else if (this.state.isExecutingActions) {
      this.handleStop();
    } else if (this.state.isOpen) {
      this.setState({ isOpen: false });
    }
  };

  private handleDocumentMouseDown = (e: MouseEvent) => {
    if (this.state.askBubble) {
      const path = typeof e.composedPath === 'function' ? e.composedPath() : [e.target];
      const onBubble = path.some(el => (el instanceof HTMLElement) && (el.classList.contains('gc-ask-bubble') || el.closest?.('.gc-ask-bubble')));
      if (!onBubble) {
        this.setState({ askBubble: null });
      }
    }
  };

  private handleSelectionChange = () => {
    if (typeof window === 'undefined') return;
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    const text = selection.toString().trim();
    if (!text || selection.rangeCount === 0) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    const range = selection.getRangeAt(0);
    const container = range.commonAncestorContainer;
    const el = container.nodeType === Node.ELEMENT_NODE ? (container as Element) : container.parentElement;
    if (!el) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    // 1. Not inside inputs, textareas, selects, or contenteditable
    if (el.closest('input, textarea, select, [contenteditable="true"], [contenteditable=""]')) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    // 2. Not inside the widget or overlays
    if (el.closest('#ghost-cursor-widget-container, ghost-cursor-widget, #ghost-cursor-overlay, #ghost-cursor-rings')) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    // 3. Not inside sensitive containers
    if (el.closest('[data-sensitive], [data-pii], .sensitive-data, #credit-card-form, [autocomplete*="password"], [autocomplete^="cc-"]')) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    const rect = typeof range.getBoundingClientRect === 'function' ? range.getBoundingClientRect() : null;
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      if (this.state.askBubble) this.setState({ askBubble: null });
      return;
    }
    const top = rect.top >= 44 ? rect.top - 38 : rect.bottom + 8;
    const left = Math.max(10, Math.min(window.innerWidth - 130, rect.left + rect.width / 2 - 45));
    this.setState({
      askBubble: { text, top, left },
    });
  };

  private handleAskBubbleClick = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!this.state.askBubble) return;
    const raw = this.state.askBubble.text;
    const snippet = raw.length > 200 ? raw.slice(0, 200) : raw;
    const prefilled = `Explain: "${snippet}"`;
    this.setState({
      isOpen: true,
      inputValue: prefilled,
      askBubble: null,
    }, () => {
      setTimeout(() => this.inputRef.current?.focus(), 50);
    });
  };

  private openDrawer = async () => {
    this.setState({ drawerOpen: true, query: '' });
    if (this.props.history) {
      try {
        const sessions = await this.props.history.list();
        this.setState({ sessions });
      } catch (err) {
        console.warn('[GhostCursor] Failed to list sessions:', err);
      }
    }
  };

  private toggleDrawer = async () => {
    if (this.state.drawerOpen) {
      this.setState({ drawerOpen: false, query: '' });
      return;
    }
    await this.openDrawer();
  };

  private handleNewChat = () => {
    this.props.history?.select(null);
    this.setState({
      drawerOpen: false,
      query: '',
      messages: [],
      showActionApproval: false,
      pendingActions: [],
      error: null,
      hasRehydrated: false,
    });
  };

  private handleSelectSession = async (sessionId: string) => {
    this.setState({ drawerOpen: false, query: '' });
    this.props.history?.select(sessionId);
    await this.loadSession(sessionId);
  };

  private loadSession = async (sessionId: string) => {
    if (!this.props.history) return;
    try {
      const rawMessages = await this.props.history.messages(sessionId);
      const messages: Message[] = rawMessages.map(m => ({
        id: crypto.randomUUID(),
        role: m.role,
        content: m.content,
        timestamp: new Date(),
      }));
      this.setState({
        messages,
        isLoading: false,
        showActionApproval: false,
        pendingActions: [],
        error: null,
        hasRehydrated: messages.length > 0,
      }, () => this.scrollToBottom());
    } catch (err) {
      console.warn('[GhostCursor] Failed to load session messages:', err);
      if (err instanceof Error && err.message === 'HTTP 404') {
        this.props.history.select(null);
        this.setState({
          messages: [],
          hasRehydrated: false,
          isLoading: false,
        });
        return;
      }
      this.setState({ isLoading: false });
    }
  };

  private cleanup() {
    window.removeEventListener('resize', this.handleResize);
    window.removeEventListener('keydown', this.handleKeyDown);
    if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function') {
      document.removeEventListener('selectionchange', this.handleSelectionChange);
      document.removeEventListener('mousedown', this.handleDocumentMouseDown);
    }
    this.unsubscribeBridge?.();
    this.unsubscribeBridge = null;
    if (this.abortController) {
      this.abortController.abort();
    }
  }

  private scrollToBottom = () => {
    const reduced = typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setTimeout(() => {
      this.messagesEndRef.current?.scrollIntoView?.({ behavior: reduced ? 'auto' : 'smooth' });
    }, 100);
  };

  private addMessage = (message: Omit<Message, 'id' | 'timestamp'>): Message => {
    const newMessage: Message = {
      ...message,
      id: crypto.randomUUID(),
      timestamp: new Date(),
    };
    this.setState(prev => {
      const isAssistant = message.role === 'assistant';
      const unreadCount = (!prev.isOpen && isAssistant) ? prev.unreadCount + 1 : prev.unreadCount;
      return {
        messages: [...prev.messages, newMessage],
        unreadCount,
      };
    }, () => this.scrollToBottom());
    return newMessage;
  };

  private applyResponse = (messageId: string, response: any, card?: RunCard | null) => {
    this.setState(prev => ({
      messages: prev.messages.map(m => m.id === messageId
        ? {
            ...m,
            content: response.reply,
            isStreaming: false,
            questions: response.questions?.length ? response.questions : undefined,
            ...(card ? { card } : {}),
          }
        : m),
    }));
    if (response.actions?.length) {
      const approvalToken = (response.runId && response.revision !== undefined)
        ? `${response.runId}:${response.revision}`
        : null;
      if (this.props.requireApprovalForActions) {
        this.setState({
          showActionApproval: true,
          pendingActions: response.actions,
          approvalToken,
        });
      } else {
        void this.executeActions(response.actions, approvalToken ?? undefined);
      }
    }
  };

  private handleSendMessage = async (e?: Event, textOverride?: string) => {
    e?.preventDefault();
    const { inputValue, isLoading, isExecutingActions } = this.state;
    const message = (textOverride ?? inputValue).trim();
    if (!message || isLoading || isExecutingActions) return;

    if (message === '/new') {
      this.setState({ inputValue: '', showSlashMenu: false });
      this.handleNewChat();
      return;
    }

    if (message === '/history') {
      this.setState({ inputValue: '', showSlashMenu: false });
      void this.openDrawer();
      return;
    }

    if (message === '/tour') {
      this.setState({ inputValue: '', showSlashMenu: false });
      if (this.props.onTour) {
        void this.props.onTour();
      } else {
        void this.handleSendMessage(undefined, 'Take me on a tour');
      }
      return;
    }

    this.props.bridge?.set({ outcome: 'none' });

    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null, showSlashMenu: false });

    this.lastRequest = message;
    this.setState({ inputValue: '', isLoading: true, error: null });

    // Add user message
    this.addMessage({ role: 'user', content: message });

    // Create assistant placeholder
    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      this.abortController = new AbortController();
      const response = await this.props.onSendMessage(message, this.state.context, {
        onStatus: (status: string) => {
          this.setState({ streamingStatus: status });
        },
        onDelta: (delta: string) => {
          this.setState(prev => ({
            messages: prev.messages.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content + delta, isStreaming: true }
                : m
            ),
          }));
        },
      });
      this.setState({ streamingStatus: null });
      this.applyResponse(assistantMsg.id, response);
    } catch (error) {
      this.setState({ streamingStatus: null });
      const raw = error instanceof Error ? error.message : 'Unknown error';
      const msgContent = raw === 'HTTP 401' ? 'Please sign in to use the assistant.' : `Error: ${raw}`;
      const stateError = raw === 'HTTP 401' ? 'Please sign in to use the assistant.' : raw;
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: msgContent, isStreaming: false }
            : m
        ),
        error: stateError,
      }));
    } finally {
      this.setState({ isLoading: false, streamingStatus: null });
    }
  };

  private handleStop = () => {
    this.isStoppedByUser = true;
    this.props.onStop?.();
  };

  private buildRunCard(actions: Action[]): RunCard | null {
    const run = this.props.bridge?.get().lastRun;
    if (!run || run.results.length === 0) return null;
    const failedIndex = run.results.findIndex(r => !r.ok);
    const steps: RunCardStep[] = actions.map((action, i) => {
      const result = run.results[i];
      const status: RunCardStep['status'] = !result ? 'skipped' : result.ok ? 'done' : i === failedIndex ? 'failed' : 'skipped';
      return {
        label: describeAction(action),
        status,
        targetId: action.target_id,
        error: result && !result.ok ? result.error : undefined,
      };
    });
    return { kind: failedIndex === -1 ? 'receipt' : 'recovery', steps, seconds: Math.round(run.ms / 100) / 10 };
  }

  private attachCard(messageId: string, card: RunCard) {
    this.setState(prev => ({ messages: prev.messages.map(m => (m.id === messageId ? { ...m, card } : m)) }));
  }

  private retryLastRequest = () => {
    if (!this.lastRequest || this.state.isLoading || this.state.isExecutingActions) return;
    void this.handleSendMessage(undefined, this.lastRequest);
  };

  private showMeWhere = (card: RunCard) => {
    const steps = card.steps
      .filter(s => s.status !== 'done' && Boolean(s.targetId))
      .map(s => ({ targetId: s.targetId as string, label: s.label }));
    if (steps.length) this.props.onShowMe?.(steps);
  };

  private executeActions = async (actions: any[], token?: string, stepByStep?: boolean) => {
    this.props.bridge?.set({ lastRun: null });
    this.isStoppedByUser = false;
    this.setState({ isLoading: true, isExecutingActions: true });
    const statusMsg = this.addMessage({ role: 'assistant', content: 'Running the approved steps...', isStreaming: true });
    try {
      const response = await this.props.onActionApproval(actions, token, stepByStep);
      if (this.isStoppedByUser) {
        this.setState(prev => ({
          messages: prev.messages.map(m => m.id === statusMsg.id
            ? { ...m, content: 'Stopped. Steps already done were kept.', isStreaming: false }
            : m),
        }));
      } else if (response) {
        const card = this.buildRunCard(actions);
        this.applyResponse(statusMsg.id, response, card);
      }
    } catch (error) {
      if (this.isStoppedByUser) {
        this.setState(prev => ({
          messages: prev.messages.map(m => m.id === statusMsg.id
            ? { ...m, content: 'Stopped. Steps already done were kept.', isStreaming: false }
            : m),
        }));
      } else {
        const text = error instanceof Error ? error.message : 'Unknown error';
        const displayContent = text.includes('out of date') ? 'This plan is out of date.' : `Error: ${text}`;
        const card = this.buildRunCard(actions);
        this.setState(prev => ({
          messages: prev.messages.map(m => m.id === statusMsg.id
            ? { ...m, content: displayContent, isStreaming: false, ...(card ? { card } : {}) }
            : m),
        }));
      }
    } finally {
      this.isStoppedByUser = false;
      this.setState({ isLoading: false, isExecutingActions: false });
    }
  };

  private handleActionApproval = async (approved: boolean, stepByStep?: boolean) => {
    const token = this.state.approvalToken;
    const actions = this.state.pendingActions;
    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null });

    if (approved && actions.length > 0) {
      await this.executeActions(actions, token ?? undefined, stepByStep);
    } else if (!approved) {
      this.addMessage({ role: 'assistant', content: 'Plan cancelled.' });
      if (this.props.onCancelApproval) {
        try {
          await this.props.onCancelApproval();
        } catch (error) {
          console.error('[GhostCursor] Cancel approval error:', error);
        }
      }
    }
  };

  private handleOptionSelect = async (option: string) => {
    if (!option || this.state.isLoading || this.state.isExecutingActions) return;
    this.props.bridge?.set({ outcome: 'none' });
    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null });

    // Send selected option as user response
    const message = option;
    this.setState({ isLoading: true });
    this.addMessage({ role: 'user', content: message });

    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      const response = await this.props.onSendMessage(message, this.state.context, {
        onStatus: (status: string) => {
          this.setState({ streamingStatus: status });
        },
        onDelta: (delta: string) => {
          this.setState(prev => ({
            messages: prev.messages.map(m =>
              m.id === assistantMsg.id
                ? { ...m, content: m.content + delta, isStreaming: true }
                : m
            ),
          }));
        },
      });
      this.setState({ streamingStatus: null });
      this.applyResponse(assistantMsg.id, response);
    } catch (error) {
      this.setState({ streamingStatus: null });
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`, isStreaming: false }
            : m
        ),
      }));
    } finally {
      this.setState({ isLoading: false, streamingStatus: null });
    }
  };

  private toggleChat = () => {
    this.setState(prev => {
      const nextIsOpen = !prev.isOpen;
      return {
        isOpen: nextIsOpen,
        unreadCount: nextIsOpen ? 0 : prev.unreadCount,
      };
    }, () => {
      if (this.state.isOpen) {
        setTimeout(() => {
          this.inputRef.current?.focus();
        }, 50);
      }
    });
  };

  private handleInputChange = (e: Event) => {
    const target = e.target as HTMLTextAreaElement;
    const val = target.value;
    const showSlashMenu = val.startsWith('/') && !val.includes(' ') && val.length <= 10;
    this.setState({ inputValue: val, showSlashMenu });
  };

  private dockState(): 'home' | 'away' {
    return this.state.ui.cursorAway ? 'away' : 'home';
  }

  private idleState(): 'none' | 'thinking' | 'peeking' {
    if (this.state.isLoading && !this.state.isExecutingActions) return 'thinking';
    if (this.state.showActionApproval) return 'peeking';
    return 'none';
  }

  private statusInfo(): { state: 'online' | 'thinking' | 'working' | 'error'; text: string } {
    const { ui, isExecutingActions, isLoading, streamingStatus } = this.state;
    if (ui.step) return { state: 'working', text: `Step ${ui.step.index}/${ui.step.total}` };
    if (isExecutingActions) return { state: 'working', text: 'Working…' };
    if (streamingStatus) {
      if (streamingStatus === 'thinking') return { state: 'thinking', text: 'Thinking…' };
      if (streamingStatus === 'planning') return { state: 'thinking', text: 'Planning…' };
      if (streamingStatus.startsWith('tool:')) return { state: 'thinking', text: `Tool: ${streamingStatus.slice(5)}` };
      return { state: 'thinking', text: streamingStatus };
    }
    if (isLoading) return { state: 'thinking', text: 'Thinking…' };
    if (ui.outcome === 'error') return { state: 'error', text: 'Needs help' };
    if (ui.outcome === 'success') return { state: 'online', text: 'Done ✓' };
    return { state: 'online', text: 'Online' };
  }

  private renderDock() {
    return (
      <div
        id="gc-dock"
        className="gc-dock"
        data-state={this.dockState()}
        data-idle={this.idleState()}
        data-outcome={this.state.ui.outcome}
      >
        <BrandCursor width={22} accent={this.tokens.accent} className="gc-dock-cursor" />
        <span className="gc-dock-ghost" aria-hidden="true" />
      </div>
    );
  }

  private renderDrawer() {
    const q = this.state.query.trim().toLowerCase();
    const filtered = this.state.sessions.filter(s => {
      if (!q) return true;
      return (s.title && s.title.toLowerCase().includes(q)) || (s.summary && s.summary.toLowerCase().includes(q));
    });

    return (
      <div className="gc-drawer" role="region" aria-label="Chat history">
        <div className="gc-drawer-head">
          <input
            type="text"
            className="gc-input gc-drawer-search"
            placeholder="Search chats..."
            value={this.state.query}
            onInput={(e: any) => this.setState({ query: e.target.value })}
            aria-label="Search chats"
          />
          <button
            type="button"
            className="gc-btn gc-btn--primary gc-drawer-new"
            onClick={this.handleNewChat}
          >
            New chat
          </button>
        </div>
        <div className="gc-drawer-list">
          {filtered.length === 0 ? (
            <div className="gc-drawer-empty">
              {this.state.query ? 'No matching chats' : 'No previous chats'}
            </div>
          ) : (
            filtered.map(s => {
              const summaryLine = s.summary ? s.summary.split('\n')[0] : '';
              const relTime = formatRelativeTime(s.updated_at);
              const isCurrent = this.props.history?.current() === s.session_id;
              return (
                <button
                  key={s.session_id}
                  type="button"
                  className={`gc-drawer-item${isCurrent ? ' gc-drawer-item--active' : ''}`}
                  onClick={() => this.handleSelectSession(s.session_id)}
                >
                  <div className="gc-drawer-item-head">
                    <span className="gc-drawer-item-title">{s.title || 'Untitled chat'}</span>
                    {relTime && <span className="gc-drawer-item-time">{relTime}</span>}
                  </div>
                  {summaryLine && (
                    <div className="gc-drawer-item-summary">{summaryLine}</div>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>
    );
  }

  private renderMissionBar() {
    const { ui, isExecutingActions } = this.state;
    const pct = ui.step ? Math.round((ui.step.index / ui.step.total) * 100) : 0;
    return (
      <div className="ghost-chat-panel gc-panel gc-mission" role="region" aria-label="Ghost Cursor is working">
        <div className="gc-mission-row">
          {this.renderDock()}
          <div className="gc-mission-text">
            <div className="gc-mission-label">{isExecutingActions ? 'WORKING' : 'RETURNING'}</div>
            <div className="gc-mission-status" aria-live="polite">{ui.status || 'Getting ready…'}</div>
            <div className="gc-mission-progress" aria-hidden="true"><span style={{ width: `${pct}%` }} /></div>
          </div>
          {(isExecutingActions || ui.cursorAway) && (
            ui.awaitingNextStep ? (
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button
                  type="button"
                  className="gc-next-step"
                  onClick={() => ui.onNextStep?.()}
                  aria-label="Next step"
                >
                  Next step
                </button>
                <button type="button" className="gc-stop" onClick={this.handleStop} aria-label="Stop">Stop</button>
              </div>
            ) : (
              <button type="button" className="gc-stop" onClick={this.handleStop} aria-label="Stop">■ Stop</button>
            )
          )}
        </div>
      </div>
    );
  }

  render() {
    const { isOpen, messages, inputValue, isLoading, isExecutingActions, unreadCount, showActionApproval, pendingActions, error } = this.state;
    const { theme, requireApprovalForActions } = this.props;

    const positions = {
      'bottom-right': { bottom: '24px', right: '24px' },
      'bottom-left': { bottom: '24px', left: '24px' },
      'top-right': { top: '24px', right: '24px' },
      'top-left': { top: '24px', left: '24px' },
      'center': { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' },
    };

    const flipped = {
      'bottom-right': 'bottom-left',
      'bottom-left': 'bottom-right',
      'top-right': 'top-left',
      'top-left': 'top-right',
      center: 'center',
    } as const;
    const basePosition = theme.position || 'bottom-right';
    const position = this.state.ui.flipSide ? flipped[basePosition] : basePosition;
    const positionStyle = positions[position] || positions['bottom-right'];

    const mission = isOpen && (isExecutingActions || this.state.ui.cursorAway);

    return (
      <div
        id="ghost-cursor-widget"
        className="gc-root"
        style={{
          position: 'fixed',
          ...positionStyle,
          zIndex: 2147483200,
        }}
      >
        <style>{this.css}</style>
        {isOpen ? (
          mission ? (
            this.renderMissionBar()
          ) : (
            <div className="ghost-chat-panel gc-panel">
              {/* Header */}
              <div className="gc-header">
                {this.renderDock()}
                <div className="gc-title">
                  <div className="gc-wordmark">{BRAND.wordmark}</div>
                  <div className="gc-tagline">{BRAND.tagline}</div>
                </div>
                <span className="gc-status" data-state={this.statusInfo().state} data-status={this.state.streamingStatus || undefined}>{this.statusInfo().text}</span>
                {this.props.history && (
                  <button
                    type="button"
                    className="gc-icon-btn"
                    onClick={this.toggleDrawer}
                    aria-label="Chat history"
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                  </button>
                )}
                <button type="button" className="gc-icon-btn" onClick={this.toggleChat} aria-label="Close chat">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </div>

              {/* Drawer if open */}
              {this.state.drawerOpen && this.renderDrawer()}

            {/* Messages */}
            <div
              role="log"
              aria-live="polite"
              className="gc-log"
            >
              {this.state.hasRehydrated && messages.length > 0 && (
                <div className="gc-divider">Earlier in this chat</div>
              )}
              {messages.length === 0 ? (
                <div className="gc-empty">
                  <div className="gc-empty-mark"><BrandCursor width={26} accent={this.tokens.accent} /></div>
                  <div className="gc-empty-title">How can I help?</div>
                  <div>Ask me to find products, add to cart, change settings or show you around.</div>
                </div>
              ) : (
                messages.map(message => (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    theme={theme}
                    onOptionSelect={this.handleOptionSelect}
                    onRetry={this.retryLastRequest}
                    onShowMe={this.showMeWhere}
                  />
                ))
              )}
              <div ref={this.messagesEndRef} />
            </div>

            {/* Action Approval Panel */}
            {showActionApproval && pendingActions.length > 0 && (
              <ActionApprovalPanel
                actions={pendingActions}
                onApprove={this.handleActionApproval}
                theme={theme}
              />
            )}

            {/* Error Display */}
            {error && (
              <div className="gc-error" role="alert">
                {error}
              </div>
            )}

            {/* Input Area */}
            <form onSubmit={this.handleSendMessage} className="gc-composer">
              {this.state.showSlashMenu && (
                <div className="gc-slash-menu" role="menu" aria-label="Slash commands">
                  {[
                    { cmd: '/new', label: '/new', desc: 'Start a new conversation' },
                    { cmd: '/history', label: '/history', desc: 'Open past conversations' },
                    { cmd: '/tour', label: '/tour', desc: 'Start a guided tour' },
                  ]
                    .filter(item => item.cmd.startsWith(inputValue.toLowerCase()))
                    .map(item => (
                      <div
                        key={item.cmd}
                        className="gc-slash-item"
                        role="menuitem"
                        onClick={() => {
                          this.setState({ inputValue: item.cmd, showSlashMenu: false }, () => {
                            void this.handleSendMessage();
                          });
                        }}
                      >
                        <span className="gc-slash-cmd">{item.label}</span>
                        <span className="gc-slash-desc">{item.desc}</span>
                      </div>
                    ))}
                </div>
              )}
              <div className="gc-input-row">
                <textarea
                  ref={this.inputRef}
                  value={inputValue}
                  onInput={this.handleInputChange}
                  onKeyDown={(e: KeyboardEvent) => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.handleSendMessage(e); }
                  }}
                  placeholder="Ask me anything..."
                  disabled={isLoading || isExecutingActions}
                  className="gc-input"
                  aria-label="Message input"
                />
                {isExecutingActions ? (
                  <button
                    type="button"
                    onClick={this.handleStop}
                    className="gc-stop"
                    aria-label="Stop"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="4" y="4" width="16" height="16" rx="2" />
                    </svg>
                    Stop
                  </button>
                ) : (
                  <button
                    type="submit"
                    disabled={!inputValue.trim() || isLoading}
                    className="gc-send"
                    aria-label="Send message"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <line x1="22" y1="2" x2="11" y2="13"></line>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                  </button>
                )}
              </div>
              {requireApprovalForActions && (
                <div className="gc-hint">Actions need your approval before they run</div>
              )}
            </form>
          </div>
        )
      ) : (
          <button
            type="button"
            id="gc-launcher"
            className="gc-launcher"
            data-state={this.dockState()}
            data-outcome={this.state.ui.outcome}
            onClick={this.toggleChat}
            aria-label="Open Ghost Cursor chat"
          >
            <span className="gc-launcher-ring" aria-hidden="true" />
            <BrandCursor width={26} accent={this.tokens.accent} className="gc-launcher-cursor" />
            {unreadCount > 0 && <span className="gc-badge">{unreadCount}</span>}
          </button>
        )}
        {this.state.askBubble && (
          <button
            type="button"
            className="gc-ask-bubble"
            style={{ top: `${this.state.askBubble.top}px`, left: `${this.state.askBubble.left}px` }}
            onMouseDown={(e: MouseEvent) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onClick={this.handleAskBubbleClick}
            aria-label="Ask Ghost"
          >
            <BrandCursor width={14} accent={this.tokens.accent} />
            <span>Ask Ghost</span>
          </button>
        )}
      </div>
    );
  }
}

interface MessageBubbleProps {
  message: Message;
  theme?: ChatWidgetProps['theme'];
  onOptionSelect: (option: string) => void;
  onRetry?: () => void;
  onShowMe?: (card: RunCard) => void;
}

const MessageBubble = ({ message, onOptionSelect, onRetry, onShowMe }: MessageBubbleProps) => {
  const isUser = message.role === 'user';
  const showTyping = !isUser && message.isStreaming && !message.content;
  const card = message.card;
  const failedStepIndex = card ? card.steps.findIndex(s => s.status === 'failed') : -1;
  const hasTargets = card ? card.steps.some(s => s.status !== 'done' && Boolean(s.targetId)) : false;

  return (
    <div className={`gc-msg ${isUser ? 'gc-msg--user' : 'gc-msg--assistant'}`}>
      <div className="gc-bubble">
        {showTyping ? <span className="gc-typing" aria-label="Assistant is typing"><i /><i /><i /></span> : message.content}
        {message.questions && message.questions.length > 0 && (
          <div className="gc-options">
            {message.questions.flatMap(q => q.options.map(opt => (
              <button key={opt} type="button" className="gc-option" onClick={() => onOptionSelect(opt)}>{opt}</button>
            )))}
          </div>
        )}
        {card && (
          <div className={`gc-card ${card.kind === 'receipt' ? 'gc-card--receipt' : 'gc-card--recovery'}`}>
            <div className="gc-card-head">
              <span className="gc-card-title">
                {card.kind === 'receipt' ? 'RECEIPT' : failedStepIndex !== -1 ? `FAILED AT STEP ${failedStepIndex + 1}` : 'FAILED'}
              </span>
              <span className="gc-card-ms">{card.seconds} s</span>
            </div>
            <ul className="gc-card-list gc-card-steps">
              {card.steps.map((step, idx) => (
                <li key={idx} className={`gc-card-step gc-card-step--${step.status}`}>
                  <span className="gc-card-mark" aria-hidden="true">
                    {step.status === 'done' ? '✓' : step.status === 'failed' ? '✕' : '–'}
                  </span>
                  <div className="gc-card-text">
                    <div>{step.label}</div>
                    {step.error && <div className="gc-card-why">{step.error}</div>}
                  </div>
                </li>
              ))}
            </ul>
            {card.kind === 'recovery' && (
              <div className="gc-card-actions">
                <button type="button" className="gc-btn gc-btn--primary" onClick={onRetry}>
                  Try again
                </button>
                {hasTargets && onShowMe && (
                  <button type="button" className="gc-btn gc-btn--ghost" onClick={() => onShowMe(card)}>
                    Show me where
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

interface ActionApprovalPanelProps {
  actions: any[];
  onApprove: (approved: boolean, stepByStep?: boolean) => void;
  theme?: ChatWidgetProps['theme'];
}

interface ActionApprovalPanelState {
  stepByStep: boolean;
}

class ActionApprovalPanel extends Component<ActionApprovalPanelProps, ActionApprovalPanelState> {
  state: ActionApprovalPanelState = {
    stepByStep: false,
  };

  render() {
    const { actions, onApprove } = this.props;
    const { stepByStep } = this.state;
    return (
      <div className="gc-plan" role="group" aria-label="Proposed plan">
        <div className="gc-plan-head">
          <span>PLAN</span>
          <span>{actions.length} {actions.length === 1 ? 'STEP' : 'STEPS'}</span>
        </div>
        <ol className="gc-plan-list">
          {actions.map((action: Action, index: number) => (
            <li key={action.id ?? index} className="gc-plan-step">
              <span className="gc-plan-num">{index + 1}</span>
              <span className="gc-plan-icon" aria-hidden="true">{ACTION_ICONS[action.type] ?? '•'}</span>
              <div>
                <div className="gc-plan-text">{describeAction(action)}</div>
                {action.explanation && <div className="gc-plan-why">{action.explanation}</div>}
              </div>
            </li>
          ))}
        </ol>
        <div className="gc-plan-toggle-row">
          <label className="gc-plan-toggle">
            <input
              type="checkbox"
              className="gc-step-by-step-toggle"
              checked={stepByStep}
              onChange={(e: any) => this.setState({ stepByStep: e.target.checked })}
              aria-label="Step by step"
            />
            <span>Step by step</span>
          </label>
        </div>
        <div className="gc-plan-actions">
          <button type="button" className="gc-btn gc-btn--ghost" onClick={() => onApprove(false, stepByStep)}>Cancel</button>
          <button type="button" className="gc-btn gc-btn--primary" onClick={() => onApprove(true, stepByStep)}>Approve and Run</button>
        </div>
      </div>
    );
  }
}

export { MessageBubble, ActionApprovalPanel };