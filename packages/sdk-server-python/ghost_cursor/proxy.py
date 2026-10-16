"""
Ghost Cursor Backend Proxy

Secure gateway that authenticates users, loads private Brain context,
forwards requests to Ghost Cursor Cloud, and handles local tool execution.
"""

import os
import hmac
import hashlib
import json
import time
import uuid
import logging
import inspect
from typing import Any, Callable, Dict, List, Literal, Optional, Union, Awaitable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import httpx
from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    ValidationError,
)

from .storage import ChatStore
from .brain_loader import BrainLoader
from .tools import Tool, ToolRegistry

logger = logging.getLogger(__name__)


# ============================================================================
# Gateway Error & Browser Protocol Models
# ============================================================================

class GatewayError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrowserContext(_Strict):
    page: str = Field(default="unknown", max_length=200)
    values: Dict[str, Union[StrictBool, StrictInt, StrictFloat, StrictStr]] = Field(default_factory=dict, max_length=100)
    availableTargets: List[str] = Field(default_factory=list, max_length=100)


class BrowserStart(_Strict):
    command: Literal["start"]
    protocolVersion: Literal["1"] = "1"
    requestId: uuid.UUID
    message: str = Field(min_length=1, max_length=6000)
    context: BrowserContext = Field(default_factory=BrowserContext)


class BrowserResult(_Strict):
    id: str = Field(min_length=1, max_length=120)
    ok: bool
    output: Optional[Any] = None
    error: Optional[str] = Field(default=None, max_length=500)


class BrowserContinue(_Strict):
    command: Literal["continue"]
    protocolVersion: Literal["1"] = "1"
    runId: uuid.UUID
    eventId: uuid.UUID
    revision: int = Field(ge=0)
    kind: Literal["actions", "answer", "cancel"]
    results: List[BrowserResult] = Field(default_factory=list, max_length=12)
    answer: Optional[str] = Field(default=None, max_length=6000)
    context: Optional[BrowserContext] = None


class PublicEnvelope(_Strict):
    """Strict browser-facing public envelope with extra='forbid' and the 7 public keys"""
    protocolVersion: Literal["1"] = "1"
    runId: str
    revision: int = Field(ge=0)
    status: Literal["awaiting_actions", "awaiting_answer", "completed", "failed", "cancelled"]
    reply: str
    questions: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None


BRAIN_CANARY = "GHOST_BRAIN_SERVER_ONLY_CANARY_2026"


# ============================================================================
# Configuration Models
# ============================================================================

class GhostCursorConfig(BaseModel):
    """Configuration for Ghost Cursor Backend"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: str = Field(..., min_length=32, description="Server-to-server API key")
    tenant_id: str = Field(default="shophive_demo", min_length=1, max_length=64, description="Tenant identifier")
    brain_dir: str = Field(default="./brain", description="Path to brain markdown files")
    service_url: str = Field(default="http://localhost:8080", description="Ghost Cursor Cloud URL")
    chat_store: Optional[ChatStore] = None
    request_timeout: float = Field(default=210.0, description="Request timeout in seconds")
    max_tool_rounds: int = Field(default=4, description="Max tool rounds per request")
    max_tool_calls_per_round: int = Field(default=4, description="Max tool calls per model plan")
    max_response_size: int = Field(default=256 * 1024, description="Max response size in bytes")
    max_tool_output_size: int = Field(default=16000, description="Max tool output size in characters")
    filter_response: Optional[Callable[[dict, str], Awaitable[dict]]] = None


class ToolCallRequest(BaseModel):
    """Incoming tool call request from Ghost Cursor Cloud"""
    id: str
    tool: str
    parameters: Dict[str, Any]


class ToolCallResponse(BaseModel):
    """Response to tool call request"""
    id: str
    ok: bool
    output: Optional[Any] = None
    error: Optional[str] = None


class HostedRunRequest(BaseModel):
    """Request to create/continue a run on Ghost Cursor Cloud"""
    protocolVersion: str = Field(default="1")
    requestId: Optional[str] = None
    runId: Optional[str] = None
    eventId: Optional[str] = None
    revision: Optional[int] = None
    message: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    brain: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    kind: Optional[str] = None
    results: Optional[List[ToolCallResponse]] = None
    answer: Optional[str] = None


class HostedRunResponse(BaseModel):
    """Response from Ghost Cursor Cloud"""
    protocolVersion: str = "1"
    runId: str
    revision: int
    status: str
    reply: str
    questions: Optional[List[Dict[str, Any]]] = None
    actions: Optional[List[Dict[str, Any]]] = None
    toolCalls: Optional[List[ToolCallRequest]] = None


# ============================================================================
# Gateway Loopback Protocol
# ============================================================================

class GatewayLoopback:
    """
    Handles the Gateway Loopback (Reverse-Dispatch) protocol for executing
    customer backend tools locally with HMAC verification.
    """

    def __init__(self, tenant_id: str, secret_key: str):
        self.tenant_id = tenant_id
        self.secret_key = secret_key.encode()

    def sign_payload(self, payload: Dict[str, Any]) -> Dict[str, str]:
        """Sign a payload with HMAC-SHA256 for tool execution requests"""
        # Create canonical payload for signing
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        timestamp = str(int(time.time()))

        message = f"{timestamp}.{canonical}".encode()
        signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()

        return {
            "X-Ghost-Signature": f"sha256={signature}",
            "X-Ghost-Timestamp": timestamp,
            "X-Ghost-Tenant-Id": self.tenant_id,
        }

    def verify_signature(self, headers: Dict[str, str], payload: Dict[str, Any]) -> bool:
        """Verify HMAC signature on incoming tool execution request"""
        signature_header = headers.get("X-Ghost-Signature")
        timestamp_header = headers.get("X-Ghost-Timestamp")
        tenant_header = headers.get("X-Ghost-Tenant-Id")

        if not all([signature_header, timestamp_header, tenant_header]):
            return False

        if tenant_header != self.tenant_id:
            return False

        # Check timestamp freshness (5 minute window)
        try:
            timestamp = int(timestamp_header)
            if abs(time.time() - timestamp) > 300:
                return False
        except ValueError:
            return False

        # Verify signature
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        message = f"{timestamp_header}.{canonical}".encode()
        expected_signature = hmac.new(self.secret_key, message, hashlib.sha256).hexdigest()

        provided_signature = signature_header.replace("sha256=", "")
        return hmac.compare_digest(expected_signature, provided_signature)

    def create_tool_execution_request(
        self,
        run_id: str,
        revision: int,
        tool_calls: List[ToolCallRequest]
    ) -> Dict[str, Any]:
        """Create a signed tool execution request to send to customer gateway"""
        payload = {
            "runId": run_id,
            "revision": revision,
            "toolCalls": [tc.model_dump() for tc in tool_calls],
        }

        headers = self.sign_payload(payload)
        return {"payload": payload, "headers": headers}


# ============================================================================
# Main Backend Class
# ============================================================================

class GhostCursorBackend:
    """
    Main entry point for Ghost Cursor Backend SDK.
    Handles proxying requests to Ghost Cursor Cloud and executing local tools.
    """

    def __init__(self, config: Optional[GhostCursorConfig] = None, **kwargs):
        if config is None:
            config = GhostCursorConfig(**kwargs)
        self.config = config
        self.brain_loader = BrainLoader(config.brain_dir)
        self.tool_registry = ToolRegistry()
        self.loopback = GatewayLoopback(config.tenant_id, config.api_key)
        self.chat_store = config.chat_store
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.request_timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http_client

    async def close(self):
        """Close HTTP client"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    def attach_chat_store(self, chat_store: ChatStore):
        """Attach a chat store for conversation persistence"""
        self.chat_store = chat_store

    def register_tool(
        self,
        name: str,
        description: str,
        schema: Any,
        read_only: bool = True,
        execute_fn: Optional[Callable] = None,
    ):
        """Register a customer backend read-only tool. Supports direct call and decorator."""
        from .tools import BackendTool

        def _make_tool(fn):
            params = schema
            if hasattr(schema, "model_json_schema"):
                params = schema.model_json_schema()
            elif hasattr(schema, "schema"):
                params = schema.schema()
            elif not isinstance(schema, dict):
                params = {"type": "object", "properties": {}}

            tool = BackendTool(
                name=name,
                description=description,
                parameters=params,
                read_only=read_only,
                execute_fn=fn,
            )
            self.tool_registry.register(tool)
            return tool

        if execute_fn is not None:
            return _make_tool(execute_fn)

        def decorator(fn):
            _make_tool(fn)
            return fn

        return decorator

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get all registered customer backend tool declarations for the orchestrator"""
        from .tools import BackendTool
        return [tool.to_declaration() for tool in self.tool_registry.get_all() if isinstance(tool, BackendTool)]

    async def handle_turn(
        self,
        payload: Dict[str, Any],
        user_id: str,
        current_page: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle a user turn: load brain, proxy to Ghost Cursor Cloud,
        execute any local tools, and return public response.
        Supports both new runs (command: 'start') and continuation (command: 'continue').
        """
        if not isinstance(payload, dict):
            raise GatewayError(400, "invalid_request")

        try:
            if payload.get("command") == "start":
                req_model = BrowserStart.model_validate(payload)
            else:
                req_model = BrowserContinue.model_validate(payload)
        except ValidationError:
            raise GatewayError(400, "invalid_request")

        if isinstance(req_model, BrowserStart):
            # Load brain context
            page = current_page or req_model.context.page
            brain_content = self.brain_loader.load_context(page)

            hosted_request = HostedRunRequest(
                protocolVersion=req_model.protocolVersion,
                requestId=str(req_model.requestId),
                message=req_model.message,
                context=req_model.context.model_dump(),
                brain=brain_content,
                capabilities=[],
                tools=self.get_tool_declarations(),
            )

            # Send to Ghost Cursor Cloud
            response = await self._call_hosted_api(hosted_request, user_id)
        else:
            continue_request = HostedRunRequest(
                protocolVersion=req_model.protocolVersion,
                runId=str(req_model.runId),
                eventId=str(req_model.eventId),
                revision=req_model.revision,
                kind=req_model.kind,
                results=[
                    ToolCallResponse(
                        id=r.id,
                        ok=r.ok,
                        output=r.output,
                        error=r.error,
                    )
                    for r in req_model.results
                ] if req_model.results else None,
                answer=req_model.answer,
                context=req_model.context.model_dump() if req_model.context is not None else {},
            )
            response = await self._call_hosted_api(continue_request, user_id)

        # Handle tool calls if any (Gateway Loopback) - loop up to max_tool_rounds
        rounds = 0
        while response.toolCalls and rounds < self.config.max_tool_rounds:
            rounds += 1
            tool_results = await self._execute_local_tools(
                response.runId,
                response.revision,
                response.toolCalls,
                user_id,
            )

            # Continue run with tool results
            continue_request = HostedRunRequest(
                protocolVersion="1",
                runId=response.runId,
                eventId=str(uuid.uuid4()),
                revision=response.revision,
                kind="tools",
                results=tool_results,
            )
            response = await self._call_hosted_api(continue_request, user_id)

        if response.toolCalls or response.status == "awaiting_tools":
            raise GatewayError(502, "tool_round_limit")

        # Return public projection (exclude toolCalls, brain, etc.)
        public_resp = self._project_public_response(response)

        # Run optional response filter
        if self.config.filter_response:
            try:
                res = self.config.filter_response(public_resp, user_id)
                if inspect.isawaitable(res):
                    public_resp = await res
                else:
                    public_resp = res
            except GatewayError:
                raise
            except Exception as e:
                logger.warning(f"Filter response error: {e}")
                raise GatewayError(502, "bad_public_response")

        if not isinstance(public_resp, dict):
            raise GatewayError(502, "bad_public_response")

        try:
            envelope = PublicEnvelope.model_validate(public_resp)
            result = envelope.model_dump()
        except ValidationError:
            raise GatewayError(502, "bad_public_response")

        if BRAIN_CANARY in json.dumps(result):
            raise GatewayError(502, "disclosure_blocked")

        if self.chat_store:
            safe_response = response.model_copy(
                update={"reply": result["reply"], "actions": result["actions"]}
            )
            await self._persist_turn(payload, safe_response, user_id)

        return result

    async def _call_hosted_api(
        self,
        request: HostedRunRequest,
        user_id: str,
    ) -> HostedRunResponse:
        """Call Ghost Cursor Cloud API"""
        client = await self._get_http_client()

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Ghost-Subject": user_id,
            "Content-Type": "application/json",
        }

        is_continue = bool(request.eventId or request.kind)
        url = f"{self.config.service_url}/v1/runs"
        if is_continue:
            run_id = request.runId or request.requestId or ""
            url = f"{self.config.service_url}/v1/runs/{run_id}/continue"
            post_data: Dict[str, Any] = {
                "protocolVersion": request.protocolVersion,
                "eventId": request.eventId or str(uuid.uuid4()),
                "revision": request.revision if request.revision is not None else 0,
                "kind": request.kind or "actions",
            }
            if request.results is not None:
                post_data["results"] = [
                    r.model_dump() if hasattr(r, "model_dump") else r for r in request.results
                ]
            if request.answer is not None:
                post_data["answer"] = request.answer
            if request.context:
                post_data["context"] = request.context
        else:
            post_data = request.model_dump(exclude_none=True)

        try:
            response = await client.post(
                url,
                json=post_data,
                headers=headers,
            )
        except httpx.HTTPError:
            raise GatewayError(502, "upstream_unavailable")

        if response.status_code >= 400:
            error_map = {404: "run_not_found", 409: "conflict", 410: "run_expired"}
            if response.status_code in error_map:
                raise GatewayError(response.status_code, error_map[response.status_code])
            raise GatewayError(502, "upstream_error")

        data = response.json()

        # Validate response size
        response_text = json.dumps(data)
        if len(response_text.encode()) > self.config.max_response_size:
            raise ValueError("Response exceeds maximum size")

        return HostedRunResponse(**data)

    async def _execute_local_tools(
        self,
        run_id: str,
        revision: int,
        tool_calls: List[ToolCallRequest],
        user_id: str,
    ) -> List[ToolCallResponse]:
        """Execute tool calls locally via Gateway Loopback"""
        results = []

        for tool_call in tool_calls:
            tool = self.tool_registry.get(tool_call.tool)
            if not tool:
                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=False,
                    error=f"Tool not found: {tool_call.tool}",
                ))
                continue

            if not tool.read_only:
                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=False,
                    error=f"Tool {tool_call.tool} is not read-only",
                ))
                continue

            try:
                # Execute with user context
                context = {"user_id": user_id, "run_id": run_id, "revision": revision}
                output = await tool.execute(tool_call.parameters, context)

                # Truncate output if too large
                output_str = json.dumps(output)
                if len(output_str) > self.config.max_tool_output_size:
                    output = {"truncated": True, "message": "Output exceeded 16KB limit"}

                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=True,
                    output=output,
                ))
            except Exception as e:
                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=False,
                    error=str(e)[:500],  # Limit error message
                ))

        return results

    async def _persist_turn(
        self,
        request_payload: Dict[str, Any],
        response: HostedRunResponse,
        user_id: str,
    ):
        """Persist conversation turn to chat store"""
        if not self.chat_store or not response.runId:
            return

        try:
            session_id = request_payload.get("sessionId") or response.runId
            session = await self.chat_store.get_session(session_id, user_id)
            if not session:
                user_msg = request_payload.get("message") or request_payload.get("answer") or "New Conversation"
                title = str(user_msg)[:50]
                session = await self.chat_store.create_session(
                    user_id=user_id,
                    tenant_id=self.config.tenant_id,
                    title=title,
                )
                session_id = session.session_id

            messages = []
            if request_payload.get("message"):
                messages.append({
                    "role": "user",
                    "content": request_payload["message"],
                })
            elif request_payload.get("answer"):
                messages.append({
                    "role": "user",
                    "content": request_payload["answer"],
                })

            if response.reply:
                messages.append({
                    "role": "assistant",
                    "content": response.reply,
                    "client_actions": [
                        a if isinstance(a, dict) else a.model_dump() for a in (response.actions or [])
                    ],
                })

            if messages:
                await self.chat_store.append_messages(session_id, user_id, messages)
        except Exception as e:
            logger.warning(f"Failed to persist chat turn: {e}")

    def _project_public_response(self, response: HostedRunResponse) -> Dict[str, Any]:
        """Project internal response to public envelope (exclude internals)"""
        allowed = {"awaiting_actions", "awaiting_answer", "completed", "failed", "cancelled"}
        if response.status not in allowed:
            raise GatewayError(502, "bad_upstream_status")

        return {
            "protocolVersion": response.protocolVersion,
            "runId": response.runId,
            "revision": response.revision,
            "status": response.status,
            "reply": response.reply,
            "questions": response.questions,
            "actions": response.actions,
            # toolCalls is intentionally excluded
        }


# ============================================================================
# FastAPI Integration Helper
# ============================================================================

class GhostCursorProxy:
    """
    Simplified proxy for FastAPI/Flask/Django integration.
    Handles the browser-facing endpoint.
    """

    def __init__(self, backend: GhostCursorBackend):
        self.backend = backend

    async def handle_websocket(self, websocket, user_id: str):
        """Handle WebSocket connection from frontend"""
        # This would be implemented per framework
        raise NotImplementedError("Use framework-specific integration")

    async def handle_http(self, request_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
        """Handle HTTP request from frontend"""
        return await self.backend.handle_turn(request_data, user_id)


# Alias for backward compatibility
GhostCursorFastAPI = GhostCursorBackend