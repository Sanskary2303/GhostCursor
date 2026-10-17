"""
Ghost Cursor Type Definitions
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@dataclass
class ChatSession:
    """Chat session model"""
    session_id: str
    tenant_id: str
    user_id: str
    title: str
    summary: Optional[str]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.created_at is not None:
            self.created_at = _as_utc(self.created_at)
        if self.updated_at is not None:
            self.updated_at = _as_utc(self.updated_at)

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "title": self.title,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass
class ChatMessage:
    """Chat message model"""
    message_id: str
    session_id: str
    role: str
    content: str
    tool_calls: List[Dict[str, Any]]
    client_actions: List[Dict[str, Any]]
    token_count: int
    created_at: datetime
    run_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.created_at is not None:
            self.created_at = _as_utc(self.created_at)

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "token_count": self.token_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

