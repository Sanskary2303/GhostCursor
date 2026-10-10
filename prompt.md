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
- The hosted service is Node.js/TypeScript. Do not move orchestration into the demo or confuse the Django customer adapter with the hosted service.
- Provide **Node.js and Python/Django customer adapters now**.
- Other customer backends can implement the documented HTTP/JSON protocol directly. Dedicated adapters for Java, .NET, Go, etc. are conveniences, not mandatory for interoperability. Do not build every possible language adapter initially.

### 2.5 Client-owned Brain is a core differentiator

Cross-page and business awareness is central to the product, not optional chat decoration. Separate three sources of knowledge:

1. **Application map/capabilities:** pages, logical targets, actions, dependencies, readiness requirements, and multi-page workflows.
2. **Private Brain:** Markdown business explanations, domain constraints, approved mappings, workflow guidance, and clarification rules maintained by the client.
3. **Live context:** current page and opted-in control values/availability supplied by the frontend integration.

Neither DOM scanning nor data attributes alone provides business understanding or knowledge of unmounted pages.

### 2.6 Security and honest production claims

Default to explicit registration and approval. Business APIs still enforce normal customer authorization. Brain prose, model output, and approval UI are not an authorization mechanism against a malicious user/browser.

Build production-oriented boundaries but do not equate a working demo with a production-certified service. Track concrete missing work, unavailable validation, and external prerequisites. Never fabricate test results or deployment success.

## 3. Technology and repository layout

Use an npm-workspaces TypeScript monorepo and a separate installable Python distribution. Do not introduce unnecessary Kubernetes or a large agent framework.

Baseline technology choices:

- Node 22.16+; prefer a currently patched supported LTS for deployment.
- TypeScript strict mode, ESM, ES2022, NodeNext resolution for Node packages.
- Fastify 5 for the hosted HTTP service.
- Zod 3 for canonical runtime contracts; Ajv 8 for customer tool argument schemas.
- PostgreSQL 17 using `pg`; PostgreSQL is authoritative run storage.
- tsup for ESM/declaration package builds; tsx for development/test execution.
- Next.js App Router, React 19 and TypeScript for the independent demo.
- Python 3.11+, Django 5.2-compatible adapter, httpx, jsonschema.
- python-dotenv only as an optional demo convenience.
- Node test runner and Playwright for service/browser verification; unittest for Python. Other test libraries are acceptable if equivalent tests and commands work.
- Docker/Compose locally; GCP Cloud Run/Cloud SQL/Secret Manager in deployment.

These are compatibility families, not instructions to install vulnerable versions. Resolve supported patched releases, commit a lockfile, audit the full tree, and document justified overrides. Do not use unverified future model or package IDs.

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
  compose.yaml
  Dockerfile
  cloudbuild.yaml
  playwright.config.ts
  packages/
    protocol/
      package.json
      src/index.ts
    sdk/
      package.json
      src/index.ts
      src/interactions.ts
    gateway-node/
      package.json
      src/index.ts
  adapters/
    django/
      pyproject.toml
      src/ghost_cursor_django/
        __init__.py
        views.py
        schemas.json
      tests/
  services/
    orchestrator/
      package.json
      .env.example
      src/app.ts
      src/store.ts
      src/providers.ts
      src/main.ts
  apps/
    demo-next/
      package.json
      next.config.mjs
      tsconfig.json
      app/
        layout.tsx
        page.tsx
        style.css
        budget-provider.tsx
        ghost-integration.tsx
        assumptions/page.tsx
        login/page.tsx
        api/ghost/route.ts
        api/login/route.ts
      lib/auth.ts
      lib/gateway.ts
      private/brain/budget.md
  examples/
    django-demo/
      manage.py
      settings.py
      urls.py
      private/budget.md
    dev/shim/server.py
  scripts/
    setup-local.mjs
    export-schemas.ts
    provider-smoke.ts
  tests/
    service.test.ts
    providers.test.ts
    browser-api.ts
    browser/demo.spec.ts
  infra/main.tf
  docs/
    INTEGRATION.md
    PROVIDERS.md
    GCP.md
    OPERATIONS.md
```

You may split large modules further, but preserve these boundaries. The demo must be a consumer of the built packages rather than importing hidden orchestrator implementation code into its UI.

Use package names `@ghost-cursor/protocol`, `@ghost-cursor/sdk`, `@ghost-cursor/gateway-node`, `@ghost-cursor/orchestrator`, and `@ghost-cursor/demo`, initially version `0.1.0`. Hosted service and demo are private workspace packages. Protocol, SDK, and gateway expose ESM plus type declarations from dist and have sensible files/exports fields. Python distribution name is `ghost-cursor-django` with import name `ghost_cursor_django`.

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
  "page": "assumptions",
  "values": { "budget.hours": "700", "budget.rate": "120" },
  "availableTargets": ["budget.hours", "budget.rate", "nav.summary"]
}
```

`values` is a record of scalars, default empty. `availableTargets` defaults empty and has at most 100 IDs. It is an observation, not a grant of permission.

### 4.3 Server capability

```json
{
  "target": "budget.hours",
  "description": "Edit engineering hours",
  "operations": ["setValue"],
  "page": "assumptions",
  "requiresApproval": true
}
```

Description is at most 500 characters. Operations are selected from the five supported operations below. Approval defaults true. Use `page: "global"` for navigation available across pages. At most 100 capabilities; reject duplicate target declarations.

### 4.4 Actions

Supported operations are exactly:

- `setValue`: registered text/number/native input or textarea.
- `select`: registered single native select.
- `setChecked`: registered checkbox/radio.
- `click`: registered button/link.
- `highlight`: registered visual target.

```json
{
  "id": "set-hours",
  "target": "budget.hours",
  "operation": "setValue",
  "value": 500,
  "explanation": "Apply the reviewed engineering-hours assumption."
}
```

`id` and `target` are logical IDs. Explanation is at most 500 characters and defaults empty. `setValue`/`select` require a string or finite number; `setChecked` requires a boolean; `click`/`highlight` must not carry a value. Validate target and operation against gateway-authorized capabilities.

The model does not choose its own approval policy. Public actions add a server-derived `requiresApproval` field. The baseline SDK still asks for approval for every batch, including navigation/highlight batches.

### 4.5 Questions, tools and model plan

Question: `{ id, text, options }`, text 1-1,000 characters, options default empty, at most ten strings of at most 200 characters.

Tool definition: `{ name, description, inputSchema }`, description at most 1,000 characters; inputSchema is a validated JSON Schema object. At most 20 definitions; reject duplicate names and invalid schemas.

Tool call: `{ id, name, arguments }`, arguments a JSON object. The name must match an approved definition and arguments must satisfy its schema.

Model plan:

```json
{
  "reply": "I will calculate a scenario before changing anything.",
  "questions": [],
  "actions": [],
  "toolCalls": [
    {
      "id": "forecast-1",
      "name": "forecast",
      "arguments": {
        "engineeringHours": 500,
        "hourlyRate": 100,
        "qaBudget": 20000
      }
    }
  ]
}
```

Reply is at most 6,000 characters. Limits: five questions, twelve actions, four tool calls. Missing arrays may normalize to empty internally, but transmitted responses should have explicit arrays. Only ONE of questions/actions/toolCalls may be nonempty in a turn. All operation/question IDs in that plan must be unique. Reply with all arrays empty means completion. Never execute partial parsed output.

### 4.6 Hosted API: create run

`POST /v1/runs` requires server Bearer credential and `X-Ghost-Subject`.

Body:

```json
{
  "protocolVersion": "1",
  "requestId": "a valid UUID",
  "message": "Bring Phoenix within budget without reducing QA.",
  "context": { "page": "summary", "values": {}, "availableTargets": [] },
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

## 9. Demonstration website: Phoenix project-budget planner

Do not build an Amazon/Netflix clone. A fictional budget planner naturally demonstrates cross-page knowledge, calculations, controlled fields, approvals, constraints and explanations without real purchases or copyrighted branding.

Build an independent Next.js application in `apps/demo-next` with:

- `/`: project summary.
- `/assumptions`: editable assumptions.
- `/login`: explicit local demo login.
- Persistent layout/provider holding ordinary React application state.
- Separate `ghost-integration.tsx` containing SDK target registrations.
- Server-only Node gateway configuration and private Brain.

### 9.1 Exact business fixture

Project: **Phoenix platform modernization**.

Formula:

```text
forecast = engineeringHours * hourlyRate + qaBudget
```

Initial values:

- Engineering hours: **700**.
- Hourly rate: **$120**.
- QA allocation: **$20,000**.
- Initial forecast: **$104,000**.
- Target budget: **$80,000**.
- QA minimum: **$20,000**.

Native field/tool constraints:

- Hours: 100-2,000.
- Hourly rate: 50-300.
- QA: 20,000-100,000.

Define read-only `forecast(engineeringHours, hourlyRate, qaBudget)` returning the validated assumptions and calculated total. The tool must not save or mutate application/financial data.

Standard demo prompt: **"Bring Phoenix within $80,000 without reducing QA."**

Mock proposal: **500 hours * $100/hour + $20,000 QA = $70,000**.

Logical target -> DOM ID:

| Target | DOM ID | Page/operation |
|---|---|---|
| `nav.assumptions` | `nav-assumptions` | global/click |
| `nav.summary` | `nav-summary` | global/click |
| `budget.hours` | `hours` | assumptions/setValue |
| `budget.rate` | `rate` | assumptions/setValue |
| `budget.qa` | `qa` | assumptions/setValue |
| `budget.total` | `forecast-total` | summary/highlight |

Mock sequence:

1. Request forecast tool with 500/100/20000.
2. After verified tool result, explain the proposed $70,000 scenario.
3. Propose click `nav.assumptions`, set hours, set rate, preserve/set QA, click `nav.summary`, highlight `budget.total`.
4. Wait for user approval.
5. Execute normal navigation and native field interactions.
6. Show summary and safe completion text based on reported outcomes.

The mock is one explicitly scripted scenario, not a real general-purpose model. Real providers must respect arbitrary user constraints or ask questions instead of unconditionally forcing the demo assumptions.

### 9.2 Ordinary client code, not copilot-only business logic

Use controlled React inputs with normal onChange handlers. The integration module must NOT pass per-field React setters/Redux dispatchers for this demo. Browser tests must demonstrate that native interaction reaches those normal handlers and the forecast derived from React state changes accordingly.

Use Next links with existing click handlers. Navigation verification waits for both pathname and destination page content. Keep SDK mounted across SPA routes.

The website must work without the assistant. Support `?copilot=off` on fresh load to demonstrate that the client application is independent.
💡
### 9.3 Demo appearance

Use a responsive dark dashboard with orange accent, clear project title, forecast/target/QA cards, readable assumption fields and a visible bottom-corner assistant. Provide instructions and explain that all data is synthetic. Do not require external fonts/network assets or original artwork to run the demo.

### 9.4 Demo authentication and Django mode

Provide `/api/login` and `/api/ghost`. Generate a random demo password and HMAC session secret locally. Use one-hour signed HttpOnly SameSite Strict cookies, secure cookies under HTTPS, exact configured-origin checks, safe errors and body limits. Never place these secrets in NEXT_PUBLIC variables.

This simple demo login is not production identity/abuse protection. Customers retain their existing authentication; production demonstrations need proper access control and rate limiting.

`DEMO_GATEWAY=node` uses the Node gateway helper in Next's server route. `DEMO_GATEWAY=django` makes the Next server relay to loopback Django, keeping the browser endpoint same-origin. Relay requires a server-held key, trusted demo subject, loopback address, no Origin header and explicit enablement. Disable the relay in production Next execution. It is only a demonstration bridge.

The Django example also exposes a separate normal session/CSRF gateway view so real Django integrations do not copy the relay's CSRF exemption.

## 10. LLM provider abstraction

Implement a server-side interface equivalent to:

```text
Provider.generate({ input, history }) => Promise<Validated Plan>
```

History contains prior plans and acknowledged continuation events. Prompt policy requires strict JSON, approved capabilities/tools, grounded calculations, clarification for missing information, respect for constraints, no repeated completed actions, and no unsupported claims of success/persistence.

Treat all application knowledge, UI/user text and tool results as data subordinate to service policy. Do not frame private Markdown as unrestricted system authority.

### 10.1 Environment selection

| LLM_PROVIDER | Credential/configuration |
|---|---|
| `mock` | No key; explicit development fixture; forbidden in production |
| `openai` | `LLM_MODEL`, `OPENAI_API_KEY` |
| `gemini` | `LLM_MODEL`, `GEMINI_API_KEY` |
| `anthropic` | `LLM_MODEL`, `ANTHROPIC_API_KEY` |
| `openai-compatible` | `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY` |

Keep keys only in `services/orchestrator/.env` locally and GCP Secret Manager in production. Provider selection/model/key changes require backend restart/redeploy, not frontend changes. Validate unknown/missing configuration at startup. Do not send OpenAI's key to a configurable third-party URL by accident.

### 10.2 Vendor mapping

- OpenAI: `/v1/chat/completions`, system/user messages, JSON object output mode for compatible models; read choices[0].message.content and stop reason.
- Gemini Developer API: generateContent with systemInstruction, content parts, JSON MIME output, x-goog-api-key; reject blocked/incomplete responses.
- Anthropic: Messages API, x-api-key and version header, system text, content blocks and output-token limit; reject truncated output.
- Compatible endpoint: configurable base URL ending in `/v1`, append `/chat/completions`; do not assume vendor-specific JSON mode is supported.

The baseline uses **strict JSON text plans containing explicit tool requests**, not native function-calling parity across vendors. Do not claim native tools or streaming if only JSON plans are implemented.

Bound responses to 256 KiB, calls to approximately 200 seconds, and reject redirects. Parse complete JSON strictly, then validate the plan. Fail closed on prose, fences, missing fields, invalid tool calls, refusal/truncation or bad status. No silent provider fallback, no partial execution, and no fabricated token usage.

Do not hardcode a model ID that has not been checked against the operator's account. Explain how to choose a model supporting the required API. Temperature, reasoning options and token parameters are not universally interchangeable.

The `gemini` adapter is Developer API with a key. **Vertex AI ADC is a separate future adapter**, not enabled merely by setting a Google project ID. Document the extension without pretending it is present.

Provide transport fixtures for all adapters and an explicit synthetic live smoke script. Running live smoke may incur charges and must not use customer data.

## 11. Development OpenAI-compatible CLI shim

Include a standalone Python shim so testing does not depend on the original SVQ checkout. Also document how to point at any existing compatible shim instead.

Requirements:

- Bind only `127.0.0.1:8765`.
- GET `/health`; POST `/v1/chat/completions`.
- Require Bearer token, default `SHIM_KEY=local` only for loopback development.
- Reject browser Origin headers, streaming, and native tools requests.
- Accept buffered role/content messages, assemble a strict JSON task prompt.
- Limit request body to 64 KiB and portable CLI prompt to roughly 24K characters.
- Configure `COPILOT_APP_JS`; execute Node plus that entrypoint directly on Windows, not a .cmd through cmd /c that can truncate multiline prompts.
- Optional `COPILOT_MODEL`; verify CLI flags against the installed CLI version.
- Use no shell, no broad permission grants, no customer repository working dir; run from a temporary directory with built-in/custom tools/instructions disabled where supported. The CLI still has local user identity; it is not a sandbox.
- Timeout after 180 seconds; strict JSON parsing; safe errors without prompt/key logging. Single-request buffered handling and no cache are acceptable.
- Return standard OpenAI content/choices/finish_reason format; no fake usage data.

Recommended backend testing configuration:

```dotenv
LLM_PROVIDER=openai-compatible
LLM_MODEL=copilot-cli
LLM_BASE_URL=http://127.0.0.1:8765/v1
LLM_API_KEY=local
```

Use synthetic data only. Never deploy the CLI shim as production SaaS infrastructure or expose it publicly. Cloud Run localhost refers to the container, not a developer laptop. A separately hosted compatible gateway needs HTTPS and authentication.

## 12. Local setup, scripts and packaging

Provide a clean quickstart and an idempotence-aware `setup-local` script. Generate random matching credentials in these ignored files, without printing values:

1. `services/orchestrator/.env`:
   PORT, DATABASE_URL, GHOST_TENANT_KEYS, LLM_PROVIDER, LLM_MODEL and selected key.
2. `apps/demo-next/.env.local`:
   GHOST_SERVICE_URL, GHOST_SERVICE_KEY, DEMO_ORIGIN, DEMO_PASSWORD,
   DEMO_SESSION_SECRET, DEMO_GATEWAY, DEMO_RELAY_KEY.
3. `examples/django-demo/.env`:
   GHOST_SERVICE_URL, GHOST_SERVICE_KEY, DJANGO_SECRET_KEY, DEMO_RELAY_KEY,
   DEMO_RELAY_ENABLED.

Refuse to overwrite any existing secret file or create mismatched partial setup. Ship placeholder `.env.example` files, not credentials.

Ports: Next 3000, Django 8000, hosted API 8080, PostgreSQL 5432, shim 8765.
Default demo origin is `http://127.0.0.1:3000`; explain that using localhost instead will fail exact-origin checks unless configuration changes consistently.

Compose provisions PostgreSQL with persistent volume, healthcheck and loopback-only published port. A clearly marked development-only database password is acceptable for local Compose, never for production. No memory fallback for normal dev API.

Required commands or equivalents:

```text
npm ci
npm run setup:local
npm run schemas
npm run typecheck
npm test
npm run build
npm run build:demo
docker compose up -d --wait
npm run dev:api
npm run dev:demo
npx playwright install chromium
npm run test:browser
npm audit
```

Build shared packages before starting consumers. Root build order: protocol, Node gateway, SDK, hosted service; build the Next site separately.

Python setup in a virtual environment:

```text
python -m venv .venv
<venv-python> -m pip install -e ./adapters/django[demo]
<venv-python> examples/django-demo/manage.py migrate
<venv-python> examples/django-demo/manage.py runserver 127.0.0.1:8000 --noreload
<venv-python> -m unittest discover -s adapters/django/tests
```

Document exact Windows PowerShell executable paths, and differences for Bash and Unix environments. Do not assume the IDE's shell is PowerShell just because the OS is Windows. Quote absolute executable paths when launching Python from a Windows command shell. Do not alter a user's global Node/npm/registry settings unnecessarily or disable TLS checks to solve installation problems.

Generate schemas from TypeScript with an export script; include them in Python package data. Test `npm pack` for publishable packages and Python wheel creation. Local tarball installation must include protocol dependency resolution. Do not publish to npm/PyPI without explicit authorization and registry-name checks.

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

### 13.3 Real-browser acceptance for BOTH gateways

Use Playwright with a self-started test-only API, Next demo and optionally Django. Tests can use the MemoryStore to remain independent of Docker, but must clearly state that they do not prove PostgreSQL behavior.

For Node and Django separately:

1. Log in using generated demo credentials without embedding them in test source.
2. Confirm initial summary is $104,000.
3. Send the standard budget request.
4. Confirm a proposed action plan appears and no values change before approval.
5. Approve and observe SPA navigation to assumptions.
6. Verify normal React state changes—not merely assigned input DOM properties.
7. Confirm return to summary with $70,000.
8. Reopen assumptions and verify 500 hours, 100 rate, 20,000 QA persisted in app state.
9. Verify browser fetch/XHR uses only its client origin, not Ghost/model endpoints.
10. Verify response lacks Brain/tool internals/canary and private Brain URL is 404.
11. Verify unauthenticated gateway call is 401.

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
3. Implement provider interface/mock and authenticated PostgreSQL-backed run API.
4. Implement Node/Django gateways and private local-tool continuation.
5. Implement framework-neutral SDK and standard-control execution with approval.
6. Build independent Phoenix demo and isolated integration module.
7. Add Node/Django/provider tests and both-gateway browser acceptance.
8. Add provider configuration/live smoke and local shim.
9. Finish package distribution, containers, GCP foundation and detailed guides.
10. Run builds/tests/audits, fix relevant issues, record verified results and gaps.

At completion summarize files/packages implemented, exact checks passed, checks not run and why, how to start the demo, where keys belong, and remaining production work. Do not dump secrets, claim deployment without evidence, or imply that a generic input engine works on every possible web widget with zero integration.

**Build the project now using these instructions. Ask only when an essential decision cannot be safely inferred. Preserve the mandatory gateway-only topology, private Brain ownership, hybrid native-control/custom-adapter approach, both customer backend adapters, and honest production-readiness boundary.**