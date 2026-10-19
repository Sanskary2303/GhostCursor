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

