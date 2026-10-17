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
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
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
              style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}
            >
              {messages.length === 0 ? (
                <div style={{ textAlign: 'center', color: '#6b7280', margin: 'auto 0', padding: '20px' }}>
                  <div style={{ fontSize: '32px', marginBottom: '8px' }}>👻</div>
                  <div style={{ fontWeight: 600, fontSize: '15px', color: '#111827', marginBottom: '4px' }}>Ghost Cursor Assistant</div>
                  <div style={{ fontSize: '13px', lineHeight: 1.4 }}>Ask me to help you navigate, find products, add to cart, or track orders!</div>
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
              <div style={{
                padding: '12px 16px',
                background: '#fef2f2',
                border: '1px solid #fecaca',
                borderRadius: '8px',
                color: '#dc2626',
                fontSize: '13px',
                margin: '0 16px 16px',
              }}>
                {error}
              </div>
            )}

            {/* Input Area */}
            <form onSubmit={this.handleSendMessage} style={{ padding: '16px', borderTop: '1px solid #e5e7eb' }}>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
                <textarea
                  ref={this.inputRef}
                  value={inputValue}
                  onInput={this.handleInputChange}
                  onKeyDown={(e: KeyboardEvent) => {
                    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); this.handleSendMessage(e); }
                  }}
                  placeholder="Ask me anything..."
                  disabled={isLoading || isExecutingActions}
                  style={{
                    flex: 1,
                    minHeight: '44px',
                    maxHeight: '120px',
                    padding: '10px 14px',
                    border: '1px solid #d1d5db',
                    borderRadius: '12px',
                    fontSize: '14px',
                    fontFamily: 'inherit',
                    resize: 'none',
                    outline: 'none',
                    lineHeight: 1.5,
                  }}
                  aria-label="Message input"
                />
                {isExecutingActions ? (
                  <button
                    type="button"
                    onClick={this.handleStop}
                    style={{
                      height: '44px',
                      padding: '0 16px',
                      borderRadius: '12px',
                      background: '#ef4444',
                      border: 'none',
                      color: 'white',
                      fontWeight: 600,
                      fontSize: '13px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                    }}
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
                    style={{
                      width: '44px',
                      height: '44px',
                      borderRadius: '12px',
                      background: inputValue.trim() && !isLoading ? theme.primaryColor : '#d1d5db',
                      border: 'none',
                      color: 'white',
                      cursor: inputValue.trim() && !isLoading ? 'pointer' : 'not-allowed',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      transition: 'background 0.2s',
                    }}
                    aria-label="Send message"
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <line x1="22" y1="2" x2="11" y2="13"></line>
                      <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                  </button>
                )}
              </div>
              {requireApprovalForActions && (
                <div style={{ marginTop: '8px', fontSize: '11px', color: '#6b7280', textAlign: 'center' }}>
                  Actions require your approval before execution
                </div>
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
  theme: ChatWidgetProps['theme'];
  onOptionSelect: (option: string) => void;
}

const MessageBubble = ({ message, theme, onOptionSelect }: MessageBubbleProps) => {
  const isUser = message.role === 'user';

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      animation: 'ghost-fade-in 0.3s ease-out',
    }}>
      <div style={{
        maxWidth: '85%',
        padding: isUser ? '12px 16px' : '12px 16px',
        background: isUser ? theme.primaryColor : '#f3f4f6',
        borderRadius: isUser ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
        color: isUser ? 'white' : '#1a1a2e',
        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
      }}>
        <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.5 }}>
          {message.content}
        </div>

        {message.questions && message.questions.length > 0 && (
          <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {message.questions.flatMap(q => q.options.map(opt => (
              <button
                key={opt}
                onClick={() => onOptionSelect(opt)}
                style={{
                  padding: '10px 14px',
                  background: isUser ? 'rgba(255,255,255,0.2)' : 'white',
                  border: isUser ? '1px solid rgba(255,255,255,0.3)' : '1px solid #d1d5db',
                  borderRadius: '8px',
                  color: isUser ? 'white' : '#1a1a2e',
                  fontSize: '13px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  textAlign: 'left',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.background = isUser ? 'rgba(255,255,255,0.3)' : '#f9fafb';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.background = isUser ? 'rgba(255,255,255,0.2)' : 'white';
                }}
              >
                {opt}
              </button>
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
  theme: ChatWidgetProps['theme'];
}

const ActionApprovalPanel = ({ actions, onApprove, theme }: ActionApprovalPanelProps) => {
  const actionLabels: Record<string, string> = {
    navigate: 'Navigate to',
    click: 'Click',
    fill_input: 'Fill input',
    select_option: 'Select option',
    toggle_switch: 'Toggle',
    guided_tour: 'Start tour',
  };

  return (
    <div style={{
      padding: '16px',
      background: '#fefce8',
      borderTop: '1px solid #fde047',
      borderBottom: '1px solid #fde047',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        marginBottom: '12px',
        fontWeight: 600,
        color: '#854d0e',
      }}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
        </svg>
        Confirm Actions
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {actions.map((action, index) => (
          <div key={index} style={{
            padding: '10px 12px',
            background: 'white',
            border: '1px solid #fde047',
            borderRadius: '8px',
            fontSize: '13px',
            color: '#374151',
          }}>
            <span style={{ fontWeight: 600, color: theme.primaryColor }}>
              {actionLabels[action.type] || action.type}
            </span>
            {' '}
            {action.target_id && `“${action.target_id}”`}
            {action.target_page && ` → ${action.target_page}`}
            {action.value && ` = "${action.value}"`}
            {action.explanation && (
              <span style={{ color: '#6b7280', marginLeft: '8px' }}>— {action.explanation}</span>
            )}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
        <button
          onClick={() => onApprove(false)}
          style={{
            flex: 1,
            padding: '10px 16px',
            background: 'white',
            border: '1px solid #d1d5db',
            borderRadius: '8px',
            color: '#374151',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Cancel
        </button>
        <button
          onClick={() => onApprove(true)}
          style={{
            flex: 1,
            padding: '10px 16px',
            background: theme.primaryColor,
            border: 'none',
            borderRadius: '8px',
            color: 'white',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Approve and Run
        </button>
      </div>
    </div>
  );
};

export { MessageBubble, ActionApprovalPanel };