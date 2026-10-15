"""
Ghost Cursor Orchestrator - Main FastAPI Application

Google ADK Agent Engine with Vertex AI Gemini 2.0 integration.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

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
)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global run_store, vertex_client, loopback_handler

    # Initialize run store
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        run_store = PostgreSQLRunStore(database_url)
        await run_store.initialize()
        logger.info("Initialized PostgreSQL run store")
    else:
        run_store = InMemoryRunStore()
        logger.warning("Using in-memory run store (not for production)")

    # Initialize Vertex AI client
    use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"
    if use_mock:
        vertex_client = MockVertexAIClient()
        logger.info("Using mock Vertex AI client")
    else:
        project_id = os.getenv("GCP_PROJECT_ID")
        location = os.getenv("GCP_LOCATION", "us-central1")
        if project_id:
            vertex_client = VertexAIClient(project_id=project_id, location=location)
            logger.info(f"Initialized Vertex AI client for project {project_id}")
        else:
            vertex_client = MockVertexAIClient()
            logger.warning("No GCP_PROJECT_ID set, using mock client")

    # Initialize loopback handler
    loopback_handler = GatewayLoopbackHandler()

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
) -> tuple[str, str]:
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


# ============================================================================
# Hosted API Endpoints
# ============================================================================

@app.post("/v1/runs", response_model=HostedRunResponse)
async def create_run(
    request: HostedCreateRunRequest,
    http_request: Request,
    tenant_subject: tuple[str, str] = Depends(verify_tenant_credentials),
):
    """
    Create a new run or deduplicate existing one.
    Server-to-server only - requires Bearer token and X-Ghost-Subject.
    """
    reject_origin_requests(http_request)

    tenant_id, subject = tenant_subject

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

        # Get available targets
        available_targets = request.context.get("availableTargets", [])

        # Create agent with brain context
        agent = create_ghost_agent(
            brain_content=brain_content,
            available_targets=available_targets,
            current_context=request.context,
            customer_backend_tools=request.tools,
        )

        # Run initial planning
        response = await _run_agent_turn(agent, run_state, request.message)

        # Update run state with response
        run_state.revision = 0
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
    tenant_subject: tuple[str, str] = Depends(verify_tenant_credentials),
):
    """
    Continue an existing run with tool results, action results, or user answer.
    """
    reject_origin_requests(http_request)

    tenant_id, subject = tenant_subject

    try:
        # Load run
        run_state = await run_store.get(run_id)
        if not run_state:
            raise HTTPException(status_code=404, detail="Run not found")

        # Verify tenant and subject
        if run_state.tenant != tenant_id or run_state.subject != subject:
            raise HTTPException(status_code=404, detail="Run not found")

        # Verify revision (optimistic locking)
        if run_state.revision != request.revision:
            raise HTTPException(status_code=409, detail="Revision mismatch")

        # Verify event ID for replay protection
        if request.eventId and run_state.latest_event_id == request.eventId:
            # Check if payload matches
            # If identical, return cached result
            if run_state.latest_event_digest == RunStore.compute_digest(request.model_dump()):
                return run_state.to_hosted_response()
            else:
                raise HTTPException(status_code=409, detail="Event ID replay with different payload")

        # Process based on kind
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

        # Update run state
        run_state.revision += 1
        run_state.revision = request.revision + 1
        run_state.status = response.status
        run_state.latest_reply = response.reply
        run_state.latest_event_id = request.eventId
        run_state.latest_event_digest = RunStore.compute_digest(request.model_dump())
        run_state.history.append({
            "revision": run_state.revision,
            "type": request.kind,
            "request": request.model_dump(),
            "response": response.model_dump(),
        })

        # Check turn limit
        if len([h for h in run_state.history if h["type"] != "initial"]) >= 12:
            if request.kind != "cancel":
                raise HTTPException(status_code=400, detail="Turn limit exceeded")

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
    results: Optional[list[ToolCallResponse]],
) -> HostedRunResponse:
    """Handle tool execution results from gateway"""
    # Reload agent with updated context
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=run_state.start_payload.get("context", {}),
        customer_backend_tools=run_state.start_payload.get("tools", []),
    )

    # Add tool results to context and re-run
    tool_results = results or []
    response = await _run_agent_turn(agent, run_state, "")

    return response


async def _handle_action_results(
    run_state: RunState,
    results: Optional[list[ToolCallResponse]],
    updated_context: Optional[dict],
) -> HostedRunResponse:
    """Handle frontend action execution results"""
    # Reload agent
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=updated_context or run_state.start_payload.get("context", {}),
        customer_backend_tools=run_state.start_payload.get("tools", []),
    )

    response = await _run_agent_turn(agent, run_state, "")

    return response


async def _handle_user_answer(
    run_state: RunState,
    answer: Optional[str],
    updated_context: Optional[dict],
) -> HostedRunResponse:
    """Handle user answer to clarification question"""
    agent = create_ghost_agent(
        brain_content=run_state.start_payload.get("brain", ""),
        available_targets=run_state.start_payload.get("context", {}).get("availableTargets", []),
        current_context=updated_context or run_state.start_payload.get("context", {}),
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