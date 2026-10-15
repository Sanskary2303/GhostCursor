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
        assert any(a["type"] == "toggle_switch" for a in data["actions"])


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
                {"id": str(uuid.uuid4()), "ok": True, "output": {"toggled": True}},
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
        assert cont_data["status"] == "completed"
        assert "123 Main St, NYC" in cont_data["reply"]


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
