"""
Ghost Cursor Python Backend SDK

A secure gateway proxy for integrating Ghost Cursor Cloud with customer backends.
Provides FastAPI, Flask, and Django integrations with automatic chat history persistence.
"""

from .proxy import GhostCursorBackend, GhostCursorProxy, GatewayError
from .storage import SQLAlchemyChatStore, InMemoryChatStore, ChatStore
from .brain_loader import BrainLoader
from .tools import Tool, ToolRegistry
from .fastapi import GhostCursorFastAPI, ghost_cursor_router

try:
    from .flask import ghost_cursor_blueprint
except ImportError:
    ghost_cursor_blueprint = None  # type: ignore

try:
    from .django import ghost_cursor_urls
except ImportError:
    ghost_cursor_urls = None  # type: ignore

__version__ = "0.1.0"

__all__ = [
    "GhostCursorBackend",
    "GhostCursorProxy",
    "GatewayError",
    "SQLAlchemyChatStore",
    "InMemoryChatStore",
    "ChatStore",
    "BrainLoader",
    "Tool",
    "ToolRegistry",
    "GhostCursorFastAPI",
    "ghost_cursor_router",
    "ghost_cursor_blueprint",
    "ghost_cursor_urls",
]