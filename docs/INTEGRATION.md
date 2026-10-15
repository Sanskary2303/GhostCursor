# Ghost Cursor Integration Guide

## Overview

This guide covers how to integrate Ghost Cursor into your web application. Ghost Cursor consists of a **Frontend SDK** (for the browser) and a **Backend SDK** (for your server).

---

## Architecture

```
User's Browser
    ↓
Customer Frontend (your app + @ghost-cursor/sdk)
    ↓ (same-origin, authenticated)
Customer Backend (your FastAPI/Flask/Django + ghost-cursor)
    ↓ (HTTPS + Bearer token)
Ghost Cursor Cloud (FastAPI + Google ADK + Gemini)
```

**Key Principle:** The browser NEVER talks directly to Ghost Cursor Cloud. All traffic goes through your backend for security.

---

## Frontend Integration

### Installation

```bash
npm install @ghost-cursor/sdk
```

### React Integration

```tsx
import { GhostCursor } from '@ghost-cursor/sdk-react';
import '@ghost-cursor/sdk-react/dist/index.css';

function App() {
  return (
    <>
      <YourExistingApp />
      <GhostCursor 
        apiEndpoint="/api/ghost-cursor"
        theme={{ primaryColor: '#0052FF', position: 'bottom-right' }}
        requireApprovalForActions={true}
      />
    </>
  );
}
```

### Vanilla JS Integration

```html
<script src="https://cdn.ghostcursor.ai/sdk/v1/ghost-cursor.min.js"></script>
<script>
  GhostCursor.init({
    endpoint: '/api/ghost-cursor',
    theme: { primaryColor: '#0052FF' }
  });
</script>
```

### Advanced Configuration

```tsx
<GhostCursor
  apiEndpoint="/api/ghost-cursor"
  theme={{
    primaryColor: '#FF6B00',
    cursorColor: '#FF4D4D',
    position: 'bottom-right'
  }}
  requireApprovalForActions={true}
  context={{
    page: window.location.pathname,
    values: { userId: currentUser.id }
  }}
  selectors={{
    exclude: ['.sensitive-data', '#credit-card-form']
  }}
/>
```

---

## Backend Integration

### Python/FastAPI Integration

```python
from fastapi import FastAPI, Depends
from ghost_cursor import GhostCursorBackend, SQLAlchemyChatStore

app = FastAPI()

# Initialize Ghost Cursor
ghost = GhostCursorBackend(
    api_key=os.environ["GHOST_CURSOR_API_KEY"],
    tenant_id=os.environ["GHOST_CURSOR_TENANT_ID"],
    brain_dir="./brain",  # Path to your markdown brain files
)

# Connect customer's database for chat history
chat_store = SQLAlchemyChatStore(engine=app.state.db_engine)
ghost.attach_chat_store(chat_store)

# Register customer backend tools
from tools.ghost_tools import register_shophive_tools
register_shophive_tools(ghost)

# Mount the Ghost Cursor router
from ghost_cursor.fastapi import ghost_cursor_router
app.include_router(ghost_cursor_router(ghost, chat_store))
```

### Flask Integration

```python
from flask import Flask
from ghost_cursor.flask import ghost_cursor_blueprint

app = Flask(__name__)

# Mount the Ghost Cursor blueprint
app.register_blueprint(
    ghost_cursor_blueprint(
        api_key=os.environ["GHOST_CURSOR_API_KEY"],
        tenant_id=os.environ["GHOST_CURSOR_TENANT_ID"],
        brain_dir="./brain",
        url_prefix="/api/ghost-cursor"
    )
)
```

### Django Integration

```python
# settings.py
GHOST_CURSOR_API_KEY = os.environ["GHOST_CURSOR_API_KEY"]
GHOST_CURSOR_TENANT_ID = os.environ["GHOST_CURSOR_TENANT_ID"]
GHOST_CURSOR_BRAIN_DIR = "./brain"

# urls.py
from ghost_cursor.django import ghost_cursor_urls
urlpatterns += ghost_cursor_urls("api/ghost-cursor/")
```

---

## Brain Files

Create markdown files in your backend to give Ghost Cursor business context.

### `brain/platform.md`

```markdown
# ShopHive Platform Overview

ShopHive is a modern footwear store. All currency is USD ($).
Free shipping applies automatically on orders over $75.
Standard return policy is 30 days.
```

### `brain/pages/products.md`

```markdown
# Product Detail Page Context

This page displays individual product information.

## Sizing Information
- Shoes are sold in US Men's sizes 7 through 13
- Sizes run true to size

## Available Sizes
- Size 10: 20 units available
- Size 11: 8 units available
```

**Important:** Brain files contain **zero HTML tags or CSS selectors**. They describe what things mean in business terms.

---

## DOM Targeting

Add `data-ghost-id` attributes to interactive elements:

```tsx
<button
  data-ghost-id="product.add_to_cart_btn"
  onClick={handleAddToCart}
>
  Add to Cart
</button>

<input
  data-ghost-id="checkout.email"
  type="email"
  placeholder="your@email.com"
/>
```

**Targeting Priority:**
1. `data-ghost-id` (recommended)
2. `data-testid`
3. `id`
4. ARIA labels
5. Visible text

---

## Backend Tools

Register read-only tools for domain-specific queries:

```python
from ghost_cursor import GhostCursorBackend
from pydantic import BaseModel

class OrderQuery(BaseModel):
    order_id: str

ghost = GhostCursorBackend(...)

@ghost.register_tool(
    name="lookup_order",
    description="Look up order status and tracking",
    schema=OrderQuery.model_json_schema(),
    read_only=True,
)
async def lookup_order(params: OrderQuery, context: dict):
    user_id = context["user_id"]
    order = await fetch_order_from_db(params.order_id, user_id)
    return order or {"error": "Order not found"}
```

**Tools execute on your backend** (not Ghost Cloud) under the user's authenticated session.

---

## Authentication & Security

### Backend Route Protection

```python
from fastapi import Depends
from your_auth import get_current_user

@app.post("/api/ghost-cursor/run")
async def handle_ghost(
    request: Request,
    user = Depends(get_current_user)  # Your auth dependency
):
    return await ghost.handle_turn(
        payload=await request.json(),
        user_id=user.id  # Inject user identity
    )
```

### CSRF Protection

For Django/Flask, ensure CSRF middleware is enabled:

```python
# Django middleware must include:
# 'django.middleware.csrf.CsrfViewMiddleware'
```

The SDK includes `X-CSRFToken` header in requests.

---

## API Reference

### Frontend SDK

| Method | Description |
|--------|-------------|
| `createGhostCursor(options)` | Initialize SDK |
| `dispose()` | Cleanup resources |
| `sendMessage(message)` | Send user message |
| `executeActions(actions)` | Programmatically execute actions |

### Backend SDK

| Method | Description |
|--------|-------------|
| `GhostCursorBackend(api_key, tenant_id, brain_dir)` | Initialize backend |
| `attach_chat_store(store)` | Attach database for chat history |
| `register_tool(...)` | Register a backend tool |
| `handle_turn(payload, user_id)` | Process user turn |
| `close()` | Cleanup resources |

---

## Error Handling

```python
try:
    response = await ghost.handle_turn(payload, user_id)
except Exception as e:
    logger.error(f"Ghost Cursor error: {e}")
    return {"error": "Internal server error"}, 500
```

```tsx
const ghostCursor = createGhostCursor({ ... });

ghostCursor.onMessage((message) => {
  if (message.error) {
    console.error(message.error);
  }
});
```

---

## Testing

### Local Development

```bash
# Start Ghost Cursor Cloud (mock mode)
cd services/orchestrator
export USE_MOCK_LLM=true
uvicorn app.main:app --reload --port 8080

# Start ShopHive backend
cd demo/shophive/backend
uvicorn main:app --reload --port 8081

# Start ShopHive frontend
cd demo/shophive/frontend
npm run dev -- --port 3000
```

### Test a User Flow

1. Open `http://localhost:3000` in your browser
2. Click the Ghost Cursor chat widget
3. Type: "Add the Air Max 90 in size 10 to my cart"
4. Verify Ghost cursor appears and animates to the product
5. Click "Approve and Run"
6. Verify the item is added to cart

---

## Migration Guide

### From Ghost Cursor v0.0.x

- Backend SDK path: `ghost-cursor` (was `ghost_cursor`)
- Frontend SDK: `@ghost-cursor/sdk` (unchanged)
- Brain files: Moved to `brain/pages/` directory

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| SDK not connecting | Check `apiEndpoint` is correct and accessible |
| Actions not executing | Verify `data-ghost-id` attributes on elements |
| Brain files not loading | Check `brain_dir` path and markdown syntax |
| Backend tools failing | Verify `read_only=True` and return valid JSON |