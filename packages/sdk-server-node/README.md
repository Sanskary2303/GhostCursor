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

