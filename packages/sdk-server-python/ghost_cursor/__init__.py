"""
Ghost Cursor Python Backend SDK

A secure gateway proxy for integrating Ghost Cursor Cloud with customer backends.
Provides FastAPI, Flask, and Django integrations with automatic chat history persistence.
"""

from .proxy import GhostCursorBackend, GhostCursorProxy
from .storage import SQLAlchemyChatStore, ChatStore
from .brain_loader import BrainLoader
from .tools import Tool, ToolRegistry
from .fastapi import GhostCursorFastAPI, ghost_cursor_router
from .flask import ghost_cursor_blueprint
from .django import ghost_cursor_urls

__version__ = "0.1.0"

__all__ = [
    "GhostCursorBackend",
    "GhostCursorProxy",
    "SQLAlchemyChatStore",
    "ChatStore",
    "BrainLoader",
    "Tool",
    "ToolRegistry",
    "GhostCursorFastAPI",
    "ghost_cursor_router",
    "ghost_cursor_blueprint",
    "ghost_cursor_urls",
]