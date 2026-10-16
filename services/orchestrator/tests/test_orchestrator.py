"""
Integration and Unit tests for Ghost Cursor Hosted Orchestrator
"""

import json
import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from services.orchestrator.app.main import app


@pytest.fixture
def auth_headers():
    return {
        "Authorization": "Bearer test-key-shophive-demo-0123456789abcdef",
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

        # Non-ASCII character in Bearer token returns 401 instead of 500
        res = await client.post(
            "/v1/runs",
            json={"protocolVersion": "1", "requestId": str(uuid.uuid4()), "message": "Hi"},
            headers={"Authorization": "Bearer \u00e9".encode("latin-1"), "X-Ghost-Subject": "usr"},
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
        "tools": [{"name": "lookup_order", "description": "Lookup order", "parameters": {}}],
    }
    payload2 = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Where is my order SH-1024?",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
        "tools": [{"name": "lookup_order", "description": "Lookup order", "parameters": {}}],
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


@pytest.mark.asyncio
async def test_old_test_key_returns_401():
    """Verify legacy hardcoded test-key-shophive-demo returns 401"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": str(uuid.uuid4()),
                "message": "test",
                "brain": "",
                "context": {"page": "home", "values": {}, "availableTargets": []},
            },
            headers={
                "Authorization": "Bearer test-key-shophive-demo",
                "X-Ghost-Subject": "user_demo_123",
                "Content-Type": "application/json",
            },
        )
        assert res.status_code == 401
        assert res.json()["error"] == "Invalid API key"


def test_missing_tenant_keys_fails(monkeypatch):
    """Missing GHOST_TENANT_KEYS raises RuntimeError"""
    from services.orchestrator.app.main import load_tenant_keys
    monkeypatch.delenv("GHOST_TENANT_KEYS", raising=False)
    with pytest.raises(RuntimeError, match="GHOST_TENANT_KEYS is required"):
        load_tenant_keys()


def test_short_tenant_key_fails(monkeypatch):
    """Tenant API key under 32 characters raises RuntimeError"""
    from services.orchestrator.app.main import load_tenant_keys
    monkeypatch.setenv("GHOST_TENANT_KEYS", '{"short-key": "shophive_demo"}')
    with pytest.raises(RuntimeError, match="at least 32 characters"):
        load_tenant_keys()


def test_invalid_tenant_id_fails(monkeypatch):
    """Tenant ID not matching ^[a-z0-9_]{1,64}$ raises RuntimeError"""
    from services.orchestrator.app.main import load_tenant_keys
    monkeypatch.setenv("GHOST_TENANT_KEYS", '{"test-key-shophive-demo-0123456789abcdef": "Invalid Tenant!"}')
    with pytest.raises(RuntimeError, match="Invalid tenant ID"):
        load_tenant_keys()


def test_invalid_provider_fails(monkeypatch):
    """Invalid GHOST_PROVIDER raises RuntimeError"""
    from services.orchestrator.app.main import init_globals
    monkeypatch.setenv("GHOST_PROVIDER", "invalid_provider")
    with pytest.raises(RuntimeError, match="GHOST_PROVIDER must be 'mock' or 'vertex'"):
        init_globals()


def test_invalid_store_fails(monkeypatch):
    """Invalid GHOST_STORE raises RuntimeError"""
    from services.orchestrator.app.main import init_globals
    monkeypatch.setenv("GHOST_PROVIDER", "mock")
    monkeypatch.setenv("GHOST_STORE", "invalid_store")
    with pytest.raises(RuntimeError, match="GHOST_STORE must be 'memory' or 'postgres'"):
        init_globals()


def test_production_refuses_mock_and_memory(monkeypatch):
    """In production, mock provider and memory store raise RuntimeError"""
    from services.orchestrator.app.main import init_globals
    monkeypatch.setenv("GHOST_ENV", "production")
    monkeypatch.setenv("GHOST_PROVIDER", "mock")
    monkeypatch.setenv("GHOST_STORE", "postgres")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    with pytest.raises(RuntimeError, match="mock provider is not allowed in production"):
        init_globals()

    monkeypatch.setenv("GHOST_PROVIDER", "vertex")
    monkeypatch.setenv("GCP_PROJECT_ID", "test-project")
    monkeypatch.setenv("GHOST_STORE", "memory")
    with pytest.raises(RuntimeError, match="memory store is not allowed in production"):
        init_globals()


def test_vertex_requires_gcp_project_id(monkeypatch):
    """GHOST_PROVIDER=vertex requires GCP_PROJECT_ID"""
    from services.orchestrator.app.main import init_globals
    monkeypatch.setenv("GHOST_ENV", "development")
    monkeypatch.setenv("GHOST_PROVIDER", "vertex")
    monkeypatch.setenv("GHOST_STORE", "memory")
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID is required"):
        init_globals()


def test_postgres_requires_database_url(monkeypatch):
    """GHOST_STORE=postgres requires DATABASE_URL"""
    from services.orchestrator.app.main import init_globals
    monkeypatch.setenv("GHOST_ENV", "development")
    monkeypatch.setenv("GHOST_PROVIDER", "mock")
    monkeypatch.setenv("GHOST_STORE", "postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        init_globals()


def test_orchestrator_startup_without_env_fails():
    """Importing orchestrator main without GHOST_TENANT_KEYS fails startup"""
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k not in ("GHOST_TENANT_KEYS", "GHOST_PROVIDER", "GHOST_STORE")}
    res = subprocess.run(
        [sys.executable, "-c", "import services.orchestrator.app.main"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert res.returncode != 0
    assert "GHOST_TENANT_KEYS is required" in res.stderr


@pytest.mark.asyncio
async def test_body_too_large_rejected(auth_headers):
    """A 70 KB body is rejected with 413 and too_large error"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        large_payload = {
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "x" * 70000,
            "brain": "",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }
        res = await client.post("/v1/runs", json=large_payload, headers=auth_headers)
        assert res.status_code == 413
        assert res.json() == {"error": "too_large"}
        assert res.headers.get("Cache-Control") == "no-store"
        assert res.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_rate_limiting(monkeypatch, auth_headers):
    """With GHOST_RATE_LIMIT_PER_MIN=3, the 4th request returns 429 rate_limited"""
    from services.orchestrator.app.main import RATE_LIMIT_STORE
    RATE_LIMIT_STORE.clear()
    monkeypatch.setenv("GHOST_RATE_LIMIT_PER_MIN", "3")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "test",
            "brain": "",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }
        for _ in range(3):
            p = dict(payload, requestId=str(uuid.uuid4()))
            res = await client.post("/v1/runs", json=p, headers=auth_headers)
            assert res.status_code == 200

        # 4th request -> 429
        p = dict(payload, requestId=str(uuid.uuid4()))
        res = await client.post("/v1/runs", json=p, headers=auth_headers)
        assert res.status_code == 429
        assert res.json() == {"error": "rate_limited"}
        assert res.headers.get("Cache-Control") == "no-store"
        assert res.headers.get("X-Content-Type-Options") == "nosniff"

    RATE_LIMIT_STORE.clear()


@pytest.mark.asyncio
async def test_security_headers_present_on_200_response():
    """A 200 response has both Cache-Control and X-Content-Type-Options headers"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/health")
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "no-store"
        assert res.headers.get("X-Content-Type-Options") == "nosniff"


@pytest.mark.asyncio
async def test_expired_run_returns_410(auth_headers):
    """A run whose expires_at is set in the past returns 410 run_expired"""
    from datetime import datetime, timezone, timedelta
    from services.orchestrator.app.main import run_store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_id = str(uuid.uuid4())
        res = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": req_id,
                "message": "Add to cart",
                "brain": "",
                "context": {"page": "home", "values": {}, "availableTargets": []},
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        run_id = res.json()["runId"]

        # Set expires_at in the past
        stored_run = await run_store.get(run_id)
        assert stored_run is not None
        stored_run.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await run_store.save(stored_run)

        # 1. Continue expired run -> 410
        continue_res = await client.post(
            f"/v1/runs/{run_id}/continue",
            json={
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": stored_run.revision,
                "kind": "cancel",
            },
            headers=auth_headers,
        )
        assert continue_res.status_code == 410
        assert continue_res.json()["error"] == "run_expired"

        # 2. Deduplicate create with expired run -> 410
        dedup_res = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": req_id,
                "message": "Add to cart",
                "brain": "",
                "context": {"page": "home", "values": {}, "availableTargets": []},
            },
            headers=auth_headers,
        )
        assert dedup_res.status_code == 410
        assert dedup_res.json()["error"] == "run_expired"


@pytest.mark.asyncio
async def test_post_missing_content_length_returns_411(auth_headers):
    """POST request without content-length header returns 411 length_required"""
    # Use ASGI directly to send POST without content-length
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/runs",
        "raw_path": b"/v1/runs",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"authorization", auth_headers["Authorization"].encode()),
            (b"x-ghost-subject", auth_headers["X-Ghost-Subject"].encode()),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
        "http_version": "1.1",
    }

    response_status = None
    response_headers = []
    response_body = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        nonlocal response_status, response_headers, response_body
        if message["type"] == "http.response.start":
            response_status = message["status"]
            response_headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_body.append(message.get("body", b""))

    await app(scope, receive, send)

    assert response_status == 411
    body_json = json.loads(b"".join(response_body).decode())
    assert body_json == {"error": "length_required"}
    header_dict = dict(response_headers)
    assert header_dict.get(b"cache-control") == b"no-store"
    assert header_dict.get(b"x-content-type-options") == b"nosniff"


@pytest.mark.asyncio
async def test_extra_field_in_create_body_rejected_422(auth_headers):
    """Extra unknown field in create body returns 422 due to extra='forbid'"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Hello",
            "context": {"page": "home", "values": {}, "availableTargets": []},
            "unexpected_field": "disallowed",
        }
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_nan_value_in_context_values_rejected_422(auth_headers):
    """NaN or non-finite float in context.values is rejected with 422"""
    from pydantic import ValidationError
    from services.orchestrator.app.models.contracts import PageContext
    with pytest.raises(ValidationError):
        PageContext(values={"bad_val": float("nan")})
    with pytest.raises(ValidationError):
        PageContext(values={"inf_val": float("inf")})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        req_id = str(uuid.uuid4())
        content = json.dumps({
            "protocolVersion": "1",
            "requestId": req_id,
            "message": "test",
            "context": {"page": "home", "values": {"rating": float("nan")}, "availableTargets": []},
        })
        res = await client.post(
            "/v1/runs",
            content=content,
            headers=dict(auth_headers, **{"Content-Type": "application/json"}),
        )
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_undeclared_tool_name_fails_run(monkeypatch, auth_headers):
    """Model calling an undeclared tool causes run to fail with plan failure reply"""
    from services.orchestrator.app import main as main_module
    from services.orchestrator.app.models.contracts import ToolCallRequest, HostedRunResponse

    async def mock_generate(*args, **kwargs):
        return HostedRunResponse(
            protocolVersion="1",
            runId=str(uuid.uuid4()),
            revision=0,
            status="awaiting_tools",
            reply="Looking up...",
            toolCalls=[ToolCallRequest(id=str(uuid.uuid4()), tool="unauthorized_tool", parameters={})],
        )

    monkeypatch.setattr(main_module.vertex_client, "generate_content", mock_generate)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/runs",
            json={
                "protocolVersion": "1",
                "requestId": str(uuid.uuid4()),
                "message": "Perform action",
                "tools": [{"name": "lookup_order", "description": "Lookup order", "parameters": {}}],
                "context": {"page": "home", "values": {}, "availableTargets": []},
            },
            headers=auth_headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "failed"
        assert data["reply"] == "I couldn't produce a valid plan. Please rephrase."
        assert not data.get("toolCalls")


def test_mixed_calls_to_parse_response_fails():
    """Passing mixed function calls to _parse_response returns failed with plan failure reply"""
    from services.orchestrator.app.llm.vertex import parse_model_response
    from types import SimpleNamespace

    # Mixed frontend + backend
    fake_mixed_response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="click",
                                args={"target_id": "btn_submit"},
                            )
                        ),
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="lookup_order",
                                args={"order_id": "123"},
                            )
                        ),
                    ]
                )
            )
        ]
    )
    result = parse_model_response(fake_mixed_response, {"run_id": "test-run", "revision": 0})
    assert result.status == "failed"
    assert result.reply == "I couldn't produce a valid plan. Please rephrase."

    # Mixed clarification + action
    fake_clarify_mixed = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="ask_clarification",
                                args={"question": "Which color?", "options": ["red", "blue"]},
                            )
                        ),
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="click",
                                args={"target_id": "btn"},
                            )
                        ),
                    ]
                )
            )
        ]
    )
    result_clarify = parse_model_response(fake_clarify_mixed, {"run_id": "test-run", "revision": 0})
    assert result_clarify.status == "failed"
    assert result_clarify.reply == "I couldn't produce a valid plan. Please rephrase."


def test_validate_actions_strict_rules():
    """validate_actions strictly enforces schemas, allowed keys, and length limits"""
    from services.orchestrator.app.models.contracts import validate_actions

    # Valid plan
    valid = [
        {"type": "navigate", "target_page": "orders", "explanation": "go to orders"},
        {"type": "click", "target_id": "order.track", "explanation": "track order"},
        {"type": "fill_input", "target_id": "search.input", "value": "shoes", "explanation": "search"},
        {"type": "select_option", "target_id": "filter.sort", "option": "price_asc", "explanation": "sort"},
        {"type": "toggle_switch", "target_id": "setting.dark", "state": True, "explanation": "dark mode"},
        {"type": "guided_tour", "steps": [{"target_id": "hero.title", "message": "welcome"}], "explanation": "tour"},
    ]
    out = validate_actions(valid)
    assert len(out) == 6

    # Extra key rejected
    with pytest.raises(ValueError, match="unexpected keys"):
        validate_actions([{"type": "click", "target_id": "btn", "extra_key": "bad"}])

    # Unsafe navigation rejected
    with pytest.raises(ValueError, match="must be an in-app page, not a URL"):
        validate_actions([{"type": "navigate", "target_page": "https://evil.com"}])

    for scheme_url in ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "mailto:a@b.c"]:
        with pytest.raises(ValueError, match="must be an in-app page, not a URL"):
            validate_actions([{"type": "navigate", "target_page": scheme_url}])

    # Accepts valid in-app pages
    assert len(validate_actions([{"type": "navigate", "target_page": "settings"}])) == 1
    assert len(validate_actions([{"type": "navigate", "target_page": "product/air-max-90"}])) == 1

    # Missing required field
    with pytest.raises(ValueError, match="missing 'target_id'"):
        validate_actions([{"type": "click"}])

    # Too many actions
    with pytest.raises(ValueError, match="at most 12 actions"):
        validate_actions([{"type": "click", "target_id": f"btn.{i}"} for i in range(13)])


def test_normalize_schema_nested_and_optional_pydantic():
    """Pydantic model with nested model and Optional field normalizes without title or $ref, and with nullable"""
    from services.orchestrator.app.tools.frontend_actions import normalize_schema
    from pydantic import BaseModel
    from typing import Any, Optional

    class SubItem(BaseModel):
        sku: str
        quantity: Optional[int] = None

    class QueryOrder(BaseModel):
        order_id: str
        item: SubItem
        notes: Optional[str] = None

    raw_schema = QueryOrder.model_json_schema()
    normalized = normalize_schema(raw_schema)

    def assert_no_key_recursive(d: Any, forbidden_key: str):
        if isinstance(d, dict):
            assert forbidden_key not in d, f"Key {forbidden_key} should not be in normalized schema: {d}"
            for v in d.values():
                assert_no_key_recursive(v, forbidden_key)
        elif isinstance(d, list):
            for item in d:
                assert_no_key_recursive(item, forbidden_key)

    assert_no_key_recursive(normalized, "title")
    assert_no_key_recursive(normalized, "$ref")
    assert_no_key_recursive(normalized, "$defs")
    assert_no_key_recursive(normalized, "definitions")

    # Check nullable
    assert normalized["properties"]["notes"]["nullable"] is True
    assert normalized["properties"]["item"]["properties"]["quantity"]["nullable"] is True

    # Check nested inlining
    assert normalized["properties"]["item"]["type"] == "object"
    assert "sku" in normalized["properties"]["item"]["properties"]


@pytest.mark.asyncio
async def test_tool_named_frontend_tool_rejected(auth_headers):
    """Customer tool colliding with frontend action (e.g. 'click') returns 422"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "check order",
        "context": {"page": "home", "values": {}, "availableTargets": []},
        "tools": [
            {
                "name": "click",
                "description": "custom click",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 422
        error_msg = res.json().get("error") or str(res.json().get("detail", ""))
        assert "collides" in error_msg.lower()


@pytest.mark.asyncio
async def test_tool_with_list_type_rejected(auth_headers):
    """Customer tool with type as a list is rejected with 422"""
    payload = {
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "check order",
        "context": {"page": "home", "values": {}, "availableTargets": []},
        "tools": [
            {
                "name": "lookup_item",
                "description": "Lookup an item",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "val": {"type": ["string", "number"]},
                    },
                },
            }
        ],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/runs", json=payload, headers=auth_headers)
        assert res.status_code == 422







