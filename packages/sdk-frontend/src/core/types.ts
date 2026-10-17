/**
 * Core TypeScript types for Ghost Cursor SDK
 * Matches the canonical protocol v1 specification
 */

// Primitive constraints
export type ProtocolVersion = '1';
/** @pattern ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ */
export type RunId = string;
/** @pattern ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ */
export type RequestId = string;
/** @pattern ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ */
export type EventId = string;
export type SubjectId = string; // 1-120 chars, ^[a-zA-Z0-9_.:@-]+$
export type TenantId = string;

// Scalar limits
export const MAX_SCALAR_LENGTH = 2000;
export const MAX_BRAIN_LENGTH = 32000;
export const MAX_TOOL_OUTPUT_LENGTH = 16000;
export const MAX_REQUEST_BODY = 64 * 1024; // 64 KiB

// Context types
export interface PageContext {
  page: string;
  values: Record<string, string | number | boolean>;
  availableTargets: string[];
}

export interface ContextSnapshot {
  page: string;
  values: Record<string, string | number | boolean>;
  availableTargets: string[];
  timestamp: number;
}

// Target registration
export interface Target {
  page: string | 'global';
  resolve: () => HTMLElement | null;
  operations: TargetOperation[];
  observe?: boolean;
  commit?: 'input' | 'change' | 'blur';
  execute?: (element: HTMLElement, action: Action, signal: AbortSignal) => Promise<void>;
  verify?: (action: Action, signal: AbortSignal) => Promise<boolean>;
  /** Human-readable name shown in plan cards, e.g. "Dark mode switch". */
  label?: string;
}

export type TargetOperation = 'click' | 'fill' | 'select' | 'toggle' | 'navigate' | 'observe';

export type ActionType = 'navigate' | 'click' | 'fill_input' | 'select_option' | 'toggle_switch' | 'guided_tour' | 'ask_clarification';

export interface Action {
  id?: string;
  type: ActionType;
  target_id?: string;
  value?: string | number | boolean;
  target_page?: string;
  explanation?: string;
  state?: boolean;
  steps?: TourStep[];
  question?: string;
  options?: string[];
  option?: string;
}

export interface TourStep {
  target_id: string;
  message: string;
  spotlight?: boolean;
}

// Protocol messages
export interface BrowserStartRequest {
  command: 'start';
  protocolVersion: ProtocolVersion;
  requestId: RequestId;
  sessionId?: RequestId;
  /**
   * @minLength 1
   * @maxLength 6000
   */
  message: string;
  context?: Partial<PageContext>;
}

export interface BrowserContinueRequest {
  command: 'continue';
  protocolVersion: ProtocolVersion;
  runId: RunId;
  eventId: EventId;
  /**
   * @asType integer
   * @minimum 0
   */
  revision: number;
  kind: 'actions' | 'answer' | 'cancel';
  /**
   * @maxItems 12
   */
  results?: ToolResult[];
  /**
   * @minLength 1
   * @maxLength 6000
   */
  answer?: string;
  context?: Partial<PageContext>;
}

export interface BrowserRequest {
  command: 'start' | 'continue';
  protocolVersion: ProtocolVersion;
  requestId?: RequestId;
  sessionId?: RequestId;
  runId?: RunId;
  eventId?: EventId;
  revision?: number;
  message?: string;
  context?: Partial<PageContext>;
  kind?: 'actions' | 'answer' | 'cancel';
  results?: ToolResult[];
  answer?: string;
}

export interface ToolResult {
  id: string;
  ok: boolean;
  output?: unknown;
  error?: string;
}

export interface PublicResponse {
  protocolVersion: ProtocolVersion;
  runId: RunId;
  revision: number;
  status: RunStatus;
  reply: string;
  questions?: ClarifyQuestion[];
  actions?: Action[];
  toolCalls?: never; // Never exposed to browser
}

export type RunStatus = 'awaiting_actions' | 'awaiting_answer' | 'completed' | 'failed' | 'cancelled';

export interface ClarifyQuestion {
  question: string;
  options: string[];
}

// Hosted API types (server-to-server)
export interface HostedCreateRunRequest {
  protocolVersion: ProtocolVersion;
  requestId: RequestId;
  message: string;
  context: PageContext;
  brain: string;
  capabilities: string[];
  tools: ToolDeclaration[];
}

export interface HostedContinueRunRequest {
  protocolVersion: ProtocolVersion;
  eventId: EventId;
  revision: number;
  kind: 'tools' | 'actions' | 'answer' | 'cancel';
  results?: ToolResult[];
  answer?: string;
  context?: Partial<PageContext>;
}

export interface HostedResponse {
  protocolVersion: ProtocolVersion;
  runId: RunId;
  revision: number;
  status: RunStatus;
  reply: string;
  questions?: ClarifyQuestion[];
  actions?: Action[];
  toolCalls?: ToolCall[];
}

export interface ToolCall {
  id: string;
  tool: string;
  parameters: Record<string, unknown>;
}

export interface ToolDeclaration {
  name: string;
  description: string;
  parameters: Record<string, unknown>; // JSON Schema
  read_only: boolean;
}