"""
Ghost Cursor Python Backend SDK

A secure gateway proxy for integrating Ghost Cursor Cloud with customer backends.
Provides FastAPI, Flask, and Django integrations with automatic chat history persistence.
"""

from .proxy import (
    GhostCursorBackend,
    GhostCursorProxy,
    GatewayError,
    BRAIN_CANARY,
    PublicEnvelope,
    hkdf_sha256,
    loopback_key,
    canonical_tool_calls,
    sign_tool_batch,
    verify_tool_batch,
)
from .storage import SQLAlchemyChatStore, InMemoryChatStore, ChatStore
from .brain_loader import BrainLoader
from .tools import Tool, ToolRegistry
from .fastapi import GhostCursorFastAPI, ghost_cursor_router

try:
    from .flask import ghost_cursor_blueprint
except ImportError:
    ghost_cursor_blueprint = None  # type: ignore

__version__ = "0.1.0"

__all__ = [
    "GhostCursorBackend",
    "GhostCursorProxy",
    "GatewayError",
    "BRAIN_CANARY",
    "PublicEnvelope",
    "SQLAlchemyChatStore",
    "InMemoryChatStore",
    "ChatStore",
    "BrainLoader",
    "Tool",
    "ToolRegistry",
    "GhostCursorFastAPI",
    "ghost_cursor_router",
    "ghost_cursor_blueprint",
    "hkdf_sha256",
    "loopback_key",
    "canonical_tool_calls",
    "sign_tool_batch",
    "verify_tool_batch",
]