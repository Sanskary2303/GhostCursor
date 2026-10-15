/**
 * Chat Widget - Preact-based UI component rendered in Shadow DOM
 * Fully style-isolated from host application
 */

import { h, Component, createRef } from 'preact';

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
  };
  requireApprovalForActions: boolean;
  onSendMessage: (message: string, context: any) => Promise<any>;
  onActionApproval: (actions: any[]) => Promise<boolean>;
  initialContext: any;
}

export interface ChatWidgetState {
  isOpen: boolean;
  messages: Message[];
  inputValue: string;
  isLoading: boolean;
  showActionApproval: boolean;
  pendingActions: any[];
  context: any;
  error: string | null;
}

export class ChatWidget extends Component<ChatWidgetProps, ChatWidgetState> {
  state: ChatWidgetState = {
    isOpen: false,
    messages: [] as Message[],
    inputValue: '',
    isLoading: false,
    showActionApproval: false,
    pendingActions: [] as any[],
    context: this.props.initialContext,
    error: null as string | null,
  };

  private messagesEndRef = createRef<HTMLDivElement>();
  private inputRef = createRef<HTMLTextAreaElement>();
  private abortController: AbortController | null = null;

  componentDidMount() {
    this.scrollToBottom();
    this.setupResizeListener();
  }

  componentWillUnmount() {
    this.cleanup();
  }

  private setupResizeListener() {
    window.addEventListener('resize', this.handleResize);
  }

  private handleResize = () => {
    this.forceUpdate();
  };

  private cleanup() {
    window.removeEventListener('resize', this.handleResize);
    if (this.abortController) {
      this.abortController.abort();
    }
  }

  private scrollToBottom = () => {
    setTimeout(() => {
      this.messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 100);
  };

  private addMessage = (message: Omit<Message, 'id' | 'timestamp'>): Message => {
    const newMessage: Message = {
      ...message,
      id: crypto.randomUUID(),
      timestamp: new Date(),
    };
    this.setState(prev => ({
      messages: [...prev.messages, newMessage],
    }), () => this.scrollToBottom());
    return newMessage;
  };

  private handleSendMessage = async (e: Event) => {
    e.preventDefault();
    const { inputValue, isLoading } = this.state;
    if (!inputValue.trim() || isLoading) return;

    const message = inputValue.trim();
    this.setState({ inputValue: '', isLoading: true });

    // Add user message
    this.addMessage({ role: 'user', content: message });

    // Create assistant placeholder
    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      this.abortController = new AbortController();
      const response = await this.props.onSendMessage(message, this.state.context);

      // Update with actual response
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id ? { ...m, content: response.reply, isStreaming: false } : m
        ),
        context: response.context || prev.context,
      }));

      // Handle questions (clarifications)
      if (response.questions && response.questions.length > 0) {
        this.setState(prev => ({
          messages: prev.messages.map(m =>
            m.id === assistantMsg.id
              ? { ...m, questions: response.questions }
              : m
          ),
        }));
      }

      // Handle actions (require approval)
      if (response.actions && response.actions.length > 0) {
        if (this.props.requireApprovalForActions) {
          this.setState({
            showActionApproval: true,
            pendingActions: response.actions,
          });
        } else {
          await this.executeActions(response.actions);
        }
      }
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

  private executeActions = async (actions: any[]) => {
    this.setState({ isLoading: true });
    try {
      const results = [];
      for (const action of actions) {
        // This would delegate to ActionExecutor
        // For now, simulate execution
        await new Promise(resolve => setTimeout(resolve, 500));
        results.push({ id: crypto.randomUUID(), ok: true, output: { executed: action } });
      }

      // Send results back
      await this.props.onSendMessage('__ACTION_RESULTS__', { actionResults: results });
    } catch (error) {
      console.error('[ChatWidget] Action execution failed:', error);
    } finally {
      this.setState({ isLoading: false });
    }
  };

  private handleActionApproval = async (approved: boolean) => {
    this.setState({ showActionApproval: false });
    if (approved && this.state.pendingActions.length > 0) {
      await this.executeActions(this.state.pendingActions);
    }
    this.setState({ pendingActions: [] });
  };

  private handleOptionSelect = async (option: string) => {
    // Send selected option as user response
    const message = option;
    this.setState({ isLoading: true });
    this.addMessage({ role: 'user', content: message });

    const assistantMsg = this.addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      const response = await this.props.onSendMessage(message, this.state.context);
      this.setState(prev => ({
        messages: prev.messages.map(m =>
          m.id === assistantMsg.id ? { ...m, content: response.reply, isStreaming: false } : m
        ),
        context: response.context || prev.context,
      }));
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
    this.setState(prev => ({ isOpen: !prev.isOpen }));
  };

  private handleInputChange = (e: Event) => {
    const target = e.target as HTMLTextAreaElement;
    this.setState({ inputValue: target.value });
  };

  render() {
    const { isOpen, messages, inputValue, isLoading, showActionApproval, pendingActions, error } = this.state;
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
        style={{
          position: 'fixed',
          ...positionStyle,
          zIndex: 99999,
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        }}
      >
        {isOpen ? (
          <div
            className="ghost-chat-panel"
            style={{
              width: '380px',
              maxWidth: 'calc(100vw - 48px)',
              height: '500px',
              maxHeight: 'calc(100vh - 96px)',
              background: 'white',
              borderRadius: '16px',
              boxShadow: '0 20px 60px rgba(0, 0, 0, 0.15)',
              display: 'flex',
              flexDirection: 'column',
              overflow: 'hidden',
              border: '1px solid #e5e7eb',
            }}
          >
            {/* Header */}
            <div style={{
              padding: '16px 20px',
              background: theme.primaryColor,
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{
                  width: '32px', height: '32px',
                  borderRadius: '50%',
                  background: 'rgba(255,255,255,0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2">
                    <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                    <circle cx="9" cy="7" r="4"></circle>
                    <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                    <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                  </svg>
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>Ghost Cursor</div>
                  <div style={{ fontSize: '12px', opacity: 0.8 }}>AI Co-pilot</div>
                </div>
              </div>
              <button
                onClick={this.toggleChat}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: 'white',
                  cursor: 'pointer',
                  padding: '8px',
                  borderRadius: '8px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
                aria-label="Close chat"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>

            {/* Messages */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
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
                  onChange={this.handleInputChange}
                  placeholder="Ask me anything..."
                  disabled={isLoading}
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
            onClick={this.toggleChat}
            style={{
              position: 'relative',
              width: '56px',
              height: '56px',
              borderRadius: '28px',
              background: theme.primaryColor || '#0052FF',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)',
              transition: 'transform 0.2s, box-shadow 0.2s',
            }}
            onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.08)')}
            onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
            aria-label="Open Ghost Cursor chat"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
            </svg>
            {messages.length > 0 && (
              <span
                style={{
                  position: 'absolute',
                  top: '-2px',
                  right: '-2px',
                  background: '#ef4444',
                  color: 'white',
                  borderRadius: '10px',
                  minWidth: '20px',
                  height: '20px',
                  fontSize: '11px',
                  fontWeight: 'bold',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0 4px',
                  border: '2px solid white',
                }}
              >
                {messages.length}
              </span>
            )}
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