"""
Run State Model

Multi-turn run state machine with revision tracking, deduplication,
and expiry management.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from .contracts import HostedRunResponse, RunStatus, RUN_EXPIRY_SECONDS


@dataclass
class RunState:
    """Internal run state"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tenant: str = ""
    subject: str = ""
    request_id: str = ""
    protocol_version: str = "1"
    revision: int = -1  # -1 = pending, 0+ = active
    status: str = "pending"
    start_payload: Dict[str, Any] = field(default_factory=dict)
    start_payload_digest: str = ""
    latest_reply: str = ""
    latest_event_id: Optional[str] = None
    latest_event_digest: Optional[str] = None
    latest_tool_results: Optional[List[Any]] = None
    latest_action_results: Optional[List[Any]] = None
    latest_kind: Optional[str] = None
    pending_ids: List[str] = field(default_factory=list)
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(seconds=RUN_EXPIRY_SECONDS)
    )

    def __post_init__(self):
        if self.start_payload and not self.start_payload_digest:
            self.start_payload_digest = RunStore.compute_digest(self.start_payload)

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def turn_count(self) -> int:
        return len([h for h in self.history if h.get("type") != "initial"])

    def to_hosted_response(self) -> HostedRunResponse:
        """Convert to hosted API response"""
        # Get latest response from history
        latest = self.history[-1] if self.history else None
        response_data = latest.get("response", {}) if latest else {}

        return HostedRunResponse(
            protocolVersion=self.protocol_version,
            runId=self.id,
            revision=self.revision,
            status=self.status,
            reply=self.latest_reply or response_data.get("reply", ""),
            questions=response_data.get("questions"),
            actions=response_data.get("actions"),
            toolCalls=response_data.get("toolCalls"),
        )

    def to_agent_context(self) -> Dict[str, Any]:
        """Convert to context dict for agent reasoning"""
        return {
            "run_id": self.id,
            "revision": self.revision,
            "status": self.status,
            "turn_count": self.turn_count,
            "kind": self.latest_kind,
            "transcript": self.transcript,
            "tool_results": [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in (self.latest_tool_results or [])
            ],
            "action_results": [
                r.model_dump() if hasattr(r, "model_dump") else r
                for r in (self.latest_action_results or [])
            ],
            "history": [
                {
                    "revision": h.get("revision"),
                    "type": h.get("type"),
                    "response": h.get("response", {}).get("reply", ""),
                }
                for h in self.history[-5:]  # Last 5 turns for context
            ],
        }

    def to_db_dict(self) -> Dict[str, Any]:
        """Serialize for database storage"""
        return {
            "id": self.id,
            "tenant": self.tenant,
            "subject": self.subject,
            "request_id": self.request_id,
            "protocol_version": self.protocol_version,
            "revision": self.revision,
            "status": self.status,
            "start_payload": self.start_payload,
            "start_payload_digest": self.start_payload_digest,
            "latest_reply": self.latest_reply,
            "latest_event_id": self.latest_event_id,
            "latest_event_digest": self.latest_event_digest,
            "pending_ids": self.pending_ids,
            "transcript": self.transcript,
            "history": self.history,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_db_dict(cls, data: Dict[str, Any]) -> "RunState":
        """Deserialize from database storage"""
        return cls(
            id=data["id"],
            tenant=data["tenant"],
            subject=data["subject"],
            request_id=data["request_id"],
            protocol_version=data.get("protocol_version", "1"),
            revision=data["revision"],
            status=data["status"],
            start_payload=data.get("start_payload", {}),
            start_payload_digest=data.get("start_payload_digest", ""),
            latest_reply=data.get("latest_reply", ""),
            latest_event_id=data.get("latest_event_id"),
            latest_event_digest=data.get("latest_event_digest"),
            pending_ids=data.get("pending_ids", []),
            transcript=data.get("transcript", []),
            history=data.get("history", []),
            created_at=datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.now(timezone.utc)),
            expires_at=datetime.fromisoformat(data["expires_at"]) if isinstance(data.get("expires_at"), str) else data.get("expires_at", datetime.now(timezone.utc) + timedelta(seconds=RUN_EXPIRY_SECONDS)),
        )


# ============================================================================
# Run Store Interface
# ============================================================================

class RunStore:
    """Abstract run store interface"""

    async def save(self, run: RunState) -> None:
        raise NotImplementedError

    async def get(self, run_id: str) -> Optional[RunState]:
        raise NotImplementedError

    async def get_by_request_id(self, tenant: str, subject: str, request_id: str) -> Optional[RunState]:
        raise NotImplementedError

    async def delete(self, run_id: str) -> None:
        raise NotImplementedError

    async def initialize(self) -> None:
        """Initialize store (create tables, etc.)"""
        pass

    async def close(self) -> None:
        """Close store connections"""
        pass

    @staticmethod
    def compute_digest(payload: Dict[str, Any]) -> str:
        """Compute SHA-256 digest of a payload for deduplication"""
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()