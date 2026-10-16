import json
import logging
from typing import Any, Callable

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from ghost_cursor.proxy import GatewayError, GhostCursorBackend

logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 64 * 1024  # 64 KiB


def _json_response(data: Any, status: int = 200) -> JsonResponse:
    response = JsonResponse(data, status=status, safe=not isinstance(data, list))
    response["Cache-Control"] = "no-store"
    return response


def gateway_view(gateway: GhostCursorBackend) -> Callable[[HttpRequest], HttpResponse]:
    """
    Django view wrapper for Ghost Cursor gateway.
    Protected by Django CSRF middleware and requires an authenticated user.
    """
    @require_POST
    def view(request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return _json_response({"error": "unauthorized"}, status=401)

        if len(request.body) > MAX_BODY_SIZE:
            return _json_response({"error": "payload_too_large"}, status=413)

        try:
            payload = json.loads(request.body.decode("utf-8"))
            if not isinstance(payload, dict):
                return _json_response({"error": "invalid_json"}, status=400)
        except Exception:
            return _json_response({"error": "invalid_json"}, status=400)

        user_id = str(user.pk)
        current_page = None
        context = payload.get("context")
        if isinstance(context, dict):
            current_page = context.get("page")
        if not current_page:
            current_page = payload.get("currentPage") or payload.get("current_page")

        try:
            result = gateway.handle_turn_sync(
                payload=payload,
                user_id=user_id,
                current_page=current_page,
            )
            return _json_response(result, status=200)
        except GatewayError as exc:
            return _json_response({"error": exc.code}, status=exc.status)
        except Exception as exc:
            logger.exception("Internal error in Ghost Cursor Django gateway view: %s", exc)
            return _json_response({"error": "internal_error"}, status=500)

    return view

