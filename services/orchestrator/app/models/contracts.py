"""
Protocol V1 Contract Definitions

Strict runtime protocol models for Ghost Cursor API.
"""

import math
import re
import hashlib
import json
from typing import Any, Dict, List, Literal, Optional, Union
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


class _Strict(BaseModel):
    """Base model that strictly forbids extra unknown fields"""
    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Primitive Constraints
# ============================================================================

ProtocolVersion = Literal["1"]

LOGICAL_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.:-]+$")
SUBJECT_PATTERN = re.compile(r"^[a-zA-Z0-9_.:@-]+$")
UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

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


RunStatusLiteral = Literal[
    "awaiting_tools",
    "awaiting_actions",
    "awaiting_answer",
    "completed",
    "failed",
    "cancelled",
]


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

class PageContext(_Strict):
    """Browser page context"""
    page: str = Field(default="unknown", max_length=200)
    values: Dict[str, Union[StrictBool, StrictInt, StrictFloat, StrictStr]] = Field(default_factory=dict)
    availableTargets: List[str] = Field(default_factory=list, max_length=MAX_TARGETS)

    @field_validator("values")
    @classmethod
    def validate_values(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if len(v) > 100:
            raise ValueError("Values may contain at most 100 keys")
        for key, value in v.items():
            if isinstance(value, float):
                if not math.isfinite(value):
                    raise ValueError(f"Value for '{key}' must be a finite number")
            if isinstance(value, str) and len(value) > MAX_SCALAR_LENGTH:
                raise ValueError(f"Value for '{key}' exceeds {MAX_SCALAR_LENGTH} characters")
        return v

    @field_validator("availableTargets")
    @classmethod
    def validate_targets(cls, v: List[str]) -> List[str]:
        if len(v) > MAX_TARGETS:
            raise ValueError(f"At most {MAX_TARGETS} available targets")
        return v


class ToolDeclaration(_Strict):
    """Customer backend tool declaration"""
    name: str = Field(..., max_length=64)
    description: str = Field(..., max_length=1000)
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not TOOL_NAME_PATTERN.match(v):
            raise ValueError("Tool name must match ^[a-z][a-z0-9_]*$")
        return v


# ============================================================================
# Tool Call Models
# ============================================================================

class ToolCallRequest(BaseModel):
    """Tool call from the agent"""
    id: str
    tool: str
    parameters: Dict[str, Any]


class ToolCallResponse(_Strict):
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

class ClarifyQuestion(_Strict):
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

class HostedCreateRunRequest(_Strict):
    """POST /v1/runs - Create a new run"""
    protocolVersion: ProtocolVersion = Field(default="1")
    requestId: str = Field(...)
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    context: PageContext = Field(default_factory=PageContext)
    brain: Optional[str] = Field(default=None, max_length=MAX_BRAIN_LENGTH)
    capabilities: List[str] = Field(default_factory=list)
    tools: List[ToolDeclaration] = Field(default_factory=list, max_length=32)

    @field_validator("requestId")
    @classmethod
    def validate_request_id(cls, v: str) -> str:
        return validate_uuid(v)


class HostedContinueRunRequest(_Strict):
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
    status: RunStatusLiteral
    reply: str
    questions: Optional[List[ClarifyQuestion]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    toolCalls: Optional[List[ToolCallRequest]] = None
    loopbackSignature: Optional[Dict[str, Any]] = None

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
# Action Validation
# ============================================================================

ACTION_TYPES = {
    "navigate",
    "click",
    "fill_input",
    "select_option",
    "toggle_switch",
    "guided_tour",
}


def validate_actions(actions: Any) -> List[Dict[str, Any]]:
    """
    Validate frontend action plan against strict schema.
    Raises ValueError on any violation.
    """
    if actions is None:
        return []
    if not isinstance(actions, list):
        raise ValueError("Actions must be a list")
    if len(actions) > 12:
        raise ValueError("A plan can have at most 12 actions")

    validated: List[Dict[str, Any]] = []
    for idx, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"Action at index {idx} must be a dictionary")

        action_type = action.get("type")
        if not action_type or not isinstance(action_type, str):
            raise ValueError(f"Action at index {idx} missing valid 'type'")

        allowed_keys = {"type", "id", "explanation"}

        if action_type == "navigate":
            allowed_keys.add("target_page")
            if "target_page" not in action:
                raise ValueError("navigate action missing 'target_page'")
            target_page = action["target_page"]
            if not isinstance(target_page, str) or not target_page:
                raise ValueError("navigate target_page must be a non-empty string")
            if len(target_page) > 200:
                raise ValueError("navigate target_page must be <= 200 characters")
            if ("://" in target_page or target_page.startswith("//")
                    or re.match(r"^[a-z][a-z0-9+.-]*:", target_page, re.IGNORECASE)):
                raise ValueError("navigate target_page must be an in-app page, not a URL")

        elif action_type == "click":
            allowed_keys.add("target_id")
            if "target_id" not in action:
                raise ValueError("click action missing 'target_id'")
            target_id = action["target_id"]
            if not isinstance(target_id, str):
                raise ValueError("click target_id must be a string")
            validate_logical_id(target_id)

        elif action_type == "fill_input":
            allowed_keys.add("target_id")
            allowed_keys.add("value")
            if "target_id" not in action:
                raise ValueError("fill_input action missing 'target_id'")
            target_id = action["target_id"]
            if not isinstance(target_id, str):
                raise ValueError("fill_input target_id must be a string")
            validate_logical_id(target_id)
            if "value" not in action:
                raise ValueError("fill_input action missing 'value'")
            value = action["value"]
            if isinstance(value, (list, dict, set, tuple)) or not isinstance(value, (str, int, float, bool)):
                raise ValueError("fill_input value must be a scalar")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("fill_input float value must be finite")
            if isinstance(value, str) and len(value) > MAX_SCALAR_LENGTH:
                raise ValueError(f"fill_input string value exceeds {MAX_SCALAR_LENGTH} characters")

        elif action_type == "select_option":
            allowed_keys.add("target_id")
            allowed_keys.add("option")
            if "target_id" not in action:
                raise ValueError("select_option action missing 'target_id'")
            target_id = action["target_id"]
            if not isinstance(target_id, str):
                raise ValueError("select_option target_id must be a string")
            validate_logical_id(target_id)
            if "option" not in action:
                raise ValueError("select_option action missing 'option'")
            option = action["option"]
            if not isinstance(option, str) or not option or len(option) > 200:
                raise ValueError("select_option option must be a non-empty string <= 200 characters")

        elif action_type == "toggle_switch":
            allowed_keys.add("target_id")
            allowed_keys.add("state")
            if "target_id" not in action:
                raise ValueError("toggle_switch action missing 'target_id'")
            target_id = action["target_id"]
            if not isinstance(target_id, str):
                raise ValueError("toggle_switch target_id must be a string")
            validate_logical_id(target_id)
            if "state" not in action:
                raise ValueError("toggle_switch action missing 'state'")
            state = action["state"]
            if not isinstance(state, bool):
                raise ValueError("toggle_switch state must be a boolean")

        elif action_type == "guided_tour":
            allowed_keys.add("steps")
            if "steps" not in action:
                raise ValueError("guided_tour action missing 'steps'")
            steps = action["steps"]
            if not isinstance(steps, list) or not (1 <= len(steps) <= 10):
                raise ValueError("guided_tour steps must be a list of 1 to 10 steps")
            for s_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    raise ValueError(f"guided_tour step at index {s_idx} must be a dict")
                if "target_id" not in step:
                    raise ValueError(f"guided_tour step at index {s_idx} missing 'target_id'")
                s_tid = step["target_id"]
                if not isinstance(s_tid, str):
                    raise ValueError(f"guided_tour step target_id must be a string")
                validate_logical_id(s_tid)
                if "message" not in step:
                    raise ValueError(f"guided_tour step at index {s_idx} missing 'message'")
                msg = step["message"]
                if not isinstance(msg, str) or not msg or len(msg) > 500:
                    raise ValueError(f"guided_tour step message must be a string <= 500 characters")
                step_extra = set(step.keys()) - {"target_id", "message", "spotlight"}
                if step_extra:
                    raise ValueError(f"guided_tour step contains unexpected keys: {step_extra}")
        else:
            raise ValueError(f"Unknown action type: {action_type}")

        extra_keys = set(action.keys()) - allowed_keys
        if extra_keys:
            raise ValueError(f"Action contains unexpected keys: {extra_keys}")

        if "explanation" in action:
            exp = action["explanation"]
            if exp is not None and (not isinstance(exp, str) or len(exp) > 500):
                raise ValueError("explanation must be a string <= 500 characters")

        if "id" in action:
            act_id = action["id"]
            if act_id is not None and (not isinstance(act_id, str) or len(act_id) > 120):
                raise ValueError("action id must be a string <= 120 characters")

        validated.append(action)

    return validated


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