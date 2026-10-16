"""
Flask Integration for Ghost Cursor Backend SDK

Provides a Blueprint exposing a secure POST endpoint for Ghost Cursor turns.
"""

from typing import Any, Callable, Dict, Optional
import inspect
import logging

from flask import Blueprint, Response, jsonify, request
from .proxy import GatewayError, GhostCursorBackend

logger = logging.getLogger(__name__)


def ghost_cursor_blueprint(
    backend: GhostCursorBackend,
    get_user_id: Callable[..., Optional[str]],
    url_prefix: Optional[str] = None,
    name: str = "ghost_cursor",
) -> Blueprint:
    """
    Create a Flask blueprint for Ghost Cursor turns.

    Args:
        backend: Initialized GhostCursorBackend instance.
        get_user_id: Callback returning the authenticated user's ID, or None if unauthenticated.
        url_prefix: Optional URL prefix for mounting.
        name: Blueprint name.

    Returns:
        Flask Blueprint exposing POST ""
    """
    bp = Blueprint(name, __name__, url_prefix=url_prefix)

    def _resolve_user_id() -> Optional[str]:
        try:
            sig = inspect.signature(get_user_id)
            if len(sig.parameters) == 0:
                return get_user_id()
            return get_user_id(request)
        except Exception:
            try:
                return get_user_id()
            except TypeError:
                return get_user_id(request)

    def _json_response(data: Any, status: int = 200) -> Response:
        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp, status

    @bp.route("", methods=["POST"])
    def handle_turn():
        user_id = _resolve_user_id()
        if not user_id:
            return _json_response({"error": "unauthorized"}, 401)

        origin = request.headers.get("Origin")
        if origin:
            expected_origin = request.host_url.rstrip("/")
            if origin.rstrip("/") != expected_origin:
                return _json_response({"error": "cross_origin_forbidden"}, 403)

        if not request.is_json:
            return _json_response({"error": "unsupported_media_type"}, 415)

        try:
            payload = request.get_json(silent=True)
            if payload is None or not isinstance(payload, dict):
                return _json_response({"error": "invalid_json"}, 400)
        except Exception:
            return _json_response({"error": "invalid_json"}, 400)

        current_page = None
        context = payload.get("context")
        if isinstance(context, dict):
            current_page = context.get("page")
        if not current_page:
            current_page = payload.get("currentPage") or payload.get("current_page")

        try:
            result = backend.handle_turn_sync(
                payload=payload,
                user_id=user_id,
                current_page=current_page,
            )
            return _json_response(result, 200)
        except GatewayError as exc:
            return _json_response({"error": exc.code}, exc.status)
        except Exception as exc:
            logger.exception("Internal error in Ghost Cursor Flask gateway: %s", exc)
            return _json_response({"error": "internal_error"}, 500)

    return bp