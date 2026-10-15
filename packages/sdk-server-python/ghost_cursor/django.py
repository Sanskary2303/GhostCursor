"""
Django Integration for Ghost Cursor Backend SDK

Provides Django views and URL configuration for integrating Ghost Cursor.
"""

from typing import Any, Callable, Dict, List, Optional

from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from .proxy import GhostCursorBackend, GhostCursorProxy
from .storage import ChatStore


# ============================================================================
# Django Views
# ============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class GhostCursorView(View):
    """
    Main Ghost Cursor view for handling browser requests.
    Requires authentication and CSRF protection for session views.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.backend = None
        self.proxy = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # Initialize backend if not already done
        if self.backend is None:
            self._initialize_backend()

    def _initialize_backend(self):
        """Initialize Ghost Cursor backend from Django settings"""
        # Get settings from Django settings
        api_key = getattr(settings, 'GHOST_CURSOR_API_KEY', None)
        tenant_id = getattr(settings, 'GHOST_CURSOR_TENANT_ID', None)
        brain_dir = getattr(settings, 'GHOST_CURSOR_BRAIN_DIR', './brain')
        service_url = getattr(settings, 'GHOST_CURSOR_SERVICE_URL', 'https://api.ghostcursor.ai')

        if not api_key or not tenant_id:
            raise ValueError(
                "GHOST_CURSOR_API_KEY and GHOST_CURSOR_TENANT_ID must be set in Django settings"
            )

        # Initialize backend
        self.backend = GhostCursorBackend(
            api_key=api_key,
            tenant_id=tenant_id,
            brain_dir=brain_dir,
            service_url=service_url,
        )
        self.proxy = GhostCursorProxy(self.backend)

    def post(self, request, *args, **kwargs):
        """Handle POST requests from frontend SDK"""
        # Require authentication
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)

        # Parse JSON body
        import json
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        # Validate request
        message = data.get("message")
        if not message:
            return JsonResponse({"error": "Message is required"}, status=400)

        context = data.get("context", {})
        request_id = data.get("requestId")

        # Use Django user ID as subject
        user_id = str(request.user.pk)

        try:
            payload = {
                "message": message,
                "context": context,
                "requestId": request_id,
            }

            response = self.backend.handle_turn(
                payload=payload,
                user_id=user_id,
                current_page=context.get("page"),
            )

            return JsonResponse(response)
        except Exception as e:
            # Log error
            import logging
            logging.error(f"Ghost Cursor error: {e}")
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class GhostCursorContinueView(View):
    """View for continuing existing Ghost Cursor runs"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.backend = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if self.backend is None:
            self._initialize_backend()

    def _initialize_backend(self):
        """Initialize Ghost Cursor backend from Django settings"""
        api_key = getattr(settings, 'GHOST_CURSOR_API_KEY', None)
        tenant_id = getattr(settings, 'GHOST_CURSOR_TENANT_ID', None)
        brain_dir = getattr(settings, 'GHOST_CURSOR_BRAIN_DIR', './brain')
        service_url = getattr(settings, 'GHOST_CURSOR_SERVICE_URL', 'https://api.ghostcursor.ai')

        if not api_key or not tenant_id:
            raise ValueError(
                "GHOST_CURSOR_API_KEY and GHOST_CURSOR_TENANT_ID must be set in Django settings"
            )

        self.backend = GhostCursorBackend(
            api_key=api_key,
            tenant_id=tenant_id,
            brain_dir=brain_dir,
            service_url=service_url,
        )

    def post(self, request, run_id, *args, **kwargs):
        """Continue an existing run"""
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)

        import json
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

        # Implementation for continue endpoint
        return JsonResponse({"error": "Continue endpoint not yet implemented"}, status=501)


class GhostCursorSessionsView(View):
    """View for listing and managing chat sessions"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chat_store = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # Chat store would be configured separately
        pass

    def get(self, request, *args, **kwargs):
        """List user sessions"""
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)

        if not self.chat_store:
            return JsonResponse({"error": "Chat store not configured"}, status=503)

        user_id = str(request.user.pk)
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))

        # This would be async - for sync Django need different approach
        return JsonResponse({"error": "Async not supported in sync Django view"}, status=501)


class GhostCursorSessionDetailView(View):
    """View for a specific session"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.chat_store = None

    def get(self, request, session_id, *args, **kwargs):
        """Get session messages"""
        if not request.user.is_authenticated:
            return JsonResponse({"error": "Authentication required"}, status=401)

        if not self.chat_store:
            return JsonResponse({"error": "Chat store not configured"}, status=503)

        user_id = str(request.user.pk)
        limit = int(request.GET.get('limit', 100))
        offset = int(request.GET.get('offset', 0))

        return JsonResponse({"error": "Async not supported in sync Django view"}, status=501)


# ============================================================================
# URL Configuration
# ============================================================================

def ghost_cursor_urls(prefix: str = "api/ghost-cursor/") -> List[Any]:
    """
    Generate Django URL patterns for Ghost Cursor.

    Usage in urls.py:
        from ghost_cursor.django import ghost_cursor_urls
        urlpatterns += ghost_cursor_urls("api/ghost-cursor/")
    """
    from django.urls import path

    return [
        path(f"{prefix}run/", GhostCursorView.as_view(), name="ghost_cursor_run"),
        path(f"{prefix}continue/<str:run_id>/", GhostCursorContinueView.as_view(), name="ghost_cursor_continue"),
        path(f"{prefix}sessions/", GhostCursorSessionsView.as_view(), name="ghost_cursor_sessions"),
        path(f"{prefix}sessions/<str:session_id>/messages/", GhostCursorSessionDetailView.as_view(), name="ghost_cursor_session_messages"),
        path(f"{prefix}health/", lambda r: JsonResponse({"status": "ok", "service": "ghost-cursor"}), name="ghost_cursor_health"),
    ]


# ============================================================================
# Integration Helper
# ============================================================================

def integrate_ghost_cursor(
    backend: GhostCursorBackend,
    chat_store: Optional[ChatStore] = None,
):
    """
    Integrate Ghost Cursor with Django settings.

    Add to settings.py:
        import os
        GHOST_CURSOR_API_KEY = os.environ["GHOST_CURSOR_API_KEY"]
        GHOST_CURSOR_TENANT_ID = os.environ["GHOST_CURSOR_TENANT_ID"]
        GHOST_CURSOR_BRAIN_DIR = "./brain"
        GHOST_CURSOR_SERVICE_URL = "https://api.ghostcursor.ai"

    Then in urls.py:
        from ghost_cursor.django import ghost_cursor_urls
        urlpatterns += ghost_cursor_urls("api/ghost-cursor/")
    """
    # This function is a placeholder for any global setup
    # The actual integration is done via settings and URLs
    pass


# ============================================================================
# Settings Documentation
# ============================================================================

GHOST_CURSOR_DJANGO_SETTINGS = """
# Add to your Django settings.py:

# Ghost Cursor Configuration
GHOST_CURSOR_API_KEY = os.environ.get("GHOST_CURSOR_API_KEY")  # Server-to-server key
GHOST_CURSOR_TENANT_ID = os.environ.get("GHOST_CURSOR_TENANT_ID")  # Your tenant ID
GHOST_CURSOR_BRAIN_DIR = "./brain"  # Path to brain markdown files
GHOST_CURSOR_SERVICE_URL = "https://api.ghostcursor.ai"  # Ghost Cursor Cloud URL

# Required middleware (ensure these are in MIDDLEWARE):
# 'django.contrib.sessions.middleware.SessionMiddleware',
# 'django.contrib.auth.middleware.AuthenticationMiddleware',
# 'django.middleware.csrf.CsrfViewMiddleware',
# 'django.middleware.common.CommonMiddleware',

# ALLOWED_HOSTS must include your domain
# SESSION_COOKIE_SECURE = True  # In production
# CSRF_COOKIE_SECURE = True  # In production

# For SDK integration, include X-CSRFToken header in requests:
# headers: { 'X-CSRFToken': getCookie('csrftoken') }
"""

# ============================================================================
# Async Django Support (for Django 4.1+ async views)
# ============================================================================

try:
    from django.views import AsyncView

    class GhostCursorAsyncView(AsyncView):
        """Async version of Ghost Cursor view for Django 4.1+"""

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.backend = None

        async def setup(self, request, *args, **kwargs):
            await super().setup(request, *args, **kwargs)
            if self.backend is None:
                self._initialize_backend()

        def _initialize_backend(self):
            api_key = getattr(settings, 'GHOST_CURSOR_API_KEY', None)
            tenant_id = getattr(settings, 'GHOST_CURSOR_TENANT_ID', None)
            brain_dir = getattr(settings, 'GHOST_CURSOR_BRAIN_DIR', './brain')
            service_url = getattr(settings, 'GHOST_CURSOR_SERVICE_URL', 'https://api.ghostcursor.ai')

            if not api_key or not tenant_id:
                raise ValueError(
                    "GHOST_CURSOR_API_KEY and GHOST_CURSOR_TENANT_ID must be set in Django settings"
                )

            self.backend = GhostCursorBackend(
                api_key=api_key,
                tenant_id=tenant_id,
                brain_dir=brain_dir,
                service_url=service_url,
            )

        async def post(self, request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required"}, status=401)

            import json
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON body"}, status=400)

            message = data.get("message")
            if not message:
                return JsonResponse({"error": "Message is required"}, status=400)

            context = data.get("context", {})
            request_id = data.get("requestId")
            user_id = str(request.user.pk)

            try:
                payload = {
                    "message": message,
                    "context": context,
                    "requestId": request_id,
                }

                response = await self.backend.handle_turn(
                    payload=payload,
                    user_id=user_id,
                    current_page=context.get("page"),
                )

                return JsonResponse(response)
            except Exception as e:
                import logging
                logging.error(f"Ghost Cursor error: {e}")
                return JsonResponse({"error": str(e)}, status=500)

except ImportError:
    # Django < 4.1 doesn't have AsyncView
    pass