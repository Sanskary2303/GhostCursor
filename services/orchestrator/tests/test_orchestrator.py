"""
Integration and Unit tests for Ghost Cursor Hosted Orchestrator
"""

import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from services.orchestrator.app.main import app


@pytest.fixture
def auth_headers():
    return {
        "Authorization": "Bearer test-key-shophive-demo",
        "X-Ghost-Subject": "user_demo_123",
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_health_check():
    """Test health check liveness probe"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ghost-cursor-orchestrator"


@pytest.mark.asyncio
async def test_reject_direct_browser_access(auth_headers):
    """Test that requests with Origin headers are rejected (defense in depth)"""
    headers = dict(auth_headers)
    headers["Origin"] = "https://evil-browser-site.com"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": str(uuid.uuid4()),
                "message": "Hello",
            },
            headers=headers,
        )
        assert response.status_code == 403
        assert "Direct browser access not allowed" in response.text


@pytest.mark.asyncio
async def test_authentication_validation():
    """Test API key and subject validation"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid API key
        res = await client.post(
            "/v1/runs",
            json={"protocolVersion": "1", "requestId": str(uuid.uuid4()), "message": "Hi"},
            headers={"Authorization": "Bearer invalid-key", "X-Ghost-Subject": "usr"},
        )
        assert res.status_code == 401

        # Missing Bearer prefix
        res = await client.post(
            "/v1/runs",
            json={"protocolVersion": "1", "requestId": str(uuid.uuid4()), "message": "Hi"},
            headers={"Authorization": "Basic some-creds", "X-Ghost-Subject": "usr"},
        )
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_run_awaiting_actions(auth_headers):
    """Test creating run that plans frontend actions (dark mode)"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "Turn on dark mode please",
        "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
        "brain": "# Theme rules\nDark mode is in settings.",
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["protocolVersion"] == "1"
        assert data["status"] == "awaiting_actions"
        assert data["revision"] == 0
        assert len(data["actions"]) > 0
        assert any(a.get("target_id") == "theme.dark" for a in data["actions"])


@pytest.mark.asyncio
async def test_create_run_awaiting_answer(auth_headers):
    """Test creating run that requests user clarification"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "Proceed to checkout",
        "context": {"page": "cart", "values": {}, "availableTargets": ["checkout.btn"]},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "awaiting_answer"
        assert len(data["questions"]) > 0
        assert "shipping address" in data["questions"][0]["question"].lower()


@pytest.mark.asyncio
async def test_create_run_awaiting_tools_and_continue_flow(auth_headers):
    """Test complete flow: create run -> awaiting_tools -> continue with tool results -> completed"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "Where is my order SH-1024?",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
        "tools": [
            {
                "name": "lookup_order",
                "description": "Lookup order status",
                "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}}},
            }
        ],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Start run -> should emit tool call
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "awaiting_tools"
        assert len(data["toolCalls"]) > 0
        assert data["toolCalls"][0]["tool"] == "lookup_order"
        run_id = data["runId"]
        tool_call_id = data["toolCalls"][0]["id"]

        # 2. Continue with tool result
        event_id = str(uuid.uuid4())
        continue_payload = {
            "protocolVersion": "1",
            "eventId": event_id,
            "revision": 0,
            "kind": "tools",
            "results": [
                {
                    "id": tool_call_id,
                    "ok": True,
                    "output": {
                        "order_id": "SH-1024",
                        "status": "Shipped",
                        "carrier": "UPS",
                        "tracking_number": "1Z999AA10123456784",
                        "shipped_date": "2024-01-17",
                        "estimated_delivery": "2024-01-20",
                    },
                }
            ],
        }

        continue_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json=continue_payload,
            headers=auth_headers,
        )
        assert continue_res.status_code == 200
        continue_data = continue_res.json()
        assert continue_data["status"] == "completed"
        assert continue_data["revision"] == 1
        assert "SH-1024" in continue_data["reply"]
        assert "UPS" in continue_data["reply"]
        assert "1Z999AA10123456784" in continue_data["reply"]


@pytest.mark.asyncio
async def test_continue_with_action_results(auth_headers):
    """Test continuing run after frontend finishes executing actions"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "Turn on dark mode",
        "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]

        # Continue with action results
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "actions",
            "results": [
                {"id": a["id"], "ok": True, "output": {}}
                for a in data["actions"]
            ],
        }

        cont_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json=continue_payload,
            headers=auth_headers,
        )
        assert cont_res.status_code == 200
        cont_data = cont_res.json()
        assert cont_data["status"] == "completed"
        assert "executed successfully" in cont_data["reply"].lower()


@pytest.mark.asyncio
async def test_continue_with_user_answer(auth_headers):
    """Test continuing run with user answering a clarification question"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "checkout",
        "context": {"page": "cart", "values": {}, "availableTargets": []},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]

        # Provide answer
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "answer",
            "answer": "123 Main St, NYC (saved)",
        }

        cont_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json=continue_payload,
            headers=auth_headers,
        )
        assert cont_res.status_code == 200
        cont_data = cont_res.json()
        assert cont_data["status"] == "awaiting_actions"
        assert len(cont_data["actions"]) > 0
        assert "saved address" in cont_data["reply"]


@pytest.mark.asyncio
async def test_cancel_run(auth_headers):
    """Test cancelling an ongoing run"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "checkout",
        "context": {"page": "cart", "values": {}, "availableTargets": []},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]

        # Cancel
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "cancel",
        }

        cont_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json=continue_payload,
            headers=auth_headers,
        )
        assert cont_res.status_code == 200
        cont_data = cont_res.json()
        assert cont_data["status"] == "cancelled"


@pytest.mark.asyncio
async def test_deduplication_and_conflict(auth_headers):
    """Test request deduplication and conflict detection"""
    req_id = str(uuid.uuid4())
    payload = {
        "protocolVersion": "1",
        "requestId": req_id,
        "message": "What is available?",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First call
        res1 = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res1.status_code == 200
        data1 = res1.json()

        # Duplicate call with identical payload -> returns cached run
        res2 = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data1["runId"] == data2["runId"]

        # Duplicate requestId with DIFFERENT payload -> 409 Conflict
        conflicting_payload = dict(payload)
        conflicting_payload["message"] = "A different message"
        res3 = await client.post("/v1/runs", json=conflicting_payload, headers=auth_headers)
        assert res3.status_code == 409


@pytest.mark.asyncio
async def test_actions_have_unique_uuid_ids(auth_headers):
    """Test that planned actions receive unique UUID IDs"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode please",
        "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "awaiting_actions"
        actions = data["actions"]
        assert len(actions) > 0

        action_ids = []
        for action in actions:
            assert "id" in action
            # Verify valid UUID string
            val = uuid.UUID(action["id"])
            assert str(val) == action["id"]
            action_ids.append(action["id"])

        # Check uniqueness across actions
        assert len(set(action_ids)) == len(action_ids)


@pytest.mark.asyncio
async def test_runs_get_different_tool_call_ids(auth_headers):
    """Test that two separate runs get different tool-call IDs"""
    payload1 = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Where is my order SH-1024?",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
    }
    payload2 = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Where is my order SH-1024?",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res1 = await client.post("/v1/runs", json=payload1, headers=auth_headers)
        res2 = await client.post("/v1/runs", json=payload2, headers=auth_headers)

        assert res1.status_code == 200
        assert res2.status_code == 200

        tc1 = res1.json()["toolCalls"]
        tc2 = res2.json()["toolCalls"]

        assert len(tc1) > 0
        assert len(tc2) > 0
        assert tc1[0]["id"] != tc2[0]["id"]


@pytest.mark.asyncio
async def test_actions_continuation_with_failure_returns_failed(auth_headers):
    """Test that an action continuation with ok: false returns status == 'failed'"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode please",
        "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 200
        data = res.json()
        run_id = data["runId"]
        actions = data["actions"]

        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "actions",
            "results": [
                {"id": actions[0]["id"], "ok": True, "output": {}},
                {"id": actions[1]["id"], "ok": False, "error": "Switch element disabled"},
            ],
        }

        cont_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json=continue_payload,
            headers=auth_headers,
        )
        assert cont_res.status_code == 200
        cont_data = cont_res.json()
        assert cont_data["status"] == "failed"
        assert cont_data["reply"] == "Stopped because a step failed. Changes already made on the page were kept."


@pytest.mark.asyncio
async def test_replay_protection(auth_headers):
    """Test identical event replay returns cached 200, changed replay returns 409"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]
        actions = data["actions"]

        event_id = str(uuid.uuid4())
        continue_payload = {
            "protocolVersion": "1",
            "eventId": event_id,
            "revision": 0,
            "kind": "actions",
            "results": [{"id": a["id"], "ok": True, "output": {}} for a in actions],
        }

        # First attempt -> 200
        res1 = await client.post(f"/v1/runs/{run_id}/continue", json=continue_payload, headers=auth_headers)
        assert res1.status_code == 200
        body1 = res1.json()

        # Identical replay -> 200 with identical body
        res2 = await client.post(f"/v1/runs/{run_id}/continue", json=continue_payload, headers=auth_headers)
        assert res2.status_code == 200
        assert res2.json() == body1

        # Changed replay with same eventId -> 409 event_conflict
        changed_payload = dict(continue_payload)
        changed_payload["context"] = {"page": "other"}
        res3 = await client.post(f"/v1/runs/{run_id}/continue", json=changed_payload, headers=auth_headers)
        assert res3.status_code == 409
        assert res3.json()["error"] == "event_conflict"


@pytest.mark.asyncio
async def test_stale_revision_rejected(auth_headers):
    """Continuing with a stale revision returns 409 stale_revision"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]
        actions = data["actions"]

        # Stale revision (e.g. 5 instead of 0)
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 5,
            "kind": "actions",
            "results": [{"id": a["id"], "ok": True, "output": {}} for a in actions],
        }
        res = await client.post(f"/v1/runs/{run_id}/continue", json=continue_payload, headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"] == "stale_revision"


@pytest.mark.asyncio
async def test_unexpected_kind_rejected(auth_headers):
    """Sending 'tools' to an awaiting_answer run returns 409 unexpected_kind"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "checkout",
        "context": {"page": "cart", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        assert data["status"] == "awaiting_answer"
        run_id = data["runId"]

        # Send tools instead of answer
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "tools",
            "results": [],
        }
        res = await client.post(f"/v1/runs/{run_id}/continue", json=continue_payload, headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"] == "unexpected_kind"


@pytest.mark.asyncio
async def test_wrong_result_ids_rejected(auth_headers):
    """Sending results with mismatched IDs returns 409 result_mismatch"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]

        # Send random result ID
        continue_payload = {
            "protocolVersion": "1",
            "eventId": str(uuid.uuid4()),
            "revision": 0,
            "kind": "actions",
            "results": [{"id": str(uuid.uuid4()), "ok": True, "output": {}}],
        }
        res = await client.post(f"/v1/runs/{run_id}/continue", json=continue_payload, headers=auth_headers)
        assert res.status_code == 409
        assert res.json()["error"] == "result_mismatch"


@pytest.mark.asyncio
async def test_terminal_run_continuation_and_cancellation(auth_headers):
    """Continuing a completed run returns 409 run_finished, while cancel returns 200"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn on dark mode",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        run_id = data["runId"]
        actions = data["actions"]

        # Complete the run
        cont_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "actions",
                "results": [{"id": a["id"], "ok": True, "output": {}} for a in actions],
            },
            headers=auth_headers,
        )
        assert cont_res.status_code == 200
        assert cont_res.json()["status"] == "completed"

        # Continuing completed run -> 409 run_finished
        next_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 1,
                "kind": "actions",
                "results": [],
            },
            headers=auth_headers,
        )
        assert next_res.status_code == 409
        assert next_res.json()["error"] == "run_finished"

        # Cancel on completed run -> 200 returning cached response
        cancel_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 1,
                "kind": "cancel",
            },
            headers=auth_headers,
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_turn_limit_enforcement(auth_headers):
    """Turn limit enforces max turns for continue but permits cancel"""
    from services.orchestrator.app.main import run_store

    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "checkout",
        "context": {"page": "cart", "values": {}, "availableTargets": []},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        data = res.json()
        assert data["status"] == "awaiting_answer"
        run_id = data["runId"]

        # Append 12 history turns directly to simulate reaching limit
        run_state = await run_store.get(run_id)
        for i in range(12):
            run_state.history.append({"type": "answer", "revision": i + 1})
        await run_store.save(run_state)

        # Continuing with answer -> 409 turn_limit
        res_limit = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "answer",
                "answer": "123 Main St",
            },
            headers=auth_headers,
        )
        assert res_limit.status_code == 409
        assert res_limit.json()["error"] == "turn_limit"

        # Cancel -> 200
        res_cancel = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "cancel",
            },
            headers=auth_headers,
        )
        assert res_cancel.status_code == 200
        assert res_cancel.json()["status"] == "cancelled"



