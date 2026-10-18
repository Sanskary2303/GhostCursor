/**
 * Browser protocol validation for Ghost Cursor Node SDK.
 * Mirrors Python Step 13 / Step 20 strict validation rules.
 */

export class GatewayError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "GatewayError";
    this.status = status;
    this.code = code;
    Object.setPrototypeOf(this, GatewayError.prototype);
  }
}

export interface BrowserContext {
  page?: string;
  values?: Record<string, boolean | number | string>;
  availableTargets?: string[];
}

export interface BrowserStart {
  command: "start";
  protocolVersion: "1" | "1.1";
  requestId: string;
  sessionId?: string;
  message: string;
  context: BrowserContext;
}

export interface BrowserResult {
  id: string;
  ok: boolean;
  output?: any;
  error?: string | null;
}

export interface BrowserContinue {
  command: "continue";
  protocolVersion: "1" | "1.1";
  runId: string;
  eventId: string;
  revision: number;
  kind: "actions" | "answer" | "cancel";
  results?: BrowserResult[];
  answer?: string | null;
  context?: BrowserContext;
}

export type BrowserRequest = BrowserStart | BrowserContinue;

export interface MetricCard {
  type: "metric";
  label: string;
  value: string | number;
  delta?: string | number;
}

export interface BarSeriesItem {
  label: string;
  value: number;
}

export interface BarsCard {
  type: "bars";
  series: BarSeriesItem[];
}

export type InsightCard = MetricCard | BarsCard;

export interface PublicResponse {
  protocolVersion: "1" | "1.1";
  runId: string;
  revision: number;
  status: "awaiting_actions" | "awaiting_answer" | "completed" | "failed" | "cancelled";
  reply: string;
  questions?: Array<Record<string, any>> | null;
  actions?: Array<Record<string, any>> | null;
  cards?: InsightCard[] | null;
}

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isPlainObject(val: unknown): val is Record<string, any> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

function isUuid(val: unknown): val is string {
  return typeof val === "string" && UUID_REGEX.test(val);
}

function assertAllowedKeys(
  obj: Record<string, any>,
  allowed: Set<string>,
  errStatus: number = 400,
  errCode: string = "invalid_request",
): void {
  for (const key of Object.keys(obj)) {
    if (!allowed.has(key)) {
      throw new GatewayError(errStatus, errCode);
    }
  }
}

const CONTEXT_ALLOWED_KEYS = new Set(["page", "values", "availableTargets"]);

export function validateBrowserContext(val: unknown): BrowserContext {
  if (!isPlainObject(val)) {
    throw new GatewayError(400, "invalid_request");
  }
  assertAllowedKeys(val, CONTEXT_ALLOWED_KEYS);

  const res: BrowserContext = {
    page: "unknown",
    values: {},
    availableTargets: [],
  };

  if (val.page !== undefined) {
    if (typeof val.page !== "string" || val.page.length > 200) {
      throw new GatewayError(400, "invalid_request");
    }
    res.page = val.page;
  }

  if (val.values !== undefined) {
    if (!isPlainObject(val.values)) {
      throw new GatewayError(400, "invalid_request");
    }
    const entries = Object.entries(val.values);
    if (entries.length > 100) {
      throw new GatewayError(400, "invalid_request");
    }
    for (const [, v] of entries) {
      const t = typeof v;
      if (t !== "boolean" && t !== "number" && t !== "string") {
        throw new GatewayError(400, "invalid_request");
      }
    }
    res.values = val.values;
  }

  if (val.availableTargets !== undefined) {
    if (!Array.isArray(val.availableTargets) || val.availableTargets.length > 100) {
      throw new GatewayError(400, "invalid_request");
    }
    for (const t of val.availableTargets) {
      if (typeof t !== "string") {
        throw new GatewayError(400, "invalid_request");
      }
    }
    res.availableTargets = val.availableTargets;
  }

  return res;
}

const START_ALLOWED_KEYS = new Set([
  "command",
  "protocolVersion",
  "requestId",
  "sessionId",
  "message",
  "context",
]);

const CONTINUE_ALLOWED_KEYS = new Set([
  "command",
  "protocolVersion",
  "runId",
  "eventId",
  "revision",
  "kind",
  "results",
  "answer",
  "context",
]);

const RESULT_ALLOWED_KEYS = new Set(["id", "ok", "output", "error"]);

export function validateBrowserRequest(rawBody: unknown): BrowserRequest {
  if (!isPlainObject(rawBody)) {
    throw new GatewayError(400, "invalid_request");
  }

  const { command } = rawBody;

  if (command === "start") {
    assertAllowedKeys(rawBody, START_ALLOWED_KEYS);

    if (rawBody.protocolVersion !== undefined && rawBody.protocolVersion !== "1" && rawBody.protocolVersion !== "1.1") {
      throw new GatewayError(400, "invalid_request");
    }

    if (!isUuid(rawBody.requestId)) {
      throw new GatewayError(400, "invalid_request");
    }

    if (rawBody.sessionId !== undefined && !isUuid(rawBody.sessionId)) {
      throw new GatewayError(400, "invalid_request");
    }

    if (
      typeof rawBody.message !== "string" ||
      rawBody.message.length < 1 ||
      rawBody.message.length > 6000
    ) {
      throw new GatewayError(400, "invalid_request");
    }

    let context: BrowserContext = { page: "unknown", values: {}, availableTargets: [] };
    if (rawBody.context !== undefined) {
      context = validateBrowserContext(rawBody.context);
    }

    return {
      command: "start",
      protocolVersion: rawBody.protocolVersion ?? "1.1",
      requestId: rawBody.requestId,
      sessionId: rawBody.sessionId,
      message: rawBody.message,
      context,
    };
  }

  if (command === "continue") {
    assertAllowedKeys(rawBody, CONTINUE_ALLOWED_KEYS);

    if (rawBody.protocolVersion !== undefined && rawBody.protocolVersion !== "1" && rawBody.protocolVersion !== "1.1") {
      throw new GatewayError(400, "invalid_request");
    }

    if (!isUuid(rawBody.runId) || !isUuid(rawBody.eventId)) {
      throw new GatewayError(400, "invalid_request");
    }

    if (
      typeof rawBody.revision !== "number" ||
      !Number.isInteger(rawBody.revision) ||
      rawBody.revision < 0
    ) {
      throw new GatewayError(400, "invalid_request");
    }

    const { kind } = rawBody;
    if (kind !== "actions" && kind !== "answer" && kind !== "cancel") {
      throw new GatewayError(400, "invalid_request");
    }

    let results: BrowserResult[] | undefined;
    if (rawBody.results !== undefined) {
      if (!Array.isArray(rawBody.results) || rawBody.results.length > 12) {
        throw new GatewayError(400, "invalid_request");
      }
      results = [];
      for (const item of rawBody.results) {
        if (!isPlainObject(item)) {
          throw new GatewayError(400, "invalid_request");
        }
        assertAllowedKeys(item, RESULT_ALLOWED_KEYS);

        if (typeof item.id !== "string" || item.id.length < 1 || item.id.length > 120) {
          throw new GatewayError(400, "invalid_request");
        }
        if (typeof item.ok !== "boolean") {
          throw new GatewayError(400, "invalid_request");
        }
        if (item.error !== undefined && item.error !== null) {
          if (typeof item.error !== "string" || item.error.length > 500) {
            throw new GatewayError(400, "invalid_request");
          }
        }
        results.push({
          id: item.id,
          ok: item.ok,
          output: item.output,
          error: item.error,
        });
      }
    }

    if (rawBody.answer !== undefined && rawBody.answer !== null) {
      if (typeof rawBody.answer !== "string" || rawBody.answer.length > 6000) {
        throw new GatewayError(400, "invalid_request");
      }
    }

    let context: BrowserContext | undefined;
    if (rawBody.context !== undefined && rawBody.context !== null) {
      context = validateBrowserContext(rawBody.context);
    }

    return {
      command: "continue",
      protocolVersion: rawBody.protocolVersion ?? "1.1",
      runId: rawBody.runId,
      eventId: rawBody.eventId,
      revision: rawBody.revision,
      kind,
      results,
      answer: rawBody.answer,
      context,
    };
  }

  throw new GatewayError(400, "invalid_request");
}

const PUBLIC_ALLOWED_KEYS = new Set([
  "protocolVersion",
  "runId",
  "revision",
  "status",
  "reply",
  "questions",
  "actions",
  "cards",
]);

const ALLOWED_STATUSES = new Set([
  "awaiting_actions",
  "awaiting_answer",
  "completed",
  "failed",
  "cancelled",
]);

export function validatePublicResponse(resp: unknown): PublicResponse {
  if (!isPlainObject(resp)) {
    throw new GatewayError(502, "bad_public_response");
  }

  assertAllowedKeys(resp, PUBLIC_ALLOWED_KEYS, 502, "bad_public_response");

  if (resp.protocolVersion !== "1" && resp.protocolVersion !== "1.1") {
    throw new GatewayError(502, "bad_public_response");
  }

  if (typeof resp.runId !== "string" || resp.runId.length === 0) {
    throw new GatewayError(502, "bad_public_response");
  }

  if (
    typeof resp.revision !== "number" ||
    !Number.isInteger(resp.revision) ||
    resp.revision < 0
  ) {
    throw new GatewayError(502, "bad_public_response");
  }

  if (!ALLOWED_STATUSES.has(resp.status)) {
    throw new GatewayError(502, "bad_public_response");
  }

  if (typeof resp.reply !== "string") {
    throw new GatewayError(502, "bad_public_response");
  }

  if (resp.questions !== undefined && resp.questions !== null && !Array.isArray(resp.questions)) {
    throw new GatewayError(502, "bad_public_response");
  }

  if (resp.actions !== undefined && resp.actions !== null && !Array.isArray(resp.actions)) {
    throw new GatewayError(502, "bad_public_response");
  }

  let cards: InsightCard[] | undefined = undefined;
  if (resp.cards !== undefined && resp.cards !== null) {
    if (!Array.isArray(resp.cards) || resp.cards.length > 3) {
      throw new GatewayError(502, "bad_public_response");
    }
    cards = [];
    for (const card of resp.cards) {
      if (!isPlainObject(card)) {
        throw new GatewayError(502, "bad_public_response");
      }
      if (card.type === "metric") {
        assertAllowedKeys(card, new Set(["type", "label", "value", "delta"]), 502, "bad_public_response");
        if (typeof card.label !== "string" || (typeof card.value !== "string" && (typeof card.value !== "number" || isNaN(card.value)))) {
          throw new GatewayError(502, "bad_public_response");
        }
        if (card.delta !== undefined && typeof card.delta !== "string" && (typeof card.delta !== "number" || isNaN(card.delta))) {
          throw new GatewayError(502, "bad_public_response");
        }
        cards.push({
          type: "metric",
          label: card.label,
          value: card.value,
          ...(card.delta !== undefined ? { delta: card.delta } : {}),
        });
      } else if (card.type === "bars") {
        assertAllowedKeys(card, new Set(["type", "series"]), 502, "bad_public_response");
        if (!Array.isArray(card.series) || card.series.length > 8) {
          throw new GatewayError(502, "bad_public_response");
        }
        const series: BarSeriesItem[] = [];
        for (const item of card.series) {
          if (!isPlainObject(item)) {
            throw new GatewayError(502, "bad_public_response");
          }
          assertAllowedKeys(item, new Set(["label", "value"]), 502, "bad_public_response");
          if (typeof item.label !== "string" || typeof item.value !== "number" || isNaN(item.value)) {
            throw new GatewayError(502, "bad_public_response");
          }
          series.push({ label: item.label, value: item.value });
        }
        cards.push({ type: "bars", series });
      } else {
        throw new GatewayError(502, "bad_public_response");
      }
    }
  }

  const result: PublicResponse = {
    protocolVersion: resp.protocolVersion === "1" ? "1" : "1.1",
    runId: resp.runId,
    revision: resp.revision,
    status: resp.status,
    reply: resp.reply,
    questions: resp.questions ?? null,
    actions: resp.actions ?? null,
  };
  if (cards !== undefined) {
    result.cards = cards;
  }
  return result;
}

