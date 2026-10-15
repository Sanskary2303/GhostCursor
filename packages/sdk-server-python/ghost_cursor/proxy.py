"""
Ghost Cursor Backend Proxy

Secure gateway that authenticates users, loads private Brain context,
forwards requests to Ghost Cursor Cloud, and handles local tool execution.
"""

import os
import hmac4
import hashlib
import json
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Awaitable
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import httpx
from pydantic import BaseModel, Field, validator

from .storage import ChatStore
from .brain_loader import BrainLoader
from .tools import Tool, ToolRegistry


# ============================================================================
# Configuration Models
# ============================================================================

class GhostCursorConfig(BaseModel):
    """Configuration for Ghost Cursor Backend"""
    api_key: str = Field(..., min_length=32, description="Server-to-server API key")
    tenant_id: str = Field(..., min_length=1, max_length=64, description="Tenant identifier")
    brain_dir: str = Field(default="./brain", description="Path to brain markdown files")
    service_url: str = Field(default="https://api.ghostcursor.ai", description="Ghost Cursor Cloud URL")
    chat_store: Optional[ChatStore] = None
    request_timeout: float = Field(default=210.0, description="Request timeout in seconds")
    max_tool_rounds: int = Field(default=4, description="Max tool rounds per request")
    max_tool_calls_per_round: int = Field(default=4, description="Max tool calls per model plan")
    max_response_size: int = Field(default=256 * 1024, description="Max response size in bytes")
    max_tool_output_size: int = Field(default=16000, description="Max tool output size in characters")


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

    def __init__(self, config: GhostCursorConfig):
        self.config = config
        self.brain_loader = BrainLoader(config.brain_dir)
        self.tool_registry = ToolRegistry()
        self.loopback = GatewayLoopback(config.tenant_id, config.api_key)
        self.chat_store = config.chat_store
        self._http_client: Optional[httpx.AsyncClient] = None

        # Register default frontend action tools
        self._register_frontend_tools()

    def _register_frontend_tools(self):
        """Register the standard frontend action tools"""
        from .tools import FrontendActionTool

        # These are declared so the orchestrator knows they exist
        # Actual execution happens on the frontend
        frontend_tools = [
            FrontendActionTool(
                name="navigate",
                description="Navigate to another page within the application",
                parameters={
                    "type": "object",
                    "properties": {
                        "target_page": {"type": "string", "description": "Target page route"},
                        "explanation": {"type": "string", "description": "Why this navigation is needed"},
                    },
                    "required": ["target_page", "explanation"],
                },
            ),
            FrontendActionTool(
                name="click",
                description="Click a registered button, link, or tab",
                parameters={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string", "description": "Logical target ID to click"},
                        "explanation": {"type": "string", "description": "Why this click is needed"},
                    },
                    "required": ["target_id", "explanation"],
                },
            ),
            FrontendActionTool(
                name="fill_input",
                description="Type or set a value in a registered input or textarea",
                parameters={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string", "description": "Logical target ID"},
                        "value": {"type": ["string", "number", "boolean"], "description": "Value to set"},
                        "explanation": {"type": "string", "description": "Why this input is needed"},
                    },
                    "required": ["target_id", "value", "explanation"],
                },
            ),
            FrontendActionTool(
                name="toggle_switch",
                description="Toggle a switch or checkbox to true or false",
                parameters={
                    "type": "object",
                    "properties": {
                        "target_id": {"type": "string", "description": "Logical target ID"},
                        "state": {"type": "boolean", "description": "Desired state (true/false)"},
                        "explanation": {"type": "string", "description": "Why this toggle is needed"},
                    },
                    "required": ["target_id", "state", "explanation"],
                },
            ),
            FrontendActionTool(
                name="guided_tour",
                description="Run an interactive guided tour spotlighting elements with explanations",
                parameters={
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "target_id": {"type": "string"},
                                    "message": {"type": "string"},
                                    "spotlight": {"type": "boolean", "default": True},
                                },
                                "required": ["target_id", "message"],
                            },
                        },
                    },
                    "required": ["steps"],
                },
            ),
            FrontendActionTool(
                name="ask_clarification",
                description="Ask the user a clarifying question before proceeding",
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Question to ask"},
                        "options": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
                    },
                    "required": ["question", "options"],
                },
            ),
        ]

        for tool in frontend_tools:
            self.tool_registry.register(tool)

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
        schema: Dict[str, Any],
        read_only: bool = True,
        execute_fn: Optional[Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Any]]] = None,
    ):
        """Register a customer backend read-only tool"""
        from .tools import BackendTool

        tool = BackendTool(
            name=name,
            description=description,
            parameters=schema,
            read_only=read_only,
            execute_fn=execute_fn,
        )
        self.tool_registry.register(tool)

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Get all registered tool declarations for the orchestrator"""
        return [tool.to_declaration() for tool in self.tool_registry.get_all()]

    async def handle_turn(
        self,
        payload: Dict[str, Any],
        user_id: str,
        current_page: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Handle a user turn: load brain, proxy to Ghost Cursor Cloud,
        execute any local tools, and return public response.
        """
        # Validate input
        if not payload.get("message"):
            raise ValueError("Message is required")

        # Load brain context
        page = current_page or payload.get("context", {}).get("page", "unknown")
        brain_content = self.brain_loader.load_context(page)

        # Get available targets from context
        available_targets = payload.get("context", {}).get("availableTargets", [])

        # Build request for Ghost Cursor Cloud
        request_id = payload.get("requestId") or str(uuid.uuid4())

        hosted_request = HostedRunRequest(
            protocolVersion="1",
            requestId=request_id,
            message=payload["message"],
            context=payload.get("context", {}),
            brain=brain_content,
            capabilities=[],
            tools=self.get_tool_declarations(),
        )

        # Send to Ghost Cursor Cloud
        response = await self._call_hosted_api(hosted_request, user_id)

        # Handle tool calls if any (Gateway Loopback)
        if response.toolCalls:
            tool_results = await self._execute_local_tools(
                response.runId,
                response.revision,
                response.toolCalls,
                user_id,
            )

            # Continue run with tool results
            continue_request = HostedRunRequest(
                protocolVersion="1",
                eventId=str(uuid.uuid4()),
                revision=response.revision,
                kind="tools",
                results=tool_results,
            )
            response = await self._call_hosted_api(continue_request, user_id)

        # Persist chat history if store available
        if self.chat_store:
            await self._persist_turn(payload, response, user_id)

        # Return public projection (exclude toolCalls, brain, etc.)
        return self._project_public_response(response)

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

        url = f"{self.config.service_url}/v1/runs"
        if request.eventId:
            url = f"{self.config.service_url}/v1/runs/{request.requestId or ''}/continue"

        response = await client.post(
            url,
            json=request.model_dump(exclude_none=True),
            headers=headers,
        )

        response.raise_for_status()
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

        # This would typically create/update a session and append messages
        # Implementation depends on the chat store interface
        pass

    def _project_public_response(self, response: HostedRunResponse) -> Dict[str, Any]:
        """Project internal response to public envelope (exclude internals)"""
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