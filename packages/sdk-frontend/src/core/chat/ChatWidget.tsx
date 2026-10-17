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

export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  actions?: any[];
  questions?: { question: string; options: string[] }[];
  isStreaming?: boolean;
}

export interface ChatWidgetProps {
  apiEndpoint: string;
  theme: {
    primaryColor: string;
    cursorColor: string;
    position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'center';
    mode?: ThemeMode;
  };
  requireApprovalForActions: boolean;
  onSendMessage: (message: string, context: any) => Promise<any>;
  onActionApproval: (actions: any[], token?: string) => Promise<any>;
  onCancelApproval?: () => Promise<any>;
  onStop?: () => void;
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
  };

  private messagesEndRef = createRef<HTMLDivElement>();
  private inputRef = createRef<HTMLTextAreaElement>();
  private abortController: AbortController | null = null;
  private isStoppedByUser = false;
  private tokens: ThemeTokens = tokensFor(
    resolveMode(this.props.theme.mode, prefersDarkScheme()),
    this.props.theme.primaryColor,
  );
  private css = tokensToCss(this.tokens) + WIDGET_CSS;

  componentDidMount() {
    this.scrollToBottom();
    this.setupResizeListener();
    window.addEventListener('keydown', this.handleKeyDown);
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
    if (e.key === 'Escape' && this.state.isOpen) {
      this.setState({ isOpen: false });
    }
  };

  private cleanup() {
    window.removeEventListener('resize', this.handleResize);
    window.removeEventListener('keydown', this.handleKeyDown);
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

  private applyResponse = (messageId: string, response: any) => {
    this.setState(prev => ({
      messages: prev.messages.map(m => m.id === messageId
        ? { ...m, content: response.reply, isStreaming: false, questions: response.questions?.length ? response.questions : undefined }
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

  private handleSendMessage = async (e: Event) => {
    e.preventDefault();
    const { inputValue, isLoading, isExecutingActions } = this.state;
    if (!inputValue.trim() || isLoading || isExecutingActions) return;

    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null });

    const message = inputValue.trim();
    this.setState({ inputValue: '', isLoading: true });

    // Add user message
    this.addMessage({ role: 'user', content: message });

    // Create assistant placeholder
    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      this.abortController = new AbortController();
      const response = await this.props.onSendMessage(message, this.state.context);
      this.applyResponse(assistantMsg.id, response);
    } catch (error) {
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`, isStreaming: false }
            : m
        ),
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    } finally {
      this.setState({ isLoading: false });
    }
  };

  private handleStop = () => {
    this.isStoppedByUser = true;
    this.props.onStop?.();
  };

  private executeActions = async (actions: any[], token?: string) => {
    this.isStoppedByUser = false;
    this.setState({ isLoading: true, isExecutingActions: true });
    const statusMsg = this.addMessage({ role: 'assistant', content: 'Running the approved steps...', isStreaming: true });
    try {
      const response = await this.props.onActionApproval(actions, token);
      if (this.isStoppedByUser) {
        this.setState(prev => ({
          messages: prev.messages.map(m => m.id === statusMsg.id
            ? { ...m, content: 'Stopped. Steps already done were kept.', isStreaming: false }
            : m),
        }));
      } else if (response) {
        this.applyResponse(statusMsg.id, response);
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
        this.setState(prev => ({
          messages: prev.messages.map(m => m.id === statusMsg.id
            ? { ...m, content: displayContent, isStreaming: false }
            : m),
        }));
      }
    } finally {
      this.isStoppedByUser = false;
      this.setState({ isLoading: false, isExecutingActions: false });
    }
  };

  private handleActionApproval = async (approved: boolean) => {
    const token = this.state.approvalToken;
    const actions = this.state.pendingActions;
    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null });

    if (approved && actions.length > 0) {
      await this.executeActions(actions, token ?? undefined);
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
    this.setState({ showActionApproval: false, pendingActions: [], approvalToken: null });

    // Send selected option as user response
    const message = option;
    this.setState({ isLoading: true });
    this.addMessage({ role: 'user', content: message });

    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      const response = await this.props.onSendMessage(message, this.state.context);
      this.applyResponse(assistantMsg.id, response);
    } catch (error) {
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id
            ? { ...m, content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`, isStreaming: false }
            : m
        ),
      }));
    } finally {
      this.setState({ isLoading: false });
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
    this.setState({ inputValue: target.value });
  };

  private dockState(): 'home' | 'away' {
    return this.state.isExecutingActions ? 'away' : 'home';
  }

  private idleState(): 'none' | 'thinking' | 'peeking' {
    if (this.state.isLoading && !this.state.isExecutingActions) return 'thinking';
    if (this.state.showActionApproval) return 'peeking';
    return 'none';
  }

  private statusInfo(): { state: 'online' | 'thinking' | 'working'; text: string } {
    if (this.state.isExecutingActions) return { state: 'working', text: 'Working…' };
    if (this.state.isLoading) return { state: 'thinking', text: 'Thinking…' };
    return { state: 'online', text: 'Online' };
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

    const positionStyle = positions[theme.position] || positions['bottom-right'];

    return (
      <div
        id="ghost-cursor-widget"
        className="gc-root"
        style={{
          position: 'fixed',
          ...positionStyle,
          zIndex: 99999,
        }}
      >
        <style>{this.css}</style>
        {isOpen ? (
          <div className="ghost-chat-panel gc-panel">
            {/* Header */}
            <div className="gc-header">
              <div
                id="gc-dock"
                className="gc-dock"
                data-state={this.dockState()}
                data-idle={this.idleState()}
              >
                <BrandCursor width={22} accent={this.tokens.accent} className="gc-dock-cursor" />
                <span className="gc-dock-ghost" aria-hidden="true" />
              </div>
              <div className="gc-title">
                <div className="gc-wordmark">{BRAND.wordmark}</div>
                <div className="gc-tagline">{BRAND.tagline}</div>
              </div>
              <span className="gc-status" data-state={this.statusInfo().state}>{this.statusInfo().text}</span>
              <button type="button" className="gc-icon-btn" onClick={this.toggleChat} aria-label="Close chat">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* Messages */}
            <div
              role="log"
              aria-live="polite"
              className="gc-log"
            >
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
        ) : (
          <button
            type="button"
            id="gc-launcher"
            className="gc-launcher"
            data-state={this.dockState()}
            onClick={this.toggleChat}
            aria-label="Open Ghost Cursor chat"
          >
            <span className="gc-launcher-ring" aria-hidden="true" />
            <BrandCursor width={26} accent={this.tokens.accent} className="gc-launcher-cursor" />
            {unreadCount > 0 && <span className="gc-badge">{unreadCount}</span>}
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
}

const MessageBubble = ({ message, onOptionSelect }: MessageBubbleProps) => {
  const isUser = message.role === 'user';
  const showTyping = !isUser && message.isStreaming && !message.content;
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
      </div>
    </div>
  );
};

interface ActionApprovalPanelProps {
  actions: any[];
  onApprove: (approved: boolean) => void;
  theme?: ChatWidgetProps['theme'];
}

const ActionApprovalPanel = ({ actions, onApprove }: ActionApprovalPanelProps) => (
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
    <div className="gc-plan-actions">
      <button type="button" className="gc-btn gc-btn--ghost" onClick={() => onApprove(false)}>Cancel</button>
      <button type="button" className="gc-btn gc-btn--primary" onClick={() => onApprove(true)}>Approve and Run</button>
    </div>
  </div>
);

export { MessageBubble, ActionApprovalPanel };