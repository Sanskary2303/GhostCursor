"""
Ghost Cursor Type Definitions
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


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

    @property
    def metadata(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "role": self.role,
            "token_count": self.token_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

