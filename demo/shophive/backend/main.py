#!/usr/bin/env python3
"""
ShopHive Demo Backend - Main Entry Point

Customer backend that integrates Ghost Cursor SDK for AI co-pilot functionality.
"""

import os
import sys
from pathlib import Path

# Add current and parent directories to path for imports
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))
sys.path.insert(0, str(backend_dir.parent.parent / "packages" / "sdk-server-python"))

import secrets
from fastapi import FastAPI, Depends, Request, HTTPException
from starlette.middleware.sessions import SessionMiddleware

# Import Ghost Cursor SDK
try:
    from ghost_cursor import GhostCursorBackend, InMemoryChatStore, SQLAlchemyChatStore
except ImportError:
    print("Error: ghost-cursor package not found. Install with: pip install ghost-cursor")
    sys.exit(1)

# Import local modules
from tools.ghost_tools import register_shophive_tools

# ============================================================================
# Configuration
# ============================================================================

GHOST_CURSOR_API_KEY = os.getenv("GHOST_CURSOR_API_KEY", "test-key-shophive-demo")
GHOST_CURSOR_TENANT_ID = os.getenv("GHOST_CURSOR_TENANT_ID", "shophive_demo")
GHOST_CURSOR_BRAIN_DIR = os.getenv("GHOST_CURSOR_BRAIN_DIR", str(backend_dir / "brain"))
GHOST_CURSOR_SERVICE_URL = os.getenv("GHOST_CURSOR_SERVICE_URL", "http://localhost:8080")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shophive.db")

# ============================================================================
# Application Setup
# ============================================================================

app = FastAPI(
    title="ShopHive Backend API",
    description="E-commerce storefront with Ghost Cursor AI integration",
    version="0.1.0",
)

SESSION_SECRET = os.getenv("SHOPHIVE_SESSION_SECRET") or secrets.token_urlsafe(32)  # random per start in dev
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=os.getenv("SHOPHIVE_SECURE_COOKIES") == "1",
    max_age=8 * 3600,
)

DEMO_USERS = {"demo": "user_demo"}
ALLOWED_ORIGINS = {
    o
    for o in os.getenv("SHOPHIVE_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    if o
}


def require_user(request: Request) -> str:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="login_required")
    return user_id


def same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    own = f"{request.url.scheme}://{request.url.netloc}"
    if origin and origin != own and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="bad_origin")

# ============================================================================
# Initialize Ghost Cursor Backend
# ============================================================================

ghost = GhostCursorBackend(
    api_key=GHOST_CURSOR_API_KEY,
    tenant_id=GHOST_CURSOR_TENANT_ID,
    brain_dir=GHOST_CURSOR_BRAIN_DIR,
    service_url=GHOST_CURSOR_SERVICE_URL,
)

# Attach chat store for conversation persistence
chat_store = InMemoryChatStore()
ghost.attach_chat_store(chat_store)

# Register customer backend tools
register_shophive_tools(ghost)

# ============================================================================
# API Routes
# ============================================================================

@app.get("/health")
async def health_check():
    """Liveness probe"""
    return {"status": "ok", "service": "shophive"}

@app.get("/api/products")
async def get_products():
    """Get all products"""
    return [
        {"id": "air-max-90", "name": "Nike Air Max 90", "price": 129.99, "sizes": ["7", "8", "9", "10", "11", "12", "13"], "colors": ["Black", "White", "Red"]},
        {"id": "jordan-1", "name": "Air Jordan 1 Retro", "price": 179.99, "sizes": ["8", "9", "10", "11", "12"], "colors": ["Black/Red", "White/Blue"]},
        {"id": "yeezy-350", "name": "Yeezy Boost 350", "price": 229.99, "sizes": ["7", "8", "9", "10", "11"], "colors": ["Beige", "Black"]},
        {"id": "ultraboost", "name": "Adidas Ultraboost 22", "price": 189.99, "sizes": ["8", "9", "10", "11", "12"], "colors": ["Black", "White", "Blue"]},
    ]

@app.get("/api/products/{product_id}")
async def get_product(product_id: str):
    """Get a single product by ID"""
    products = await get_products()
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@app.post("/api/login", dependencies=[Depends(same_origin)])
async def login(request: Request):
    data = await request.json()
    username = data.get("username")
    if username in DEMO_USERS:
        request.session["user_id"] = DEMO_USERS[username]
        request.session["username"] = username
        return {"user": username}
    raise HTTPException(status_code=401, detail="invalid_credentials")

@app.post("/api/logout", dependencies=[Depends(same_origin)])
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}

@app.get("/api/me")
async def me(request: Request):
    username = request.session.get("username")
    if not username:
        raise HTTPException(status_code=401, detail="login_required")
    return {"user": username}

# ============================================================================
# Ghost Cursor Integration
# ============================================================================

from fastapi import APIRouter

ghost_router = APIRouter(prefix="/api/ghost-cursor", tags=["ghost-cursor"])

@ghost_router.post("", dependencies=[Depends(same_origin)])
@ghost_router.post("/run", dependencies=[Depends(same_origin)])
@ghost_router.post("/continue", dependencies=[Depends(same_origin)])
async def handle_ghost_turn(request: Request, user_id: str = Depends(require_user)):
    """Handle Ghost Cursor conversation turns"""
    payload = await request.json()
    return await ghost.handle_turn(payload=payload, user_id=user_id)

@ghost_router.get("/sessions")
async def list_sessions(user_id: str = Depends(require_user)):
    """List user chat sessions"""
    if ghost.chat_store:
        sessions = await ghost.chat_store.list_sessions(user_id)
        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "summary": s.summary,
                    "updated_at": s.updated_at.isoformat(),
                }
                for s in sessions
            ]
        }
    return {"sessions": []}

app.include_router(ghost_router)

# ============================================================================
# Static Files (Frontend)
# ============================================================================

from fastapi import HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dir = (backend_dir.parent / "frontend" / "dist").resolve()
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dir / "assets"), name="assets")

@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    candidate = (frontend_dir / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(frontend_dir):
        return FileResponse(candidate)
    return FileResponse(frontend_dir / "index.html")

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)