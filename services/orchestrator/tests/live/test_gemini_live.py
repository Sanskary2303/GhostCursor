"""
Live Vertex AI Integration Test (Step 22)

Skipped unless GHOST_LIVE_TESTS=1.
Requires valid GCP credentials (e.g. gcloud auth application-default login).
"""

import os
import pytest
from services.orchestrator.app.agent import create_ghost_agent
from services.orchestrator.app.llm import DEFAULT_MODEL
from services.orchestrator.app.llm.gemini import GeminiProvider


@pytest.mark.skipif(
    os.getenv("GHOST_LIVE_TESTS") != "1",
    reason="GHOST_LIVE_TESTS != 1 (live tests require GCP credentials and network access)",
)
@pytest.mark.asyncio
async def test_gemini_live_real_plan_generation():
    """Live call to Vertex AI Gemini Flash checking real action generation"""
    project_id = os.getenv("GCP_PROJECT_ID", "default-project")
    location = os.getenv("GCP_LOCATION", "us-central1")
    model = os.getenv("GHOST_MODEL", DEFAULT_MODEL)

    provider = GeminiProvider(project=project_id, location=location, model=model)

    agent = create_ghost_agent(
        brain_content="ShopHive is an e-commerce platform.",
        available_targets=["btn_checkout", "cart_link"],
        current_context={"page": "cart", "values": {}, "availableTargets": ["btn_checkout", "cart_link"]},
    )

    transcript = [
        {"role": "user", "parts": [{"text": "Click the checkout button"}]}
    ]

    response = await provider.generate_content(
        agent=agent,
        user_message="Click the checkout button",
        run_context={"run_id": "live-test-run", "revision": 0},
        transcript=transcript,
    )

    assert response.protocolVersion == "1"
    assert response.status in ("awaiting_actions", "completed")
    assert len(transcript) >= 2
    assert transcript[-1]["role"] == "model"


@pytest.mark.skipif(
    os.getenv("GHOST_LIVE_TESTS") != "1",
    reason="GHOST_LIVE_TESTS != 1 (live tests require GCP credentials and network access)",
)
@pytest.mark.asyncio
async def test_gemini_live_two_turns():
    """Live call testing multi-turn continuation with thought signatures (Step 61)"""
    project_id = os.getenv("GCP_PROJECT_ID", "default-project")
    location = os.getenv("GCP_LOCATION", "us-central1")
    model = os.getenv("GHOST_MODEL", DEFAULT_MODEL)

    provider = GeminiProvider(project=project_id, location=location, model=model)

    agent = create_ghost_agent(
        brain_content="Settings page. The dark mode switch is theme.toggle (on = dark).",
        available_targets=["theme.toggle"],
        current_context={"page": "settings", "values": {"theme.toggle": False}, "availableTargets": ["theme.toggle"]},
    )

    transcript = [
        {"role": "user", "parts": [{"text": "Turn on dark mode"}]}
    ]

    first = await provider.generate_content(
        agent=agent,
        user_message="Turn on dark mode",
        run_context={"run_id": "live-test-turns", "revision": 0},
        transcript=transcript,
    )

    assert first.actions, first.reply

    # Append one user turn with one function_response part per action
    function_response_parts = [
        {"function_response": {"name": action["type"], "response": {"ok": True, "output": {}}}}
        for action in first.actions
    ]
    transcript.append({"role": "user", "parts": function_response_parts})

    second = await provider.generate_content(
        agent=agent,
        user_message="",
        run_context={"run_id": "live-test-turns", "revision": 1},
        transcript=transcript,
    )

    assert second.status == "completed"


