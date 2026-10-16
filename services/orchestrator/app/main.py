"""
Ghost Cursor Orchestrator - Main FastAPI Application

Google ADK Agent Engine with Vertex AI Gemini 2.0 integration.
"""

from __future__ import annotations

import collections
import copy
import hmac
import json
import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .agent import create_ghost_agent, GhostAgent
from .models.run import RunStore, RunState, RunStatus
from .models.contracts import (
    HostedCreateRunRequest,
    HostedContinueRunRequest,
    HostedRunResponse,
    ToolCallRequest,
    ToolCallResponse,
    ProtocolVersion,
    MAX_TURNS,
    ToolDeclaration,
    validate_actions,
)

EXPECTED_KINDS = {
    "awaiting_tools": {"tools", "cancel"},
    "awaiting_actions": {"actions", "cancel"},
    "awaiting_answer": {"answer", "cancel"},
}
from .tools.frontend_actions import FRONTEND_ACTION_TOOLS, FRONTEND_TOOL_NAMES, is_frontend_tool, normalize_schema
from .storage.run_store import PostgreSQLRunStore, InMemoryRunStore
from .llm.vertex import VertexAIClient, MockVertexAIClient
from .tools.loopback import GatewayLoopbackHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")


def load_tenant_keys() -> Dict[str, str]:
    raw = os.getenv("GHOST_TENANT_KEYS")
    if not raw:
        raise RuntimeError("GHOST_TENANT_KEYS is required")
    try:
        data = json.loads(raw)
    except Exception as e:
        raise RuntimeError(f"Invalid JSON in GHOST_TENANT_KEYS: {e}")
    if not isinstance(data, dict) or not data:
        raise RuntimeError("GHOST_TENANT_KEYS must be a non-empty object")
    for key, tenant in data.items():
        if not isinstance(key, str) or len(key) < 32:
            raise RuntimeError(f"Tenant API key must be at least 32 characters: {key[:8] if isinstance(key, str) else type(key)}...")
        if not isinstance(tenant, str) or not TENANT_ID_PATTERN.match(tenant):
            raise RuntimeError(f"Invalid tenant ID: {tenant!r}. Tenant must match ^[a-z0-9_]{{1,64}}$")
    return data


TENANT_KEYS: Dict[str, str] = load_tenant_keys()

# Global instances
run_store: Optional[RunStore] = None
vertex_client: Optional[VertexAIClient] = None
loopback_handler: Optional[GatewayLoopbackHandler] = None


def init_globals():
    """Ensure global services are initialized even if lifespan wasn't triggered (e.g. tests)"""
    global run_store, vertex_client, loopback_handler
    ghost_env = os.getenv("GHOST_ENV", "development").lower()
    ghost_provider = os.getenv("GHOST_PROVIDER")
    ghost_store = os.getenv("GHOST_STORE")

    if not ghost_provider or ghost_provider not in ("mock", "vertex"):
        raise RuntimeError(f"GHOST_PROVIDER must be 'mock' or 'vertex', got: {ghost_provider!r}")
    if not ghost_store or ghost_store not in ("memory", "postgres"):
        raise RuntimeError(f"GHOST_STORE must be 'memory' or 'postgres', got: {ghost_store!r}")

    if ghost_env == "production":
        if ghost_provider == "mock":
            raise RuntimeError("mock provider is not allowed in production")
        if ghost_store == "memory":
            raise RuntimeError("memory store is not allowed in production")

    if ghost_store == "postgres" and not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is required when GHOST_STORE is 'postgres'")

    if ghost_provider == "vertex" and not os.getenv("GCP_PROJECT_ID"):
        raise RuntimeError("GCP_PROJECT_ID is required when GHOST_PROVIDER is 'vertex'")

    if run_store is None:
        if ghost_store == "postgres":
            run_store = PostgreSQLRunStore(os.environ["DATABASE_URL"])
        else:
            run_store = InMemoryRunStore()

    if vertex_client is None:
        if ghost_provider == "vertex":
            project_id = os.environ["GCP_PROJECT_ID"]
            location = os.getenv("GCP_LOCATION", "us-central1")
            vertex_client = VertexAIClient(project_id=project_id, location=location)
        else:
            vertex_client = MockVertexAIClient()

    if loopback_handler is None:
        loopback_handler = GatewayLoopbackHandler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global run_store, vertex_client, loopback_handler

    init_globals()

    if isinstance(run_store, PostgreSQLRunStore):
        await run_store.initialize()
        logger.info("Initialized PostgreSQL run store")

    yield

    # Cleanup
    if run_store:
        await run_store.close()
    if vertex_client and hasattr(vertex_client, 'close'):
        await vertex_client.close()


app = FastAPI(
    title="Ghost Cursor Orchestrator",
    description="AI Co-pilot orchestration service with Google ADK and Vertex AI",
    version="0.1.0",
    lifespan=lifespan,
)

# Note: In-memory rate limiting is per-instance, not distributed across multiple workers/nodes.
RATE_LIMIT_STORE: Dict[str, collections.deque] = {}
rate_limit_store = RATE_LIMIT_STORE


@app.middleware("http")
async def security_and_limits_middleware(request: Request, call_next):
    if request.method == "POST":
        content_length_header = request.headers.get("content-length")
        if not content_length_header:
            return JSONResponse(
                status_code=411,
                content={"error": "length_required"},
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        try:
            content_length = int(content_length_header)
        except ValueError:
            return JSONResponse(
                status_code=411,
                content={"error": "length_required"},
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        if content_length > 65536:
            return JSONResponse(
                status_code=413,
                content={"error": "too_large"},
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        body = await request.body()
        if len(body) > 65536:
            return JSONResponse(
                status_code=413,
                content={"error": "too_large"},
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

        # Rate limiting: key is request.client.host (fallback to 127.0.0.1 if None)
        client_host = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        limit = int(os.getenv("GHOST_RATE_LIMIT_PER_MIN", "60"))
        dq = RATE_LIMIT_STORE.setdefault(client_host, collections.deque())
        while dq and dq[0] <= now - 60.0:
            dq.popleft()

        if len(dq) >= limit:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited"},
                headers={
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        dq.append(now)

    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ============================================================================
# Authentication & Authorization
# ============================================================================

async def verify_tenant_credentials(
    authorization: str = Header(...),
    x_ghost_subject: str = Header(..., alias="X-Ghost-Subject"),
) -> Tuple[str, str]:
    """
    Verify server-to-server credentials and extract tenant/subject.

    Expected format: Authorization: Bearer <api_key>
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")

    api_key = authorization[7:]  # Remove "Bearer "

    matched_tenant = None
    for k, t in TENANT_KEYS.items():
        if hmac.compare_digest(k, api_key):
            matched_tenant = t

    if not matched_tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate subject format
    if not x_ghost_subject or not (1 <= len(x_ghost_subject) <= 120):
        raise HTTPException(status_code=400, detail="Invalid X-Ghost-Subject")

    if not re.match(r'^[a-zA-Z0-9_.:@-]+$', x_ghost_subject):
        raise HTTPException(status_code=400, detail="Invalid subject format")

    return matched_tenant, x_ghost_subject


def reject_origin_requests(request: Request):
    """Reject requests with Origin header (defense in depth)"""
    if request.headers.get("origin"):
        raise HTTPException(status_code=403, detail="Direct browser access not allowed")


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health")
async def health_check():
    """Liveness probe - no secrets required"""
    return {
        "status": "ok",
        "service": "ghost-cursor-orchestrator",
        "version": "0.1.0",
    }


def _register_pending(response: HostedRunResponse, run_state: RunState) -> None:
    if response.actions:
        for action in response.actions:
            action["id"] = str(uuid.uuid4())
        run_state.pending_ids = [a["id"] for a in response.actions]
    elif response.toolCalls:
        run_state.pending_ids = [tc.id for tc in response.toolCalls]
    else:
        run_state.pending_ids = []


# ============================================================================
# Hosted API Endpoints
# ============================================================================

@app.post("/v1/runs", response_model=HostedRunResponse)
async def create_run(
    request: HostedCreateRunRequest,
    http_request: Request,
    tenant_subject: Tuple[str, str] = Depends(verify_tenant_credentials),
):
    """
    Create a new run or deduplicate existing one.
    Server-to-server only - requires Bearer token and X-Ghost-Subject.
    """
    reject_origin_requests(http_request)

    tenant_id, subject = tenant_subject
    init_globals()

    try:
        # Validate and normalize customer tools
        for t in request.tools:
            if is_frontend_tool(t.name):
                raise HTTPException(
                    status_code=422,
                    detail=f"Customer tool name '{t.name}' collides with built-in frontend tool",
                )
            try:
                t.parameters = normalize_schema(t.parameters)
            except ValueError as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid schema for tool '{t.name}': {e}",
                )

        # Check for deduplication
        existing_run = await run_store.get_by_request_id(tenant_id, subject, request.requestId)
        if existing_run:
            if existing_run.is_expired:
                raise HTTPException(status_code=410, detail="run_expired")
            # Verify payload matches
            if existing_run.start_payload_digest != RunStore.compute_digest(request.model_dump()):
                raise HTTPException(status_code=409, detail="Payload mismatch for existing requestId")
            return existing_run.to_hosted_response()

        # Create new run with pending revision
        run_state = RunState(
            tenant=tenant_id,
            subject=subject,
            request_id=request.requestId,
            protocol_version=request.protocolVersion,
            start_payload=request.model_dump(),
            revision=-1,  # Pending revision
        )

        # Load brain content (passed from gateway)
        brain_content = request.brain

        # Get available targets and context dict
        context_dict = (
            request.context.model_dump()
            if hasattr(request.context, "model_dump")
            else request.context
        )
        available_targets = context_dict.get("availableTargets", [])

        # Create agent with brain context
        customer_tools = [t.model_dump() if hasattr(t, "model_dump") else t for t in request.tools]
        agent = create_ghost_agent(
            brain_content=brain_content,
            available_targets=available_targets,
            current_context=context_dict,
            customer_backend_tools=customer_tools,
        )

        # Run initial planning
        run_state.revision = 0
        response = await _run_agent_turn(agent, run_state, request.message)
        _register_pending(response, run_state)
        response.revision = 0

        # Update run state with response
        run_state.status = response.status
        run_state.latest_reply = response.reply
        run_state.history.append({
            "revision": 0,
            "type": "initial",
            "request": request.message,
            "response": response.model_dump(),
        })

        # Save run
        await run_store.save(run_state)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating run: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/v1/runs/{run_id}/continue", response_model=HostedRunResponse)
async def continue_run(
    run_id: str,
    request: HostedContinueRunRequest,
    http_request: Request,
    tenant_subject: Tuple[str, str] = Depends(verify_tenant_credentials),
):
    """
    Continue an existing run with tool results, action results, or user answer.
    """
    reject_origin_requests(http_request)

    tenant_id, subject = tenant_subject
    init_globals()

    try:
        # Load run
        run_state = await run_store.get(run_id)
        if not run_state:
            raise HTTPException(status_code=404, detail="Run not found")

        # Verify tenant and subject
        if run_state.tenant != tenant_id or run_state.subject != subject:
            raise HTTPException(status_code=404, detail="Run not found")

        if run_state.is_expired:
            raise HTTPException(status_code=410, detail="run_expired")

        digest = RunStore.compute_digest(request.model_dump())
        if request.eventId == run_state.latest_event_id:
            if digest == run_state.latest_event_digest:
                return run_state.to_hosted_response()
            raise HTTPException(status_code=409, detail="event_conflict")
        if run_state.is_terminal:
            if request.kind == "cancel":
                return run_state.to_hosted_response()
            raise HTTPException(status_code=409, detail="run_finished")
        if request.revision != run_state.revision:
            raise HTTPException(status_code=409, detail="stale_revision")
        if request.kind not in EXPECTED_KINDS.get(run_state.status, set()):
            raise HTTPException(status_code=409, detail="unexpected_kind")
        if request.kind != "cancel" and run_state.turn_count >= MAX_TURNS:
            raise HTTPException(status_code=409, detail="turn_limit")
        if request.kind in ("tools", "actions"):
            if sorted(r.id for r in (request.results or [])) != sorted(run_state.pending_ids):
                raise HTTPException(status_code=409, detail="result_mismatch")
        run_state = copy.deepcopy(run_state)

        # Process based on kind
        run_state.latest_tool_results = []
        run_state.latest_action_results = []
        target_revision = request.revision + 1
        run_state.revision = target_revision
        run_state.latest_kind = request.kind
        if request.kind == "tools":
            response = await _handle_tool_results(run_state, request.results)
        elif request.kind == "actions":
            response = await _handle_action_results(run_state, request.results, request.context)
        elif request.kind == "answer":
            response = await _handle_user_answer(run_state, request.answer, request.context)
        elif request.kind == "cancel":
            response = await _handle_cancellation(run_state)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown kind: {request.kind}")

        _register_pending(response, run_state)
        response.revision = target_revision

        # Update run state
        run_state.status = response.status
        run_state.latest_reply = response.reply
        run_state.latest_event_id = request.eventId
        run_state.latest_event_digest = digest
        run_state.history.append({
            "revision": run_state.revision,
            "type": request.kind,
            "request": request.model_dump(),
            "response": response.model_dump(),
        })

        # Save run
        await run_store.save(run_state)

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error continuing run: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============================================================================
# Agent Execution Helpers
# ============================================================================

async def _run_agent_turn(agent: GhostAgent, run_state: RunState, user_message: str) -> HostedRunResponse:
    """Run a single agent turn and return response"""
    if not vertex_client:
        raise RuntimeError("Vertex client not initialized")

    # Generate response using Vertex AI
    response = await vertex_client.generate_content(
        agent=agent,
        user_message=user_message,
        run_context=run_state.to_agent_context(),
    )

    if response.status in ("failed", "cancelled"):
        return response

    # 1. Reject mixed outputs if any
    active_outputs = sum([
        bool(response.toolCalls),
        bool(response.actions),
        bool(response.questions),
    ])
    if active_outputs > 1:
        logger.warning("Mixed output types in model response")
        return HostedRunResponse(
            protocolVersion=response.protocolVersion or "1",
            runId=response.runId or run_state.id,
            revision=max(0, run_state.revision),
            status="failed",
            reply="I couldn't produce a valid plan. Please rephrase.",
        )

    # 2. Validate actions if actions are present
    if response.actions:
        try:
            response.actions = validate_actions(response.actions)
        except Exception as e:
            logger.warning(f"Action validation failed: {e}")
            return HostedRunResponse(
                protocolVersion=response.protocolVersion or "1",
                runId=response.runId or run_state.id,
                revision=max(0, run_state.revision),
                status="failed",
                reply="I couldn't produce a valid plan. Please rephrase.",
            )

    # 3. Check tool calls belong to declared tools
    if response.toolCalls:
        declared_tools = set()
        for t in run_state.start_payload.get("tools", []):
            if isinstance(t, dict):
                declared_tools.add(t.get("name"))
            elif hasattr(t, "name"):
                declared_tools.add(t.name)

        for tc in response.toolCalls:
            tc_name = getattr(tc, "tool", None) or (tc.get("tool") if isinstance(tc, dict) else None)
            if tc_name not in declared_tools:
                logger.warning(f"Undeclared tool call attempted: {tc_name}")
                return HostedRunResponse(
                    protocolVersion=response.protocolVersion or "1",
                    runId=response.runId or run_state.id,
                    revision=max(0, run_state.revision),
                    status="failed",
                    reply="I couldn't produce a valid plan. Please rephrase.",
                )

    # 4. Derive status
    if response.toolCalls:
        response.status = "awaiting_tools"
    elif response.actions:
        response.status = "awaiting_actions"
    elif response.questions:
        response.status = "awaiting_answer"
    else:
        response.status = "completed"

    return response


async def _handle_tool_results(
    run_state: RunState,
    results: Optional[List[ToolCallResponse]],
) -> HostedRunResponse:
    """Handle tool execution results from gateway"""
    run_state.latest_tool_results = results or []
    # Reload agent with updated context
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=run_state.start_payload.get("context", {}),
        customer_backend_tools=run_state.start_payload.get("tools", []),
    )

    response = await _run_agent_turn(agent, run_state, "")

    return response


async def _handle_action_results(
    run_state: RunState,
    results: Optional[List[ToolCallResponse]],
    updated_context: Optional[Any],
) -> HostedRunResponse:
    """Handle frontend action execution results"""
    run_state.latest_action_results = results or []
    if any(not r.ok for r in (results or [])):
        return HostedRunResponse(
            protocolVersion="1",
            runId=run_state.id,
            revision=run_state.revision,
            status="failed",
            reply="Stopped because a step failed. Changes already made on the page were kept.",
        )

    context_dict = (
        updated_context.model_dump()
        if hasattr(updated_context, "model_dump")
        else (updated_context or run_state.start_payload.get("context", {}))
    )
    # Reload agent
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=context_dict,
        customer_backend_tools=run_state.start_payload.get("tools", []),
    )

    response = await _run_agent_turn(agent, run_state, "")

    return response


async def _handle_user_answer(
    run_state: RunState,
    answer: Optional[str],
    updated_context: Optional[Any],
) -> HostedRunResponse:
    """Handle user answer to clarification question"""
    context_dict = (
        updated_context.model_dump()
        if hasattr(updated_context, "model_dump")
        else (updated_context or run_state.start_payload.get("context", {}))
    )
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=context_dict,
        customer_backend_tools=run_state.start_payload.get("tools", []),
    )

    response = await _run_agent_turn(agent, run_state, answer or "")

    return response


async def _handle_cancellation(run_state: RunState) -> HostedRunResponse:
    """Handle run cancellation"""
    return HostedRunResponse(
        protocolVersion="1",
        runId=run_state.id,
        revision=run_state.revision,
        status="cancelled",
        reply="Operation cancelled by user.",
    )


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": err.get("loc"),
            "msg": str(err.get("msg")),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=422,
        content={"detail": errors},
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )