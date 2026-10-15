#!/usr/bin/env python3
"""
ShopHive Demo Backend - Main Entry Point

Customer backend that integrates Ghost Cursor SDK for AI co-pilot functionality.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "packages" / "sdk-server-python"))

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware

# Import Ghost Cursor SDK
try:
    from ghost_cursor import GhostCursorBackend, SQLAlchemyChatStore
    from ghost_cursor.fastapi import integrate_ghost_cursor
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
GHOST_CURSOR_BRAIN_DIR = os.getenv("GHOST_CURSOR_BRAIN_DIR", "./brain")
GHOST_CURSOR_SERVICE_URL = os.getenv("GHOST_CURSOR_SERVICE_URL", "https://api.ghostcursor.ai")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shophive.db")

# ============================================================================
# Application Setup
# ============================================================================

app = FastAPI(
    title="ShopHive Backend API",
    description="E-commerce storefront with Ghost Cursor AI integration",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ============================================================================
# Initialize Ghost Cursor Backend
# ============================================================================

ghost = GhostCursorBackend(
    api_key=GHOST_CURSOR_API_KEY,
    tenant_id=GHOST_CURSOR_TENANT_ID,
    brain_dir=GHOST_CURSOR_BRAIN_DIR,
    service_url=GHOST_CURSOR_SERVICE_URL,
)

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

# ============================================================================
# Ghost Cursor Integration
# ============================================================================

from fastapi import APIRouter

ghost_router = APIRouter(prefix="/api/ghost-cursor", tags=["ghost-cursor"])

@ghost_router.post("/run")
async def handle_ghost_turn(request: Request, user_id: str = "anonymous"):
    """Handle Ghost Cursor conversation turns"""
    payload = await request.json()
    return await ghost.handle_turn(payload=payload, user_id=user_id)

@ghost_router.get("/sessions")
async def list_sessions(user_id: str = "anonymous"):
    """List user chat sessions"""
    return {"sessions": []}

app.include_router(ghost_router)

# ============================================================================
# Static Files (Frontend)
# ============================================================================

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        index_path = frontend_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)