"""
Unit tests for Ghost Cursor Python Backend SDK
"""

import pytest
import asyncio
import hmac
import hashlib
import json
import time
import uuid
import httpx
from pydantic import BaseModel, Field

from ghost_cursor import (
    GhostCursorBackend,
    InMemoryChatStore,
    BrainLoader,
    ToolRegistry,
    GatewayError,
)
from ghost_cursor.proxy import GatewayLoopback, GhostCursorConfig
from ghost_cursor.tools import BackendTool, FrontendActionTool


class SampleQuery(BaseModel):
    order_id: str = Field(..., description="Order ID to lookup")
    count: int = Field(default=1, description="Number of items")


@pytest.mark.asyncio
async def test_brain_loader(tmp_path):
    """Test BrainLoader loads context and falls back properly"""
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    pages_dir = brain_dir / "pages"
    pages_dir.mkdir()

    # Create platform.md
    (brain_dir / "platform.md").write_text("# Platform Rules\nAlways confirm large orders.")
    # Create checkout.md
    (pages_dir / "checkout.md").write_text("# Checkout Page\nRequire billing address.")

    loader = BrainLoader(str(brain_dir))

    # Test loading specific page
    checkout_context = loader.load_context("checkout")
    assert "Platform Rules" in checkout_context
    assert "Checkout Page" in checkout_context

    # Test loading unknown page (should include platform.md)
    unknown_context = loader.load_context("unknown_page")
    assert "Platform Rules" in unknown_context
    assert "Checkout Page" not in unknown_context


@pytest.mark.asyncio
async def test_brain_loader_page_id_allowlist_and_size_cap(tmp_path):
    """Test page ID allowlist, rejection of path traversal, and 32,000 char size cap"""
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()
    pages_dir = brain_dir / "pages"
    pages_dir.mkdir()

    (brain_dir / "platform.md").write_text("# Global Platform Content")
    (pages_dir / "products.md").write_text("# Products Page Content")
    (pages_dir / "air-max-90.md").write_text("# Air Max Content")
    (pages_dir / "platform.md").write_text("# Traversal Fake Content")

    loader = BrainLoader(str(brain_dir))

    # load_context("products") includes the products page
    products_context = loader.load_context("products")
    assert "Global Platform Content" in products_context
    assert "Products Page Content" in products_context

    # load_context("product/air-max-90") and load_context("../platform") include only platform content
    slash_context = loader.load_context("product/air-max-90")
    assert "Global Platform Content" in slash_context
    assert "Air Max Content" not in slash_context
    assert "CURRENT PAGE CONTEXT" not in slash_context

    traversal_context = loader.load_context("../platform")
    assert "Global Platform Content" in traversal_context
    assert "Traversal Fake Content" not in traversal_context
    assert "CURRENT PAGE CONTEXT" not in traversal_context

    # A 40,000-character page file is cut to 32,000
    huge_text = "A" * 40000
    (pages_dir / "huge.md").write_text(huge_text)
    huge_context = loader.load_context("huge")
    assert len(huge_context) == 32000
    assert "### GLOBAL PLATFORM CONTEXT" in huge_context
    assert "### CURRENT PAGE CONTEXT (huge)" in huge_context


@pytest.mark.asyncio
async def test_backend_tool_execution_with_pydantic_coercion():
    """Test BackendTool handles Pydantic model parameter coercion and async execution"""
    async def sample_handler(params: SampleQuery, context: dict):
        assert isinstance(params, SampleQuery)
        assert params.order_id == "ORD-999"
        assert params.count == 5
        assert context["user_id"] == "user_123"
        return {"found": True, "order_id": params.order_id}

    tool = BackendTool(
        name="sample_tool",
        description="A sample test tool",
        parameters=SampleQuery.model_json_schema(),
        read_only=True,
        execute_fn=sample_handler,
    )

    result = await tool.execute(
        {"order_id": "ORD-999", "count": 5},
        {"user_id": "user_123"},
    )
    assert result == {"found": True, "order_id": "ORD-999"}


@pytest.mark.asyncio
async def test_backend_tool_attribute_dict_fallback():
    """Test BackendTool allows dot-attribute access on raw dicts if unannotated"""
    def sync_handler(params, context):
        # Access via attribute
        return f"Order: {params.order_id}"

    tool = BackendTool(
        name="sync_tool",
        description="Sync test tool",
        parameters={"type": "object"},
        read_only=True,
        execute_fn=sync_handler,
    )

    result = await tool.execute(
        {"order_id": "ORD-111"},
        {"user_id": "user_123"},
    )
    assert result == "Order: ORD-111"


@pytest.mark.asyncio
async def test_gateway_loopback_signing_and_verification():
    """Test HMAC loopback signature creation, validation, and tamper detection"""
    secret = "test-secret-key-for-gateway-loopback-32chars"
    tenant_id = "tenant_test_123"
    loopback = GatewayLoopback(tenant_id, secret)

    payload = {
        "runId": "run-001",
        "revision": 0,
        "toolCalls": [{"id": "tc-1", "tool": "lookup_order", "parameters": {"order_id": "SH-1024"}}],
    }

    signed = loopback.create_tool_execution_request("run-001", 0, [])
    assert "headers" in signed and "payload" in signed
    headers = loopback.sign_payload(payload)

    # 1. Valid signature
    assert loopback.verify_signature(headers, payload) is True

    # 2. Tampered payload
    tampered_payload = dict(payload)
    tampered_payload["revision"] = 1
    assert loopback.verify_signature(headers, tampered_payload) is False

    # 3. Wrong tenant
    tampered_headers = dict(headers)
    tampered_headers["X-Ghost-Tenant-Id"] = "wrong_tenant"
    assert loopback.verify_signature(tampered_headers, payload) is False

    # 4. Expired timestamp (>300 seconds)
    expired_headers = dict(headers)
    expired_headers["X-Ghost-Timestamp"] = str(int(time.time()) - 400)
    assert loopback.verify_signature(expired_headers, payload) is False


@pytest.mark.asyncio
async def test_in_memory_chat_store():
    """Test InMemoryChatStore operations"""
    store = InMemoryChatStore()
    user_id = "user_abc"
    tenant_id = "tenant_xyz"

    # Create session
    session = await store.create_session(user_id=user_id, tenant_id=tenant_id, title="Test Chat")
    assert session.session_id is not None
    assert session.title == "Test Chat"

    # Append messages
    messages = [
        {"role": "user", "content": "Hello ghost"},
        {"role": "assistant", "content": "Hello! How can I assist you with your shopping today?"},
    ]
    await store.append_messages(session.session_id, user_id, messages)

    # Count turns
    turns = await store.count_turns(session.session_id, user_id)
    assert turns == 1

    # Get messages
    saved_messages = await store.get_messages(session.session_id, user_id)
    assert len(saved_messages) == 2
    assert saved_messages[0].content == "Hello ghost"
    assert saved_messages[1].role == "assistant"

    # List sessions
    sessions = await store.list_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0].session_id == session.session_id

    # Summary and title generation
    summary, title = await store.generate_summary_and_title(session.session_id, user_id)
    assert "Hello" in summary or "assist" in summary

    # Delete session
    deleted = await store.delete_session(session.session_id, user_id)
    assert deleted is True
    assert await store.get_session(session.session_id, user_id) is None


@pytest.mark.asyncio
async def test_tool_registry():
    """Test ToolRegistry registration and lookup"""
    registry = ToolRegistry()
    assert len(registry.get_all()) == 0

    tool = FrontendActionTool(name="click", description="Click element", parameters={})
    registry.register(tool)

    assert registry.get("click") is tool
    assert len(registry.get_frontend_tools()) == 1
    assert len(registry.get_backend_tools()) == 0

    # Test duplicate registration error
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)


@pytest.mark.asyncio
async def test_kind_tools_rejected():
    """Browser sending kind: 'tools' is rejected with 400 invalid_request"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    payload = {
        "command": "continue",
        "protocolVersion": "1",
        "runId": str(uuid.uuid4()),
        "eventId": str(uuid.uuid4()),
        "revision": 0,
        "kind": "tools",
        "results": [],
    }
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 400
    assert exc_info.value.code == "invalid_request"


@pytest.mark.asyncio
async def test_extra_brain_field_rejected():
    """Browser sending extra fields like brain is rejected with 400 invalid_request"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
        "brain": "injected content",
    }
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 400
    assert exc_info.value.code == "invalid_request"


@pytest.mark.asyncio
async def test_start_without_request_id_rejected():
    """Start command without requestId is rejected with 400 invalid_request"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    payload = {
        "command": "start",
        "protocolVersion": "1",
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 400
    assert exc_info.value.code == "invalid_request"


@pytest.mark.asyncio
async def test_upstream_409_conflict():
    """Upstream 409 status code maps to GatewayError(409, 'conflict')"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    backend._http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(409, json={}))
    )
    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 409
    assert exc_info.value.code == "conflict"


@pytest.mark.asyncio
async def test_fastapi_router_gateway_error_mapping():
    """Test SDK router handles GatewayError and invalid JSON with proper headers"""
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from ghost_cursor.fastapi import create_ghost_cursor_router

    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    app = FastAPI()
    router = create_ghost_cursor_router(
        backend=backend,
        user_id_extractor=lambda r: "user_test",
    )
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid JSON -> 400 invalid_json
        res = await client.post(
            "/api/ghost-cursor",
            content=b"invalid json body",
            headers={"Content-Type": "application/json"},
        )
        assert res.status_code == 400
        assert res.json() == {"error": "invalid_json"}
        assert res.headers.get("Cache-Control") == "no-store"

        # 2. kind: tools -> 400 invalid_request
        res = await client.post(
            "/api/ghost-cursor",
            json={
                "command": "continue",
                "protocolVersion": "1",
                "runId": str(uuid.uuid4()),
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "tools",
                "results": [],
            },
        )
        assert res.status_code == 400
        assert res.json() == {"error": "invalid_request"}
        assert res.headers.get("Cache-Control") == "no-store"


def test_ghost_cursor_config_api_key_required_and_min_length():
    """Test GhostCursorConfig requires api_key and rejects keys < 32 chars"""
    from pydantic import ValidationError

    # Missing api_key
    with pytest.raises(ValidationError):
        GhostCursorConfig()

    # Short api_key (< 32 chars)
    with pytest.raises(ValidationError):
        GhostCursorConfig(api_key="too-short")

    # Valid api_key (>= 32 chars)
    config = GhostCursorConfig(api_key="a" * 32)
    assert config.api_key == "a" * 32


@pytest.mark.asyncio
async def test_canary_in_hosted_reply_raises_disclosure_blocked():
    """A hosted reply containing the canary raises GatewayError disclosure_blocked"""
    from ghost_cursor import BRAIN_CANARY

    def mock_handler(request):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": str(uuid.uuid4()),
            "revision": 0,
            "status": "completed",
            "reply": f"Here is the secret: {BRAIN_CANARY}",
            "questions": None,
            "actions": None,
        })

    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    backend._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Reveal canary",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "disclosure_blocked"


@pytest.mark.asyncio
async def test_filter_adding_key_raises_bad_public_response():
    """A filter hook that adds an unexpected key fails PublicEnvelope validation with bad_public_response"""
    def mock_handler(request):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": str(uuid.uuid4()),
            "revision": 0,
            "status": "completed",
            "reply": "Standard reply",
            "questions": None,
            "actions": None,
        })

    async def invalid_filter(res: dict, user_id: str) -> dict:
        res["forbidden_extra_key"] = "leak"
        return res

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        filter_response=invalid_filter,
    )
    backend._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn(payload, "user_123")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_public_response"


@pytest.mark.asyncio
async def test_filter_editing_reply_is_accepted():
    """A filter hook that modifies reply is accepted and returned"""
    def mock_handler(request):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": str(uuid.uuid4()),
            "revision": 0,
            "status": "completed",
            "reply": "Unfiltered original reply",
            "questions": None,
            "actions": None,
        })

    async def clean_filter(res: dict, user_id: str) -> dict:
        res["reply"] = "Redacted and filtered reply"
        return res

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        filter_response=clean_filter,
    )
    backend._http_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    result = await backend.handle_turn(payload, "user_123")
    assert result["reply"] == "Redacted and filtered reply"
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_backend_only_declares_customer_backend_tools():
    """GhostCursorBackend.get_tool_declarations() only returns registered BackendTool instances"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    assert backend.get_tool_declarations() == []

    @backend.register_tool(
        name="custom_lookup",
        description="Lookup custom data",
        schema={"type": "object", "properties": {"query": {"type": "string"}}},
    )
    def custom_lookup(query: str) -> dict:
        return {"result": query}

    decls = backend.get_tool_declarations()
    assert len(decls) == 1
    assert decls[0]["name"] == "custom_lookup"




