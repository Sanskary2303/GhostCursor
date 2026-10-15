"""
Protocol V1 Contract Definitions

Strict runtime protocol models for Ghost Cursor API.
"""

import re
import hashlib
import json
from typing import Any, Dict, List, Literal, Optional, Union
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================================
# Primitive Constraints
# ============================================================================

ProtocolVersion = Literal["1"]

LOGICAL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]+$")
SUBJECT_PATTERN = re.compile(r"^[a-zA-Z0-9_.:@-]+$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

MAX_SCALAR_LENGTH = 2000
MAX_MESSAGE_LENGTH = 6000
MAX_BRAIN_LENGTH = 32000
MAX_TOOL_OUTPUT_LENGTH = 16000
MAX_REQUEST_BODY = 64 * 1024  # 64 KiB
MAX_RESPONSE_BODY = 256 * 1024  # 256 KiB
MAX_TARGETS = 100
MAX_OPTIONS = 10
MAX_RESULTS = 12
MAX_TURNS = 12

RUN_EXPIRY_SECONDS = 30 * 60  # 30 minutes


class RunStatus(str, Enum):
    """Run status enum"""
    AWAITING_TOOLS = "awaiting_tools"
    AWAITING_ACTIONS = "awaiting_actions"
    AWAITING_ANSWER = "awaiting_answer"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# Validators
# ============================================================================

def validate_logical_id(value: str) -> str:
    """Validate logical ID format"""
    if not value or len(value) > 120:
        raise ValueError("Logical ID must be 1-120 characters")
    if not LOGICAL_ID_PATTERN.match(value):
        raise ValueError("Logical ID contains invalid characters")
    return value


def validate_uuid(value: str) -> str:
    """Validate UUID format"""
    if not UUID_PATTERN.match(value):
        raise ValueError("Invalid UUID format")
    return value


def validate_subject(value: str) -> str:
    """Validate subject format"""
    if not value or len(value) > 120:
        raise ValueError("Subject must be 1-120 characters")
    if not SUBJECT_PATTERN.match(value):
        raise ValueError("Subject contains invalid characters")
    return value


# ============================================================================
# Context & Target Models
# ============================================================================

class PageContext(BaseModel):
    """Browser page context"""
    page: str = Field(default="unknown", max_length=200)
    values: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict)
    availableTargets: List[str] = Field(default_factory=list, max_length=MAX_TARGETS)

    @field_validator("values")
    @classmethod
    def validate_values(cls, v: Dict) -> Dict:
        for key, value in v.items():
            if isinstance(value, str) and len(value) > MAX_SCALAR_LENGTH:
                raise ValueError(f"Value for '{key}' exceeds {MAX_SCALAR_LENGTH} characters")
        return v

    @field_validator("availableTargets")
    @classmethod
    def validate_targets(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_TARGETS:
            raise ValueError(f"At most {MAX_TARGETS} available targets")
        return v


# ============================================================================
# Tool Call Models
# ============================================================================

class ToolCallRequest(BaseModel):
    """Tool call from the agent"""
    id: str
    tool: str
    parameters: Dict[str, Any]


class ToolCallResponse(BaseModel):
    """Result of tool execution"""
    id: str
    ok: bool
    output: Optional[Any] = None
    error: Optional[str] = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_result(self):
        if self.ok and self.error:
            raise ValueError("Success result cannot carry error")
        if not self.ok and self.output is not None:
            raise ValueError("Failure result cannot carry output")
        return self


# ============================================================================
# Question Models
# ============================================================================

class ClarifyQuestion(BaseModel):
    """Clarifying question for the user"""
    question: str = Field(..., min_length=1, max_length=1000)
    options: List[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_OPTIONS:
            raise ValueError(f"At most {MAX_OPTIONS} options")
        for opt in v:
            if len(opt) > 200:
                raise ValueError("Option must be at most 200 characters")
        return v


# ============================================================================
# Hosted API Request Models
# ============================================================================

class HostedCreateRunRequest(BaseModel):
    """POST /v1/runs - Create a new run"""
    protocolVersion: ProtocolVersion = Field(default="1")
    requestId: str = Field(...)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    context: PageContext = Field(default_factory=PageContext)
    brain: Optional[str] = Field(default=None, max_length=MAX_BRAIN_LENGTH)
    capabilities: List[str] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)

    @field_validator("requestId")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        return validate_uuid(v)


class HostedContinueRunRequest(BaseModel):
    """POST /v1/runs/{runId}/continue"""
    protocolVersion: ProtocolVersion = Field(default="1")
    eventId: str = Field(...)
    revision: int = Field(..., ge=0)
    kind: Literal["tools", "actions", "answer", "cancel"]
    results: Optional[List[ToolCallResponse]] = None
    answer: Optional[str] = Field(default=None, min_length=1, max_length=MAX_MESSAGE_LENGTH)
    context: Optional[PageContext] = None

    @field_validator("eventId")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        return validate_uuid(v)

    @model_validator(mode="after")
    def validate_continuation(self):
        if self.kind == "answer":
            if self.results:
                raise ValueError("Answer continuation cannot carry results")
            if not self.answer:
                raise ValueError("Answer continuation requires answer text")
        elif self.kind == "cancel":
            if self.results or self.answer:
                raise ValueError("Cancel continuation carries no results or answer")
        elif self.kind in ("tools", "actions"):
            if self.answer:
                raise ValueError(f"{self.kind} continuation cannot carry an answer")
            if self.results:
                if len(self.results) > MAX_RESULTS:
                    raise ValueError(f"At most {MAX_RESULTS} results")
                # Check for duplicate IDs
                ids = [r.id for r in self.results]
                if len(ids) != len(set(ids)):
                    raise ValueError("Duplicate result IDs")
        return self


# ============================================================================
# Hosted API Response Models
# ============================================================================

class HostedRunResponse(BaseModel):
    """Response from hosted API"""
    protocolVersion: ProtocolVersion = "1"
    runId: str
    revision: int
    status: str  # RunStatus value
    reply: str
    questions: Optional[List[ClarifyQuestion]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    toolCalls: Optional[List[ToolCallRequest]] = None

    @model_validator(mode="after")
    def validate_discrete_plan(self):
        """Only ONE of questions, actions, or toolCalls may be non-empty"""
        non_empty = 0
        if self.questions and len(self.questions) > 0:
            non_empty += 1
        if self.actions and len(self.actions) > 0:
            non_empty += 1
        if self.toolCalls and len(self.toolCalls) > 0:
            non_empty += 1
        if non_empty > 1:
            raise ValueError("Only ONE of questions, actions, or toolCalls may be non-empty")
        return self


# ============================================================================
# Browser Gateway Models (subset of hosted models)
# ============================================================================

class BrowserStartRequest(BaseModel):
    """Browser start request - accepted by customer gateway"""
    command: Literal["start"]
    requestId: str
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    context: PageContext = Field(default_factory=PageContext)

    @field_validator("requestId")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        return validate_uuid(v)


class BrowserContinueRequest(BaseModel):
    """Browser continue request - accepted by customer gateway"""
    command: Literal["continue"]
    runId: str
    eventId: str
    revision: int = Field(..., ge=0)
    kind: Literal["actions", "answer", "cancel"]  # No 'tools' from browser
    results: Optional[List[ToolCallResponse]] = None
    answer: Optional[str] = Field(default=None, max_length=MAX_MESSAGE_LENGTH)
    context: Optional[PageContext] = None

    @field_validator("eventId")
    @classmethod
    def validate_event_id(cls, v: str) -> str:
        return validate_uuid(v)


class PublicResponse(BaseModel):
    """Public response projected to browser - excludes toolCalls"""
    protocolVersion: ProtocolVersion = "1"
    runId: str
    revision: int
    status: str
    reply: str
    questions: Optional[List[ClarifyQuestion]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    # toolCalls intentionally excluded - never exposed to browser


# ============================================================================
# Canary Detection
# ============================================================================

BRAIN_CANARY = "GHOST_BRAIN_SERVER_ONLY_CANARY_2026"


def check_response_for_canary(response: str) -> bool:
    """Check if a response contains the Brain canary marker"""
    return BRAIN_CANARY in response


def compute_payload_digest(payload: Dict[str, Any]) -> str:
    """Compute SHA-256 digest of a payload for deduplication"""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()