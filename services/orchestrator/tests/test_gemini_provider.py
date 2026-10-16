"""
Unit Tests for GeminiProvider (Step 22)
"""

import pytest
import uuid
from types import SimpleNamespace
from typing import Any, Dict, List

from services.orchestrator.app.agent import create_ghost_agent
from services.orchestrator.app.llm.gemini import GeminiProvider, prune_transcript
from services.orchestrator.app.llm.vertex import ProviderError


@pytest.mark.asyncio
async def test_gemini_provider_generate_content_success(monkeypatch):
    """Monkeypatch generate_content and assert parsed actions and transcript tracking"""
    provider = GeminiProvider(project="test-proj", location="us-central1", model="gemini-2.0-flash")
    agent = create_ghost_agent(
        brain_content="ShopHive demo",
        available_targets=["btn_checkout"],
        current_context={"page": "cart", "values": {}, "availableTargets": ["btn_checkout"]},
    )

    transcript: List[Dict[str, Any]] = [
        {"role": "user", "parts": [{"text": "Click the checkout button"}]}
    ]

    async def fake_generate_content(model: str, contents: Any, config: Any):
        assert model == "gemini-2.0-flash"
        assert len(contents) == 1
        assert config.temperature == 0.2
        assert config.automatic_function_calling.disable is True

        return SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(
                                function_call=SimpleNamespace(
                                    name="click",
                                    args={"target_id": "btn_checkout", "explanation": "Click checkout to proceed"},
                                ),
                                text=None,
                            ),
                            SimpleNamespace(
                                function_call=None,
                                text="I will click the checkout button for you.",
                            ),
                        ]
                    )
                )
            ]
        )

    monkeypatch.setattr(provider.client.aio.models, "generate_content", fake_generate_content)

    resp = await provider.generate_content(
        agent=agent,
        user_message="Click the checkout button",
        run_context={"run_id": "run-123", "revision": 0},
        transcript=transcript,
    )

    # 1. Assert response
    assert resp.status == "awaiting_actions"
    assert resp.reply == "I will click the checkout button for you."
    assert len(resp.actions) == 1
    assert resp.actions[0]["type"] == "click"
    assert resp.actions[0]["target_id"] == "btn_checkout"
    assert resp.actions[0]["explanation"] == "Click checkout to proceed"

    # 2. Assert transcript updated
    assert len(transcript) == 2
    assert transcript[0]["role"] == "user"
    assert transcript[1]["role"] == "model"
    assert len(transcript[1]["parts"]) == 2
    assert transcript[1]["parts"][0]["function_call"]["name"] == "click"
    assert transcript[1]["parts"][0]["function_call"]["args"]["target_id"] == "btn_checkout"
    assert transcript[1]["parts"][1]["text"] == "I will click the checkout button for you."


@pytest.mark.asyncio
async def test_gemini_provider_sdk_error_raises_provider_error(monkeypatch):
    """Any SDK error in generate_content raises ProviderError without fallback"""
    provider = GeminiProvider(project="test-proj", location="us-central1", model="gemini-2.0-flash")
    agent = create_ghost_agent(brain_content="", available_targets=[], current_context={})

    async def fake_failing_generate_content(*args, **kwargs):
        raise RuntimeError("GCP 503 Service Unavailable")

    monkeypatch.setattr(provider.client.aio.models, "generate_content", fake_failing_generate_content)

    with pytest.raises(ProviderError) as exc_info:
        await provider.generate_content(
            agent=agent,
            user_message="Hello",
            run_context={"run_id": "run-fail", "revision": 0},
            transcript=[{"role": "user", "parts": [{"text": "Hello"}]}],
        )

    assert "GCP 503" in str(exc_info.value)


@pytest.mark.asyncio
async def test_main_handles_provider_error_safely(auth_headers, monkeypatch):
    """Orchestrator turns ProviderError into status=failed and safe unavailable message"""
    from httpx import AsyncClient, ASGITransport
    from services.orchestrator.app.main import app
    import services.orchestrator.app.main as main_mod

    class FailingProvider:
        async def generate_content(self, *args, **kwargs):
            raise ProviderError("Connection refused by Vertex AI")

    monkeypatch.setattr(main_mod, "vertex_client", FailingProvider())

    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "checkout",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["reply"] == "The assistant is unavailable right now."


def test_prune_transcript_caps_at_max_parts():
    """prune_transcript keeps at most max_parts and ensures leading role is 'user'"""
    transcript = [
        {"role": "user", "parts": [{"text": f"msg {i}"}]}
        for i in range(50)
    ]
    pruned = prune_transcript(transcript, max_parts=40)
    total_parts = sum(len(t["parts"]) for t in pruned)
    assert total_parts <= 40
    assert pruned[0]["role"] == "user"

