"""
End-to-End Integration Tests for Ghost Cursor Full Stack

Tests the complete 4-tier topology:
Browser Client -> Customer Gateway (ShopHive) -> Hosted Orchestrator -> Loopback Local Tool -> Client
"""

import sys
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

# Import both apps
from services.orchestrator.app.main import app as orch_app
from services.orchestrator.app.llm.vertex import MockVertexAIClient
sys.path.insert(0, "demo/shophive/backend")
from main import app as shop_app, ghost


@pytest.mark.asyncio
async def test_e2e_action_planning_flow(monkeypatch):
    """
    Test E2E action planning:
    Frontend asks "Add to cart" -> Gateway proxies to Orchestrator -> Orchestrator returns actions
    -> Gateway projects clean public response -> Frontend reports action completion -> Done.
    """
    orch_transport = ASGITransport(app=orch_app)
    shop_transport = ASGITransport(app=shop_app)

    # Intercept GhostCursorBackend HTTP client to route to test orch_transport instead of external network
    async def mock_get_http_client(self):
        return AsyncClient(transport=orch_transport, base_url="http://localhost:8080")

    monkeypatch.setattr(ghost, "_get_http_client", mock_get_http_client.__get__(ghost, type(ghost)))

    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        # Log in first
        login_res = await client.post("/api/login", json={"username": "demo"})
        assert login_res.status_code == 200

        # 1. Frontend sends start command
        start_payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Add to cart",
            "context": {
                "page": "products/air-max-90",
                "values": {},
                "availableTargets": ["product.size.10", "product.add_to_cart_btn"],
            },
        }

        response = await client.post("/api/ghost-cursor", json=start_payload)
        assert response.status_code == 200
        data = response.json()

        assert data["protocolVersion"] == "1"
        assert data["status"] == "awaiting_actions"
        assert len(data["actions"]) == 2
        assert data["actions"][0]["target_id"] == "product.size.10"
        assert data["actions"][1]["target_id"] == "product.add_to_cart_btn"
        # Verify internal toolCalls or brain are NOT leaked in public response
        assert "toolCalls" not in data or data.get("toolCalls") is None
        assert "brain" not in data

        run_id = data["runId"]

        # 2. Frontend executes actions and sends continue command
        continue_payload = {
            "command": "continue",
            "protocolVersion": "1",
            "runId": run_id,
            "eventId": str(uuid.uuid4()),
            "revision": data["revision"],
            "kind": "actions",
            "results": [
                {"id": a["id"], "ok": True, "output": {}}
                for a in data["actions"]
            ],
        }

        cont_response = await client.post("/api/ghost-cursor", json=continue_payload)
        assert cont_response.status_code == 200
        cont_data = cont_response.json()
        assert cont_data["status"] == "completed"
        assert "added it to your cart" in cont_data["reply"].lower()


@pytest.mark.asyncio
async def test_e2e_gateway_loopback_tool_execution(monkeypatch):
    """
    Test Gateway Loopback (Reverse-Dispatch) local tool execution:
    User asks "Where is order SH-1024?"
    -> Customer Gateway forwards request to Hosted Orchestrator
    -> Orchestrator determines it needs private customer domain data, issues toolCall 'lookup_order'
    -> Customer Gateway detects toolCall, executes it LOCALLY against customer mock database
    -> Customer Gateway automatically loops back to Orchestrator with the order details
    -> Orchestrator composes final synthesized reply with tracking info
    -> Gateway returns public response to user without ever leaking internal database query/toolCalls
    """
    orch_transport = ASGITransport(app=orch_app)
    shop_transport = ASGITransport(app=shop_app)

    async def mock_get_http_client(self):
        return AsyncClient(transport=orch_transport, base_url="http://localhost:8080")

    monkeypatch.setattr(ghost, "_get_http_client", mock_get_http_client.__get__(ghost, type(ghost)))

    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        # Log in first
        login_res = await client.post("/api/login", json={"username": "demo"})
        assert login_res.status_code == 200

        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Where is my order SH-1024?",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }

        response = await client.post("/api/ghost-cursor", json=payload)
        assert response.status_code == 200
        data = response.json()

        # The loopback loop in GhostCursorBackend executes local tool and continues to completion
        assert data["status"] == "completed"
        assert "SH-1024" in data["reply"]
        assert "UPS" in data["reply"]
        assert "1Z999AA10123456784" in data["reply"]
        assert "toolCalls" not in data or data.get("toolCalls") is None

        # Verify chat store recorded the session
        sessions_res = await client.get("/api/ghost-cursor/sessions")
        assert sessions_res.status_code == 200
        sessions_data = sessions_res.json()
        assert len(sessions_data["sessions"]) > 0


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected():
    """Unauthenticated request to /api/ghost-cursor returns 401."""
    shop_transport = ASGITransport(app=shop_app)
    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Add to cart",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }
        response = await client.post("/api/ghost-cursor", json=payload)
        assert response.status_code == 401
        assert response.json()["detail"] == "login_required"


@pytest.mark.asyncio
async def test_query_param_user_id_ignored_without_session():
    """Passing user_id in query params without session returns 401."""
    shop_transport = ASGITransport(app=shop_app)
    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Add to cart",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }
        response = await client.post("/api/ghost-cursor?user_id=someone", json=payload)
        assert response.status_code == 401
        assert response.json()["detail"] == "login_required"


@pytest.mark.asyncio
async def test_order_lookup_ownership_authorization(monkeypatch):
    """
    User cannot lookup orders belonging to other users:
    User is logged in as 'demo' (user_demo), but queries SH-987 (owned by user_other).
    Tool returns 'not found', synthesized reply confirms order not found.
    """
    orch_transport = ASGITransport(app=orch_app)
    shop_transport = ASGITransport(app=shop_app)

    async def mock_get_http_client(self):
        return AsyncClient(transport=orch_transport, base_url="http://localhost:8080")

    monkeypatch.setattr(ghost, "_get_http_client", mock_get_http_client.__get__(ghost, type(ghost)))

    new_fixtures = {
        "sh-987": {
            "status": "awaiting_tools",
            "reply": "Let me look up that order for you...",
            "toolCalls": [
                {"id": str(uuid.uuid4()), "tool": "lookup_order", "parameters": {"order_id": "SH-987"}},
            ],
        },
        **MockVertexAIClient.FIXTURES,
    }
    monkeypatch.setattr(MockVertexAIClient, "FIXTURES", new_fixtures)

    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        login_res = await client.post("/api/login", json={"username": "demo"})
        assert login_res.status_code == 200

        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Where is order SH-987?",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }

        response = await client.post("/api/ghost-cursor", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "not found" in data["reply"].lower()


@pytest.mark.asyncio
async def test_login_invalid_body():
    """POST /api/login with non-JSON body returns 400, and non-dict JSON returns 401."""
    shop_transport = ASGITransport(app=shop_app)
    headers = {"Origin": "http://localhost:8081"}
    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        res_not_json = await client.post("/api/login", content=b"not json", headers=headers)
        assert res_not_json.status_code == 400
        assert res_not_json.json()["detail"] == "invalid_json"

        res_non_dict = await client.post("/api/login", json=[1], headers=headers)
        assert res_non_dict.status_code == 401
        assert res_non_dict.json()["detail"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_order_lookup_different_user_cannot_read_sh_1024(monkeypatch):
    """
    A different user cannot read SH-1024 (owned by user_demo):
    User is logged in as 'other' (user_other), and queries SH-1024.
    Tool returns 'not found', synthesized reply confirms order not found.
    """
    orch_transport = ASGITransport(app=orch_app)
    shop_transport = ASGITransport(app=shop_app)

    async def mock_get_http_client(self):
        return AsyncClient(transport=orch_transport, base_url="http://localhost:8080")

    monkeypatch.setattr(ghost, "_get_http_client", mock_get_http_client.__get__(ghost, type(ghost)))

    async with AsyncClient(transport=shop_transport, base_url="http://localhost:8081") as client:
        login_res = await client.post("/api/login", json={"username": "other"})
        assert login_res.status_code == 200

        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Where is my order SH-1024?",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }

        response = await client.post("/api/ghost-cursor", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "not found" in data["reply"].lower()




