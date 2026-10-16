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

    monkeypatch.setattr(app.state, "provider", FailingProvider())

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


def test_prune_transcript_drops_leading_function_response():
    """A transcript whose first kept turn would be a function-response turn starts with a plain user text turn"""
    transcript = [
        {"role": "user", "parts": [{"text": "First user message"}]},
        {"role": "model", "parts": [{"function_call": {"name": "ask_clarification", "args": {}}}]},
        {"role": "user", "parts": [{"function_response": {"name": "ask_clarification", "response": {"answer": "A"}}}]},
        {"role": "model", "parts": [{"text": "Proceeding"}]},
        {"role": "user", "parts": [{"text": "Clean user message"}]},
    ]
    pruned = prune_transcript(transcript, max_parts=3)
    assert len(pruned) == 1
    assert pruned[0]["parts"] == [{"text": "Clean user message"}]


@pytest.mark.asyncio
async def test_ask_clarification_answer_transcript_format(app, auth_headers, monkeypatch):
    """Continuing with kind=answer after ask_clarification sends function_response in transcript"""
    from httpx import AsyncClient, ASGITransport
    from services.orchestrator.app.models.contracts import HostedRunResponse
    import services.orchestrator.app.main as main_mod

    recorded_transcripts = []

    class ClarificationModelClient:
        async def generate_content(self, agent, user_message, run_context, transcript):
            recorded_transcripts.append([dict(t) for t in transcript])
            if not any(t.get("role") == "model" for t in transcript):
                transcript.append({
                    "role": "model",
                    "parts": [{
                        "function_call": {
                            "name": "ask_clarification",
                            "args": {
                                "question": "Which address?",
                                "options": ["Home", "Work"],
                            },
                        }
                    }],
                })
                return HostedRunResponse(
                    protocolVersion="1",
                    runId=run_context.get("run_id", "run-1"),
                    revision=run_context.get("revision", 0),
                    status="awaiting_answer",
                    reply="Which address?",
                    questions=[{
                        "question": "Which address?",
                        "options": ["Home", "Work"],
                    }],
                )
            else:
                return HostedRunResponse(
                    protocolVersion="1",
                    runId=run_context.get("run_id", "run-1"),
                    revision=run_context.get("revision", 1),
                    status="completed",
                    reply="Thanks for the answer!",
                )

    client_instance = ClarificationModelClient()
    monkeypatch.setattr(app.state, "provider", client_instance)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_id = str(uuid.uuid4())
        start_res = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": req_id,
                "message": "Checkout my cart",
                "context": {"page": "cart", "values": {}, "availableTargets": []},
            },
            headers=auth_headers,
        )
        assert start_res.status_code == 200
        start_data = start_res.json()
        assert start_data["status"] == "awaiting_answer"
        run_id = start_data["runId"]

        continue_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "answer",
                "answer": "Home",
            },
            headers=auth_headers,
        )
        assert continue_res.status_code == 200
        continue_data = continue_res.json()
        assert continue_data["status"] == "completed"

        assert len(recorded_transcripts) >= 2
        second_turn_transcript = recorded_transcripts[-1]
        user_turns = [t for t in second_turn_transcript if t.get("role") == "user"]
        assert len(user_turns) >= 2
        last_user_turn = user_turns[-1]
        assert last_user_turn["parts"] == [
            {
                "function_response": {
                    "name": "ask_clarification",
                    "response": {"answer": "Home"},
                }
            }
        ]

