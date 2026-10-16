# @ghost-cursor/server

Dependency-free Node.js gateway SDK for Ghost Cursor Cloud.

## Installation

```bash
npm install @ghost-cursor/server
```

## Express Integration

The integrating route must apply the app's own authentication, CSRF protection, and body limit before calling `gateway.handle`:

```ts
import express from "express";
import { Gateway } from "@ghost-cursor/server";

const app = express();
const gateway = new Gateway({
  serviceUrl: process.env.GHOST_CURSOR_SERVICE_URL!,
  serviceKey: process.env.GHOST_CURSOR_API_KEY!,
  loadBrain: async (subject, context) => "# Platform Rules\nAlways confirm large orders.",
  requestTimeoutMs: 210_000, // optional: upstream request timeout in ms (default 210,000)
  toolTimeoutMs: 10_000,      // optional: tool execution timeout in ms (default 10,000)
});

app.post("/api/ghost-cursor", express.json({ limit: "64kb" }), requireAuth, checkCsrf, async (req, res) => {
  try {
    const response = await gateway.handle(req.user.id, req.body);
    res.setHeader("Cache-Control", "no-store").json(response);
  } catch (err: any) {
    res.status(err.status || 500).setHeader("Cache-Control", "no-store").json({ error: err.code || "internal_error" });
  }
});
```

## Options

`new Gateway(options)` accepts:

- `serviceUrl` (`string`, required): URL of the Ghost Cursor hosted service (HTTPS or localhost HTTP).
- `serviceKey` (`string`, required): API authentication key for upstream service.
- `loadBrain` (`string` or `(subject, context) => Promise<string> | string`, required): Platform rules/brain prompt.
- `capabilities` (`string[]` or `(subject) => Promise<string[]> | string[]`, optional): List of allowed capabilities.
- `tools` (`Record<string, Tool>` or `Tool[]` or callback, optional): Customer backend tools.
- `filterResponse` (`(res, subject) => Promise<PublicResponse> | PublicResponse`, optional): Response transformation hook.
- `fetch` (`typeof globalThis.fetch`, optional): Custom fetch implementation.
- `requestTimeoutMs` (`number`, optional, default `210000`): Upstream HTTP request timeout in milliseconds.
- `toolTimeoutMs` (`number`, optional, default `10000`): Tool execution timeout in milliseconds.


