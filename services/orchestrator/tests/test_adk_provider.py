"""
Unit tests for Google ADK Provider (Step 53).

All tests run 100% offline with zero network calls in CI by utilizing
mock LLMs derived from google.adk.models.base_llm.BaseLlm.
"""

from __future__ import annotations

import os
import uuid
import pytest
from typing import AsyncGenerator, Dict, Any, List

from google.genai import types
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions import InMemorySessionService

from services.orchestrator.app.agent import create_ghost_agent, create_adk_agent
from services.orchestrator.app.llm.adk import ADKProvider, DynamicLongRunningTool, build_adk_tools
from services.orchestrator.app.models.contracts import validate_actions


class MockLlm(BaseLlm):
    """Offline mock LLM for testing ADK provider flows."""
    model: str = "mock-gemini-2.0-flash"
    responses: List[types.Content] = []
    turn: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        if self.turn < len(self.responses):
            content = self.responses[self.turn]
            self.turn += 1
            yield LlmResponse(content=content)
        else:
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="Default mock completion.")],
                )
            )


@pytest.fixture
def session_service():
    return InMemorySessionService()


@pytest.mark.asyncio
async def test_adk_action_tools_awaiting_actions(session_service):
    """
    Action tool calls (navigate + toggle_switch) produce awaiting_actions
    with 2 validated actions and 0 local tool executions.
    """
    turn1_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="navigate",
                    args={"target_page": "settings", "explanation": "Go to settings"},
                )
            ),
            types.Part(
                function_call=types.FunctionCall(
                    name="toggle_switch",
                    args={"target_id": "appearance.dark_mode", "state": True, "explanation": "Enable dark mode"},
                )
            ),
        ],
    )
    mock_llm = MockLlm(responses=[turn1_content])
    provider = ADKProvider(
        project="test-project",
        session_service=session_service,
        llm_client=mock_llm,
    )

    agent = create_ghost_agent(
        brain_content="Settings page has dark mode.",
        available_targets=["appearance.dark_mode"],
        current_context={"page": "dashboard", "values": {}},
    )

    run_id = str(uuid.uuid4())
    run_context = {"run_id": run_id, "subject": "user_1", "revision": 0}
    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "Switch to dark mode"}]}
    ]

    response = await provider.generate_content(
        agent=agent,
        user_message="Switch to dark mode",
        run_context=run_context,
        transcript=transcript,
    )

    assert response.status == "awaiting_actions"
    assert response.actions is not None
    assert len(response.actions) == 2

    # Validate actions schema and logical IDs
    validated = validate_actions(response.actions)
    assert len(validated) == 2
    assert validated[0]["type"] == "navigate"
    assert validated[0]["target_page"] == "settings"
    assert validated[1]["type"] == "toggle_switch"
    assert validated[1]["target_id"] == "appearance.dark_mode"
    assert validated[1]["state"] is True

    # Verify model turn was appended to transcript
    assert len(transcript) == 2
    assert transcript[1]["role"] == "model"
    assert len(transcript[1]["parts"]) == 2


@pytest.mark.asyncio
async def test_adk_continuation_turn_resumes_model(session_service):
    """
    Continuation turn with function responses resumes ADK model, reaches
    next model turn, and maintains function_response in transcript.
    """
    turn1_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="navigate",
                    args={"target_page": "settings", "explanation": "Go to settings"},
                )
            )
        ],
    )
    turn2_content = types.Content(
        role="model",
        parts=[types.Part(text="Successfully navigated to settings.")],
    )
    mock_llm = MockLlm(responses=[turn1_content, turn2_content])
    provider = ADKProvider(
        project="test-project",
        session_service=session_service,
        llm_client=mock_llm,
    )

    agent = create_ghost_agent(
        brain_content="Navigation info.",
        available_targets=[],
        current_context={"page": "home", "values": {}},
    )

    run_id = str(uuid.uuid4())
    run_context = {"run_id": run_id, "subject": "user_1", "revision": 0}
    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "Go to settings"}]}
    ]

    # Turn 1: Planning
    resp1 = await provider.generate_content(
        agent=agent,
        user_message="Go to settings",
        run_context=run_context,
        transcript=transcript,
    )
    assert resp1.status == "awaiting_actions"

    # Turn 2: Continuation with tool execution result
    transcript.append({
        "role": "user",
        "parts": [{
            "function_response": {
                "name": "navigate",
                "response": {"ok": True, "output": {"url": "/settings"}},
            }
        }],
    })

    resp2 = await provider.generate_content(
        agent=agent,
        user_message="",
        run_context=run_context,
        transcript=transcript,
    )

    assert resp2.status == "completed"
    assert "Successfully navigated" in resp2.reply
    # Verify transcript contains user function_response and final model reply
    assert len(transcript) == 4
    assert transcript[2]["role"] == "user"
    assert "function_response" in transcript[2]["parts"][0]
    assert transcript[3]["role"] == "model"
    assert transcript[3]["parts"][0]["text"] == "Successfully navigated to settings."


@pytest.mark.asyncio
async def test_adk_customer_backend_tools_awaiting_tools(session_service):
    """
    Customer backend tools produce awaiting_tools with toolCalls.
    """
    turn1_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="lookup_order",
                    args={"order_id": "SH-1024"},
                )
            )
        ],
    )
    turn2_content = types.Content(
        role="model",
        parts=[types.Part(text="Your order SH-1024 has shipped.")],
    )
    mock_llm = MockLlm(responses=[turn1_content, turn2_content])
    provider = ADKProvider(
        project="test-project",
        session_service=session_service,
        llm_client=mock_llm,
    )

    customer_tools = [{
        "name": "lookup_order",
        "description": "Look up order tracking info",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    }]

    agent = create_ghost_agent(
        brain_content="Orders can be looked up.",
        available_targets=[],
        current_context={"page": "orders", "values": {}},
        customer_backend_tools=customer_tools,
    )

    run_id = str(uuid.uuid4())
    run_context = {"run_id": run_id, "subject": "user_1", "revision": 0}
    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "Where is my order SH-1024?"}]}
    ]

    resp1 = await provider.generate_content(
        agent=agent,
        user_message="Where is my order SH-1024?",
        run_context=run_context,
        transcript=transcript,
    )

    assert resp1.status == "awaiting_tools"
    assert resp1.toolCalls is not None
    assert len(resp1.toolCalls) == 1
    assert resp1.toolCalls[0].tool == "lookup_order"
    assert resp1.toolCalls[0].parameters == {"order_id": "SH-1024"}

    # Resume with tool output
    transcript.append({
        "role": "user",
        "parts": [{
            "function_response": {
                "name": "lookup_order",
                "response": {"ok": True, "output": {"status": "shipped"}},
            }
        }],
    })

    resp2 = await provider.generate_content(
        agent=agent,
        user_message="",
        run_context=run_context,
        transcript=transcript,
    )

    assert resp2.status == "completed"
    assert "SH-1024 has shipped" in resp2.reply


@pytest.mark.asyncio
async def test_adk_clarification_question(session_service):
    """
    ask_clarification tool call produces awaiting_answer with ClarifyQuestion.
    """
    turn1_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="ask_clarification",
                    args={
                        "question": "Which color would you prefer?",
                        "options": ["Red", "Blue", "Black"],
                    },
                )
            )
        ],
    )
    mock_llm = MockLlm(responses=[turn1_content])
    provider = ADKProvider(
        project="test-project",
        session_service=session_service,
        llm_client=mock_llm,
    )

    agent = create_ghost_agent(
        brain_content="Products available.",
        available_targets=[],
        current_context={"page": "products", "values": {}},
    )

    run_id = str(uuid.uuid4())
    run_context = {"run_id": run_id, "subject": "user_1", "revision": 0}
    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "I want shoes"}]}
    ]

    response = await provider.generate_content(
        agent=agent,
        user_message="I want shoes",
        run_context=run_context,
        transcript=transcript,
    )

    assert response.status == "awaiting_answer"
    assert response.questions is not None
    assert len(response.questions) == 1
    assert response.questions[0].question == "Which color would you prefer?"
    assert response.questions[0].options == ["Red", "Blue", "Black"]


@pytest.mark.asyncio
async def test_adk_invalid_target_rejected(session_service):
    """
    Invalid action target with illegal characters fails validation.
    """
    turn1_content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    name="click",
                    args={"target_id": "invalid target with spaces!!!", "explanation": "Click bad element"},
                )
            )
        ],
    )
    mock_llm = MockLlm(responses=[turn1_content])
    provider = ADKProvider(
        project="test-project",
        session_service=session_service,
        llm_client=mock_llm,
    )

    agent = create_ghost_agent(
        brain_content="",
        available_targets=[],
        current_context={"page": "home", "values": {}},
    )

    run_id = str(uuid.uuid4())
    run_context = {"run_id": run_id, "subject": "user_1", "revision": 0}
    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "Click it"}]}
    ]

    response = await provider.generate_content(
        agent=agent,
        user_message="Click it",
        run_context=run_context,
        transcript=transcript,
    )

    assert response.status == "awaiting_actions"
    # Action validation should fail when validated
    with pytest.raises(ValueError, match="Logical ID contains invalid characters"):
        validate_actions(response.actions)


def test_adk_provider_missing_config_fails(monkeypatch):
    """
    GHOST_PROVIDER=adk without GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT fails fast on startup.
    """
    from services.orchestrator.app.main import init_globals

    monkeypatch.setenv("GHOST_PROVIDER", "adk")
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID or GOOGLE_CLOUD_PROJECT is required when GHOST_PROVIDER is 'adk'"):
        init_globals()


def test_adk_provider_config_maps_env_vars(monkeypatch):
    """
    GHOST_PROVIDER=adk maps GCP_PROJECT_ID to GOOGLE_CLOUD_PROJECT and sets GOOGLE_GENAI_USE_VERTEXAI.
    """
    from services.orchestrator.app.main import init_globals
    import services.orchestrator.app.main as main_mod

    # Reset globals
    main_mod.vertex_client = None

    monkeypatch.setenv("GHOST_PROVIDER", "adk")
    monkeypatch.setenv("GHOST_STORE", "memory")
    monkeypatch.setenv("GCP_PROJECT_ID", "my-test-adk-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)

    init_globals()

    assert os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "TRUE"
    assert os.environ.get("GOOGLE_CLOUD_PROJECT") == "my-test-adk-project"
    assert os.environ.get("GOOGLE_CLOUD_LOCATION") == "us-central1"
    assert main_mod.vertex_client is not None
    assert type(main_mod.vertex_client).__name__ == "ADKProvider"

    # Cleanup
    main_mod.vertex_client = None


def test_create_adk_agent_factory():
    """
    create_adk_agent factory creates an ADK LlmAgent with long-running tools.
    """
    agent = create_adk_agent(
        brain_content="Test brain knowledge.",
        available_targets=["btn.submit"],
        current_context={"page": "checkout", "values": {}},
        customer_backend_tools=[{
            "name": "check_inventory",
            "description": "Check stock",
            "parameters": {"type": "object", "properties": {"sku": {"type": "string"}}},
        }],
    )

    assert agent.name == "ghost_cursor_orchestrator"
    assert "Test brain knowledge." in agent.instruction
    tool_names = [t.name for t in agent.tools]
    assert "navigate" in tool_names
    assert "click" in tool_names
    assert "toggle_switch" in tool_names
    assert "check_inventory" in tool_names


@pytest.mark.skipif(not os.getenv("GHOST_ADK_LIVE"), reason="Live test requires GHOST_ADK_LIVE=1 and GCP credentials")
@pytest.mark.asyncio
async def test_adk_provider_live():
    """
    Optional live end-to-end test against real Gemini 2.0 via Google ADK.
    """
    project = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    assert project, "GCP project ID required for live test"
    provider = ADKProvider(project=project, model="gemini-2.0-flash")

    agent = create_ghost_agent(
        brain_content="Appearance settings contains a dark mode toggle.",
        available_targets=["appearance.theme_toggle"],
        current_context={"page": "dashboard", "values": {"theme": "light"}},
    )

    run_context = {"run_id": str(uuid.uuid4()), "subject": "live_user", "revision": 0}
    transcript = [{"role": "user", "parts": [{"text": "Please switch the appearance to dark mode"}]}]

    response = await provider.generate_content(
        agent=agent,
        user_message="Please switch the appearance to dark mode",
        run_context=run_context,
        transcript=transcript,
    )

    assert response.status in ("awaiting_actions", "completed")
