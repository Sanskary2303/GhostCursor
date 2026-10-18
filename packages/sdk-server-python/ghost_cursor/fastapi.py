"""
FastAPI Integration for Ghost Cursor Backend SDK

Provides ready-to-use router and dependency injection for FastAPI applications.
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from functools import wraps

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .proxy import GhostCursorBackend, GhostCursorProxy, GatewayError
from .storage import SQLAlchemyChatStore, ChatStore

logger = logging.getLogger(__name__)


# ============================================================================
# Request/Response Models
# ============================================================================

class GhostCursorStartRequest(BaseModel):
    """Request to start a new Ghost Cursor conversation"""
    message: str = Field(..., min_length=1, max_length=6000)
    context: Dict[str, Any] = Field(default_factory=dict)
    requestId: Optional[str] = None


class GhostCursorContinueRequest(BaseModel):
    """Request to continue an existing conversation"""
    runId: str
    eventId: str
    revision: int
    kind: str = Field(..., pattern="^(actions|answer|cancel)$")
    results: Optional[List[Dict[str, Any]]] = None
    answer: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class GhostCursorResponse(BaseModel):
    """Public response to frontend"""
    protocolVersion: str = "1.1"
    runId: str
    revision: int
    status: str
    reply: str
    questions: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    cards: Optional[List[Dict[str, Any]]] = None


class SessionCreateRequest(BaseModel):
    """Request to create a new chat session"""
    title: str = Field(default="New Conversation", max_length=255)


class SessionResponse(BaseModel):
    """Chat session response"""
    session_id: str
    tenant_id: str
    user_id: str
    title: str
    summary: Optional[str] = None
    created_at: str
    updated_at: str


# ============================================================================
# Dependencies
# ============================================================================

class GhostCursorDependencies:
    """Container for Ghost Cursor dependencies"""

    def __init__(
        self,
        backend: GhostCursorBackend,
        user_id_extractor: Callable[[Request], str],
        chat_store: Optional[ChatStore] = None,
    ):
        self.backend = backend
        self.chat_store = chat_store
        self.user_id_extractor = user_id_extractor


# ============================================================================
# Router Factory
# ============================================================================

def create_ghost_cursor_router(
    backend: GhostCursorBackend,
    user_id_extractor: Callable[[Request], str],
    chat_store: Optional[ChatStore] = None,
    prefix: str = "/api/ghost-cursor",
    tags: List[str] = ["ghost-cursor"],
) -> APIRouter:
    """
    Create a FastAPI router with Ghost Cursor endpoints.

    Args:
        backend: GhostCursorBackend instance
        user_id_extractor: Function to extract user_id from request
        chat_store: Optional ChatStore for session persistence
        prefix: URL prefix for routes
        tags: OpenAPI tags

    Returns:
        Configured APIRouter
    """

    router = APIRouter(prefix=prefix, tags=tags)

    # Dependency to get user ID
    def get_user_id(request: Request) -> str:
        return user_id_extractor(request)

    @router.post("", response_model=GhostCursorResponse)
    @router.post("/run", response_model=GhostCursorResponse)
    @router.post("/continue", response_model=GhostCursorResponse)
    async def handle_ghost_turn(
        http_request: Request,
        user_id: str = Depends(get_user_id),
    ):
        """
        Handle Ghost Cursor conversation turn (start or continue).
        Proxies to Ghost Cursor Cloud via server-to-server HTTPS.
        """
        try:
            try:
                payload = await http_request.json()
            except Exception:
                return JSONResponse(
                    {"error": "invalid_json"},
                    status_code=400,
                    headers={"Cache-Control": "no-store"},
                )

            current_page = None
            if isinstance(payload, dict) and isinstance(payload.get("context"), dict):
                current_page = payload["context"].get("page")

            response = await backend.handle_turn(
                payload=payload,
                user_id=user_id,
                current_page=current_page,
            )
            return JSONResponse(content=response)
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

    @router.get("/sessions", response_model=List[SessionResponse])
    async def list_sessions(
        user_id: str = Depends(get_user_id),
        limit: int = 20,
        offset: int = 0,
    ):
        """List user's chat sessions"""
        active_store = chat_store or getattr(backend, "chat_store", None)
        if not active_store:
            raise HTTPException(status_code=503, detail="Chat store not configured")

        sessions = await active_store.list_sessions(user_id, limit=limit, offset=offset)
        return [
            SessionResponse(
                session_id=s.session_id,
                tenant_id=s.tenant_id,
                user_id=s.user_id,
                title=s.title,
                summary=s.summary,
                created_at=s.created_at.isoformat(),
                updated_at=s.updated_at.isoformat(),
            )
            for s in sessions
        ]

    @router.post("/sessions", response_model=SessionResponse)
    async def create_session(
        request: SessionCreateRequest,
        user_id: str = Depends(get_user_id),
    ):
        """Create a new chat session"""
        try:
            active_store = chat_store or getattr(backend, "chat_store", None)
            if not active_store:
                raise HTTPException(status_code=503, detail="Chat store not configured")

            tenant_id = backend.config.tenant_id if hasattr(backend, 'config') else "default"

            session = await active_store.create_session(
                user_id=user_id,
                tenant_id=tenant_id,
                title=request.title,
            )

            return SessionResponse(
                session_id=session.session_id,
                tenant_id=session.tenant_id,
                user_id=session.user_id,
                title=session.title,
                summary=session.summary,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
            )
        except GatewayError as e:
            return JSONResponse(
                {"error": e.code},
                status_code=e.status,
                headers={"Cache-Control": "no-store"},
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Internal error in create_session")
            return JSONResponse(
                {"error": "internal_error"},
                status_code=500,
                headers={"Cache-Control": "no-store"},
            )

    @router.get("/sessions/{session_id}/messages", response_model=List[Dict[str, Any]])
    async def get_session_messages(
        session_id: str,
        user_id: str = Depends(get_user_id),
        limit: int = 100,
        offset: int = 0,
    ):
        """Get messages for a session"""
        active_store = chat_store or getattr(backend, "chat_store", None)
        if not active_store:
            raise HTTPException(status_code=503, detail="Chat store not configured")

        messages = await active_store.get_messages(session_id, user_id, limit=limit, offset=offset)
        return [
            {
                "message_id": m.message_id,
                "session_id": m.session_id,
                "role": m.role,
                "content": m.content,
                "tool_calls": m.tool_calls,
                "client_actions": m.client_actions,
                "token_count": m.token_count,
                "created_at": m.created_at.isoformat(),
            }
            for m in messages
        ]

    return router


# Alias for backward compatibility
ghost_cursor_router = create_ghost_cursor_router
GhostCursorFastAPI = GhostCursorBackend


# ============================================================================
# FastAPI App Integration Helper
# ============================================================================

def integrate_ghost_cursor(
    app: Any,  # FastAPI app
    backend: GhostCursorBackend,
    user_id_extractor: Callable[[Request], str],
    chat_store: Optional[ChatStore] = None,
    prefix: str = "/api/ghost-cursor",
):
    """
    Integrate Ghost Cursor into a FastAPI application.

    Usage:
        from ghost_cursor.fastapi import integrate_ghost_cursor
        from ghost_cursor import GhostCursorBackend

        backend = GhostCursorBackend(
            api_key=os.environ["GHOST_CURSOR_API_KEY"],
            tenant_id="my_tenant",
            brain_dir="./brain",
        )

        integrate_ghost_cursor(app, backend, user_id_extractor=my_user_extractor)
    """
    router = create_ghost_cursor_router(
        backend=backend,
        user_id_extractor=user_id_extractor,
        chat_store=chat_store,
        prefix=prefix,
    )
    app.include_router(router)

    # Store backend reference for cleanup
    app.state.ghost_cursor_backend = backend


# ============================================================================
# Security Helpers
# ============================================================================

def require_auth(user_id_extractor: Callable[[Request], str]):
    """
    Dependency that requires authentication.
    Raises 401 if user cannot be identified.
    """
    async def _require_auth(request: Request) -> str:
        user_id = user_id_extractor(request)
        if not user_id or user_id == "anonymous":
            raise HTTPException(status_code=401, detail="Authentication required")
        return user_id

    return _require_auth


# ============================================================================
# Middleware for Request Size Limits
# ============================================================================

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request body size limits"""

    def __init__(self, app: Any, max_size: int = 64 * 1024):
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: StarletteRequest, call_next: Callable) -> Response:
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_size:
                    return JSONResponse(
                        status_code=413,
                        content={"error": f"Request body exceeds {self.max_size} bytes limit"},
                    )
            except ValueError:
                pass

        # For streaming bodies, we can't easily check - rely on FastAPI's built-in limits
        return await call_next(request)


# ============================================================================
# Health Check Endpoint
# ============================================================================

def add_health_check(router: APIRouter):
    """Add a health check endpoint to the router"""

    @router.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok", "service": "ghost-cursor"}

    return router