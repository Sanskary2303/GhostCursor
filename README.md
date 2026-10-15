# 👻 Ghost Cursor

**AI-Powered Chatbot on Steroids — Chat, Navigate, and Act on Behalf of Your Users**

Ghost Cursor is a plug-and-play SaaS platform that transforms any website's chat experience from a passive Q&A bot into an active, intelligent co-pilot. It doesn't just tell users *how* to do something — it **does it for them**: navigating pages, filling forms, triggering actions, running guided tours, and asking smart clarifying questions along the way.

Any customer — e-commerce, streaming platforms, fintech dashboards, SaaS products — can integrate Ghost Cursor with **minimal code changes** using our Frontend SDK and Backend SDK.

> [!NOTE]
> **Hackathon Build** — This prototype is built for the Google AI Hackathon. It targets a clean, working demo with max 5 concurrent users, a Python/GCP stack, and a fully functional demo customer app that showcases every feature.

---

## Table of Contents

- [What It Does](#what-it-does)
- [Demo Customer App](#demo-customer-app)
- [High-Level Architecture](#high-level-architecture)
- [System Architecture — Deep Dive](#system-architecture--deep-dive)
  - [Frontend Layer](#1-frontend-layer-customer-side)
  - [Backend Layer](#2-backend-layer-ghost-cursor-managed)
  - [Communication Protocol](#3-communication-protocol-fe--be)
- [Integration Model](#integration-model)
  - [Frontend SDK](#frontend-sdk-ghostcursorjs)
  - [Backend SDK](#backend-sdk-ghost_cursor-python)
  - [Minimal Customer Code Changes](#minimal-customer-code-changes)
- [Infrastructure & Deployment](#infrastructure--deployment)
  - [GCP Architecture](#gcp-architecture)
  - [Multi-Tenancy](#multi-tenancy-strategy)
  - [Data Flow & Security](#data-flow--security)
- [Core Features — Technical Breakdown](#core-features--technical-breakdown)
- [Tech Stack](#tech-stack)
- [Decision Log](#decision-log)
- [Demo Script — Feature Showcase](#demo-script--feature-showcase)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Roadmap](#roadmap)

---

## What It Does

| Feature | Description | Demo Scenario |
|---|---|---|
| 🖥️ **Screen-Aware Guidance** | Understands the exact page and values the user is on — context-aware responses, not generic answers | User asks "what is this page?" on any page of the demo app, and Ghost Cursor describes exactly what they see |
| 🎯 **AI Cursor Auto-Actions** | Navigates and fills the right inputs where users struggle — clicks buttons, fills forms, scrolls to elements | User says "add the blue sneakers to my cart" and watches the ghost cursor navigate to the product, select size, and click Add to Cart |
| 📊 **ROI Sensitivity Insight** | Shows which assumptions push ROI up or down — data-driven backend tools for business intelligence | User asks "how does free shipping affect my margins?" and gets an interactive sensitivity analysis |
| ❓ **Smart Clarifying Questions** | Asks for missing inputs if needed, then completes the step — never makes wrong assumptions | User says "checkout" but has no shipping address — Ghost Cursor asks for it before proceeding |
| 🎬 **Guided Explainers** | Highlights and narrates what changed, like an in-app tour — step-by-step visual walkthroughs | User asks "how do I track my order?" and gets a guided tour highlighting each step |

---

## Demo Customer App

To showcase Ghost Cursor's capabilities for the hackathon, we're building **ShopHive** — a demo e-commerce storefront that acts as our "customer" who has integrated Ghost Cursor.

```
┌────────────────────────────────────────────────────────────┐
│                     SHOPHIVE (Demo App)                     │
│               "An online sneaker store"                     │
│                                                            │
│  Pages:                                                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │  Homepage    │ │  Product     │ │  Cart        │       │
│  │  (catalog    │ │  Detail      │ │  (items,     │       │
│  │   grid)     │ │  (images,    │ │   totals,    │       │
│  │             │ │   size pick, │ │   promo      │       │
│  │             │ │   add-to-    │ │   code)      │       │
│  │             │ │   cart)      │ │              │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │  Checkout    │ │  Order       │ │  Settings /  │       │
│  │  (shipping,  │ │  Tracking    │ │  Profile     │       │
│  │   payment,   │ │  (status,    │ │  (notifs,    │       │
│  │   confirm)   │ │   timeline)  │ │   address,   │       │
│  │             │ │              │ │   prefs)     │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                            │
│  ┌──────────────────────────────────────────────────┐      │
│  │  👻 Ghost Cursor Widget (bottom-right)           │      │
│  │  Integrated via: <GhostCursor endpoint="..." />  │      │
│  └──────────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────┘
```

### Why an E-Commerce Demo?

- **Universal understanding** — judges and audience instantly "get" an online store
- **Rich interaction surface** — navigation, forms, multi-step flows (checkout), settings
- **Every feature gets a natural demo** — no contrived scenarios
- **Visual impact** — animated cursor adding items to cart is instantly impressive

### Demo Feature Mapping

| Feature | ShopHive Demo Scenario | Wow Factor |
|---|---|---|
| **Screen-Aware Guidance** | On product page: "What sizes are available?" → AI reads the actual size options from the page and responds | AI knows what's on screen without any pre-programming |
| **AI Cursor Auto-Actions** | "Add the Air Max 90 in size 10 to my cart" → Ghost cursor navigates to product, selects size 10, clicks Add to Cart | User watches an AI control their browser in real-time |
| **ROI Sensitivity Insight** | "What if I offer 20% off sitewide?" → Shows margin impact, break-even volume, revenue sensitivity chart | Business intelligence from a chat bubble |
| **Smart Clarifying Questions** | "I want to checkout" (no address saved) → "Where should we ship? Pick from saved addresses or enter new" → then proceeds | Doesn't blindly fail — asks what it needs |
| **Guided Explainers** | "How do I track my order?" → Step-by-step tour highlighting Orders page → order row → status timeline → tracking link | Like a human walking you through the app |

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                     SHOPHIVE (Demo Customer App)                     │
│                                                                      │
│  ┌──────────┐    ┌───────────────┐    ┌───────────┐                 │
│  │          │    │  Action       │───▶│ AI Cursor │  (animated      │
│  │  User    │───▶│  Executor     │    └───────────┘   pointer)      │
│  │          │    │               │    ┌─────────────┐               │
│  └──────────┘    │               │───▶│ Tour Overlay│  (highlights  │
│       │          │               │    └─────────────┘   & tooltips) │
│       │          └───────┬───────┘    ┌─────────────┐               │
│       │                  │       └───▶│ App State   │               │
│       ▼                  │            │             │               │
│  ┌──────────┐            │            └──────┬──────┘               │
│  │ Chat UI  │────────────┘                   │                      │
│  │ (Widget) │                          ┌─────▼──────┐               │
│  └────┬─────┘                          │  Context   │               │
│       │           FRONTEND SDK         │  Provider  │               │
│───────┼──────────(@ghost-cursor/js)────┴────────────┼───────────────│
│       │                                              │               │
│       ▼                                              │               │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │       SHOPHIVE BACKEND (FastAPI — thin proxy)                │   │
│  │       ghost-cursor Python SDK (4 lines of integration)       │   │
│  └──────────────────────┬───────────────────────────────────────┘   │
└──────────────────────────┼──────────────────────────────────────────┘
                           │  Authenticated API calls
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│            GHOST CURSOR CLOUD (Our SaaS — GCP Cloud Run)            │
│                                                                      │
│  ┌─────────────────────────────┐    ┌──────────────────┐            │
│  │  Orchestrator / Agent       │───▶│ Gemini API       │            │
│  │  (Python / FastAPI)         │    │ (Vertex AI)      │            │
│  │                             │    └──────────────────┘            │
│  │  - Session management       │    ┌──────────────────┐            │
│  │  - Intent classification    │───▶│ Backend Tools    │            │
│  │  - Action planning          │    │ ROI calc, data   │            │
│  │  - Tool orchestration       │    │ APIs, analytics  │            │
│  │  - Conversation memory      │    └──────────────────┘            │
│  └─────────────────────────────┘    ┌──────────────────┐            │
│                                     │ Firestore        │            │
│                                     │ (tenant config,  │            │
│                                     │  sessions, logs) │            │
│                                     └──────────────────┘            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## System Architecture — Deep Dive

### 1. Frontend Layer (Customer Side)

The Frontend SDK (`@ghost-cursor/js`) is a lightweight JavaScript/TypeScript package that the customer drops into their web app. It contains **zero AI logic** — it is purely an executor and renderer.

#### Components

| Component | Responsibility |
|---|---|
| **Chat UI Widget** | Floating chat bubble/panel. Renders messages, input box, quick-reply buttons. Communicates with the backend via WebSocket. Fully themeable to match the customer's brand. |
| **Action Executor** | Receives action commands from the backend (e.g., `click("#submit-btn")`, `fill("#email", "user@example.com")`, `navigate("/settings")`). Executes them against the live DOM. |
| **AI Cursor** | A visual animated cursor element that moves across the screen to show the user what the AI is doing. CSS-animated, non-intrusive. |
| **Tour Overlay** | Renders spotlight highlights, tooltips, and step-by-step narration overlays. Used for the Guided Explainers feature. |
| **Context Provider** | Reads the current page state — URL, visible elements, form values, page title, active modals — and sends this context snapshot to the backend so the AI knows *where* the user is. |

#### Context Provider — How Screen-Awareness Works

```
┌──────────────────────────────────────┐
│        Customer's Web Page           │
│                                      │
│  ┌─ Context Provider scans: ──────┐  │
│  │ • Current URL & route params   │  │
│  │ • Page title & meta            │  │
│  │ • Visible interactive elements │  │
│  │   (buttons, inputs, links)     │  │
│  │ • Form field values            │  │
│  │ • Active modals / drawers      │  │
│  │ • Error messages on screen     │  │
│  │ • User's scroll position       │  │
│  └────────────────────────────────┘  │
│               │                      │
│               ▼                      │
│   Serialized as lightweight JSON     │
│   snapshot → sent to backend         │
└──────────────────────────────────────┘
```

The Context Provider uses **MutationObserver** and **IntersectionObserver** to efficiently track DOM changes without polling. It generates a page context snapshot on every meaningful state change (route change, modal open, form interaction). Customers can configure which selectors to include/exclude for privacy.

---

### 2. Backend Layer (Ghost Cursor Cloud — Our SaaS)

Fully managed by us. Deployed on **GCP Cloud Run** — zero cluster management, auto-scales to zero when idle, scales up for the hackathon demo.

#### Components

| Component | Responsibility | GCP Service |
|---|---|---|
| **API Gateway** | Rate limiting, tenant identification (API key), request routing | Cloud Run (built into the FastAPI app) |
| **Orchestrator / Agent** | Google Agent Development Kit (ADK) multi-turn agentic loop. Receives user messages + page context. Plans and executes actions with Gemini 2.0. | Cloud Run (Python 3.12 / FastAPI + Google ADK) |
| **LLM Gateway** | Abstraction over Gemini models via Vertex AI (Gemini 2.0 Flash / Pro). Prompt management, token budgeting, response streaming. | Vertex AI (Gemini 2.0 Flash / Pro) |
| **Backend Tools** | Customer-registered read-only tools executed via Gateway Loopback (Reverse-Dispatch) under authentic user session (`X-Ghost-Subject`). | Executed on Customer Backend via SDK |
| **Session & Run State Store** | Ephemeral multi-turn run state, revision tracking, and event deduplication (TTL 30m). Persistent chat history is customer-owned in customer DB. | Firestore / Cloud SQL (PostgreSQL 17) |
| **Tenant Configuration** | Per-customer settings: branding, allowed actions, registered backend tool declarations, page schemas. | Firestore / Cloud SQL |
| **Logging & Monitoring** | Structured run interaction tracking, error logging, performance metrics. | Cloud Logging + Cloud Monitoring |

#### Orchestrator Agent — Decision Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR AGENT LOOP                       │
│                                                                  │
│  User Message + Page Context Snapshot                            │
│           │                                                      │
│           ▼                                                      │
│  ┌─────────────────┐                                            │
│  │ Google ADK Agent│                                            │
│  │ (Gemini 2.0)    │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┼─────┬──────────┬──────────┬───────────┐             │
│     ▼     ▼     ▼          ▼          ▼           ▼             │
│  [Chat] [Act] [Tour]  [Clarify]  [Tool Call]  [Multi-Step]     │
│     │     │     │          │          │           │             │
│     ▼     ▼     ▼          ▼          ▼           ▼             │
│  Text   Action  Tour     Question   Customer    Plan +         │
│  Reply  Commands Sequence  to User   Tool Loop   Sub-steps      │
│           │     │          │          │           │             │
│           └─────┴──────────┴──────────┴───────────┘             │
│                        │                                         │
│                        ▼                                         │
│               Response to Frontend                               │
│               (via WebSocket / HTTP)                             │
└─────────────────────────────────────────────────────────────────┘
```

#### Agent Response Types

```json
// Type 1: Text reply (Screen-Aware Guidance)
{
  "type": "message",
  "content": "You're on the Air Max 90 product page. Available sizes: 8, 9, 10, 11. The price is $129.99."
}

// Type 2: UI Action tool call (AI Cursor Auto-Actions with Element Targeting Cascade)
{
  "type": "action",
  "steps": [
    { "tool": "navigate", "parameters": { "target_page": "products/air-max-90" } },
    { "tool": "click", "parameters": { "target_id": "product.size.10" } },
    { "tool": "click", "parameters": { "target_id": "product.add_to_cart_btn" } }
  ]
}

// Type 3: Clarifying question (Smart Clarifying Questions)
{
  "type": "clarify",
  "question": "Which shipping address should I use?",
  "options": ["123 Main St, NYC (saved)", "Enter a new address"]
}

// Type 4: Guided tour (Guided Explainers)
{
  "type": "tour",
  "steps": [
    { "target_id": "nav.orders", "message": "First, click on Orders in the sidebar", "spotlight": true },
    { "target_id": "orders.recent_item", "message": "Here's your most recent order", "spotlight": true },
    { "target_id": "orders.tracking_link", "message": "Click this link to see real-time tracking", "spotlight": true }
  ]
}

// Type 5: Tool result (ROI Sensitivity Insight)
{
  "type": "tool_result",
  "tool": "roi_calculator",
  "data": {
    "scenario": "20% sitewide discount",
    "currentMargin": "35%",
    "projectedMargin": "15%",
    "breakEvenVolume": "+133% more orders needed",
    "sensitivity": [
      { "factor": "Discount %", "impact": "high", "direction": "negative" },
      { "factor": "Order Volume", "impact": "high", "direction": "positive" },
      { "factor": "Avg Order Value", "impact": "medium", "direction": "positive" }
    ]
  },
  "display": "card"
}
```

---

### 3. Communication Protocol (FE ↔ BE)

```
┌──────────────┐        WebSocket (ws://)         ┌──────────────────┐
│              │ ──────────────────────────────▶   │                  │
│  Frontend    │    { message, pageContext }        │  Customer's      │
│  SDK         │ ◀──────────────────────────────   │  Backend         │
│              │    { response, actions }           │  (thin proxy)    │
└──────────────┘                                   └───────┬──────────┘
                                                           │
                                                    REST API (HTTPS)
                                                    + API Key auth
                                                           │
                                                   ┌───────▼──────────┐
                                                   │  Ghost Cursor    │
                                                   │  Cloud (GCP)     │
                                                   └──────────────────┘
```

| Decision | Choice | Rationale |
|---|---|---|
| **FE ↔ Customer Backend** | WebSocket | Real-time bidirectional comms for streaming responses and action sequences |
| **Customer Backend ↔ Ghost Cursor Cloud** | REST over HTTPS + SSE streaming | Simple proxy. Streamed responses via SSE for real-time feel |
| **Authentication** | API Key in header | Dead simple for hackathon. One key per tenant |
| **Payload format** | JSON | Universal, debuggable |

---

## Integration Model

### Frontend SDK (`@ghost-cursor/js`)

**Install:**

```bash
npm install @ghost-cursor/js
```

**React Integration (5 lines):**

```jsx
import { GhostCursor } from '@ghost-cursor/js/react';

function App() {
  return (
    <>
      <YourExistingApp />
      <GhostCursor endpoint="/api/ghost-cursor" theme="auto" />
    </>
  );
}
```

**Vanilla JS (3 lines):**

```html
<script src="https://cdn.ghostcursor.ai/sdk/v1/ghost-cursor.min.js"></script>
<script>
  GhostCursor.init({ endpoint: '/api/ghost-cursor', theme: 'auto' });
</script>
```

**Advanced Config:**

```jsx
<GhostCursor
  endpoint="/api/ghost-cursor"
  theme={{ primaryColor: '#FF6B00', position: 'bottom-right' }}
  context={{ userId: currentUser.id, plan: currentUser.plan }}
  permissions={{
    canNavigate: true,
    canFillForms: true,
    canClick: true,
    requireConfirmation: true,   // ask user before executing
  }}
  selectors={{
    exclude: ['.sensitive-data', '#credit-card-form'],
  }}
/>
```

### Backend SDK (`ghost_cursor` Python)

The Backend SDK is a lightweight Python package that customers install on **their own backend**. It acts as a secure proxy — validating requests, attaching tenant credentials, and forwarding to Ghost Cursor Cloud.

**Why proxy through the customer's backend?**
1. **Security**: API keys never exposed to the browser
2. **Auth integration**: Customer validates their own user sessions before proxying
3. **Custom context**: Customer can inject server-side data (user profile, subscription tier)

**Install:**

```bash
pip install ghost-cursor
```

**FastAPI Integration (6 lines):**

```python
from ghost_cursor import GhostCursorProxy

ghost = GhostCursorProxy(
    api_key=os.environ["GHOST_CURSOR_API_KEY"],
    tenant_id=os.environ["GHOST_CURSOR_TENANT_ID"],
)

@app.websocket("/api/ghost-cursor")
async def ghost_cursor_ws(websocket: WebSocket):
    await ghost.handle_websocket(websocket)
```

**Flask Integration:**

```python
from ghost_cursor.flask import ghost_cursor_blueprint

app.register_blueprint(ghost_cursor_blueprint(
    api_key=os.environ["GHOST_CURSOR_API_KEY"],
    tenant_id=os.environ["GHOST_CURSOR_TENANT_ID"],
), url_prefix="/api/ghost-cursor")
```

**Django Integration:**

```python
# settings.py
GHOST_CURSOR_API_KEY = os.environ["GHOST_CURSOR_API_KEY"]
GHOST_CURSOR_TENANT_ID = os.environ["GHOST_CURSOR_TENANT_ID"]

# urls.py
from ghost_cursor.django import ghost_cursor_urls
urlpatterns += ghost_cursor_urls("/api/ghost-cursor/")
```

### Minimal Customer Code Changes

| Area | Changes Required | Lines of Code |
|---|---|---|
| Frontend | Import SDK + add one component | ~5 lines |
| Backend | Install SDK + add proxy route | ~6 lines |
| Config | Set environment variables | 2 env vars |
| **Total** | | **~11 lines + 2 env vars** |

---

## Infrastructure & Deployment

> [!IMPORTANT]
> **Hackathon Prototype** — Optimized for simplicity and speed of deployment. No Kubernetes, no cluster management. Everything runs on GCP managed services that scale to zero and cost nearly nothing when idle.

### GCP Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        GCP PROJECT: ghost-cursor                     │
│                                                                      │
│  ┌─────────────────────────────────┐                                │
│  │  Cloud Storage (GCS Bucket)     │  ← Hosts Frontend SDK bundle   │
│  │  + Cloud CDN                    │    (ghost-cursor.min.js)        │
│  └────────────────┬────────────────┘                                │
│                   │                                                  │
│  ┌────────────────▼────────────────┐                                │
│  │  Cloud Run — "ghost-cursor-api" │  ← Orchestrator + Agent        │
│  │                                 │                                │
│  │  Python 3.12 / FastAPI          │                                │
│  │  - Agent loop                   │                                │
│  │  - WebSocket support            │                                │
│  │  - Tool execution               │                                │
│  │  - Session management           │                                │
│  │                                 │                                │
│  │  Scaling: min=0, max=2          │                                │
│  │  Memory: 1 GB                   │                                │
│  │  CPU: 1 vCPU                    │                                │
│  │  Concurrency: 5                 │                                │
│  └────────────────┬────────────────┘                                │
│                   │                                                  │
│         ┌─────────┼──────────┐                                      │
│         ▼         ▼          ▼                                      │
│  ┌─────────┐ ┌─────────┐ ┌─────────────┐                           │
│  │ Vertex  │ │Firestore│ │ Cloud       │                           │
│  │ AI      │ │/ Cloud  │ │ Logging     │                           │
│  │         │ │  SQL    │ │             │                           │
│  │ Gemini  │ │         │ │ Structured  │                           │
│  │ 2.0     │ │Runs     │ │ logs for    │                           │
│  │ Flash / │ │Tenants  │ │ debugging   │                           │
│  │ Pro     │ │Configs  │ │ & analytics │                           │
│  └─────────┘ └─────────┘ └─────────────┘                           │
│                                                                      │
│  ┌─────────────────────────────────┐                                │
│  │  Cloud Run — "shophive-demo"    │  ← Demo Customer App           │
│  │                                 │                                │
│  │  React Frontend (static)        │                                │
│  │  + FastAPI Backend (proxy)      │                                │
│  │  + Customer DB (Chat History)   │                                │
│  │  + Ghost Cursor SDK integrated  │                                │
│  │                                 │                                │
│  │  Scaling: min=0, max=1          │                                │
│  └─────────────────────────────────┘                                │
└──────────────────────────────────────────────────────────────────────┘
```

### GCP Services Used

| Service | Purpose | Why This Over Alternatives |
|---|---|---|
| **Cloud Run** | Hosts both the Ghost Cursor API and the ShopHive demo app | Zero cluster management, scales to zero (free when idle), built-in HTTPS, WebSocket support, deploy with a single `gcloud run deploy` command |
| **Vertex AI (Gemini)** | LLM for intent classification, action planning, conversation | Google's own AI — perfect for a Google hackathon. Gemini 2.0 Flash for speed, Pro for complex reasoning. Native GCP integration = no API key management hassles |
| **Firestore / Cloud SQL (PostgreSQL 17)** | Ephemeral multi-turn run state, event deduplication, tenant config | Ephemeral run storage with 30-minute TTL. Persistent chat histories are maintained in the customer's own database |
| **Cloud Storage + Cloud CDN** | Hosts and serves the Frontend SDK JS bundle | Global low-latency delivery. GCS is dirt cheap for static files |
| **Cloud Logging** | Structured logging for debugging and analytics | Automatic integration with Cloud Run — zero setup. Queryable logs |
| **Cloud Monitoring** | Uptime checks, latency dashboards, error alerting | Automatic Cloud Run metrics. Set up a basic dashboard for the demo |
| **Secret Manager** | Stores API keys, tenant secrets | Secure, auto-rotatable. Cloud Run native integration via env vars |
| **Artifact Registry** | Stores Docker images for Cloud Run deployments | GCP-native container registry. Faster pulls than Docker Hub |

### Why NOT These Services (For Prototype)

| Skipped Service | Reason |
|---|---|
| ~~GKE (Kubernetes)~~ | Overkill for 5 users. Cloud Run gives us containers without cluster management |
| ~~Centralized Customer Chat DB~~ | Anti-pattern for enterprise SaaS. Customer stores persistent chat history in their own database for GDPR/data sovereignty |
| ~~Pub/Sub~~ | No async event streaming needed at prototype scale. Direct function calls suffice |
| ~~Memorystore (Redis)~~ | No caching layer needed at 5-user scale. Firestore / in-memory latency (~50ms) is fine |
| ~~Cloud Tasks~~ | No background job queue needed. Everything runs synchronously in the agent loop |
| ~~Cloud Armor~~ | WAF/DDoS protection unnecessary for hackathon demo |

### Deployment Flow

```
┌──────────────────────────────────────────────────┐
│              DEPLOYMENT (one command each)         │
│                                                    │
│  Ghost Cursor API:                                 │
│  $ gcloud run deploy ghost-cursor-api \            │
│      --source ./services/orchestrator \            │
│      --region us-central1 \                        │
│      --set-env-vars "GCP_PROJECT=ghost-cursor"     │
│                                                    │
│  ShopHive Demo:                                    │
│  $ gcloud run deploy shophive-demo \               │
│      --source ./demo/shophive \                    │
│      --region us-central1                          │
│                                                    │
│  Frontend SDK:                                     │
│  $ gsutil cp dist/ghost-cursor.min.js \            │
│      gs://ghost-cursor-sdk/v1/                     │
│                                                    │
│  That's it. Three commands. Done. 🚀               │
└──────────────────────────────────────────────────┘
```

### Estimated GCP Costs (Hackathon)

| Service | Estimated Cost | Notes |
|---|---|---|
| Cloud Run | ~\$0 | Free tier: 2M requests/month, 360K vCPU-sec. Prototype won't come close |
| Vertex AI (Gemini) | ~\$5-15 | Pay per token. Flash is cheap (~\$0.075/1M input tokens). Demo = ~1K conversations |
| Firestore / Cloud SQL | ~\$0 | Free tier: 50K reads, 20K writes, 20K deletes per day |
| Cloud Storage | ~\$0.01 | Hosting a single JS file |
| **Total** | **~\$5-15** | Almost entirely LLM costs |

### Multi-Tenancy & Data Sovereignty Strategy

> [!NOTE]
> Ghost Cursor enforces strict **customer data sovereignty**: persistent chat histories, messages, and transcripts remain inside the customer's own database via Backend SDK schema adapters. Ghost Cursor Cloud holds only ephemeral multi-turn run states (auto-expired after 30 minutes) and tenant configuration.

```text
Ghost Cursor Cloud (Ephemeral Run Store):
────────────────────────────────────────
tenants/
  └── {tenant_id}/
        ├── config          ← branding, allowed actions, backend tool schemas
        └── runs/
              └── {run_id}/ ← ephemeral state machine (TTL: 30 minutes)
                    ├── revision (optimistic locking)
                    ├── deduplication (event hashes)
                    └── status (awaiting_actions, completed, etc.)

Customer Database (Customer Data Sovereignty):
─────────────────────────────────────────────
ghost_chat_sessions (session_id, user_id, title, summary, created_at)
ghost_chat_messages (message_id, session_id, role, content, tool_calls, client_actions)
```

### Data Flow & Security

```
┌─────────────────────────────────────────────────────────────────┐
│                     SECURITY MODEL                               │
│                                                                  │
│  Browser ──(HTTPS/WSS)──▶ Customer Backend ──(HTTPS)──▶ Ghost   │
│                              │                          Cursor   │
│                              │                          Cloud    │
│                                                                  │
│  1. Frontend SDK:            No API keys in browser              │
│     → Configurable selector exclusions (PII)                     │
│     → Shadow DOM sandboxing for CSS isolation                    │
│                                                                  │
│  2. Customer Backend:        Validates user session              │
│     → Attaches API key from Secret Manager                       │
│     → Can filter/redact sensitive data                           │
│                                                                  │
│  3. Ghost Cursor Cloud:      API key + tenant auth               │
│     → All traffic over HTTPS/TLS 1.3                             │
│     → Firestore encryption at rest (Google-managed keys)         │
│     → Cloud Run: no SSH, no persistent disk, ephemeral           │
│     → IAM: principle of least privilege                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Features — Technical Breakdown

### 1. Screen-Aware Guidance

**How it works:**
1. Context Provider (FE SDK) scans the live DOM → generates a lightweight page context snapshot
2. Snapshot sent with every user message to the Orchestrator
3. Orchestrator includes context in the Gemini prompt → AI understands *exactly* where the user is
4. Response is tailored to the current screen, not generic documentation

**ShopHive Demo:**
- User is on the Air Max 90 product page
- User asks: "What colors are available?"
- Context Provider sends: `{ url: "/products/air-max-90", elements: [{ type: "color-picker", options: ["Black", "White", "Red"] }] }`
- Gemini responds: "The Air Max 90 comes in Black, White, and Red. Want me to select one?"

**Technical details:**
- Context snapshot is ~2-5 KB JSON
- Uses `MutationObserver` for reactive DOM tracking (no polling)
- Sensitive fields (password, credit card) auto-excluded

### 2. AI Cursor Auto-Actions

**How it works:**
1. User says "Add the blue sneakers to my cart"
2. Orchestrator uses Gemini to plan a multi-step action sequence
3. Action commands sent to FE SDK's Action Executor
4. AI Cursor (animated ghost pointer) visually shows each step
5. User watches the cursor move and click — full transparency

**ShopHive Demo:**
```
User: "Add Air Max 90 size 10 to my cart"
Agent plans:
  1. navigate(target_page="products/air-max-90")
  2. click(target_id="product.size.10")
  3. click(target_id="product.add_to_cart_btn")
AI Cursor animates through each step. Cart counter updates. ✓
```

**Technical details:**
- Element targeting priority: `data-ghost-id` → `data-testid` → `id` → ARIA labels → CSS selector
- Built-in retry logic with fallback selectors
- `requireConfirmation` mode: user approves before execution
- Action timeout: 5s per step, then agent asks for help

### 3. ROI Sensitivity Insight

**How it works:**
1. Orchestrator detects a business/analytical intent
2. Calls the ROI Calculator tool with parameters extracted from the message
3. Tool computes sensitivity analysis
4. Results rendered as a structured card in the chat UI

**ShopHive Demo:**
```
User: "What if I offer free shipping on orders over $50?"
Tool calculates:
  - Current avg shipping cost: $8.50/order
  - % of orders over $50: 62%
  - Margin impact: -3.2%
  - Break-even: need 12% more orders
  - Sensitivity: shipping cost is the #1 factor
Rendered as an interactive card with sliders
```

### 4. Smart Clarifying Questions

**How it works:**
1. User says "Checkout now"
2. Agent checks: shipping address? Payment method? Cart empty?
3. Missing info → asks a targeted question with quick-reply options
4. User answers → agent proceeds

**ShopHive Demo:**
```
User: "I want to checkout"
Agent detects: no shipping address on file
Agent: "Where should we ship your order?"
  [Use saved: 123 Main St]  [Enter new address]
User picks saved address
Agent: proceeds with checkout, auto-fills the form
```

### 5. Guided Explainers

**How it works:**
1. User asks "How do I track my order?"
2. Orchestrator generates a tour sequence with selectors and explanations
3. Tour Overlay renders spotlight highlights + tooltip narration
4. User steps through the tour (next/prev/skip)

**ShopHive Demo:**
```
User: "Show me how to find my orders"
Tour steps:
  1. Spotlight #orders-nav → "Click 'My Orders' in the sidebar"
  2. Spotlight .order-row:first → "Here's your most recent order — #ORD-2847"
  3. Spotlight .order-status → "This shows the current status: 'Shipped'"
  4. Spotlight .tracking-link → "Click here to see real-time tracking on the carrier's site"
```

---

## Tech Stack

### Frontend SDK (`@ghost-cursor/js`)

| Layer | Technology | Rationale |
|---|---|---|
| Language | TypeScript | Type safety, excellent DX |
| Chat UI | Preact (3KB) | React-compatible but tiny — keeps SDK lightweight |
| Styling | CSS-in-JS (vanilla-extract) | Zero-runtime, Shadow DOM friendly |
| DOM Actions | Custom execution engine | In-browser DOM manipulation, not headless |
| AI Cursor | CSS transforms + Web Animations API | Smooth 60fps, GPU-accelerated |
| Tour Engine | Custom (inspired by Shepherd.js) | Lightweight, headless, controllable |
| Bundler | Vite + Rollup | Fast dev, tree-shakeable production builds |

### Ghost Cursor Backend (Our SaaS)

| Layer | Technology | Rationale |
|---|---|---|
| Language | Python 3.12 | Fast development, rich AI/ML ecosystem, team expertise |
| Framework | FastAPI | Async-native, WebSocket support, auto-generated OpenAPI docs, fast |
| LLM | Vertex AI — Gemini 2.0 Flash / Pro | Google's own LLM — native GCP integration, great for Google hackathon, competitive quality |
| Agent Framework | Google Agent Development Kit (ADK) | Native Gemini 2.0 tool-calling, typed function declarations, structured multi-turn agentic loop |
| Database | Firestore / Cloud SQL (PostgreSQL 17) | Ephemeral run state, deduplication, tenant configs (30-minute TTL). Chat history is customer-owned in customer DB |
| Hosting | Cloud Run | Zero cluster management, auto-scale, single deploy command |
| Logging | Cloud Logging | Automatic Cloud Run integration |
| Secrets | Secret Manager | Secure, auto-integrated with Cloud Run env vars |

### ShopHive Demo App

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React 18 + Vite + TailwindCSS | Fast to build, looks professional, component library ecosystem |
| Backend | FastAPI (Python) | Same language as Ghost Cursor backend — fewer context switches. Serves as the "customer backend" with Ghost Cursor SDK integrated |
| Data | SQLite / PostgreSQL + JSON | Customer database stores chat history via SDK migrations; mock product catalog |
| Hosting | Cloud Run | Single container: serves React build + FastAPI API |

---

## Decision Log

### D-001: Python Over Java/Spring Boot for Backend

| Aspect | Detail |
|---|---|
| **Decision** | Use Python 3.12 with FastAPI for the Ghost Cursor orchestrator backend |
| **Context** | Hackathon prototype needing rapid development with the best AI/ML ecosystem |
| **Alternatives** | Spring Boot/Kotlin (production-grade but slower to develop), Node.js (good but weaker AI libs), Go (fast but minimal AI ecosystem) |
| **Trade-offs** | Python's GIL limits true CPU parallelism (mitigated by async I/O — our workload is I/O-bound anyway: waiting on LLM responses, DB calls). Slightly higher memory than Go. But gains: fastest development speed, best AI library ecosystem (Google ADK, google-genai), team expertise, rapid prototyping |
| **Status** | ✅ Accepted |

### D-002: GCP Cloud Run Over GKE

| Aspect | Detail |
|---|---|
| **Decision** | Deploy everything on Cloud Run instead of GKE (Kubernetes) |
| **Context** | Hackathon prototype with max 5 concurrent users. Zero time budget for cluster management |
| **Alternatives** | GKE Autopilot (managed K8s — still overkill), Compute Engine VMs (more control but manual ops), Cloud Functions (no WebSocket support) |
| **Trade-offs** | Cloud Run has a 60-min request timeout (fine for WebSocket sessions under an hour). Limited to 1000 concurrent requests per instance (we need 5). Cold starts of ~2-3s on first request after scale-to-zero. But gains: zero ops, deploy in one command, scales to zero = free when idle, built-in HTTPS |
| **Status** | ✅ Accepted |

### D-003: Vertex AI Gemini Over OpenAI

| Aspect | Detail |
|---|---|
| **Decision** | Use Vertex AI with Gemini 2.0 models as the primary (and only, for prototype) LLM provider |
| **Context** | Google AI Hackathon. Using Google's own AI is both strategic and practical |
| **Alternatives** | OpenAI GPT-4o (excellent but not Google-native), Anthropic Claude (great reasoning but adds vendor complexity), multi-provider (adds complexity for no prototype benefit) |
| **Trade-offs** | Gemini function calling has some quirks vs OpenAI's mature tooling. Smaller third-party ecosystem. But gains: native GCP integration (no separate API keys, uses service account), impresses hackathon judges, competitive quality (Gemini 2.0 Flash is fast + cheap), Vertex AI is SOC2/HIPAA compliant out of the box |
| **Status** | ✅ Accepted |

### D-004: Ephemeral Run Store & Customer Database Sovereignty

| Aspect | Detail |
|---|---|
| **Decision** | Ghost Cursor Cloud uses Firestore / Cloud SQL strictly for ephemeral run states (deduplication, optimistic concurrency, 30m TTL), while persistent chat histories are stored exclusively in the customer's own database |
| **Context** | Enterprise SaaS compliance (GDPR, SOC2, data sovereignty) mandates that customer conversation transcripts never sit unmanaged in a third-party cloud |
| **Alternatives** | Centralized multi-tenant chat database on Ghost Cursor Cloud (creates vendor lock-in, data sovereignty violations, and compliance liabilities) |
| **Trade-offs** | Requires customer backend SDK to run migrations and persist chat logs. Mitigated by SDK providing ready-made schemas (`ghost_chat_sessions`, `ghost_chat_messages`) and `SQLAlchemyChatStore` abstractions |
| **Status** | ✅ Accepted |

### D-005: Proxy Architecture (FE → Customer Backend → Ghost Cursor Cloud)

| Aspect | Detail |
|---|---|
| **Decision** | Frontend SDK communicates with the customer's own backend, which proxies to our cloud API. The FE SDK never calls Ghost Cursor's API directly |
| **Context** | Secure, realistic integration pattern that mirrors production SaaS |
| **Alternatives** | Direct FE → Ghost Cursor Cloud (simpler but exposes API keys in browser, unrealistic for production) |
| **Trade-offs** | Adds one network hop of latency (~10-30ms). Requires customers to add a backend route. But gains: security (no API keys in browser), realistic demo of how real customers would integrate, server-side context enrichment |
| **Status** | ✅ Accepted |

### D-006: Approval-First Action Execution

| Aspect | Detail |
|---|---|
| **Decision** | Enforce approval-first execution (`requireConfirmation: true`) — mutating or multi-step action sequences require explicit user confirmation ("Approve and Run") prior to execution |
| **Context** | Trust and safety. Automated actions without consent could perform unintended purchases or data mutations |
| **Alternatives** | Auto-execute everything (dangerous and scary), never confirm (unrealistic for SaaS transactions) |
| **Trade-offs** | Adds a confirmation step before execution. But gains: absolute user safety, auditability, prevents unintended cart checkout or sensitive field modification |
| **Status** | ✅ Accepted |

### D-007: Shadow DOM for Chat Widget

| Aspect | Detail |
|---|---|
| **Decision** | Render Chat UI and Tour Overlay inside Shadow DOM for CSS isolation |
| **Context** | SDK injects into customer's page — must not break their styles or be broken by them |
| **Alternatives** | iFrame (full isolation but no DOM access for AI Cursor), CSS namespacing (fragile) |
| **Trade-offs** | Shadow DOM has quirks (font inheritance, form participation). But gains: complete style isolation, no CSS conflicts. AI Cursor and Action Executor operate outside Shadow DOM on the real DOM |
| **Status** | ✅ Accepted |

### D-008: Single Cloud Run Service (Monolith for Prototype)

| Aspect | Detail |
|---|---|
| **Decision** | Deploy the Ghost Cursor backend as a single Cloud Run service (monolith), not microservices |
| **Context** | Prototype with 5 users. No need for service decomposition |
| **Alternatives** | Microservices (agent, gateway, tools as separate services — adds networking complexity, inter-service auth, deployment coordination) |
| **Trade-offs** | All code in one process — a bug in one module can crash everything. No independent scaling per component. But gains: one deploy command, one log stream, no inter-service latency, dramatically simpler debugging. Can decompose later if/when we hit scale issues |
| **Status** | ✅ Accepted |

### D-009: Element Targeting Cascade

| Aspect | Detail |
|---|---|
| **Decision** | Use a priority cascade: `data-ghost-id` → `data-testid` → `id` → ARIA labels → CSS selector → text content |
| **Context** | AI Cursor must reliably find DOM elements across different customer apps |
| **Alternatives** | CSS selectors only (fragile), XPath (verbose), visual/coordinate-based (heavy) |
| **Trade-offs** | More complex targeting logic. But gains: works out-of-the-box without customer changes, can be made more robust by customer adding `data-ghost-id` attributes |
| **Status** | ✅ Accepted |

### D-010: React for Demo App (ShopHive)

| Aspect | Detail |
|---|---|
| **Decision** | Build ShopHive demo in React + TailwindCSS |
| **Context** | Need a polished, professional-looking demo app fast |
| **Alternatives** | Next.js (SSR adds complexity), Vue (team less familiar), vanilla HTML (too slow to build, looks amateur) |
| **Trade-offs** | React adds a build step and bundle size. But gains: fastest development with component libraries, TailwindCSS for instant professional styling, easy Ghost Cursor React SDK integration |
| **Status** | ✅ Accepted |

### D-011: Gateway Loopback (Reverse-Dispatch) for Customer Backend Tools

| Aspect | Detail |
|---|---|
| **Decision** | Customer backend read-only tools are executed on the customer's own backend gateway via a cryptographically signed HMAC reverse-dispatch loop rather than direct inbound HTTP calls |
| **Context** | Customer internal databases and private microservices cannot be opened up to the public internet |
| **Alternatives** | Direct webhooks into customer private networks (requires opening firewall ports or VPNs) |
| **Trade-offs** | Requires turn coordination between Cloud Run orchestrator and customer gateway. But gains: zero firewall exposure, customer authorizes execution with active user session (`X-Ghost-Subject`), HMAC-SHA256 verification |
| **Status** | ✅ Accepted |

### D-012: Customer-Owned Chat History via SDK Abstraction

| Aspect | Detail |
|---|---|
| **Decision** | The Backend SDK provides ready-to-run database migrations and `SQLAlchemyChatStore` for the customer's database, while Ghost Cursor Cloud remains stateless regarding user chat logs |
| **Context** | Customers need out-of-the-box session management, multi-turn history replay, and auto-summarization without surrendering data privacy |
| **Alternatives** | Leave chat persistence entirely to the customer to code from scratch (high integration friction) |
| **Trade-offs** | Customer database must run standard SQL migration. But gains: immediate out-of-the-box session APIs, auto-summarization, and 100% compliance |
| **Status** | ✅ Accepted |

---

## Demo Script — Feature Showcase

> [!TIP]
> This is the planned demo flow for the hackathon presentation. Each step is designed to highlight a different Ghost Cursor feature with maximum visual impact.

### Act 1: "Meet ShopHive" (30 seconds)
- Show ShopHive homepage — a clean, modern sneaker store
- Point out the Ghost Cursor chat widget in the bottom-right corner
- "ShopHive integrated Ghost Cursor with just 11 lines of code. Let me show you what it can do."

### Act 2: Screen-Aware Guidance (45 seconds)
- Navigate to a product page (Air Max 90)
- Open Ghost Cursor chat
- Type: **"What am I looking at?"**
- Ghost Cursor responds with exact details from the page: product name, price, available sizes, colors
- Type: **"Is this on sale?"**
- Ghost Cursor reads the sale badge from the DOM and responds accurately
- **Key point**: "The AI sees exactly what the user sees — no pre-programming needed."

### Act 3: AI Cursor Auto-Actions (60 seconds) ⭐ *Hero Feature*
- Type: **"Add the Air Max 90 in size 10 to my cart"**
- ✨ Ghost cursor appears and **animates across the screen**:
  1. Moves to the size selector → clicks "10"
  2. Moves to the "Add to Cart" button → clicks it
  3. Cart counter animates from 0 → 1
- The user watches AI control their browser in real-time
- **Key point**: "The AI doesn't just tell you how — it does it for you."

### Act 4: Smart Clarifying Questions (45 seconds)
- Type: **"I want to checkout"**
- Ghost Cursor: "You have 1 item in your cart ($129.99). Where should I ship it?"
  - [123 Main St (saved)] [Enter new address]
- User picks saved address
- Ghost cursor auto-fills the checkout form
- **Key point**: "It asks only what it needs — no blind guessing."

### Act 5: Guided Explainers (45 seconds)
- Type: **"How do I track my order?"**
- Tour overlay activates:
  1. Spotlight on "My Orders" nav item → "Click here to see your orders"
  2. Spotlight on order row → "Here's your recent order #2847"
  3. Spotlight on tracking link → "Click to track on the carrier's site"
- User clicks through the tour
- **Key point**: "Like having a human guide walk you through the app."

### Act 6: ROI Sensitivity Insight (45 seconds)
- Switch to an "Admin" view of ShopHive
- Type: **"What happens to my margins if I offer 20% off sitewide?"**
- Ghost Cursor runs the ROI calculator tool
- Renders a card: margin impact (-18%), break-even volume (+133%), sensitivity factors
- **Key point**: "Not just a chatbot — a business intelligence co-pilot."

### Act 7: Integration Demo (30 seconds)
- Show the ShopHive codebase side-by-side
- Highlight the 5 lines in `App.jsx` (Frontend SDK)
- Highlight the 6 lines in `main.py` (Backend SDK)
- "That's it. 11 lines. Any website can do this."

### Total Demo Time: ~5 minutes

---

## Repository Structure

```
ghost-cursor/
├── packages/
│   └── sdk-frontend/               # @ghost-cursor/js — Frontend SDK
│       ├── src/
│       │   ├── core/
│       │   │   ├── chat-ui/         # Chat widget (Preact)
│       │   │   ├── executor/        # Action Executor
│       │   │   ├── cursor/          # AI Cursor animation
│       │   │   ├── tour/            # Tour Overlay engine
│       │   │   ├── context/         # Context Provider
│       │   │   └── transport/       # WebSocket client
│       │   └── react/               # React wrapper
│       ├── package.json
│       └── vite.config.ts
│
├── packages/
│   └── sdk-server-python/           # ghost-cursor — Python Backend SDK
│       ├── ghost_cursor/
│       │   ├── __init__.py
│       │   ├── proxy.py             # GhostCursorProxy class
│       │   ├── fastapi.py           # FastAPI integration
│       │   ├── flask.py             # Flask integration
│       │   └── django.py            # Django integration
│       ├── pyproject.toml
│       └── README.md
│
├── services/
│   └── orchestrator/                # Ghost Cursor Cloud Backend
│       ├── app/
│       │   ├── main.py              # FastAPI app entry point
│       │   ├── agent.py             # Google ADK agent definition & tools
│       │   ├── brain_loader.py      # Dynamic Brain resolver (platform.md + {page}.md)
│       │   ├── tools/
│       │   │   ├── frontend_actions.py # navigate, click, fill_input, tour, clarify
│       │   │   └── loopback.py      # Gateway loopback for customer tools
│       │   ├── llm/
│       │   │   └── vertex.py        # Vertex AI / Gemini 2.0 configuration
│       │   ├── models/
│       │   │   ├── run.py           # Multi-turn run state & revisions
│       │   │   └── contracts.py     # Protocol v1 schemas
│       │   └── storage/
│       │       └── run_store.py     # Ephemeral run storage & deduplication
│       ├── Dockerfile
│       ├── requirements.txt
│       └── cloudbuild.yaml
│
├── demo/
│   └── shophive/                    # Demo Customer App
│       ├── frontend/
│       │   ├── src/
│       │   │   ├── App.jsx
│       │   │   ├── pages/
│       │   │   │   ├── Home.jsx           # Product catalog grid
│       │   │   │   ├── ProductDetail.jsx  # Single product page
│       │   │   │   ├── Cart.jsx           # Shopping cart
│       │   │   │   ├── Checkout.jsx       # Checkout form
│       │   │   │   ├── OrderTracking.jsx  # Order status
│       │   │   │   └── Settings.jsx       # User settings
│       │   │   ├── components/
│       │   │   └── data/
│       │   │       └── products.json      # Mock product catalog
│       │   ├── package.json
│       │   └── vite.config.ts
│       ├── backend/
│       │   ├── main.py                    # FastAPI — serves React + proxy
│       │   └── requirements.txt
│       ├── Dockerfile
│       └── cloudbuild.yaml
│
├── infra/
│   ├── deploy.sh                    # One-script deployment to GCP
│   └── setup-gcp.sh                 # Initial GCP project setup
│
├── docs/
│   ├── integration-guide.md
│   └── demo-script.md
│
└── README.md                        # ← You are here
```

---

## Getting Started

### Prerequisites

```bash
# Install Google Cloud SDK
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud config set project ghost-cursor

# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  secretmanager.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com
```

### Local Development

```bash
# 1. Ghost Cursor Backend (Orchestrator)
cd services/orchestrator
python -m venv venv && source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080

# 2. Frontend SDK
cd packages/sdk-frontend
npm install
npm run dev    # starts dev server on :5173

# 3. ShopHive Demo App
cd demo/shophive/frontend
npm install
npm run dev    # starts React dev server on :3000

cd demo/shophive/backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8081
```

### Deploy to GCP (3 commands)

```bash
# Deploy Ghost Cursor API
gcloud run deploy ghost-cursor-api \
  --source ./services/orchestrator \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "GCP_PROJECT=ghost-cursor" \
  --max-instances 2 \
  --concurrency 5

# Deploy ShopHive Demo
gcloud run deploy shophive-demo \
  --source ./demo/shophive \
  --region us-central1 \
  --allow-unauthenticated

# Upload Frontend SDK to CDN
gsutil cp packages/sdk-frontend/dist/ghost-cursor.min.js \
  gs://ghost-cursor-sdk/v1/
```

---

## Roadmap

### ✅ Phase 0 — Hackathon Prototype (NOW)
- [ ] Frontend SDK core (Chat UI + Action Executor + AI Cursor + Tour Overlay)
- [ ] React wrapper (`<GhostCursor />`)
- [ ] Python Backend Orchestrator (FastAPI + Gemini via Vertex AI)
- [ ] Python Backend SDK (`ghost-cursor` package)
- [ ] Screen-Aware Guidance (Context Provider)
- [ ] AI Cursor Auto-Actions (click, fill, navigate, scroll)
- [ ] Smart Clarifying Questions
- [ ] Guided Explainers (Tour Overlay)
- [ ] Backend Tools
- [ ] ShopHive demo app (React + FastAPI)
- [ ] GCP deployment (Cloud Run + Firestore + Vertex AI)
- [ ] Demo script rehearsed and polished

### Phase 1 — Post-Hackathon MVP (Months 1-3)
- [ ] Customer onboarding dashboard (web UI)
- [ ] Multi-tenant API key management
- [ ] Conversation analytics dashboard
- [ ] Action undo/rollback
- [ ] Sandbox mode for safe testing
- [ ] Node.js Backend SDK
- [ ] Vue.js and vanilla JS wrappers
- [ ] Multi-LLM support (add OpenAI, Anthropic)

### Phase 2 — Production (Months 4-8)
- [ ] Multi-region deployment
- [ ] Rate limiting and abuse protection
- [ ] SOC2 compliance
- [ ] Enterprise tier: dedicated infra, BYOK encryption
- [ ] Angular and Svelte wrappers
- [ ] Java, PHP, Go, Ruby Backend SDKs
- [ ] A/B testing for AI responses
- [ ] Mobile SDK (React Native)

---

## License

Proprietary — © 2026 Ghost Cursor. All rights reserved.

---

<p align="center">
  <b>Ghost Cursor</b> — Your users don't need to figure things out. The AI just does it. 👻
</p>
