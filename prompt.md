# Standalone implementation prompt - Ghost Cursor
---

## 1. Your assignment
💡
You are a senior full-stack, SDK, security, and cloud engineer. Implement **Ghost Cursor**, an application-aware AI assistant offered as a service to other web platforms. Create the maintained frontend package, hosted backend, customer-backend adapters, independent demonstration website, tests, and extensive documentation.

The assistant must understand the current screen, reason about other pages and business context, ask clarifying questions, propose grounded actions, obtain user approval, and animate a cursor while a deterministic SDK performs those actions. It must do more than answer questions: help users complete approved workflows.

Use the supplied target workspace. If a path is needed and none was supplied, use `C:\Projects\ghost-cursor` on Windows or ask for the target workspace once. Inspect existing files first, preserve unrelated work, and never overwrite credentials or an existing project blindly. Do not modify a neighboring application repository.

Begin by creating/updating `MEMORY.md` with the implementation plan and decisions. Then implement and verify the runnable baseline. Keep `MEMORY.md` and `README.md` accurate as work proceeds. Do not stop at a conceptual architecture or empty scaffold. Do not describe unimplemented features as completed.

This prompt defines:

1. **Mandatory architectural decisions** that must not be changed silently.
2. **A concrete runnable baseline** to recreate.
3. **Production gates and extensions** that must be tracked honestly rather than presented as already implemented or verified.

No model API key or GCP credential is assumed available. Make the baseline fully demonstrable with a clearly identified mock provider. Do not silently fall back to mocks when real providers fail.

## 2. Product rationale and non-negotiable decisions

### 2.1 Only one communication topology

The ONLY supported integration is:

```text
User's browser
  Customer application + Ghost Cursor SDK
        |
        | Same-origin request, existing customer authentication
        v
Customer backend gateway
  Authenticate user / authorize data / load private Brain / run local tools
        |
        | Server-to-server tenant credential and authenticated subject
        v
Ghost Cursor hosted backend
  Validate / orchestrate / persist run / call provider
        |
        v
Selected model provider

Responses return through the same chain.
```

Do NOT implement a browser-to-Ghost direct mode, browser-to-model mode, or public Brain fetcher. This is a deliberate decision, not an optional enterprise add-on: customers will always have private business knowledge that must not be shipped as browser-side data.

The browser must never receive provider keys, customer-to-Ghost service keys, complete prompts, private Brain documents, internal tool requests/results, or the hosted run's internal history. It receives only approved user-facing text, questions, actions, run identity/revision, and status.

Important qualification: generated replies can disclose information included in a prompt. Server-side storage and response projection do not mathematically guarantee secrecy. Minimize supplied knowledge, support customer disclosure filters, and keep undisclosable secrets behind tools that return approved results. Explicitly disclose that selected excerpts reach Ghost and the chosen model.

### 2.2 AI chooses intent; deterministic code controls execution

The model never directly accesses the DOM or executes code. It emits structured, validated actions using logical registered target IDs. The SDK resolves targets using customer-authored code and performs approved operations.

Prohibit model-generated JavaScript, eval, selectors, arbitrary URLs, arbitrary HTTP requests, shell commands, and unrestricted page-wide clicking.

Cursor animation is presentation. Arrival at an element or successful dispatch of a click is not evidence that a business transaction succeeded.

### 2.3 Minimal customer changes, not a false zero-code promise

Customers should integrate through a small frontend registration module and a backend gateway/configuration module, not rewrite their router, state management, components, business logic, database, or authentication.

Ordinary buttons can be clicked programmatically and invoke existing handlers. For example, a click can invoke React onClick, change state, rerender, and run relevant effects. Do not claim JavaScript clicks cannot update application state.

However, assigning an input's DOM value alone does not reliably notify controlled framework state. Provide built-in native setters and appropriate events for standard controls. Use custom adapters only where the widget/application requires them. Do not demand a Redux dispatch or React setter callback for every field.

Programmatic events remain untrusted (`isTrusted=false`). They do not create genuine user activation, reproduce every gesture, or bypass browser permissions. Some widgets need explicit adapters. State this clearly in documentation.

### 2.4 Framework-neutral frontend; universal backend protocol

- The SDK is TypeScript/JavaScript with no React/Next/Redux runtime dependency.
- It can be used by React, Next.js, Vue, Angular, or plain JavaScript applications.
- Importing it during SSR must not access window/document immediately.
- The hosted service is Python 3.12 (FastAPI + Google Agent Development Kit Engine).
- Provide Python (FastAPI/Flask/Django) and Node.js customer backend SDK adapters.
- Other customer backends can implement the documented HTTP/JSON protocol directly. Dedicated adapters for Java, .NET, Go, etc. are conveniences, not mandatory for interoperability.

### 2.5 Client-owned Brain is a core differentiator

Cross-page and business awareness is central to the product, not optional chat decoration. Separate three sources of knowledge:

1. **Application map/capabilities:** pages, logical targets, actions, dependencies, readiness requirements, and multi-page workflows.
2. **Private Brain:** Markdown business explanations, domain constraints, approved mappings, workflow guidance, and clarification rules maintained by the client (strictly zero HTML tags or DOM selectors; dynamic route resolution via `platform.md` + `pages/{page}.md`).
3. **Live context:** current page and opted-in control values/availability supplied by the frontend integration.

Neither DOM scanning nor data attributes alone provides business understanding or knowledge of unmounted pages.

### 2.6 Security and honest production claims

Default to explicit registration and approval. Business APIs still enforce normal customer authorization. Brain prose, model output, and approval UI are not an authorization mechanism against a malicious user/browser.

Build production-oriented boundaries but do not equate a working demo with a production-certified service. Track concrete missing work, unavailable validation, and external prerequisites. Never fabricate test results or deployment success.

### 2.7 Customer Data Sovereignty (Stateless Cloud Engine)

Ghost Cursor Cloud is a stateless reasoning engine and does not persist conversational chats or personal customer records. Chat session records, message histories, and execution audits are persisted exclusively in the customer's own database using SDK-provided schemas (`ghost_chat_sessions`, `ghost_chat_messages`) and the `SQLAlchemyChatStore` abstraction. Ephemeral multi-turn run state (TTL: 30 minutes) on Cloud Run / Cloud SQL (PostgreSQL 17) or Firestore handles event deduplication, optimistic concurrency, and revision locking.

### 2.8 Customer Backend Read-Only Tools via Gateway Loopback

Domain-specific backend knowledge tools (e.g., `lookup_order`, `check_warehouse_stock`, `simulate_discount_roi`) are registered directly in the customer's backend gateway via the Backend SDK and executed locally via the Gateway Loopback (Reverse-Dispatch) protocol. When the Google ADK Agent emits a tool call, the orchestrator requests local execution from the customer gateway signed with HMAC-SHA256 (`X-Ghost-Signature`) and authorized with the user's authentic session (`X-Ghost-Subject`). Tools are strictly read-only and bounded to 16,000 characters.

## 3. Technology and repository layout

Use an npm-workspaces TypeScript monorepo for client packages and a Python distribution for backend services. Deploy the orchestrator as a single Cloud Run container (Modular Monolith) rather than Kubernetes or microservices.

Baseline technology choices:

- Python 3.12 with FastAPI for the hosted orchestrator (`services/orchestrator`).
- Google Agent Development Kit (ADK) with Gemini 2.0 Flash / Pro via Vertex AI.
- TypeScript strict mode, ESM, Vite + Rollup for Frontend SDK (`packages/sdk-frontend`).
- Shadow DOM sandboxing for Chat Widget & Tour Overlay; Cursor Canvas directly on Host DOM.
- Element Targeting Cascade (`data-ghost-id` → `data-testid` → `id` → ARIA labels → visible text).
- Python Backend SDK (`packages/sdk-server-python`) with FastAPI, Flask, Django support and `SQLAlchemyChatStore`.
- React 18 + Vite + TailwindCSS for the independent demonstration website (**ShopHive** in `demo/shophive`).
- Ephemeral run storage on Cloud Run / Cloud SQL (PostgreSQL 17) or Firestore with 30-minute TTL; Customer database (PostgreSQL / SQLite) for chat history.
- Docker/Compose locally; GCP Cloud Run, Secret Manager, Cloud Logging, Cloud Monitoring in deployment.

Required structure and responsibilities:

```text
ghost-cursor/
  MEMORY.md
  README.md
  LICENSE
  package.json
  package-lock.json
  tsconfig.json
  .gitignore
  .dockerignore
  packages/
    sdk-frontend/                  # @ghost-cursor/sdk & React wrapper (TS/Preact/Shadow DOM)
      package.json
      src/index.ts
      src/interactions.ts
      src/core/
      src/react/
    sdk-server-python/             # ghost-cursor (Python Backend SDK)
      pyproject.toml
      ghost_cursor/
        __init__.py
        brain_loader.py
        storage.py
        proxy.py
        fastapi.py
  services/
    orchestrator/                  # Ghost Cursor Cloud Backend (Python 3.12 / FastAPI + Google ADK)
      Dockerfile
      requirements.txt
      app/
        main.py
        agent.py
        brain_loader.py
        tools/
        llm/
        storage/
  demo/
    shophive/                      # Independent Showcase Customer App (ShopHive)
      frontend/                    # React 18 + Vite + TailwindCSS
        package.json
        src/
          App.tsx
          pages/
      backend/                     # FastAPI customer backend
        requirements.txt
        main.py
        tools/ghost_tools.py
        brain/
          platform.md
          pages/
        migrations/
          001_ghost_chat_schema.sql
  infra/
  docs/
    INTEGRATION.md
    PROVIDERS.md
    GCP.md
    OPERATIONS.md
```

You may split large modules further, but preserve these boundaries. The demo must be an authentic customer application integrating the SDK rather than importing internal orchestrator implementation code into its UI.

Use package names `@ghost-cursor/sdk`, `@ghost-cursor/sdk-react`, and Python distribution `ghost-cursor`. Hosted orchestrator and demo are separate services deployed on Cloud Run.

Preserve supplied licensing and assets. The reference project uses MIT with Copyright (c) 2026; retain that notice when recreating that project under its license. Do not falsely attribute unrelated new work or claim that unprovided artwork has been reproduced. Functional acceptance must not depend on access to original binary artwork.

## 4. Canonical contracts: implement these explicitly

Use a versioned, strict runtime protocol. Reject unknown properties at security boundaries instead of silently forwarding them. Generate JSON Schemas for Python from the canonical TypeScript definitions and ship them in the wheel. Cross-field refinements may need equivalent Python checks; test parity explicitly.

### 4.1 Primitive constraints

- `protocolVersion`: literal string `"1"`.
- Logical ID: string 1-120 characters matching `^[a-zA-Z0-9_.:-]+$`.
- Run/request/event identifiers: UUIDs.
- Scalar: string at most 2,000 characters, finite number, or boolean.
- Subject asserted by gateway: opaque string 1-120 characters matching `^[a-zA-Z0-9_.:@-]+$`. It is not supplied by browser request JSON.

### 4.2 Context

```json
{
  "page": "products",
  "values": { "product.selected_size": "10", "product.price": "129.99" },
  "availableTargets": ["product.size.9", "product.size.10", "product.add_to_cart_btn", "nav.cart"]
}
```

`values` is a record of scalars, default empty. `availableTargets` defaults empty and has at most 100 IDs. It is an observation, not a grant of permission.

### 4.3 Element Targeting Cascade & Target Verification

Target elements are resolved exclusively via the deterministic **Element Targeting Cascade**:
1. Level 1: Explicit Logical ID (`data-ghost-id="product.add_to_cart_btn"`)
2. Level 2: Automated Test ID (`data-testid="add-to-cart"`)
3. Level 3: Standard DOM ID (`id="add-to-cart-button"`)
4. Level 4: ARIA Accessibility Labels (`aria-label`, `role="button"`)
5. Level 5: Semantic Text & Visible Value Matching ("Add to Cart")

The model never writes custom code or raw DOM scripts. It receives fixed, typed tool definitions and emits tool call JSON with registered `target_id` parameters.

### 4.4 Fixed Frontend Action Tools

The Google ADK Agent is equipped with fixed Frontend Action Tools:
- `navigate(target_page: str, explanation: str)`: SPA route transition.
- `click(target_id: str, explanation: str)`: click button/link/tab.
- `fill_input(target_id: str, value: str|num, explanation: str)`: native setter dispatch.
- `toggle_switch(target_id: str, state: bool, explanation: str)`: switch/checkbox toggle.
- `guided_tour(steps: list[dict])`: spotlight walkthrough sequence.
- `ask_clarification(question: str, options: list[str])`: prompt user when ambiguous.

Approval Policy: Mutating or multi-step action sequences require explicit user confirmation ("Approve and Run") prior to execution.

### 4.5 Questions, Tools and Model Plan

Question: `{ question, options }`, question 1-1,000 characters, options at most ten strings of at most 200 characters.

Customer Backend Read-Only Tools: registered on customer backend (e.g. `lookup_order`, `check_warehouse_stock`, `simulate_discount_roi`), executed via Gateway Loopback under authentic user session context (`X-Ghost-Subject`).

Model Plan / Tool Calls:

```json
{
  "tool": "click",
  "parameters": {
    "target_id": "product.add_to_cart_btn",
    "explanation": "Add the selected size 10 sneakers to the cart."
  }
}
```

Discrete Plan Rules: Within any single model turn, only ONE of `questions`, `actions`, or `toolCalls` may be non-empty. An empty array across all three indicates terminal plan completion. Never execute partial parsed output.

### 4.6 Hosted API: create run

`POST /v1/runs` requires server Bearer credential and `X-Ghost-Subject`.

Body:

```json
{
  "protocolVersion": "1",
  "requestId": "a valid UUID",
  "message": "Add the Air Max 90 in size 10 to my cart.",
  "context": { "page": "products", "values": {}, "availableTargets": ["product.size.10", "product.add_to_cart_btn"] },
  "brain": "Authorized private Markdown excerpts, server-to-server only",
  "capabilities": [],
  "tools": []
}
```

The displayed UUID placeholder is explanatory, not a valid test fixture. Generate real UUIDs in requests. Message is 1-6,000 characters; Brain at most 32,000. Use a total hosted request limit of 64 KiB as well as field limits.

### 4.7 Hosted API: continue run

`POST /v1/runs/{runId}/continue` uses the same server authentication.

Body: `protocolVersion`, UUID `eventId`, nonnegative integer `revision`, `kind`, `results` (default empty), optional `answer`, optional updated `context`.

Kinds: `tools`, `actions`, `answer`, `cancel`.

Result: `{ id, ok, output?, error? }`. Error is a safe string at most 500 characters. Success cannot carry error; failure cannot carry output. At most twelve results, no duplicate IDs, and IDs must match every pending operation exactly. Report unexecuted remaining actions as failed/skipped safely when a batch stops; do not pretend they executed.

An answer requires nonblank text at most 6,000 characters and no results. Non-answer events cannot carry an answer. Cancellation carries no results.

Statuses:

- `awaiting_tools`: customer backend executes authorized read-only tools.
- `awaiting_actions`: SDK may execute approved actions.
- `awaiting_answer`: user must supply clarification.
- `completed`, `failed`, `cancelled`: terminal, no executable plan remains.

Response: `protocolVersion`, `runId`, `revision`, `status`, `reply`, `questions`, `actions`, and server-only `toolCalls`. Validate consistency between status and nonempty arrays. Derive status, do not trust a model to assign it.

### 4.8 Browser gateway protocol

The SDK posts to a customer-owned endpoint such as `/api/ghost`.

Start accepts ONLY:

```json
{
  "command": "start",
  "requestId": "a valid UUID",
  "message": "User request",
  "context": { "page": "summary", "values": {}, "availableTargets": [] }
}
```

Continue accepts `command: "continue"`, `runId`, `eventId`, `revision`, kind `actions|answer|cancel`, corresponding results/answer, and optional context. There is no browser `tools` continuation.

Reject browser-supplied Brain, subject identity, tenant identity, tool definitions, tool results, capabilities and permission grants. Existing customer authentication supplies identity; gateway configuration supplies privileges/knowledge.

Public response explicitly selects:

```text
protocolVersion, runId, revision, status, reply, questions, actions
```

Never spread internal run/provider JSON into a public response. Never expose an `awaiting_tools` state to the SDK; the gateway handles it internally. Revalidate the final result after any custom disclosure filter. HTTP error bodies are safe errors, separate from successful task envelopes.

## 5. Hosted orchestration and PostgreSQL

Implement a service entrypoint and a testable app builder with injected Store and Provider. Normal development and production use PostgreSQL. A MemoryStore is allowed only for isolated tests and explicitly labeled test servers; it must not be a silent fallback if the database is unavailable.

Authentication:

- Configure a server-secret map from random credentials to tenant IDs.
- Credential length at least 32 characters; compare safely without leaking keys.
- Derive tenant solely from the matched credential.
- Require validated gateway-asserted subject on every run operation.
- Scope every database lookup/update to both tenant and subject.
- Cross-tenant/user access returns 404; absent/invalid credentials 401.
- Reject Origin-bearing hosted requests with 403 as defense in depth. Origin absence alone is NOT proof of a trusted backend.

Expose `/health` as liveness without secrets. Apply no-store and nosniff headers, safe error responses, credential-redacted logs, 64-KiB request bounds and a basic 60 requests/minute instance-local limiter. Explain that this is not distributed per-tenant quota enforcement.

Baseline database table `ghost_runs`:

- UUID `id` primary key.
- `tenant`, `subject`, UUID `request_id`.
- `expires_at` timestamp.
- JSONB `data` containing internal run state.
- Unique `(tenant, subject, request_id)` and expiry index.

Internal state includes original input, plan/status, revision, history, start-payload digest, expiry and latest event ID/digest. Preserve immutable start identity/digest even as live context updates.

Behavior:

1. Create/deduplicate by tenant, subject and requestId.
2. Start planning from an internal pending revision such as -1; successful initial planning yields revision 0.
3. Same start ID with identical payload returns existing state; changed payload under that ID produces 409.
4. Continue only at the exact current revision and expected kind.
5. Identical latest-event replay returns its stored result; altered payload using that eventId, or stale revision, produces 409.
6. Validate result identities, preserve receipts, append bounded history, update context, and replan when appropriate.
7. A failed/unverified result terminates execution without more actions.
8. If subsequent model generation fails AFTER receiving completed action results, commit those receipts and a safe failed state. Do not roll them back and invite re-execution of already-applied effects.
9. Cancellation stops future execution; already-applied changes are not rolled back.
10. Expire runs after 30 minutes; expired access is 410. Limit to twelve continuation turns but keep cancellation available at the limit.

Use transactional locking and revision checks for the baseline, a bounded pool (initially five connections), connection timeout, and lock timeout (initially three seconds). Include explicit migration mode. Do not run implicit schema migrations automatically in production service startup.

The reference baseline serializes a run with SELECT FOR UPDATE and may hold the transaction during model generation. If you retain this simplification, mark it as a scaling limitation. Prefer short transactional claims/leases for production. Do not promise exactly-once arbitrary external effects, a full durable event ledger, read/reconciliation APIs or async workers unless actually implemented. Expiry does not delete records; retention/deletion is a separate required process.

## 6. Customer backend adapters

### 6.1 Shared behavior

The gateway is a small integration helper, not a second agent implementation. It authenticates via the customer's existing system, obtains approved knowledge, calls Ghost, handles local read-only tool requests and returns a public envelope.

Do not forward customer cookies/passwords/bearer access tokens to Ghost. Use an opaque authenticated subject and the server-held tenant service credential.

No Ghost-initiated inbound endpoint is required. Tool loop:

```text
Gateway -> Ghost: create/continue
Ghost -> Gateway: awaiting_tools + validated tool requests
Gateway: authorize and execute local registered read-only handlers
Gateway -> Ghost: matching results
Ghost -> Gateway: next plan/question/completion
Gateway -> SDK: public projection only
```

Limit the gateway to four tool rounds per browser request and four calls per model plan. Bound each hosted response to 256 KiB and each local tool output to 16,000 characters. Reject redirects and unapproved endpoints. Use HTTPS, allowing loopback HTTP only in development. Reject configured URLs with userinfo, query, or fragment. Never accept service URLs from model/browser input.

Use approximately 210-second per-hosted-request timeout. A sequence of slow model rounds can exceed an overall browser/proxy deadline: document it and design async continuations as production work instead of hiding the problem. Customer tools must impose their own database/API deadlines and honor cancellation where possible.

**Baseline local tools MUST be read-only.** They execute automatically. Do not register charge, email, delete, approve, save or other mutating handlers without an additional approval-bound and idempotent transactional protocol.

Tool idempotency metadata is `runId:revision:toolCallId`. This is not by itself a durable receipt or exactly-once guarantee. Concurrent requests can repeat a pending read-only call. Authorization must be checked inside local handlers too.

### 6.2 Node API

Provide `Gateway` constructor options:

```text
serviceUrl: string
serviceKey: string
loadBrain(subject, context): Promise<string>
capabilities(subject): Promise<Capability[]>
tools(subject): Promise<Record<string, Tool>>
filterResponse?(publicResponse, subject): Promise<PublicResponse>
fetch?: injectable transport for tests
```

Expose `handle(authenticatedSubject, rawBrowserBody): Promise<PublicResponse>`.

Tool has `description`, `inputSchema`, and
`execute(arguments, { subject, idempotencyKey }): Promise<JSON value>`.

The integrating route must apply existing auth, CSRF/origin defenses, body limits and rate limits before calling handle. Validate the browser input, hosted envelope, tool request and final public response. Convert internal exceptions to safe errors.

### 6.3 Python/Django API

Ship an installable Python distribution with corresponding `Gateway` and `Tool`. Use snake_case constructor options: `service_url`, `service_key`, `load_brain`, `capabilities`, `tools`, optional `filter_response`, and test-injectable transport. Python Tool uses `input_schema` and `execute(args, meta)`.

Support synchronous callbacks for the baseline and document worker/time-budget implications. Do not claim an async Django adapter if it is not implemented.

Provide `gateway_view(gateway)` in `ghost_cursor_django.views`:

- POST-only, CSRF-protected, no csrf_exempt on the browser session view.
- Require `request.user.is_authenticated`.
- Subject derives from `str(request.user.pk)`.
- Validate request/body size and return safe errors with no-store headers.
- Explain SessionMiddleware, AuthenticationMiddleware, CsrfViewMiddleware, ALLOWED_HOSTS, secure cookies/TLS, and SDK `X-CSRFToken` header integration.

Package generated schemas with the wheel so customers do not need Node. Do not silently diverge Python validation from TypeScript; use shared positive/negative fixtures and equivalent semantic invariants after JSON Schema checks.

## 7. Private Brain ownership and retrieval

Clients maintain private Markdown in their own repository/backend or existing CMS. The initial demo has one compact workflow Brain; large clients can implement authorized retrieval through callbacks or read-only knowledge tools.

Never put private Brain in Next `public/`, a browser bundle, frontend imports, public CDN, localStorage/sessionStorage, or a raw browser response.

Map known logical page IDs to fixed documents. Reject arbitrary paths. Resolve knowledge using authenticated user/tenant permissions, not a model-supplied user identity or an unrestricted document name.

Recommended Brain sections:

- Purpose and allowed user-facing explanation.
- Logical page/action/target IDs and navigation map.
- Field meanings, units, defaults, dependencies and loading conditions.
- Business constraints and available read-only tools.
- Approved mappings and what must be clarified instead of guessed.
- Workflow completion/failure criteria.
- Disclosure classification, version, owner and review date.

Do not rely on prose as enforcement. Numerical calculations must be grounded in tools where relevant; actual business authorization/validation stays in code.

The hosted service receives selected excerpts and stores them in the run until retention deletes them. The selected LLM also processes them. Explain this in integration/provider docs, including residency/retention/vendor-policy choices.

Use a private synthetic test marker such as `GHOST_BRAIN_SERVER_ONLY_CANARY_2026`. Include a demo disclosure filter that rejects responses containing it. This is a regression canary, NOT comprehensive leakage prevention. Never send genuinely undisclosable secrets just because a filter exists.

## 8. Frontend SDK API and interaction engine

### 8.1 Public SDK API

Provide:

```text
createGhostCursor({
  gatewayUrl,
  page: () => currentLogicalPage,
  targets: Record<logicalTargetId, Target>,
  headers?: () => headers | Promise<headers>,
  mount?: HTMLElement
}) -> { dispose() }
```

Target:

```text
page: logicalPageId | 'global'
resolve(): HTMLElement | null
operations: allowed operation list
observe?: boolean
commit?: 'input' | 'change' | 'blur'
execute?(element, action, signal): Promise<void>
verify?(action, signal): Promise<boolean>
```

Registration is customer-authored. Existing stable element IDs, refs, scoped resolvers and optional data attributes are acceptable. Resolving exactly one intended element is part of integration correctness. The model never receives permission to manufacture selectors.

Observe only opted-in target values on the current/global page. Do not collect all inputs and then try to redact secrets afterward. Password/file/hidden inputs must be refused even if accidentally registered. Labels and identifiers can also contain sensitive data; keep them minimal.

Mount only after browser/application initialization. Return cleanup and use it on unmount. In Next, mount under a persistent client layout so ordinary SPA navigation does not destroy the running SDK. No import-time DOM access.

### 8.2 Widget and visual behavior

- Framework-neutral DOM UI in Shadow DOM for style isolation.
- Chat log, textarea, Send, Stop, clarification options and action-review panel.
- Render model text as text, not HTML/unsanitized Markdown.
- Explicit "Approve and run" button before any batch.
- Visible cursor movement and spotlight around the current target.
- Accessible labels/live-region announcements, keyboard usability and reduced motion support. Do not claim a complete accessibility audit without running it.
- Disable conflicting requests during execution/approval.
- Reject stale approval callbacks and do not continue networking after dispose.
- Stop local execution promptly; explain that applied changes remain.

Keep cursor/presentation separate from action semantics. Highlights can include short user-safe explanations. Do not require a specific tour library if a small accessible implementation suffices.

### 8.3 Execution lifecycle

For every action:

1. Confirm registration and allowed operation.
2. Resolve target and wait for readiness with a bounded timeout (initially 8 s).
3. Reject disconnected, invisible, inert, disabled, readonly or sensitive controls.
4. Animate cursor/scroll/highlight.
5. Re-resolve immediately before acting; reject a stale element reference.
6. Execute the control-specific operation through existing application behavior.
7. Wait for rendering/validation; run a customer verifier if supplied.
8. Report the exact level of evidence, success/failure/uncertainty.
9. Stop remaining actions after failure or local cancellation.

Avoid speculative retries. Never treat "event dispatched" as "saved successfully." Custom adapters must have bounded waits and respect AbortSignal. Pure DOM verification is weaker than application/server verification; label it honestly.

### 8.4 Built-in native controls

**Text/number/textarea:** use the correct native prototype value setter rather than only assigning the instance property. Emit bubbling input so ordinary controlled-input handlers can update framework state. Support explicit commit profiles for change/blur. Validate native constraints on a detached probe before notifying the application. Verify retained value after render; reject reversion, unexpected formatting or invalid state instead of assuming success.

Supported baseline native input types can include text, number, email, search, URL, telephone, date, time and range. Do not claim custom sliders are supported merely because a native range input is supported.

**Native select:** single-select only initially; require an existing enabled option and enabled optgroup; emit relevant input/change events.

**Checkbox/radio:** click only if desired state differs. Do not duplicate the toggle by setting checked and then clicking. Reject radio false; select another radio instead.

**Button/link:** invoke existing click behavior only on explicitly registered targets. Block cross-origin/new-window navigation in the baseline. Verify SPA destination route/content using callbacks; do not assume a fixed sleep is enough.

**Custom controls:** optional execute/verify adapters for component libraries, masked fields, editors or widgets. Customer-specific adapters are exceptions, not mandatory callbacks for every standard field.

Do NOT indiscriminately fire every keyboard/pointer/input/change/blur event. Doing so can duplicate validations, API calls, autosaves or submits. A JS click is not the full physical pointer sequence. Never use Enter/blur simply as a universal "commit" hack. Autosaving fields may be consequential even without a Save button.

### 8.5 Persistence boundaries

Demonstrate execution across SPA page changes with persistent mounting and destination readiness. The baseline need not automatically resume after a hard reload. Do not blindly replay a persisted queue after reload/disconnect: the last operation may already have happened. Track durable receipts/reconciliation as separate production work. Task revision is not application-state concurrency protection; customer postconditions must guard changing business state.

## 9. Demonstration website: ShopHive Footwear & Apparel Store

To showcase Ghost Cursor's complete feature set in an authentic domain, implement **ShopHive** — a production-grade demo e-commerce storefront for sneakers and sportswear.

Build an independent customer application in `demo/shophive` with:

- Frontend (`demo/shophive/frontend`): React 18 + Vite + TailwindCSS.
  - `/`: Product catalog grid.
  - `/product/:id`: Single product detail page (interactive size selection, stock checks, add-to-cart).
  - `/cart`: Shopping cart with totals and promo code input.
  - `/checkout`: Multi-step checkout form (shipping address, payment options).
  - `/orders`: Order history and timeline tracking.
  - `/settings`: User preferences and theme toggle.
  - Mounted `<GhostCursor apiEndpoint="/api/ghost-cursor" />` widget rendered in the bottom right corner.
- Backend (`demo/shophive/backend`): FastAPI customer gateway.
  - Hosts customer user session and proxies requests to Ghost Cursor Cloud.
  - Attaches `SQLAlchemyChatStore` to manage customer-owned chat sessions and messages.
  - Registers read-only backend tools (`lookup_order`, `check_warehouse_stock`, `simulate_discount_roi`).
  - Serves dynamic Brain files from `brain/platform.md` and `brain/pages/*.md`.

### 9.1 Exact Showcase Scenarios & Verification Fixtures

1. **Screen-Aware Guidance:**
   - User on Product Detail Page asks: *"What sizes are available?"*
   - Ghost Cursor inspects the live DOM context and active warehouse stock, responding with available sizes and price.
2. **AI Cursor Auto-Actions:**
   - User asks: *"Add the Air Max 90 in size 10 to my cart"*
   - Ghost Cursor plans: `navigate(target_page="products/air-max-90")` → `click(target_id="product.size.10")` → `click(target_id="product.add_to_cart_btn")`.
   - AI Cursor animates across the viewport and updates React cart state.
3. **Customer Backend Read-Only Tools (Gateway Loopback):**
   - User asks: *"Where is order SH-1024?"*
   - Google ADK agent calls `lookup_order(order_id="SH-1024")`. Customer gateway executes tool locally under `X-Ghost-Subject` and returns tracking status.
4. **Smart Clarifying Questions:**
   - User says: *"I want to checkout"*
   - Ghost Cursor asks: *"Which shipping address should I use: 123 Main St (saved) or enter a new address?"*
5. **Guided Tours:**
   - User asks: *"How do I track my return?"*
   - Multi-step spotlight overlay highlights the orders tab and carrier tracking link.

### 9.2 Quantified Customer Integration Delta

Showcase in code comments and documentation that integrating Ghost Cursor required only:
- **Frontend:** ~9 lines of JSX in `App.tsx` + `data-ghost-id` attributes on key buttons/inputs.
- **Backend:** ~14 lines of setup in `main.py` + 1 tools registration module (`tools/ghost_tools.py`).
- **Database:** Running standard migration `001_ghost_chat_schema.sql` for chat history persistence.
- **Total Customer Delta:** **3 files modified, 3 files created, ~61 lines of code (< 1 hour of dev effort)**.

## 10. Google ADK & Vertex AI Agent Engine

The core agent orchestration is implemented in Python 3.12 using the **Google Agent Development Kit (ADK)** and Vertex AI Gemini 2.0 Flash / Pro.

### 10.1 ADK Agent Definition (`services/orchestrator/app/agent.py`)

- Instantiates `google.adk.agents.llm_agent.Agent` with `gemini-2.0-flash`.
- Provides fixed **Frontend Action Tools**: `navigate`, `click`, `fill_input`, `toggle_switch`, `guided_tour`, `ask_clarification`.
- Appends customer's dynamically registered **Backend Knowledge Tools** forwarded by the customer gateway.
- Enforces strict single-tool-type response per turn and validation against registered logical target IDs.
- For local testing without active GCP credentials, provide an explicit mock agent provider that replays deterministic tool call fixtures.

## 11. Local Setup, Scripts and Packaging

Provide clean setup scripts and reproducible local development:

```bash
# 1. Ghost Cursor Backend Orchestrator
cd services/orchestrator
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080

# 2. Frontend SDK
cd packages/sdk-frontend
npm install
npm run dev

# 3. ShopHive Demo Application
cd demo/shophive/frontend
npm install
npm run dev -- --port 3000

cd demo/shophive/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8081
```

Ignore node_modules, dist, .next, .venv, .env variants except examples, Python cache, local SQLite files, test artifacts, tarballs/wheels, Terraform state/plans and editor metadata. Docker build context must exclude secrets, local databases and state.

## 13. Tests and acceptance criteria

Do not report a test as passed merely because you wrote it. Run what the environment permits, preserve exact command/result evidence, and explicitly list blocked checks.

### 13.1 Protocol/service tests

- Reject mixed questions/actions/tools, invalid values, duplicate IDs and unknown fields.
- Reject browser Brain/tool results/subject/tenant injection.
- Reject absent/wrong server credentials and hosted requests with Origin.
- Enforce tenant and user isolation on every run continuation.
- Deduplicate identical starts; reject changed payload under same requestId.
- Support identical latest-event retry; reject conflicting replay/stale revision.
- Reject expired runs and unknown targets/operations/tools/arguments.
- Validate matching action/tool result identities and continuation kind.
- Stop after failed/unverified action, and retain receipts if replanning fails.
- Permit cancellation at turn limit; reject further non-idempotent terminal events.
- Verify gateway tools run privately and response projection excludes internals.
- Add real PostgreSQL transaction/concurrency tests when a database is available.

### 13.2 Gateway parity and provider tests

- Node and Django accept/reject equivalent fixtures, including nested field types.
- Private Brain goes server-to-server and never appears in the public envelope.
- Tool failures/oversized outputs become safe failures; unapproved tools do not run.
- Revalidate after custom disclosure filters; malformed output fails closed.
- Django browser view enforces session authentication and CSRF.
- Provider fixtures verify endpoint/header/body mappings and strict output parsing.
- Reject malformed/incomplete model responses and unsupported configurations.
- Mock is prohibited in production; provider failures never switch to mock.
- Live-provider tests are separate, opt-in and require real credentials.

### 13.3 Real-browser acceptance for ShopHive Demo

Use Playwright with a self-started test-only orchestrator API and the ShopHive demo application:

1. Open ShopHive homepage (`/`) and verify the product grid and `<GhostCursor />` widget are mounted.
2. Navigate to the product page (Air Max 90).
3. Send request: *"Add the Air Max 90 in size 10 to my cart"*.
4. Confirm a proposed action plan appears (`navigate`, `click` size 10, `click` Add to Cart) and no values change before approval.
5. Click *"Approve and Run"* and observe AI cursor animation across the screen to select size 10 and click Add to Cart.
6. Verify native React state changes — the cart counter animates from 0 to 1 (not merely detached property assignments).
7. Proceed to checkout, trigger the clarifying address question, and verify form field auto-filling.
8. Verify customer read-only tool execution (`lookup_order`, `check_warehouse_stock`) and 3-step return tour overlay.
9. Verify browser fetch/XHR uses only its same-origin client gateway (`/api/ghost-cursor`), never direct Ghost Cloud or model endpoints.
10. Verify public envelope lacks Brain internals/canary and canary strings are filtered.
11. Verify unauthenticated gateway calls return 401.

Also cover stop/dispose, failed control changes, native select/checkbox/radio, constraints, stale targets and custom-verifier behavior. Use reduced-motion tests and appropriate accessible selectors where possible.

Test successful production Next build and packed SDK imports/SSR safety. Audit dependencies, including transitive dependencies. Do not copy historical passing results from the source idea into this new project's memory; rerun them.

## 14. GCP deployment deliverables

Produce a GCP deployment foundation and detailed operator guide. Do not create chargeable resources, publish containers/packages, or perform destructive actions without explicit authorization and credentials.

### 14.1 Baseline services

- Cloud Run for hosted API; independent deployment for demo/customer gateway.
- Cloud SQL PostgreSQL 17, private IP only, regional HA, backups and PITR.
- Encrypted database connections; require certificate verification/client trust configuration rather than treating a private IP as encryption.
- Secret Manager for provider keys, tenant credential map and database URL.
- Artifact Registry for versioned images.
- Cloud Build for checks and image publication; do not auto-deploy implicitly.
- Dedicated least-privilege runtime/deployer identities.
- VPC/subnet/private service connection and Direct VPC egress for private SQL.
- External HTTPS load balancer, managed TLS, static edge IP and Cloud Armor.
- Restricted Cloud Run ingress preventing direct public run.app bypass.
- Logging/Monitoring setup directions and operational checklists.

Terraform input concepts: project, region, domain, immutable image reference, provider/model selection, env-variable-to-secret-ID map, deploy_service flag.

### 14.2 Staged provisioning

1. Select separate development/staging/production projects, billing, region, residency requirements, budgets and operator permissions.
2. Initialize protected Terraform remote state for team/production use; state access is sensitive. Do not commit local state/plans.
3. Enable required APIs and provision prerequisites with deploy_service=false.
4. Create secret containers, not plaintext secret values inside Terraform state.
5. Provision database users securely; distinguish migration permissions from production runtime DML permissions.
6. Populate Secret Manager from a secure process, not committed files or shell arguments exposing credentials. Configure trusted database TLS material.
7. Build/test/publish an API image with dedicated build identity; review image vulnerabilities and pin a tested digest.
8. Enable the Cloud Run service, migration job and edge with deploy_service=true.
9. Execute migration explicitly before customer traffic is enabled.
10. Configure DNS and wait for certificate activation; point client backend at the HTTPS edge URL.
11. Verify auth failures, tenant isolation, edge bypass prevention, SQL connectivity, rollback and restore before live rollout.

Initial sizing can be 1-5 instances, concurrency five, one CPU, 512 MiB RAM, 240-second HTTP timeout and five SQL connections per instance. These are starting values, not a measured capacity promise. Account for pool size × instance count. Long model calls inside database transactions are a known scaling limitation.

If the external load balancer needs an allUsers Cloud Run invoker binding, explain that application Bearer authentication remains mandatory and restricted ingress prevents direct public bypass. Respect organization policies that prohibit such bindings; do not weaken authorization to get a deployment working.

Use deletion protection for database/service. Discuss pinned secret versions, rotation, image provenance/scanning, CI Workload Identity Federation, safe migrations, canary deployment and rollback without destructive schema reversal.

Provide non-root multi-stage Docker targets named api and demo. Docker build must not copy .env/credentials/state. Cloud Build should run Node checks/tests/build, publish a versioned API image, and clearly distinguish publication from deployment. Do not claim browser/Python tests run in that pipeline unless configured.

### 14.3 GCP options to explain, not falsely mark implemented

- Cloud Tasks for async run continuations with authenticated workers, retries, leases and idempotency.
- Pub/Sub and BigQuery for redacted events/usage analytics.
- Memorystore for distributed quotas/cache if justified by load.
- Vertex AI with ADC/project/location and scoped IAM as a separate provider adapter.
- Cloud Storage/CDN for public versioned bundles/docs, never private Brain.
- Identity Platform for provider-admin identity, not replacing client auth.
- Sensitive Data Protection for classification/redaction, not a secrecy guarantee.
- Cloud KMS/CMEK when required by customer policy.
- GKE only when demonstrated requirements exceed Cloud Run; not baseline.

Document concrete adoption steps, prerequisites and costs. Clearly mark optional services not provisioned by the baseline Terraform.

## 15. Documentation requirements

This repository must be documentation-heavy and usable by a new maintainer.

### README.md

Product summary; only supported topology; honest release status; requirements; exact Node/Django quickstarts; generated-secret locations; demo walkthrough; provider configuration ownership; repo map; build/test commands; integration overview; links to detailed guides; explicit unpublished/undeployed status.

### MEMORY.md

Decisions and rationale; implementation sequence; current completed/in-progress work; real test commands/results; environment issues; production gaps and next steps. Keep evidence dated. Never claim successful deployment from HCL parsing.

### docs/INTEGRATION.md

Frontend target/context API, native behavior, custom adapters/verifiers, lifecycle, Node/Django helper APIs, auth/CSRF, private Brain authoring, universal HTTP protocol, packaging/install commands, client/provider responsibilities and onboarding.

### docs/PROVIDERS.md

Exact env variables and where keys live; how to change provider/model/restart; vendor capability differences; strict parsing/failure behavior; synthetic smoke; shim startup/path/flags/limits; existing-compatible-endpoint usage; Vertex versus Developer API distinction; Secret Manager/rotation/data disclosure policy.

### docs/GCP.md

Step-by-step operator commands and console actions from an empty staging project through prerequisites, secrets, image, service, migration, DNS/TLS, verification, monitoring, scaling, rollback and restore. No hidden assumptions about credentials, build identities, billing, database TLS or organization policy.

### docs/OPERATIONS.md

Threat model, protections, known limitations, production checklist, dependency maintenance, troubleshooting, retention/deletion, incident response and recovery. Explain partial execution and why actions are not automatically reversible.

## 16. Production gates: distinguish baseline from target

The product direction is scalable and production-oriented, but the minimum recreation is a verified development baseline. Maintain this distinction:

| Area | Minimum baseline | Production work unless actually implemented |
|---|---|---|
| Orchestration | Bounded synchronous HTTP | Async workers, short claims/leases, reconnectable delivery |
| Run state | PostgreSQL, revisions, start/latest-event deduplication | Full durable event ledger and reconciliation |
| Server tools | Authorized read-only local calls | Approval-bound idempotent mutation protocol |
| Browser navigation | Persistent SPA SDK | Safe reload recovery without blind replay |
| UI compatibility | Tested native controls and adapters | Broad browser/widget/accessibility support |
| Freshness | Task revision and optional postconditions | Application-state concurrency protection |
| Quotas | Local/IP throttles | Distributed tenant/user usage and spend enforcement |
| Knowledge | Client callback-selected Markdown | Managed retrieval/indexing/admin if required |
| Retention | Expired run access rejected | Scheduled deletion, export, contractual backup policy |
| Providers | Strict adapters and fixtures | Live-model evaluations/account verification |
| Database | PostgreSQL implementation | Actual integration/concurrency/restore/load evidence |
| Deployment | Docker/GCP foundation | Built images, Terraform provider validation, staging verification |
| Identity | Static tenant-key configuration/demo session | Operational tenant administration/rotation controls |

Do not present checks as complete when Docker, Terraform, cloud access or provider keys are unavailable. Continue with everything that can be verified locally, then report the exact blockers and commands needed. HCL syntax parsing is not terraform validate; mock browser tests are not real database tests; API fixtures are not live model verification; expiring rows is not deleting customer data.

## 17. Suggested execution order

1. Inspect workspace, preserve existing work, write MEMORY and initial README.
2. Establish workspace, packages, strict schemas and generated Python contracts.
3. Implement Google ADK agent engine (`services/orchestrator`) with Gemini 2.0 Flash and mock test fixtures.
4. Implement Backend SDK (`ghost_cursor`) with Dynamic Brain Loader, `SQLAlchemyChatStore`, and Gateway Tool Loopback.
5. Implement Frontend SDK (`@ghost-cursor/sdk`) with Shadow DOM sandboxing and Element Targeting Cascade.
6. Build independent ShopHive demo storefront (`demo/shophive`) with React frontend and FastAPI backend.
7. Add Python ADK tests, Brain loader tests, and Playwright browser acceptance tests.
8. Add GCP Cloud Run deployment configuration and documentation.

At completion summarize files/packages implemented, exact checks passed, checks not run and why, how to start the demo, where keys belong, and remaining production work. Do not dump secrets, claim deployment without evidence, or imply that a generic input engine works on every possible web widget with zero integration.

**Build the project now using these instructions. Ask only when an essential decision cannot be safely inferred. Preserve the mandatory gateway-only topology, private Brain ownership, hybrid native-control/custom-adapter approach, both customer backend adapters, and honest production-readiness boundary.**