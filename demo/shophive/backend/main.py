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

import logging
import secrets
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

logger = logging.getLogger(__name__)

# Import Ghost Cursor SDK
try:
    from ghost_cursor import GhostCursorBackend, InMemoryChatStore, SQLAlchemyChatStore, GatewayError
except ImportError:
    print("Error: ghost-cursor package not found. Install with: pip install ghost-cursor")
    sys.exit(1)

from sqlalchemy.ext.asyncio import create_async_engine

# Import local modules
from tools.ghost_tools import register_shophive_tools

# ============================================================================
# Configuration
# ============================================================================

GHOST_CURSOR_API_KEY = os.environ["GHOST_CURSOR_API_KEY"]
GHOST_CURSOR_TENANT_ID = os.getenv("GHOST_CURSOR_TENANT_ID", "shophive_demo")
GHOST_CURSOR_BRAIN_DIR = os.getenv("GHOST_CURSOR_BRAIN_DIR", str(backend_dir / "brain"))
GHOST_CURSOR_SERVICE_URL = os.getenv("GHOST_CURSOR_SERVICE_URL", "http://localhost:8080")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./shophive.db")
if DATABASE_URL.startswith("sqlite:///"):
    DATABASE_URL = DATABASE_URL.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

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
db_engine = create_async_engine(DATABASE_URL)
chat_store = SQLAlchemyChatStore(db_engine, tenant_id=GHOST_CURSOR_TENANT_ID)
ghost.attach_chat_store(chat_store)

_tables_initialized = False

async def ensure_tables():
    global _tables_initialized
    if not _tables_initialized:
        await chat_store.create_tables()
        _tables_initialized = True

@app.on_event("startup")
async def startup_event():
    await ensure_tables()

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
    try:
        data = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_json")
    username = data.get("username") if isinstance(data, dict) else None
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
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "invalid_json"},
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )

    try:
        await ensure_tables()
        data = await ghost.handle_turn(payload=payload, user_id=user_id)
        return JSONResponse(data)
    except GatewayError as e:
        return JSONResponse(
            {"error": e.code},
            status_code=e.status,
            headers={"Cache-Control": "no-store"},
        )
    except Exception:
        logger.exception("Internal error in handle_ghost_turn")
        return JSONResponse(
            {"error": "internal_error"},
            status_code=500,
            headers={"Cache-Control": "no-store"},
        )

@ghost_router.get("/sessions")
async def list_sessions(user_id: str = Depends(require_user)):
    """List user chat sessions"""
    await ensure_tables()
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
    index_file = frontend_dir / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(index_file)

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)