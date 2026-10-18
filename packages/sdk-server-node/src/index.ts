/**
 * Ghost Cursor Node Server SDK
 *
 * Dependency-free TypeScript Gateway adapter for integrating Ghost Cursor Cloud
 * with Node.js/Express/Fastify backends.
 */

import crypto, { randomUUID } from "node:crypto";
import {
  BrowserContext,
  BrowserRequest,
  BrowserStart,
  BrowserContinue,
  BrowserResult,
  GatewayError,
  PublicResponse,
  MetricCard,
  BarSeriesItem,
  BarsCard,
  InsightCard,
  validateBrowserRequest,
  validatePublicResponse,
} from "./validate.js";

export {
  BrowserContext,
  BrowserRequest,
  BrowserStart,
  BrowserContinue,
  BrowserResult,
  GatewayError,
  PublicResponse,
  MetricCard,
  BarSeriesItem,
  BarsCard,
  InsightCard,
  validateBrowserRequest,
  validatePublicResponse,
};

export const BRAIN_CANARY = "GHOST_BRAIN_SERVER_ONLY_CANARY_2026";

export interface ToolContext {
  subject: string;
  idempotencyKey: string;
}

export interface Tool {
  description: string;
  inputSchema?: Record<string, any>;
  execute(args: any, context: ToolContext): Promise<any> | any;
}

export interface GatewayOptions {
  serviceUrl: string;
  serviceKey: string;
  tenantId: string;
  loadBrain: ((subject: string, context: BrowserContext) => Promise<string> | string) | string;
  capabilities?: ((subject: string) => Promise<string[]> | string[]) | string[];
  tools?:
    | ((subject: string) => Promise<Record<string, Tool>> | Record<string, Tool>)
    | Record<string, Tool>
    | Tool[];
  filterResponse?: (publicResponse: PublicResponse, subject: string) => Promise<PublicResponse> | PublicResponse;
  fetch?: typeof globalThis.fetch;
  requestTimeoutMs?: number;
  toolTimeoutMs?: number;
  insecureHttpHosts?: string[];
}

interface HostedToolCall {
  id: string;
  tool: string;
  parameters?: any;
}

interface HostedRunResponse {
  protocolVersion: string;
  runId: string;
  revision: number;
  status: string;
  reply: string;
  questions?: Array<Record<string, any>> | null;
  actions?: Array<Record<string, any>> | null;
  toolCalls?: HostedToolCall[];
  loopbackSignature?: { v?: number; ts?: number; sig?: string } | null;
}

export function canonicalJson(val: any): string {
  if (val === null || typeof val !== "object") {
    return JSON.stringify(val);
  }
  if (Array.isArray(val)) {
    return "[" + val.map(canonicalJson).join(",") + "]";
  }
  const keys = Object.keys(val).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(val[k])).join(",") + "}";
}

export function loopbackKey(serviceKey: string): Buffer {
  return Buffer.from(crypto.hkdfSync("sha256", serviceKey, Buffer.alloc(0), "ghost-loopback-v1", 32));
}

export function signToolBatch(
  key: Buffer,
  tenant: string,
  runId: string,
  revision: number,
  toolCalls: any[],
  ts?: number
): { v: number; ts: number; sig: string } {
  const timestamp = ts ?? Math.floor(Date.now() / 1000);
  const canonical = canonicalJson(toolCalls);
  const msg = `${tenant}.${timestamp}.${runId}.${revision}.${canonical}`;
  const sig = crypto.createHmac("sha256", key).update(msg).digest("hex");
  return { v: 1, ts: timestamp, sig };
}

export function verifyToolBatch(
  key: Buffer,
  tenant: string,
  runId: string,
  revision: number,
  toolCalls: any[],
  signaturePayload?: { v?: number; ts?: number; sig?: string } | null,
  now?: number,
  maxAgeSeconds = 300
): boolean {
  if (!signaturePayload || typeof signaturePayload !== "object") return false;
  if (signaturePayload.v !== 1) return false;
  const ts = signaturePayload.ts;
  const sig = signaturePayload.sig;
  if (typeof ts !== "number" || !Number.isInteger(ts) || typeof sig !== "string") return false;
  const currentNow = now ?? Math.floor(Date.now() / 1000);
  if (Math.abs(currentNow - ts) > maxAgeSeconds) return false;

  const canonical = canonicalJson(toolCalls);
  const msg = `${tenant}.${ts}.${runId}.${revision}.${canonical}`;
  const expectedSig = crypto.createHmac("sha256", key).update(msg).digest("hex");

  const expBuf = Buffer.from(expectedSig, "hex");
  const gotBuf = Buffer.from(sig, "hex");
  if (expBuf.length !== gotBuf.length || expBuf.length === 0) return false;
  return crypto.timingSafeEqual(expBuf, gotBuf);
}

export function validateServiceUrl(rawUrl: string, insecureHttpHosts: string[] = []): string {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error(`Invalid serviceUrl: "${rawUrl}" is not a valid URL`);
  }

  const hostname = parsed.hostname.replace(/^\[|\]$/g, "");
  const isLocal =
    hostname === "localhost" ||
    hostname === "127.0.0.1" ||
    hostname === "::1" ||
    insecureHttpHosts.map((h) => h.toLowerCase()).includes(hostname);

  if (parsed.protocol === "http:") {
    if (!isLocal) {
      throw new Error(`Invalid serviceUrl: http is only allowed for localhost or hosts listed in insecureHttpHosts, got "${parsed.hostname}"`);
    }
  } else if (parsed.protocol !== "https:") {
    throw new Error(`Invalid serviceUrl: scheme must be https or http (localhost), got "${parsed.protocol}"`);
  }

  if (parsed.username || parsed.password) {
    throw new Error("Invalid serviceUrl: credentials (username/password) are not allowed");
  }

  if (parsed.search) {
    throw new Error("Invalid serviceUrl: query parameters are not allowed");
  }

  if (parsed.hash) {
    throw new Error("Invalid serviceUrl: fragment identifiers are not allowed");
  }

  return rawUrl.replace(/\/+$/, "");
}

async function readBodyWithCap(res: Response, maxBytes: number): Promise<string> {
  if (res.body && typeof (res.body as any).getReader === "function") {
    const reader = (res.body as any).getReader();
    const chunks: Uint8Array[] = [];
    let totalBytes = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) {
        totalBytes += value.byteLength;
        if (totalBytes > maxBytes) {
          try {
            await reader.cancel();
          } catch {}
          throw new GatewayError(502, "upstream_too_large");
        }
        chunks.push(value);
      }
    }
    const combined = new Uint8Array(totalBytes);
    let offset = 0;
    for (const c of chunks) {
      combined.set(c, offset);
      offset += c.byteLength;
    }
    return new TextDecoder().decode(combined);
  }

  const text = await res.text();
  const byteLength = new TextEncoder().encode(text).byteLength;
  if (byteLength > maxBytes) {
    throw new GatewayError(502, "upstream_too_large");
  }
  return text;
}

function matchesSchema(schema: any, value: any): boolean {
  if (!schema || typeof schema !== 'object') return true;
  const t = schema.type;
  if (t === 'object') {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
    for (const key of schema.required ?? []) if (!(key in value)) return false;
    for (const [key, sub] of Object.entries(schema.properties ?? {})) {
      if (key in value && !matchesSchema(sub, value[key])) return false;
    }
    return true;
  }
  if (t === 'array') return Array.isArray(value) && value.every((v) => matchesSchema(schema.items, v));
  if (t === 'string' && typeof value !== 'string') return false;
  if (t === 'boolean' && typeof value !== 'boolean') return false;
  if (t === 'number' && typeof value !== 'number') return false;
  if (t === 'integer' && !Number.isInteger(value)) return false;
  if (Array.isArray(schema.enum) && !schema.enum.includes(value)) return false;
  return true;
}

export class Gateway {
  private readonly serviceUrl: string;
  private readonly serviceKey: string;
  private readonly tenantId: string;
  private readonly loopbackKey: Buffer;
  private readonly loadBrain: ((subject: string, context: BrowserContext) => Promise<string> | string) | string;
  private readonly capabilities?: ((subject: string) => Promise<string[]> | string[]) | string[];
  private readonly tools?:
    | ((subject: string) => Promise<Record<string, Tool>> | Record<string, Tool>)
    | Record<string, Tool>
    | Tool[];
  private readonly filterResponse?: (publicResponse: PublicResponse, subject: string) => Promise<PublicResponse> | PublicResponse;
  private readonly fetchFn: typeof globalThis.fetch;
  private readonly requestTimeoutMs: number;
  private readonly toolTimeoutMs: number;

  constructor(options: GatewayOptions) {
    if (!options) throw new Error("GatewayOptions are required");
    if (!options.serviceUrl) throw new Error("serviceUrl is required");
    if (!options.serviceKey) throw new Error("serviceKey is required");
    if (!options.tenantId) throw new Error("tenantId is required");

    this.serviceUrl = validateServiceUrl(options.serviceUrl, options.insecureHttpHosts);
    this.serviceKey = options.serviceKey;
    this.tenantId = options.tenantId;
    this.loopbackKey = loopbackKey(this.serviceKey);
    this.loadBrain = options.loadBrain;
    this.capabilities = options.capabilities;
    this.tools = options.tools;
    this.filterResponse = options.filterResponse;
    this.fetchFn = options.fetch || globalThis.fetch;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 210_000;
    this.toolTimeoutMs = options.toolTimeoutMs ?? 10_000;
  }

  private async resolveBrain(subject: string, context: BrowserContext): Promise<string> {
    if (typeof this.loadBrain === "function") {
      return await this.loadBrain(subject, context);
    }
    return this.loadBrain || "";
  }

  private async resolveCapabilities(subject: string): Promise<string[]> {
    if (!this.capabilities) return [];
    if (typeof this.capabilities === "function") {
      return await this.capabilities(subject);
    }
    return this.capabilities;
  }

  private async resolveTools(subject: string): Promise<Map<string, Tool>> {
    const map = new Map<string, Tool>();
    if (!this.tools) return map;

    let raw: Record<string, Tool> | Tool[];
    if (typeof this.tools === "function") {
      raw = await this.tools(subject);
    } else {
      raw = this.tools;
    }

    if (Array.isArray(raw)) {
      for (const t of raw) {
        const name = (t as any).name;
        if (name) map.set(name, t);
      }
    } else if (raw && typeof raw === "object") {
      for (const [name, t] of Object.entries(raw)) {
        map.set(name, t);
      }
    }
    return map;
  }

  private getToolDeclarations(toolsMap: Map<string, Tool>): Array<{ name: string; description: string; parameters: any }> {
    const declarations: Array<{ name: string; description: string; parameters: any }> = [];
    for (const [name, tool] of toolsMap.entries()) {
      declarations.push({
        name,
        description: tool.description || "",
        parameters: tool.inputSchema || (tool as any).parameters || { type: "object", properties: {} },
      });
    }
    return declarations;
  }

  private async callHostedApi(path: string, body: any, subject: string): Promise<HostedRunResponse> {
    const url = `${this.serviceUrl}${path}`;
    let res: Response;
    try {
      res = await this.fetchFn(url, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${this.serviceKey}`,
          "X-Ghost-Subject": subject,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        redirect: "manual",
        signal: AbortSignal.timeout(this.requestTimeoutMs),
      });
    } catch {
      throw new GatewayError(502, "upstream_unavailable");
    }

    if (res.status >= 400) {
      const errorMap: Record<number, string> = {
        404: "run_not_found",
        409: "conflict",
        410: "run_expired",
      };
      const code = errorMap[res.status] || "upstream_error";
      const status = res.status in errorMap ? res.status : 502;
      throw new GatewayError(status, code);
    }

    if (res.status < 200 || res.status >= 300) {
      throw new GatewayError(502, "upstream_error");
    }

    const text = await readBodyWithCap(res, 256 * 1024);
    let data: any;
    try {
      data = JSON.parse(text);
    } catch {
      throw new GatewayError(502, "upstream_error");
    }

    if (!data || typeof data !== "object") {
      throw new GatewayError(502, "upstream_error");
    }

    return data as HostedRunResponse;
  }

  async handle(subject: string, rawBody: unknown): Promise<PublicResponse> {
    if (typeof subject !== "string" || subject.length === 0) {
      throw new GatewayError(400, "invalid_request");
    }

    const req = validateBrowserRequest(rawBody);
    const toolsMap = await this.resolveTools(subject);
    const toolDeclarations = this.getToolDeclarations(toolsMap);

    let hostedResponse: HostedRunResponse;

    if (req.command === "start") {
      const brainContent = await this.resolveBrain(subject, req.context);
      const capabilitiesList = await this.resolveCapabilities(subject);

      const payload = {
        protocolVersion: req.protocolVersion,
        requestId: req.requestId,
        message: req.message,
        context: req.context,
        brain: brainContent,
        capabilities: capabilitiesList,
        tools: toolDeclarations,
      };

      hostedResponse = await this.callHostedApi("/v1/runs", payload, subject);
    } else {
      const payload: Record<string, any> = {
        protocolVersion: req.protocolVersion,
        eventId: req.eventId,
        revision: req.revision,
        kind: req.kind,
        results: req.results,
      };
      if (req.answer !== undefined) payload.answer = req.answer;
      if (req.context !== undefined) payload.context = req.context;

      hostedResponse = await this.callHostedApi(`/v1/runs/${req.runId}/continue`, payload, subject);
    }

    // Handle tool calls (Gateway Loopback) - max 4 rounds
    const MAX_TOOL_ROUNDS = 4;
    const MAX_TOOL_CALLS_PER_ROUND = 4;
    const MAX_TOOL_OUTPUT_LENGTH = 16000;

    let rounds = 0;
    const collectedCards: InsightCard[] = [];
    while (hostedResponse.toolCalls && hostedResponse.toolCalls.length > 0 && rounds < MAX_TOOL_ROUNDS) {
      rounds++;
      const toolCalls = hostedResponse.toolCalls;

      // Verify HMAC loopback signature before executing local tools
      const valid = verifyToolBatch(
        this.loopbackKey,
        this.tenantId,
        hostedResponse.runId,
        hostedResponse.revision,
        toolCalls,
        hostedResponse.loopbackSignature
      );
      if (!valid) {
        throw new GatewayError(502, "bad_tool_signature");
      }

      const toolResults: Array<{ id: string; ok: boolean; output?: any; error?: string }> = [];

      if (toolCalls.length > MAX_TOOL_CALLS_PER_ROUND) {
        for (const tc of toolCalls) {
          toolResults.push({
            id: tc.id,
            ok: false,
            error: "too many tool calls in one plan",
          });
        }
      } else {
        for (const tc of toolCalls) {
          const tool = toolsMap.get(tc.tool);
          if (!tool) {
            toolResults.push({
              id: tc.id,
              ok: false,
              error: `Tool not found: ${tc.tool}`,
            });
            continue;
          }

          const args = tc.parameters ?? {};
          if (!matchesSchema(tool.inputSchema, args)) {
            toolResults.push({ id: tc.id, ok: false, error: "invalid arguments" });
            continue;
          }

          const ctx: ToolContext = {
            subject,
            idempotencyKey: `${hostedResponse.runId}:${hostedResponse.revision}:${tc.id}`,
          };

          let timer: ReturnType<typeof setTimeout> | undefined;
          const timeout = new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error("tool timed out")), this.toolTimeoutMs);
          });
          try {
            const output = await Promise.race([Promise.resolve(tool.execute(args, ctx)), timeout]);

            let outVal = output;
            if (outVal && typeof outVal === "object" && Array.isArray((outVal as any).cards)) {
              for (const c of (outVal as any).cards) {
                if (collectedCards.length < 3) {
                  collectedCards.push(c);
                }
              }
            }
            const serialized = JSON.stringify(output);
            if (serialized && serialized.length > MAX_TOOL_OUTPUT_LENGTH) {
              outVal = { truncated: true, message: "Output exceeded 16KB limit" };
            }
            toolResults.push({
              id: tc.id,
              ok: true,
              output: outVal,
            });
          } catch (err: any) {
            toolResults.push({
              id: tc.id,
              ok: false,
              error: String(err?.message || err).slice(0, 500),
            });
          } finally {
            clearTimeout(timer);
          }
        }
      }

      const continuePayload = {
        protocolVersion: req.protocolVersion,
        eventId: randomUUID(),
        revision: hostedResponse.revision,
        kind: "tools",
        results: toolResults,
      };

      hostedResponse = await this.callHostedApi(`/v1/runs/${hostedResponse.runId}/continue`, continuePayload, subject);
    }

    if (
      (hostedResponse.toolCalls && hostedResponse.toolCalls.length > 0) ||
      (hostedResponse as any).status === "awaiting_tools"
    ) {
      throw new GatewayError(502, "tool_round_limit");
    }

    const allowedStatuses = new Set(["awaiting_actions", "awaiting_answer", "completed", "failed", "cancelled"]);
    if (!allowedStatuses.has(hostedResponse.status)) {
      throw new GatewayError(502, "bad_upstream_status");
    }

    let publicResp: PublicResponse = {
      protocolVersion: (hostedResponse.protocolVersion === "1.1" || req.protocolVersion === "1.1") ? "1.1" : (hostedResponse.protocolVersion as any || "1.1"),
      runId: hostedResponse.runId,
      revision: hostedResponse.revision,
      status: hostedResponse.status as any,
      reply: hostedResponse.reply,
      questions: hostedResponse.questions ?? null,
      actions: hostedResponse.actions ?? null,
    };
    if (collectedCards.length > 0) {
      publicResp.cards = collectedCards;
    } else if ((hostedResponse as any).cards && Array.isArray((hostedResponse as any).cards)) {
      publicResp.cards = (hostedResponse as any).cards.slice(0, 3);
    }

    if (this.filterResponse) {
      try {
        publicResp = await this.filterResponse(publicResp, subject);
      } catch (err) {
        if (err instanceof GatewayError) throw err;
        throw new GatewayError(502, "bad_public_response");
      }
    }

    publicResp = validatePublicResponse(publicResp);

    if (JSON.stringify(publicResp).includes(BRAIN_CANARY)) {
      throw new GatewayError(502, "disclosure_blocked");
    }

    return publicResp;
  }

  async *streamTurn(rawRequest: any, subject: string): AsyncGenerator<string, void, unknown> {
    const req = validateBrowserRequest(rawRequest);
    const toolsMap = await this.resolveTools(subject);
    const toolDeclarations = this.getToolDeclarations(toolsMap);

    yield `event: status\ndata: ${JSON.stringify({ status: "thinking" })}\n\n`;

    let hostedResponse: HostedRunResponse;

    if (req.command === "start") {
      const brain = await this.resolveBrain(subject, req.context);
      const capabilities = await this.resolveCapabilities(subject);

      const payload = {
        protocolVersion: req.protocolVersion,
        requestId: req.requestId,
        message: req.message,
        context: req.context,
        brain,
        capabilities,
        tools: toolDeclarations,
      };

      hostedResponse = await this.callHostedApi("/v1/runs", payload, subject);
    } else {
      const payload: Record<string, any> = {
        protocolVersion: req.protocolVersion,
        eventId: req.eventId,
        revision: req.revision,
        kind: req.kind,
        results: req.results,
      };
      if (req.answer !== undefined) payload.answer = req.answer;
      if (req.context !== undefined) payload.context = req.context;

      hostedResponse = await this.callHostedApi(`/v1/runs/${req.runId}/continue`, payload, subject);
    }

    const MAX_TOOL_ROUNDS = 4;
    const MAX_TOOL_CALLS_PER_ROUND = 4;
    const MAX_TOOL_OUTPUT_LENGTH = 16000;

    let rounds = 0;
    const collectedCards: InsightCard[] = [];
    while (hostedResponse.toolCalls && hostedResponse.toolCalls.length > 0 && rounds < MAX_TOOL_ROUNDS) {
      rounds++;
      const toolCalls = hostedResponse.toolCalls;

      for (const tc of toolCalls) {
        yield `event: status\ndata: ${JSON.stringify({ status: `tool:${tc.tool}` })}\n\n`;
      }

      const valid = verifyToolBatch(
        this.loopbackKey,
        this.tenantId,
        hostedResponse.runId,
        hostedResponse.revision,
        toolCalls,
        hostedResponse.loopbackSignature
      );
      if (!valid) {
        throw new GatewayError(502, "bad_tool_signature");
      }

      const toolResults: Array<{ id: string; ok: boolean; output?: any; error?: string }> = [];

      if (toolCalls.length > MAX_TOOL_CALLS_PER_ROUND) {
        for (const tc of toolCalls) {
          toolResults.push({ id: tc.id, ok: false, error: "too many tool calls in one plan" });
        }
      } else {
        for (const tc of toolCalls) {
          const tool = toolsMap.get(tc.tool);
          if (!tool) {
            toolResults.push({ id: tc.id, ok: false, error: `Tool not found: ${tc.tool}` });
            continue;
          }

          const args = tc.parameters ?? {};
          if (!matchesSchema(tool.inputSchema, args)) {
            toolResults.push({ id: tc.id, ok: false, error: "invalid arguments" });
            continue;
          }

          const ctx: ToolContext = {
            subject,
            idempotencyKey: `${hostedResponse.runId}:${hostedResponse.revision}:${tc.id}`,
          };

          let timer: ReturnType<typeof setTimeout> | undefined;
          const timeout = new Promise((_, reject) => {
            timer = setTimeout(() => reject(new Error("tool timed out")), this.toolTimeoutMs);
          });
          try {
            const output = await Promise.race([Promise.resolve(tool.execute(args, ctx)), timeout]);
            let outVal = output;
            if (outVal && typeof outVal === "object" && Array.isArray((outVal as any).cards)) {
              for (const c of (outVal as any).cards) {
                if (collectedCards.length < 3) {
                  collectedCards.push(c);
                }
              }
            }
            const serialized = JSON.stringify(output);
            if (serialized && serialized.length > MAX_TOOL_OUTPUT_LENGTH) {
              outVal = { truncated: true, message: "Output exceeded 16KB limit" };
            }
            toolResults.push({ id: tc.id, ok: true, output: outVal });
          } catch (err: any) {
            toolResults.push({ id: tc.id, ok: false, error: err?.message || "tool error" });
          } finally {
            if (timer) clearTimeout(timer);
          }
        }
      }

      const continuePayload = {
        protocolVersion: req.protocolVersion,
        eventId: randomUUID(),
        revision: hostedResponse.revision,
        kind: "tools",
        results: toolResults,
      };

      yield `event: status\ndata: ${JSON.stringify({ status: "planning" })}\n\n`;
      hostedResponse = await this.callHostedApi(
        `/v1/runs/${hostedResponse.runId}/continue`,
        continuePayload,
        subject
      );
    }

    if (hostedResponse.toolCalls && hostedResponse.toolCalls.length > 0) {
      throw new GatewayError(502, "tool_round_limit");
    }

    if (hostedResponse.actions && hostedResponse.actions.length > 0) {
      yield `event: status\ndata: ${JSON.stringify({ status: "planning" })}\n\n`;
    }

    let publicResp: PublicResponse = {
      protocolVersion: (hostedResponse.protocolVersion === "1.1" || req.protocolVersion === "1.1") ? "1.1" : (hostedResponse.protocolVersion as any || "1.1"),
      runId: hostedResponse.runId,
      revision: hostedResponse.revision,
      status: hostedResponse.status as any,
      reply: hostedResponse.reply,
      questions: hostedResponse.questions ?? null,
      actions: hostedResponse.actions ?? null,
    };
    if (collectedCards.length > 0) {
      publicResp.cards = collectedCards;
    } else if ((hostedResponse as any).cards && Array.isArray((hostedResponse as any).cards)) {
      publicResp.cards = (hostedResponse as any).cards.slice(0, 3);
    }

    if (this.filterResponse) {
      try {
        publicResp = await this.filterResponse(publicResp, subject);
      } catch (err) {
        if (err instanceof GatewayError) throw err;
        throw new GatewayError(502, "bad_public_response");
      }
    }

    publicResp = validatePublicResponse(publicResp);

    if (JSON.stringify(publicResp).includes(BRAIN_CANARY)) {
      throw new GatewayError(502, "disclosure_blocked");
    }

    const reply = publicResp.reply || "";
    if (reply) {
      const words = reply.match(/\S+\s*/g) || [reply];
      let accumulated = "";
      for (const word of words) {
        if (word.includes(BRAIN_CANARY) || (accumulated + word).includes(BRAIN_CANARY)) {
          throw new GatewayError(502, "disclosure_blocked");
        }
        accumulated += word;
        yield `event: delta\ndata: ${JSON.stringify({ delta: word })}\n\n`;
      }
    }

    yield `event: envelope\ndata: ${JSON.stringify(publicResp)}\n\n`;
  }
}

