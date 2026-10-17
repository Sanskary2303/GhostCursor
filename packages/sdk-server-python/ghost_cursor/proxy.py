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
import asyncio
from urllib.parse import urlsplit
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
    field_validator,
    model_validator,
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
    sessionId: Optional[uuid.UUID] = None
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
    tool_timeout: float = Field(default=10.0, description="Tool execution timeout in seconds")
    filter_response: Optional[Callable[[dict, str], Awaitable[dict]]] = None

    insecure_http_hosts: List[str] = Field(
        default_factory=lambda: [h.strip().lower() for h in os.getenv("GHOST_CURSOR_INSECURE_HTTP_HOSTS", "").split(",") if h.strip()]
    )

    @model_validator(mode="after")
    def validate_service_url(self) -> "GhostCursorConfig":
        parsed = urlsplit(self.service_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("service_url scheme must be https or http")
        if not parsed.hostname:
            raise ValueError("service_url must have a host")
        allowed_http = {"localhost", "127.0.0.1", "::1", *(h.lower() for h in self.insecure_http_hosts)}
        if parsed.scheme == "http" and parsed.hostname not in allowed_http:
            raise ValueError("http service_url is only allowed for localhost or hosts listed in insecure_http_hosts")
        if parsed.username or parsed.password:
            raise ValueError("service_url must not contain username or password")
        if parsed.query or parsed.fragment:
            raise ValueError("service_url must not contain query or fragment")
        return self


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
    loopbackSignature: Optional[Dict[str, Any]] = None


# ============================================================================
# Gateway Loopback Protocol
# ============================================================================

def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    if not salt:
        salt = b"\x00" * 32
    return hmac.new(salt, ikm, hashlib.sha256).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int = 32) -> bytes:
    t = b""
    okm = b""
    i = 1
    while len(okm) < length:
        t = hmac.new(prk, t + info + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return okm[:length]


def hkdf_sha256(ikm: bytes, salt: bytes = b"", info: bytes = b"", length: int = 32) -> bytes:
    """RFC 5869 HKDF-SHA256 key derivation function."""
    prk = hkdf_extract(salt, ikm)
    return hkdf_expand(prk, info, length)


def loopback_key(api_key: str) -> bytes:
    """Derive 32-byte loopback key from customer API key via HKDF-SHA256."""
    return hkdf_sha256(api_key.encode("utf-8"), salt=b"", info=b"ghost-loopback-v1", length=32)


def canonical_tool_calls(tool_calls: Any) -> str:
    """Format tool calls as canonical JSON (recursive sorted keys, separators (',', ':'), ensure_ascii=False)."""
    def _to_plain(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return _to_plain(obj.model_dump())
        if isinstance(obj, dict):
            return {k: _to_plain(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_plain(item) for item in obj]
        return obj

    plain = _to_plain(tool_calls)
    return json.dumps(plain, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sign_tool_batch(
    key: bytes,
    tenant: str,
    run_id: str,
    revision: int,
    tool_calls: Any,
    ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Sign a batch of tool calls with HMAC-SHA256."""
    if ts is None:
        ts = int(time.time())
    canonical = canonical_tool_calls(tool_calls)
    message = f"{tenant}.{ts}.{run_id}.{revision}.{canonical}".encode("utf-8")
    sig = hmac.new(key, message, hashlib.sha256).hexdigest()
    return {
        "v": 1,
        "ts": ts,
        "sig": sig,
    }


def verify_tool_batch(
    key: bytes,
    tenant: str,
    run_id: str,
    revision: int,
    tool_calls: Any,
    signature_payload: Optional[Dict[str, Any]],
    now: Optional[int] = None,
    max_age_seconds: int = 300,
) -> bool:
    """Verify HMAC-SHA256 signature on an incoming tool batch."""
    if not signature_payload or not isinstance(signature_payload, dict):
        return False
    if signature_payload.get("v") != 1:
        return False
    ts = signature_payload.get("ts")
    sig = signature_payload.get("sig")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not isinstance(sig, str):
        return False
    ts_int = int(ts)
    if now is None:
        now = int(time.time())
    if abs(now - ts_int) > max_age_seconds:
        return False
    canonical = canonical_tool_calls(tool_calls)
    message = f"{tenant}.{ts_int}.{run_id}.{revision}.{canonical}".encode("utf-8")
    expected = hmac.new(key, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)

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
        self._background: set = set()

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get a new HTTP client instance"""
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.config.request_timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=False,
        )

    async def close(self):
        """Close HTTP client (noop; clients are scoped to handle_turn lifecycle)"""
        pass

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
            schema_model = None
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                schema_model = schema
                if hasattr(schema, "model_json_schema"):
                    params = schema.model_json_schema()
                else:
                    params = schema.schema()
            elif hasattr(schema, "model_json_schema"):
                params = schema.model_json_schema()
            elif hasattr(schema, "schema"):
                params = schema.schema()
            elif not isinstance(schema, dict):
                params = {"type": "object", "properties": {}}

            if schema_model is None and fn:
                try:
                    sig = inspect.signature(fn)
                    p_list = list(sig.parameters.values())
                    if p_list and isinstance(p_list[0].annotation, type) and issubclass(p_list[0].annotation, BaseModel):
                        schema_model = p_list[0].annotation
                except Exception:
                    pass

            tool = BackendTool(
                name=name,
                description=description,
                parameters=params,
                read_only=read_only,
                execute_fn=fn,
                schema_model=schema_model,
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

        raw_client = self._get_http_client()
        client = await raw_client if inspect.isawaitable(raw_client) else raw_client
        async with client:
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
                response = await self._call_hosted_api(hosted_request, user_id, client=client)
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
                response = await self._call_hosted_api(continue_request, user_id, client=client)

            # Handle tool calls if any (Gateway Loopback) - loop up to max_tool_rounds
            rounds = 0
            executed_tool_calls: List[Dict[str, str]] = []
            while response.toolCalls and rounds < self.config.max_tool_rounds:
                rounds += 1
                for tc in response.toolCalls:
                    executed_tool_calls.append({"id": tc.id, "tool": tc.tool})

                # Verify HMAC loopback signature before executing local tools
                key = loopback_key(self.config.api_key)
                if not verify_tool_batch(
                    key=key,
                    tenant=self.config.tenant_id,
                    run_id=response.runId,
                    revision=response.revision,
                    tool_calls=response.toolCalls,
                    signature_payload=response.loopbackSignature,
                ):
                    raise GatewayError(502, "bad_tool_signature")

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
                response = await self._call_hosted_api(continue_request, user_id, client=client)

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
                await self._persist_turn(payload, safe_response, user_id, executed_tool_calls=executed_tool_calls)

            return result

    def handle_turn_sync(
        self,
        payload: Dict[str, Any],
        user_id: str,
        current_page: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronously execute a conversation turn using asyncio.run."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(
                    asyncio.run,
                    self.handle_turn(payload=payload, user_id=user_id, current_page=current_page),
                ).result()

        return asyncio.run(self.handle_turn(payload=payload, user_id=user_id, current_page=current_page))

    async def _call_hosted_api(
        self,
        request: HostedRunRequest,
        user_id: str,
        client: Optional[httpx.AsyncClient] = None,
    ) -> HostedRunResponse:
        """Call Ghost Cursor Cloud API"""
        if client is None:
            raw_client = self._get_http_client()
            client_inst = await raw_client if inspect.isawaitable(raw_client) else raw_client
            async with client_inst:
                return await self._call_hosted_api(request, user_id, client=client_inst)

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
            async with client.stream("POST", url, json=post_data, headers=headers) as response:
                if response.status_code >= 400:
                    error_map = {404: "run_not_found", 409: "conflict", 410: "run_expired"}
                    if response.status_code in error_map:
                        raise GatewayError(response.status_code, error_map[response.status_code])
                    raise GatewayError(502, "upstream_error")
                elif response.status_code < 200 or response.status_code >= 300:
                    raise GatewayError(502, "upstream_error")

                chunks = []
                total_bytes = 0
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    if total_bytes > self.config.max_response_size:
                        raise GatewayError(502, "upstream_too_large")
                    chunks.append(chunk)

                body = b"".join(chunks)
        except GatewayError:
            raise
        except httpx.HTTPError:
            raise GatewayError(502, "upstream_unavailable")

        try:
            data = json.loads(body)
        except Exception:
            raise GatewayError(502, "upstream_error")

        return HostedRunResponse(**data)

    async def _execute_local_tools(
        self,
        run_id: str,
        revision: int,
        tool_calls: List[ToolCallRequest],
        user_id: str,
    ) -> List[ToolCallResponse]:
        """Execute tool calls locally via Gateway Loopback"""
        if len(tool_calls) > self.config.max_tool_calls_per_round:
            return [
                ToolCallResponse(
                    id=tc.id,
                    ok=False,
                    error="too many tool calls in one plan",
                )
                for tc in tool_calls
            ]

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

            # Validate arguments
            try:
                tool.validate_arguments(tool_call.parameters)
            except Exception:
                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=False,
                    error="invalid arguments",
                ))
                continue

            try:
                # Execute with user context
                context = {
                    "user_id": user_id,
                    "run_id": run_id,
                    "revision": revision,
                    "idempotency_key": f"{run_id}:{revision}:{tool_call.id}",
                }
                output = await asyncio.wait_for(
                    tool.execute(tool_call.parameters, context),
                    timeout=self.config.tool_timeout,
                )

                # Truncate output if too large
                output_str = json.dumps(output)
                if len(output_str) > self.config.max_tool_output_size:
                    output = {"truncated": True, "message": "Output exceeded 16KB limit"}

                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=True,
                    output=output,
                ))
            except asyncio.TimeoutError:
                results.append(ToolCallResponse(
                    id=tool_call.id,
                    ok=False,
                    error="tool timed out",
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
        executed_tool_calls: Optional[List[Dict[str, str]]] = None,
    ):
        """Persist conversation turn to chat store"""
        if not self.chat_store or not response.runId:
            return

        try:
            command = request_payload.get("command")
            session = None
            if command == "start":
                session_id_val = request_payload.get("sessionId")
                if session_id_val:
                    session = await self.chat_store.get_session(str(session_id_val), user_id)
                if not session:
                    user_msg = request_payload.get("message") or "New Conversation"
                    title = str(user_msg)[:50]
                    session = await self.chat_store.create_session(
                        user_id=user_id,
                        tenant_id=self.config.tenant_id,
                        title=title,
                    )
                session_id = session.session_id
            else:
                # continue
                run_id = str(response.runId)
                session = await self.chat_store.find_session_by_run(run_id, user_id)
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
                text = str(request_payload["message"])
                messages.append({
                    "role": "user",
                    "content": text,
                    "run_id": str(response.runId),
                    "token_count": max(1, len(text) // 4),
                })
            elif request_payload.get("answer"):
                text = str(request_payload["answer"])
                messages.append({
                    "role": "user",
                    "content": text,
                    "run_id": str(response.runId),
                    "token_count": max(1, len(text) // 4),
                })

            if response.reply is not None:
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": response.reply,
                    "run_id": str(response.runId),
                    "token_count": max(1, len(str(response.reply)) // 4),
                    "client_actions": [
                        a if isinstance(a, dict) else a.model_dump() for a in (response.actions or [])
                    ],
                    "tool_calls": executed_tool_calls or [],
                }
                messages.append(assistant_msg)

            if messages:
                await self.chat_store.append_messages(session_id, user_id, messages)

            user_turns = await self.chat_store.count_turns(session_id, user_id)
            if user_turns > 0 and user_turns % 4 == 0:
                task = asyncio.create_task(self.summarize_session(session_id, user_id))
                self._background.add(task)
                task.add_done_callback(self._background.discard)
        except Exception as e:
            logger.warning(f"Failed to persist chat turn: {e}")

    async def summarize_session(self, session_id: str, user_id: str) -> None:
        """Background worker that calls orchestrator /v1/summaries, falling back to heuristic."""
        if not self.chat_store:
            return
        try:
            messages = await self.chat_store.get_messages(session_id, user_id)
            convo = [{"role": m.role, "text": m.content} for m in messages if m.role in ("user", "assistant")]
            if not convo:
                return

            title: Optional[str] = None
            summary: Optional[str] = None
            try:
                base_url = self.config.service_url.rstrip("/")
                if base_url.endswith("/v1/runs"):
                    base_url = base_url[:-len("/v1/runs")]
                elif base_url.endswith("/v1"):
                    base_url = base_url[:-len("/v1")]
                url = f"{base_url}/v1/summaries"
                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "X-Ghost-Subject": user_id,
                    "Content-Type": "application/json",
                }
                raw_client = self._get_http_client()
                client = await raw_client if inspect.isawaitable(raw_client) else raw_client
                async with client:
                    resp = await client.post(
                        url,
                        json={"messages": convo[-40:]},
                        headers=headers,
                        timeout=self.config.request_timeout,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if isinstance(data, dict):
                            t = data.get("title")
                            s = data.get("summary")
                            if isinstance(t, str) and isinstance(s, str):
                                title = t
                                summary = s
            except Exception as e:
                logger.warning(f"Failed to fetch summary from orchestrator: {type(e).__name__}")

            if not title or not summary:
                s_heur, t_heur = await self.chat_store.generate_summary_and_title(session_id, user_id)
                title = title or t_heur
                summary = summary or s_heur

            await self.chat_store.update_session_metadata(
                session_id=session_id,
                user_id=user_id,
                title=title,
                summary=summary,
            )
        except Exception as e:
            logger.warning(f"Failed to summarize session {session_id}: {type(e).__name__}")

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