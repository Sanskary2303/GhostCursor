"""
Ghost Cursor Orchestrator - Main FastAPI Application

Google ADK Agent Engine with Vertex AI Gemini 2.0 integration.
"""

from __future__ import annotations

import copy
import os
import uuid
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
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
)

EXPECTED_KINDS = {
    "awaiting_tools": {"tools", "cancel"},
    "awaiting_actions": {"actions", "cancel"},
    "awaiting_answer": {"answer", "cancel"},
}
from .storage.run_store import PostgreSQLRunStore, InMemoryRunStore
from .llm.vertex import VertexAIClient, MockVertexAIClient
from .tools.frontend_actions import FRONTEND_ACTION_TOOLS
from .tools.loopback import GatewayLoopbackHandler

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
run_store: Optional[RunStore] = None
vertex_client: Optional[VertexAIClient] = None
loopback_handler: Optional[GatewayLoopbackHandler] = None


def init_globals():
    """Ensure global services are initialized even if lifespan wasn't triggered (e.g. tests)"""
    global run_store, vertex_client, loopback_handler
    if run_store is None:
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            run_store = PostgreSQLRunStore(database_url)
        else:
            run_store = InMemoryRunStore()

    if vertex_client is None:
        use_mock = os.getenv("USE_MOCK_LLM", "true").lower() == "true"
        if use_mock:
            vertex_client = MockVertexAIClient()
        else:
            project_id = os.getenv("GCP_PROJECT_ID")
            location = os.getenv("GCP_LOCATION", "us-central1")
            if project_id:
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

# CORS - restrict in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


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

    # In production, validate against Secret Manager / database
    # For now, use a simple mapping
    valid_keys = {
        os.getenv("TENANT_API_KEY_1", "test-key-1"): "tenant_1",
        os.getenv("TENANT_API_KEY_2", "test-key-2"): "tenant_2",
        os.getenv("GHOST_CURSOR_API_KEY", "test-key-shophive-demo"): "shophive_demo",
        "test-key-shophive-demo": "shophive_demo",
    }

    tenant_id = valid_keys.get(api_key)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate subject format
    if not x_ghost_subject or not (1 <= len(x_ghost_subject) <= 120):
        raise HTTPException(status_code=400, detail="Invalid X-Ghost-Subject")

    # Basic format validation
    import re
    if not re.match(r'^[a-zA-Z0-9_.:@-]+$', x_ghost_subject):
        raise HTTPException(status_code=400, detail="Invalid subject format")

    return tenant_id, x_ghost_subject


def reject_origin_requests(request: Request):
    """Reject requests with Origin header (defense in depth)"""
    if request.headers.get("origin"):
        raise HTTPException(status_code=403, detail="Direct browser access not allowed")


# ============================================================================
# Request/Response Models
# ============================================================================

class PublicResponse(BaseModel):
    """Public response projected to browser"""
    protocolVersion: ProtocolVersion = "1"
    runId: str
    revision: int
    status: RunStatus
    reply: str
    questions: Optional[list] = None
    actions: Optional[list] = None


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
        # Check for deduplication
        existing_run = await run_store.get_by_request_id(tenant_id, subject, request.requestId)
        if existing_run:
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
        agent = create_ghost_agent(
            brain_content=brain_content,
            available_targets=available_targets,
            current_context=context_dict,
            customer_backend_tools=request.tools,
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