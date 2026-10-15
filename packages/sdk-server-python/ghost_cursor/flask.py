"""
Flask Integration for Ghost Cursor Backend SDK

Provides a blueprint for easy integration into Flask applications.
"""

from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint, jsonify, request, session, current_app
from werkzeug.exceptions import BadRequest, Unauthorized

from .proxy import GhostCursorBackend, GhostCursorProxy
from .storage import ChatStore


# ============================================================================
# Blueprint Factory
# ============================================================================

def ghost_cursor_blueprint(
    api_key: str,
    tenant_id: str,
    brain_dir: str = "./brain",
    chat_store: Optional[ChatStore] = None,
    user_id_extractor: Optional[Callable[[Any], str]] = None,
    service_url: str = "https://api.ghostcursor.ai",
    url_prefix: str = "/api/ghost-cursor",
) -> Blueprint:
    """
    Create a Flask blueprint with Ghost Cursor endpoints.

    Args:
        api_key: Server-to-server API key
        tenant_id: Tenant identifier
        brain_dir: Path to brain markdown files
        chat_store: Optional ChatStore for session persistence
        user_id_extractor: Function to extract user_id from request/session
        service_url: Ghost Cursor Cloud service URL
        url_prefix: URL prefix for routes

    Returns:
        Configured Flask Blueprint
    """

    bp = Blueprint("ghost_cursor", __name__, url_prefix=url_prefix)

    # Initialize backend
    backend = GhostCursorBackend(
        api_key=api_key,
        tenant_id=tenant_id,
        brain_dir=brain_dir,
        service_url=service_url,
        chat_store=chat_store,
    )

    proxy = GhostCursorProxy(backend)

    # Default user ID extractor
    def default_user_extractor(req: Any) -> str:
        # Try Flask session first
        if hasattr(req, 'session') and req.session.get('user_id'):
            return req.session['user_id']
        # Try current_user if Flask-Login is used
        if hasattr(req, 'user') and req.user.is_authenticated:
            return str(req.user.get_id())
        # Fallback to anonymous
        return "anonymous"

    get_user_id = user_id_extractor or default_user_extractor

    # ============================================================================
    # Routes
    # ============================================================================

    @bp.route("/run", methods=["POST"])
    def handle_ghost_turn():
        """Start a new Ghost Cursor conversation turn"""
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        data = request.get_json()
        if not data:
            raise BadRequest("Invalid JSON body")

        message = data.get("message")
        if not message:
            raise BadRequest("Message is required")

        context = data.get("context", {})
        request_id = data.get("requestId")

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        try:
            payload = {
                "message": message,
                "context": context,
                "requestId": request_id,
            }

            response = backend.handle_turn(
                payload=payload,
                user_id=user_id,
                current_page=context.get("page"),
            )

            return jsonify(response)
        except Exception as e:
            current_app.logger.error(f"Ghost Cursor error: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/continue", methods=["POST"])
    def continue_ghost_turn():
        """Continue an existing Ghost Cursor run"""
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        data = request.get_json()
        if not data:
            raise BadRequest("Invalid JSON body")

        # Implementation would go here
        return jsonify({"error": "Continue endpoint not yet implemented"}), 501

    @bp.route("/sessions", methods=["GET"])
    def list_sessions():
        """List user's chat sessions"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        limit = request.args.get("limit", 20, type=int)
        offset = request.args.get("offset", 0, type=int)

        # This would be async in real implementation
        # For Flask sync, we'd need to handle differently
        return jsonify({"error": "Async session listing not implemented for sync Flask"}), 501

    @bp.route("/sessions", methods=["POST"])
    def create_session():
        """Create a new chat session"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        data = request.get_json() or {}
        title = data.get("title", "New Conversation")

        # Sync wrapper for async store
        return jsonify({"error": "Session creation not implemented for sync Flask"}), 501

    @bp.route("/sessions/<session_id>/messages", methods=["GET"])
    def get_session_messages(session_id: str):
        """Get messages for a session"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        return jsonify({"error": "Message retrieval not implemented for sync Flask"}), 501

    @bp.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "ok", "service": "ghost-cursor"})

    # Store backend for potential cleanup
    bp.backend = backend

    return bp


# ============================================================================
# Async Flask Integration (for Quart/async Flask)
# ============================================================================

def ghost_cursor_blueprint_async(
    api_key: str,
    tenant_id: str,
    brain_dir: str = "./brain",
    chat_store: Optional[ChatStore] = None,
    user_id_extractor: Optional[Callable[[Any], str]] = None,
    service_url: str = "https://api.ghostcursor.ai",
    url_prefix: str = "/api/ghost-cursor",
) -> Blueprint:
    """
    Create a Flask/Quart blueprint with async Ghost Cursor endpoints.

    This version is for async-capable Flask implementations (Quart, Flask 2.3+ with async support).
    """

    bp = Blueprint("ghost_cursor", __name__, url_prefix=url_prefix)

    # Initialize backend
    backend = GhostCursorBackend(
        api_key=api_key,
        tenant_id=tenant_id,
        brain_dir=brain_dir,
        service_url=service_url,
        chat_store=chat_store,
    )

    proxy = GhostCursorProxy(backend)

    # Default user ID extractor
    def default_user_extractor(req: Any) -> str:
        if hasattr(req, 'session') and req.session.get('user_id'):
            return req.session['user_id']
        if hasattr(req, 'user') and req.user.is_authenticated:
            return str(req.user.get_id())
        return "anonymous"

    get_user_id = user_id_extractor or default_user_extractor

    @bp.route("/run", methods=["POST"])
    async def handle_ghost_turn():
        """Start a new Ghost Cursor conversation turn"""
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        data = request.get_json()
        if not data:
            raise BadRequest("Invalid JSON body")

        message = data.get("message")
        if not message:
            raise BadRequest("Message is required")

        context = data.get("context", {})
        request_id = data.get("requestId")

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        try:
            payload = {
                "message": message,
                "context": context,
                "requestId": request_id,
            }

            response = await backend.handle_turn(
                payload=payload,
                user_id=user_id,
                current_page=context.get("page"),
            )

            return jsonify(response)
        except Exception as e:
            current_app.logger.error(f"Ghost Cursor error: {e}")
            return jsonify({"error": str(e)}), 500

    @bp.route("/continue", methods=["POST"])
    async def continue_ghost_turn():
        """Continue an existing Ghost Cursor run"""
        if not request.is_json:
            return jsonify({"error": "Content-Type must be application/json"}), 415

        data = request.get_json()
        if not data:
            raise BadRequest("Invalid JSON body")

        return jsonify({"error": "Continue endpoint not yet implemented"}), 501

    @bp.route("/sessions", methods=["GET"])
    async def list_sessions():
        """List user's chat sessions"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        limit = request.args.get("limit", 20, type=int)
        offset = request.args.get("offset", 0, type=int)

        sessions = await chat_store.list_sessions(user_id, limit=limit, offset=offset)
        return jsonify([
            {
                "session_id": s.session_id,
                "tenant_id": s.tenant_id,
                "user_id": s.user_id,
                "title": s.title,
                "summary": s.summary,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ])

    @bp.route("/sessions", methods=["POST"])
    async def create_session():
        """Create a new chat session"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        data = request.get_json() or {}
        title = data.get("title", "New Conversation")

        tenant_id = backend.config.tenant_id if hasattr(backend, 'config') else "default"
        session = await chat_store.create_session(user_id=user_id, tenant_id=tenant_id, title=title)

        return jsonify({
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "title": session.title,
            "summary": session.summary,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        })

    @bp.route("/sessions/<session_id>/messages", methods=["GET"])
    async def get_session_messages(session_id: str):
        """Get messages for a session"""
        if not chat_store:
            return jsonify({"error": "Chat store not configured"}), 503

        user_id = get_user_id(request)
        if user_id == "anonymous":
            raise Unauthorized("Authentication required")

        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)

        messages = await chat_store.get_messages(session_id, user_id, limit=limit, offset=offset)
        return jsonify([
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
        ])

    @bp.route("/health", methods=["GET"])
    def health_check():
        """Health check endpoint"""
        return jsonify({"status": "ok", "service": "ghost-cursor"})

    bp.backend = backend
    return bp