# Ghost Cursor Python SDK

Backend gateway SDK for integrating Ghost Cursor into Python web frameworks.

## Installation

```bash
pip install ghost-cursor
```

## Quick Start

```python
from ghost_cursor import GhostCursorBackend

ghost = GhostCursorBackend(
    api_key="your-api-key",
    tenant_id="your-tenant-id",
    brain_dir="./brain",
    service_url="http://localhost:8080",
)

@app.post("/api/ghost-cursor")
async def handle_ghost_turn(request: Request):
    payload = await request.json()
    return await ghost.handle_turn(payload=payload, user_id="anonymous")
```

> **Note:** Backend tools registered with Ghost Cursor must be read-only.

