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
from pydantic import BaseModel, Field, ValidationError

from ghost_cursor import (
    GhostCursorBackend,
    InMemoryChatStore,
    BrainLoader,
    ToolRegistry,
    GatewayError,
    loopback_key,
    canonical_tool_calls,
    sign_tool_batch,
    verify_tool_batch,
)
from ghost_cursor.proxy import GatewayLoopback, GhostCursorConfig
from ghost_cursor.tools import BackendTool, FrontendActionTool


def make_mock_awaiting_tools(backend, run_id, revision, tool_calls, reply="Executing..."):
    key = loopback_key(backend.config.api_key)
    sig = sign_tool_batch(key, backend.config.tenant_id, run_id, revision, tool_calls)
    return {
        "protocolVersion": "1",
        "runId": run_id,
        "revision": revision,
        "status": "awaiting_tools",
        "reply": reply,
        "questions": None,
        "actions": None,
        "toolCalls": tool_calls,
        "loopbackSignature": sig,
    }


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
    backend._get_http_client = lambda: httpx.AsyncClient(
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
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

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
async def test_canary_in_hosted_reply_not_saved_to_chat_store():
    """A hosted reply blocked by canary disclosure check is never written to chat store"""
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
    store = InMemoryChatStore()
    backend.attach_chat_store(store)
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

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
    assert await store.list_sessions("user_123") == []


@pytest.mark.asyncio
async def test_filtered_reply_persists_filtered_content_to_chat_store():
    """A filter_response hook changing reply persists the filtered reply to chat store"""
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

    async def filter_hook(res: dict, user_id: str) -> dict:
        res["reply"] = "[filtered]"
        return res

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        filter_response=filter_hook,
    )
    store = InMemoryChatStore()
    backend.attach_chat_store(store)
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    result = await backend.handle_turn(payload, "user_123")
    assert result["reply"] == "[filtered]"
    sessions = await store.list_sessions("user_123")
    assert len(sessions) == 1
    messages = await store.get_messages(sessions[0].session_id, "user_123")
    assert len(messages) == 2
    assert messages[1].role == "assistant"
    assert messages[1].content == "[filtered]"


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
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

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
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

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


from ghost_cursor import SQLAlchemyChatStore
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_chat_persistence_start_and_continue_same_session():
    """Start + answer in one run -> one session with 4 messages, all having run_id"""
    store = InMemoryChatStore(tenant_id="tenant_main")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_main",
    )
    backend.attach_chat_store(store)

    run_id = str(uuid.uuid4())
    step = 0

    def mock_handler(request):
        nonlocal step
        step += 1
        if step == 1:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 1,
                "status": "awaiting_answer",
                "reply": "Which size would you like?",
                "questions": [{"id": "q1", "question": "Size?", "options": ["9", "10"]}],
                "actions": None,
            })
        else:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Added size 10 to cart.",
                "questions": None,
                "actions": None,
            })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # 1. Start turn
    start_payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Add shoes to my cart",
        "context": {"page": "product", "values": {}, "availableTargets": []},
    }
    res1 = await backend.handle_turn(start_payload, "user_alice")
    assert res1["status"] == "awaiting_answer"

    # Verify session and messages after start
    sessions = await store.list_sessions("user_alice")
    assert len(sessions) == 1
    session_id = sessions[0].session_id

    msgs1 = await store.get_messages(session_id, "user_alice")
    assert len(msgs1) == 2
    assert msgs1[0].role == "user"
    assert msgs1[0].content == "Add shoes to my cart"
    assert msgs1[0].run_id == run_id
    assert msgs1[1].role == "assistant"
    assert msgs1[1].content == "Which size would you like?"
    assert msgs1[1].run_id == run_id

    # 2. Continue turn (answer)
    continue_payload = {
        "command": "continue",
        "protocolVersion": "1",
        "runId": run_id,
        "eventId": str(uuid.uuid4()),
        "revision": 1,
        "kind": "answer",
        "answer": "10",
    }
    res2 = await backend.handle_turn(continue_payload, "user_alice")
    assert res2["status"] == "completed"

    # Verify still exactly 1 session, now with 4 messages
    sessions = await store.list_sessions("user_alice")
    assert len(sessions) == 1
    msgs2 = await store.get_messages(session_id, "user_alice")
    assert len(msgs2) == 4
    assert [m.role for m in msgs2] == ["user", "assistant", "user", "assistant"]
    assert msgs2[2].content == "10"
    assert msgs2[2].run_id == run_id
    assert msgs2[3].content == "Added size 10 to cart."
    assert msgs2[3].run_id == run_id


@pytest.mark.asyncio
async def test_second_start_creates_new_session_or_reuses_session_id():
    """A second start creates a new session, or reuses session if sessionId provided"""
    store = InMemoryChatStore(tenant_id="tenant_main")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_main",
    )
    backend.attach_chat_store(store)

    run_id_1 = str(uuid.uuid4())
    run_id_2 = str(uuid.uuid4())
    run_id_3 = str(uuid.uuid4())

    def mock_handler(request):
        body = json.loads(request.content)
        if "first" in body.get("message", ""):
            rid = run_id_1
        elif "second" in body.get("message", ""):
            rid = run_id_2
        else:
            rid = run_id_3
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": rid,
            "revision": 0,
            "status": "completed",
            "reply": "Reply for " + body.get("message", ""),
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # First start
    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "first start",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_bob")

    sessions = await store.list_sessions("user_bob")
    assert len(sessions) == 1
    session_1_id = sessions[0].session_id

    # Second start without sessionId -> new session created
    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "second start",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_bob")

    sessions = await store.list_sessions("user_bob")
    assert len(sessions) == 2

    # Third start with explicit sessionId -> reuses session_1
    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session_1_id,
        "message": "third message to session 1",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_bob")

    sessions = await store.list_sessions("user_bob")
    assert len(sessions) == 2
    session_1_msgs = await store.get_messages(session_1_id, "user_bob")
    assert len(session_1_msgs) == 4  # 2 messages from first turn + 2 from third turn


@pytest.mark.asyncio
async def test_chat_sessions_scoping_by_user_and_tenant():
    """Sessions of another user or tenant are never listed"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store_tenant_a = SQLAlchemyChatStore(engine, tenant_id="tenant_a")
    await store_tenant_a.create_tables()

    store_tenant_b = SQLAlchemyChatStore(engine, tenant_id="tenant_b")

    # Create session for user_1 in tenant_a
    sess1 = await store_tenant_a.create_session("user_1", "tenant_a", title="User 1 Tenant A")
    # Create session for user_2 in tenant_a
    sess2 = await store_tenant_a.create_session("user_2", "tenant_a", title="User 2 Tenant A")
    # Create session for user_1 in tenant_b
    sess3 = await store_tenant_b.create_session("user_1", "tenant_b", title="User 1 Tenant B")

    # User 1 on Tenant A sees only User 1's Tenant A session
    u1_ta = await store_tenant_a.list_sessions("user_1")
    assert len(u1_ta) == 1
    assert u1_ta[0].session_id == sess1.session_id

    # User 2 on Tenant A sees only User 2's Tenant A session
    u2_ta = await store_tenant_a.list_sessions("user_2")
    assert len(u2_ta) == 1
    assert u2_ta[0].session_id == sess2.session_id

    # User 1 on Tenant B sees only User 1's Tenant B session
    u1_tb = await store_tenant_b.list_sessions("user_1")
    assert len(u1_tb) == 1
    assert u1_tb[0].session_id == sess3.session_id

    # User 2 on Tenant B has no sessions
    u2_tb = await store_tenant_b.list_sessions("user_2")
    assert len(u2_tb) == 0


@pytest.mark.asyncio
async def test_assistant_tool_calls_recorded_without_outputs():
    """Assistant messages record executed tool calls as [{'id': ..., 'tool': ...}] without outputs"""
    store = InMemoryChatStore(tenant_id="tenant_main")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_main",
    )
    backend.attach_chat_store(store)

    @backend.register_tool(
        name="lookup_order",
        description="Lookup order details",
        schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
    )
    def lookup_order(order_id: str) -> dict:
        return {"status": "shipped", "tracking": "TRK-9999", "secret_debug": "never-store-outputs"}

    run_id = str(uuid.uuid4())
    step = 0

    def mock_handler(request):
        nonlocal step
        step += 1
        if step == 1:
            return httpx.Response(200, json=make_mock_awaiting_tools(
                backend,
                run_id,
                1,
                [{"id": "tc_order_1", "tool": "lookup_order", "parameters": {"order_id": "SH-101"}}],
                reply="Looking up your order...",
            ))
        else:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Your order SH-101 is shipped!",
                "questions": None,
                "actions": None,
            })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Where is my order SH-101?",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
    }
    result = await backend.handle_turn(payload, "user_charlie")
    assert result["status"] == "completed"

    sessions = await store.list_sessions("user_charlie")
    assert len(sessions) == 1
    msgs = await store.get_messages(sessions[0].session_id, "user_charlie")
    assert len(msgs) == 2
    assistant_msg = msgs[1]
    assert assistant_msg.role == "assistant"
    assert assistant_msg.tool_calls == [{"id": "tc_order_1", "tool": "lookup_order"}]
    # Output must NOT be present
    assert "output" not in assistant_msg.tool_calls[0]
    assert "secret_debug" not in json.dumps(assistant_msg.tool_calls)


@pytest.mark.asyncio
async def test_session_auto_summary_after_four_user_turns():
    """Summarization and title update are triggered every 4 user turns"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SQLAlchemyChatStore(engine, tenant_id="tenant_summary")
    await store.create_tables()

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_summary",
    )
    backend.attach_chat_store(store)

    run_id = str(uuid.uuid4())

    def mock_handler(request):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 0,
            "status": "completed",
            "reply": "Assistant reply regarding sneaker selection and sizing advice.",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # Turn 1: start
    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Turn 1 user question",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_dan")

    sessions = await store.list_sessions("user_dan")
    assert len(sessions) == 1
    session_id = sessions[0].session_id
    assert sessions[0].summary is None

    # Turns 2, 3, 4 with continue (or start with same sessionId)
    for i in range(2, 5):
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "sessionId": session_id,
            "message": f"Turn {i} user question",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }, "user_dan")

    turns = await store.count_turns(session_id, "user_dan")
    assert turns == 4

    if backend._background:
        await asyncio.gather(*backend._background)

    # Now verify summary and title were updated
    updated_session = await store.get_session(session_id, "user_dan")
    assert updated_session is not None
    assert updated_session.summary is not None
    assert len(updated_session.summary) > 0
    await engine.dispose()



# ============================================================================
# Step 25: Gateway Hardening Tests (G-3, G-4)
# ============================================================================

def test_service_url_validation():
    """service_url must be https or http for localhost/127.0.0.1/::1, with no user/pass/query/fragment"""
    valid_urls = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://[::1]:8080",
        "https://cloud.ghostcursor.ai",
        "https://cloud.ghostcursor.ai/v1/runs",
        "https://anything.example",
    ]
    for url in valid_urls:
        cfg = GhostCursorConfig(
            api_key="test-key-shophive-demo-0123456789abcdef",
            service_url=url,
        )
        assert cfg.service_url == url

    invalid_urls = [
        "http://cloud.ghostcursor.ai",                     # http on non-localhost
        "http://192.168.1.1:8080",                         # http on non-loopback IP
        "http://api:8080",                                 # rejected by default
        "http://[2001:db8::1]:8080",                       # IPv6 non-loopback rejected
        "http://evil-host:8080",                           # non-loopback single-label rejected
        "http://metadata.google.internal",                 # internal metadata rejected
        "https://user:pass@cloud.ghostcursor.ai",           # user/pass
        "https://cloud.ghostcursor.ai?token=secret",        # query
        "https://cloud.ghostcursor.ai#section",             # fragment
        "ftp://localhost:8080",                             # scheme not http/https
        "not-a-valid-url",                                  # no scheme
    ]
    for url in invalid_urls:
        with pytest.raises(ValidationError):
            GhostCursorConfig(
                api_key="test-key-shophive-demo-0123456789abcdef",
                service_url=url,
            )

    # http://api:8080 accepted with insecure_http_hosts=["api"]
    cfg_insecure = GhostCursorConfig(
        api_key="test-key-shophive-demo-0123456789abcdef",
        service_url="http://api:8080",
        insecure_http_hosts=["api"],
    )
    assert cfg_insecure.service_url == "http://api:8080"

    # insecure_http_hosts=["API"] accepts http://api:8080
    cfg_case = GhostCursorConfig(
        api_key="test-key-shophive-demo-0123456789abcdef",
        service_url="http://api:8080",
        insecure_http_hosts=["API"],
    )
    assert cfg_case.service_url == "http://api:8080"


@pytest.mark.asyncio
async def test_upstream_too_large_streaming():
    """Streaming response exceeding max_response_size aborts with GatewayError(502, 'upstream_too_large')"""
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        max_response_size=100,  # 100 bytes cap
    )

    def mock_handler(request):
        # Generate 500 bytes response
        payload = {
            "protocolVersion": "1",
            "runId": str(uuid.uuid4()),
            "revision": 0,
            "status": "completed",
            "reply": "x" * 400,
        }
        return httpx.Response(200, content=json.dumps(payload).encode())

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Hello",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }, "user_123")

    assert exc_info.value.status == 502
    assert exc_info.value.code == "upstream_too_large"


@pytest.mark.asyncio
async def test_http_client_follow_redirects_false():
    """HTTP client has follow_redirects=False, upstream redirects map to 502 upstream_error"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    client = await backend._get_http_client()
    assert client.follow_redirects is False

    backend._get_http_client = lambda: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"Location": "/redirect"}))
    )

    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "Hello",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }, "user_123")

    assert exc_info.value.status == 502
    assert exc_info.value.code == "upstream_error"


@pytest.mark.asyncio
async def test_too_many_tool_calls_in_one_plan():
    """If len(toolcalls) > max_tool_calls_per_round, answer every call with ok: false, error: 'too many tool calls in one plan'"""
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        max_tool_calls_per_round=4,
    )

    run_id = str(uuid.uuid4())
    recorded_continue_body = None

    def mock_handler(request):
        nonlocal recorded_continue_body
        body = json.loads(request.content)
        if request.url.path.endswith("/continue"):
            recorded_continue_body = body
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Handled tool failure",
                "questions": None,
                "actions": None,
            })
        # Initial response emits 5 tool calls (> 4 limit)
        tool_calls = [
            {"id": f"tc_{i}", "tool": "lookup", "parameters": {}}
            for i in range(5)
        ]
        return httpx.Response(200, json=make_mock_awaiting_tools(
            backend,
            run_id,
            1,
            tool_calls,
            reply="Executing tools...",
        ))

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Run many tools",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_123")

    assert recorded_continue_body is not None
    results = recorded_continue_body["results"]
    assert len(results) == 5
    for r in results:
        assert r["ok"] is False
        assert r["error"] == "too many tool calls in one plan"


@pytest.mark.asyncio
async def test_argument_validation_pydantic_and_dict():
    """Tool arguments are validated before execution: Pydantic -> model_validate, Dict -> jsonschema.validate"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")

    class OrderParams(BaseModel):
        order_id: str

    executed_tools = []

    @backend.register_tool(
        name="lookup_pydantic",
        description="Lookup via Pydantic model",
        schema=OrderParams,
    )
    def lookup_pydantic(params: OrderParams):
        executed_tools.append("lookup_pydantic")
        return {"status": "ok"}

    @backend.register_tool(
        name="lookup_dict",
        description="Lookup via Dict schema",
        schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "quantity": {"type": "integer"},
            },
            "required": ["sku", "quantity"],
        },
    )
    def lookup_dict(sku: str, quantity: int):
        executed_tools.append("lookup_dict")
        return {"status": "ok"}

    run_id = str(uuid.uuid4())
    recorded_continue_body = None

    def mock_handler(request):
        nonlocal recorded_continue_body
        body = json.loads(request.content)
        if request.url.path.endswith("/continue"):
            recorded_continue_body = body
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Finished",
                "questions": None,
                "actions": None,
            })
        tool_calls = [
            {"id": "tc_pydantic", "tool": "lookup_pydantic", "parameters": {}},  # missing required order_id
            {"id": "tc_dict", "tool": "lookup_dict", "parameters": {"sku": "S1", "quantity": "not_an_int"}},  # invalid type
        ]
        return httpx.Response(200, json=make_mock_awaiting_tools(
            backend,
            run_id,
            1,
            tool_calls,
            reply="Executing...",
        ))

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Run invalid tools",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_123")

    assert recorded_continue_body is not None
    results = recorded_continue_body["results"]
    assert len(results) == 2
    assert results[0]["id"] == "tc_pydantic"
    assert results[0]["ok"] is False
    assert results[0]["error"] == "invalid arguments"

    assert results[1]["id"] == "tc_dict"
    assert results[1]["ok"] is False
    assert results[1]["error"] == "invalid arguments"

    # Neither tool function should have run
    assert len(executed_tools) == 0


@pytest.mark.asyncio
async def test_tool_context_idempotency_key():
    """Tool receives idempotency_key: f'{run_id}:{revision}:{tool_call.id}' in context"""
    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")

    received_context = {}

    @backend.register_tool(
        name="test_context_tool",
        description="Inspects context",
        schema={"type": "object", "properties": {}},
    )
    async def test_context_tool(params: dict, context: dict):
        received_context.update(context)
        return {"status": "ok"}

    run_id = str(uuid.uuid4())

    def mock_handler(request):
        if request.url.path.endswith("/continue"):
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Done",
                "questions": None,
                "actions": None,
            })
        return httpx.Response(200, json=make_mock_awaiting_tools(
            backend,
            run_id,
            1,
            [{"id": "tc_idem_1", "tool": "test_context_tool", "parameters": {}}],
            reply="Executing...",
        ))

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Inspect context",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_123")

    assert received_context.get("idempotency_key") == f"{run_id}:1:tc_idem_1"
    assert received_context.get("user_id") == "user_123"
    assert received_context.get("run_id") == run_id
    assert received_context.get("revision") == 1


@pytest.mark.asyncio
async def test_tool_timeout():
    """Tool execution exceeding config.tool_timeout fails with ok: false, error: 'tool timed out'"""
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tool_timeout=0.05,  # 50ms timeout
    )

    @backend.register_tool(
        name="sleepy_tool",
        description="Tool that takes too long",
        schema={"type": "object", "properties": {}},
    )
    async def sleepy_tool(params: dict, context: dict):
        await asyncio.sleep(0.5)  # 500ms > 50ms
        return {"status": "finished"}

    run_id = str(uuid.uuid4())
    recorded_continue_body = None

    def mock_handler(request):
        nonlocal recorded_continue_body
        body = json.loads(request.content)
        if request.url.path.endswith("/continue"):
            recorded_continue_body = body
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 2,
                "status": "completed",
                "reply": "Timeout handled",
                "questions": None,
                "actions": None,
            })
        return httpx.Response(200, json=make_mock_awaiting_tools(
            backend,
            run_id,
            1,
            [{"id": "tc_slow", "tool": "sleepy_tool", "parameters": {}}],
            reply="Executing...",
        ))

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Run slow tool",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_123")

    assert recorded_continue_body is not None
    results = recorded_continue_body["results"]
    assert len(results) == 1
    assert results[0]["id"] == "tc_slow"
    assert results[0]["ok"] is False
    assert results[0]["error"] == "tool timed out"


def test_django_gateway_view():
    """Django gateway_view requires POST, CSRF enabled, auth, size checks, and delegates via handle_turn_sync"""
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            SECRET_KEY="test-secret-key-django-ghost-cursor",
            ALLOWED_HOSTS=["*"],
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
            ],
        )
        django.setup()

    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    from ghost_cursor_django import gateway_view

    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    view = gateway_view(backend)

    # 1. Assert not csrf_exempt
    assert not getattr(view, "csrf_exempt", False)

    rf = RequestFactory()

    # 2. 405 for GET
    get_req = rf.get("/api/ghost-cursor")
    get_req.user = AnonymousUser()
    get_res = view(get_req)
    assert get_res.status_code == 405

    # 3. 401 when unauthenticated
    post_unauth = rf.post("/api/ghost-cursor", data=json.dumps({"message": "hi"}), content_type="application/json")
    post_unauth.user = AnonymousUser()
    res_unauth = view(post_unauth)
    assert res_unauth.status_code == 401
    assert json.loads(res_unauth.content)["error"] == "unauthorized"
    assert res_unauth.headers["Cache-Control"] == "no-store"

    # Fake authenticated user
    class MockUser:
        is_authenticated = True
        pk = "user_42"

    auth_user = MockUser()

    # 4. 413 when body > 64 KiB
    huge_data = "a" * (65 * 1024)
    post_huge = rf.post("/api/ghost-cursor", data=huge_data, content_type="application/json")
    post_huge.user = auth_user
    res_huge = view(post_huge)
    assert res_huge.status_code == 413
    assert json.loads(res_huge.content)["error"] == "payload_too_large"
    assert res_huge.headers["Cache-Control"] == "no-store"

    # 5. 400 for invalid JSON
    post_bad_json = rf.post("/api/ghost-cursor", data="not json at all", content_type="application/json")
    post_bad_json.user = auth_user
    res_bad_json = view(post_bad_json)
    assert res_bad_json.status_code == 400
    assert json.loads(res_bad_json.content)["error"] == "invalid_json"

    # 6. 200 on success with monkeypatched handle_turn_sync
    recorded_call = {}
    def mock_handle_turn_sync(payload, user_id, current_page=None):
        recorded_call["payload"] = payload
        recorded_call["user_id"] = user_id
        recorded_call["current_page"] = current_page
        return {
            "protocolVersion": "1",
            "runId": "run_test_123",
            "revision": 0,
            "status": "completed",
            "reply": "All good from Django",
            "questions": None,
            "actions": None,
        }

    backend.handle_turn_sync = mock_handle_turn_sync
    valid_payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello Django",
        "context": {"page": "checkout"},
    }
    post_valid = rf.post("/api/ghost-cursor", data=json.dumps(valid_payload), content_type="application/json")
    post_valid.user = auth_user
    res_valid = view(post_valid)
    assert res_valid.status_code == 200
    assert res_valid.headers["Cache-Control"] == "no-store"
    assert json.loads(res_valid.content)["reply"] == "All good from Django"
    assert recorded_call["user_id"] == "user_42"
    assert recorded_call["current_page"] == "checkout"


def test_flask_blueprint():
    """Flask ghost_cursor_blueprint exposes POST "", checks auth, checks Origin, requires JSON, and delegates"""
    from flask import Flask
    from ghost_cursor.flask import ghost_cursor_blueprint

    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")

    current_user_id = None
    def get_user_id():
        return current_user_id

    app = Flask(__name__)
    bp = ghost_cursor_blueprint(backend, get_user_id=get_user_id)
    app.register_blueprint(bp, url_prefix="/api/ghost-cursor")
    client = app.test_client()

    valid_payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello Flask",
        "context": {"page": "home"},
    }

    # 1. 401 if get_user_id returns nothing (current_user_id is None)
    res_unauth = client.post("/api/ghost-cursor", json=valid_payload)
    assert res_unauth.status_code == 401
    assert res_unauth.get_json()["error"] == "unauthorized"
    assert res_unauth.headers["Cache-Control"] == "no-store"

    # Authenticate user
    current_user_id = "user_flask_99"

    # 2. 403 if Origin header is present and differs from request.host_url.rstrip("/")
    res_bad_origin = client.post(
        "/api/ghost-cursor",
        json=valid_payload,
        headers={"Origin": "https://malicious-site.com"},
    )
    assert res_bad_origin.status_code == 403
    assert res_bad_origin.get_json()["error"] == "cross_origin_forbidden"
    assert res_bad_origin.headers["Cache-Control"] == "no-store"

    # 3. 415 if body isn't JSON
    res_not_json = client.post(
        "/api/ghost-cursor",
        data="just text",
        headers={"Content-Type": "text/plain"},
    )
    assert res_not_json.status_code == 415
    assert res_not_json.get_json()["error"] == "unsupported_media_type"

    # 4. 400 for invalid JSON
    res_invalid_json = client.post(
        "/api/ghost-cursor",
        data="{malformed json",
        headers={"Content-Type": "application/json"},
    )
    assert res_invalid_json.status_code == 400
    assert res_invalid_json.get_json()["error"] == "invalid_json"

    # 5. 200 with handle_turn_sync monkeypatched
    recorded_call = {}
    def mock_handle_turn_sync(payload, user_id, current_page=None):
        recorded_call["payload"] = payload
        recorded_call["user_id"] = user_id
        recorded_call["current_page"] = current_page
        return {
            "protocolVersion": "1",
            "runId": "run_flask_456",
            "revision": 0,
            "status": "completed",
            "reply": "All good from Flask",
            "questions": None,
            "actions": None,
        }

    backend.handle_turn_sync = mock_handle_turn_sync
    res_ok = client.post(
        "/api/ghost-cursor",
        json=valid_payload,
        headers={"Origin": "http://localhost"},
    )
    assert res_ok.status_code == 200
    assert res_ok.headers["Cache-Control"] == "no-store"
    assert res_ok.get_json()["reply"] == "All good from Flask"
    assert recorded_call["user_id"] == "user_flask_99"
    assert recorded_call["current_page"] == "home"


@pytest.mark.asyncio
async def test_session_id_isolation_in_memory_store():
    """Two users and one InMemoryChatStore: user B sends user A's sessionId on start.
    A's messages are unchanged, and B gets a new session with a different ID."""
    store = InMemoryChatStore(tenant_id="tenant_test")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_test",
    )
    backend.attach_chat_store(store)

    run_counter = 0

    def mock_handler(request):
        nonlocal run_counter
        run_counter += 1
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": f"run_{run_counter}",
            "revision": 0,
            "status": "completed",
            "reply": f"Reply to turn {run_counter}",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # User A starts a session
    start_a = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Message from user A",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    await backend.handle_turn(start_a, "user_a")

    sessions_a = await store.list_sessions("user_a")
    assert len(sessions_a) == 1
    session_a_id = sessions_a[0].session_id

    msgs_a = await store.get_messages(session_a_id, "user_a")
    assert len(msgs_a) == 2
    assert msgs_a[0].content == "Message from user A"

    # User B starts a session sending User A's sessionId
    start_b = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session_a_id,
        "message": "Message from user B",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    await backend.handle_turn(start_b, "user_b")

    # User A's messages remain intact
    msgs_a_after = await store.get_messages(session_a_id, "user_a")
    assert len(msgs_a_after) == 2
    assert msgs_a_after[0].content == "Message from user A"

    # User B gets a new session with a different ID
    sessions_b = await store.list_sessions("user_b")
    assert len(sessions_b) == 1
    session_b_id = sessions_b[0].session_id
    assert session_b_id != session_a_id

    msgs_b = await store.get_messages(session_b_id, "user_b")
    assert len(msgs_b) == 2
    assert msgs_b[0].content == "Message from user B"


@pytest.mark.asyncio
async def test_session_id_isolation_sqlalchemy_store():
    """SQLAlchemyChatStore with in-memory SQLite: user B sending user A's sessionId
    does not cause an IntegrityError or drop the turn; B's turn is saved into a new session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SQLAlchemyChatStore(engine, tenant_id="tenant_test")
    await store.create_tables()

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_test",
    )
    backend.attach_chat_store(store)

    run_counter = 0

    def mock_handler(request):
        nonlocal run_counter
        run_counter += 1
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": f"run_sql_{run_counter}",
            "revision": 0,
            "status": "completed",
            "reply": f"SQL reply {run_counter}",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    # User A starts
    start_a = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "User A SQLite message",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    await backend.handle_turn(start_a, "user_a")

    sessions_a = await store.list_sessions("user_a")
    assert len(sessions_a) == 1
    session_a_id = sessions_a[0].session_id

    # User B starts sending User A's sessionId
    start_b = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session_a_id,
        "message": "User B SQLite message",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }
    await backend.handle_turn(start_b, "user_b")

    # Verify A's messages
    msgs_a = await store.get_messages(session_a_id, "user_a")
    assert len(msgs_a) == 2
    assert msgs_a[0].content == "User A SQLite message"

    # Verify B's turn IS saved into a distinct session
    sessions_b = await store.list_sessions("user_b")
    assert len(sessions_b) == 1
    session_b_id = sessions_b[0].session_id
    assert session_b_id != session_a_id

    msgs_b = await store.get_messages(session_b_id, "user_b")
    assert len(msgs_b) == 2
    assert msgs_b[0].content == "User B SQLite message"

    await engine.dispose()


@pytest.mark.asyncio
async def test_in_memory_chat_store_rejects_duplicate_session_id():
    """InMemoryChatStore raises ValueError if an existing session_id is passed to create_session"""
    store = InMemoryChatStore(tenant_id="tenant_test")
    s1 = await store.create_session("user_1", "tenant_test", title="Session 1", session_id="fixed-id-123")
    assert s1.session_id == "fixed-id-123"

    with pytest.raises(ValueError, match="session_id already exists"):
        await store.create_session("user_2", "tenant_test", title="Session 2", session_id="fixed-id-123")


@pytest.mark.asyncio
async def test_sqlalchemy_chat_store_cascade_deletion():
    """delete_session removes the session and cleans up all messages without leaving orphan rows"""
    from ghost_cursor.storage import SQGCBChatMessage
    import sqlalchemy as sa

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SQLAlchemyChatStore(engine, tenant_id="tenant_cascade")
    await store.create_tables()

    session = await store.create_session("user_1", "tenant_cascade", title="Cascade test")
    sess_id = session.session_id

    await store.append_messages(
        sess_id,
        "user_1",
        [
            {"role": "user", "content": "Hello world", "token_count": 2},
            {"role": "assistant", "content": "Hi there", "token_count": 2},
        ],
    )

    msgs = await store.get_messages(sess_id, "user_1")
    assert len(msgs) == 2

    # Verify messages exist in database
    async with await store._get_session() as db_session:
        res = await db_session.execute(
            sa.select(SQGCBChatMessage).where(SQGCBChatMessage.session_id == sess_id)
        )
        assert len(res.scalars().all()) == 2

    # Delete session
    deleted = await store.delete_session(sess_id, "user_1")
    assert deleted is True

    # Verify session is gone
    assert await store.get_session(sess_id, "user_1") is None
    assert await store.get_messages(sess_id, "user_1") == []

    # Verify no orphan messages in database table
    async with await store._get_session() as db_session:
        res = await db_session.execute(
            sa.select(SQGCBChatMessage).where(SQGCBChatMessage.session_id == sess_id)
        )
        assert len(res.scalars().all()) == 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_chat_store_tenant_isolation_get_and_delete():
    """Multi-tenant isolation: tenant B cannot read, append to, or delete tenant A's session"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store_a = SQLAlchemyChatStore(engine, tenant_id="tenant_a")
    await store_a.create_tables()
    store_b = SQLAlchemyChatStore(engine, tenant_id="tenant_b")

    sess_a = await store_a.create_session("user_common", "tenant_a", title="Tenant A Session")
    sess_id = sess_a.session_id

    await store_a.append_messages(
        sess_id,
        "user_common",
        [{"role": "user", "content": "Msg A", "token_count": 1}],
    )

    # Tenant B tries to get session, messages, append, count, delete
    assert await store_b.get_session(sess_id, "user_common") is None
    assert await store_b.get_messages(sess_id, "user_common") == []
    assert await store_b.count_turns(sess_id, "user_common") == 0
    with pytest.raises(ValueError, match="Unauthorized or session not found"):
        await store_b.append_messages(sess_id, "user_common", [{"role": "user", "content": "Attack"}])
    assert await store_b.delete_session(sess_id, "user_common") is False

    # Tenant A still has the session and messages
    assert await store_a.get_session(sess_id, "user_common") is not None
    assert len(await store_a.get_messages(sess_id, "user_common")) == 1

    await engine.dispose()


@pytest.mark.asyncio
async def test_in_memory_chat_store_cascade_and_tenant_isolation():
    """InMemoryChatStore cascade deletion removes messages and enforces tenant isolation"""
    store_a = InMemoryChatStore(tenant_id="tenant_a")
    sess = await store_a.create_session("user_1", "tenant_a", title="InMemory Session")
    sess_id = sess.session_id

    await store_a.append_messages(
        sess_id,
        "user_1",
        [{"role": "user", "content": "Hello", "token_count": 1}],
    )
    assert len(await store_a.get_messages(sess_id, "user_1")) == 1

    # Store B with different tenant cannot access or delete
    store_b = InMemoryChatStore(tenant_id="tenant_b")
    store_b._sessions = store_a._sessions
    store_b._messages = store_a._messages

    assert await store_b.get_session(sess_id, "user_1") is None
    assert await store_b.get_messages(sess_id, "user_1") == []
    assert await store_b.delete_session(sess_id, "user_1") is False

    # Delete via store_a cascades
    assert await store_a.delete_session(sess_id, "user_1") is True
    assert sess_id not in store_a._sessions
    assert sess_id not in store_a._messages


@pytest.mark.asyncio
async def test_persist_turn_calculates_token_count():
    """_persist_turn calculates token_count = max(1, len(text) // 4)"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    store = SQLAlchemyChatStore(engine, tenant_id="tenant_tokens")
    await store.create_tables()

    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_tokens",
        chat_store=store,
    )

    user_text = "Where is my package please?"
    assistant_text = "Your package is currently in transit."

    def mock_handler(request):
        return httpx.Response(
            200,
            json={
                "protocolVersion": "1",
                "runId": "run_token_test",
                "revision": 0,
                "status": "completed",
                "reply": assistant_text,
                "actions": [],
            },
        )

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": user_text,
        "context": {"page": "orders", "values": {}, "availableTargets": []},
    }
    await backend.handle_turn(payload, "user_1")

    sessions = await store.list_sessions("user_1")
    assert len(sessions) == 1
    messages = await store.get_messages(sessions[0].session_id, "user_1")
    assert len(messages) == 2

    user_msg = next(m for m in messages if m.role == "user")
    asst_msg = next(m for m in messages if m.role == "assistant")

    assert user_msg.token_count == max(1, len(user_text) // 4)
    assert asst_msg.token_count == max(1, len(assistant_text) // 4)
    assert user_msg.token_count > 0
    assert asst_msg.token_count > 0

    await engine.dispose()


@pytest.mark.asyncio
async def test_reply_returns_before_background_summary_completes():
    """Turn 4 reply returns immediately while background summary task runs concurrently"""
    store = InMemoryChatStore(tenant_id="tenant_summary_bg")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_summary_bg",
    )
    backend.attach_chat_store(store)

    run_id = str(uuid.uuid4())
    gate = asyncio.Event()

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/summaries"):
            # Sleep synchronously or block in async transport?
            # MockTransport handler can be async if transport is async
            pass
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 0,
            "status": "completed",
            "reply": "Assistant reply",
            "questions": None,
            "actions": None,
        })

    # Since httpx.MockTransport supports async handler:
    async def async_mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/summaries"):
            await gate.wait()
            return httpx.Response(200, json={
                "title": "Background Title",
                "summary": "Background model summary sentence one. Sentence two.",
            })
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 0,
            "status": "completed",
            "reply": "Assistant reply",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(async_mock_handler))

    # Turn 1
    t1 = await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "First user message about buying shoes",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_bg")
    assert t1["status"] == "completed"
    sessions = await store.list_sessions("user_bg")
    session_id = sessions[0].session_id

    # Turns 2 & 3
    for i in (2, 3):
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "sessionId": session_id,
            "message": f"User turn {i}",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }, "user_bg")

    # Turn 4: triggers background summary
    t4 = await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session_id,
        "message": "User turn 4 triggers summary",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "user_bg")

    # The turn returned immediately!
    assert t4["status"] == "completed"

    # Background task is in flight and blocked on gate
    assert len(backend._background) > 0
    current_session = await store.get_session(session_id, "user_bg")
    assert current_session.title != "Background Title"
    assert current_session.summary is None

    # Now unblock background task
    gate.set()
    await asyncio.gather(*backend._background)

    updated_session = await store.get_session(session_id, "user_bg")
    assert updated_session.title == "Background Title"
    assert updated_session.summary == "Background model summary sentence one. Sentence two."


@pytest.mark.asyncio
async def test_background_summary_unreachable_orchestrator_falls_back_to_heuristic():
    """If orchestrator /v1/summaries fails, background task falls back to heuristic without raising"""
    store = InMemoryChatStore(tenant_id="tenant_fail_orch")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_fail_orch",
    )
    backend.attach_chat_store(store)

    run_id = str(uuid.uuid4())

    async def async_mock_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/summaries"):
            raise httpx.ConnectError("Connection refused")
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 0,
            "status": "completed",
            "reply": "Assistant reply",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(async_mock_handler))

    session_id = None
    for i in range(1, 5):
        payload = {
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": f"Looking for running shoes step {i}",
            "context": {"page": "home", "values": {}, "availableTargets": []},
        }
        if session_id:
            payload["sessionId"] = session_id
        res = await backend.handle_turn(payload, "user_fail")
        assert res["status"] == "completed"
        if not session_id:
            sess_list = await store.list_sessions("user_fail")
            session_id = sess_list[0].session_id

    # Wait for background task to finish
    if backend._background:
        await asyncio.gather(*backend._background)

    # Verify fallback heuristic title and summary are saved
    sess = await store.get_session(session_id, "user_fail")
    assert sess.title == "Looking for running shoes step 1"
    assert "Looking for running shoes" in sess.summary


def test_loopback_fixed_parity_vector():
    """Verify exact parity vector for HKDF-derived loopback signing."""
    api_key = "test-key-shophive-demo-0123456789abcdef"
    tenant = "shophive_demo"
    ts = 1700000000
    run_id = "r1"
    revision = 2
    tool_calls = [{"id": "c1", "tool": "lookup_order", "parameters": {"order_id": "SH-1024"}}]

    key = loopback_key(api_key)
    assert key.hex() == "8392dd6329e8ba2ce5fa8b87549948f8c7bd0f0220b6a318b4b3d105f2d20c8f"

    canonical = canonical_tool_calls(tool_calls)
    assert canonical == '[{"id":"c1","parameters":{"order_id":"SH-1024"},"tool":"lookup_order"}]'

    sig_payload = sign_tool_batch(key, tenant, run_id, revision, tool_calls, ts=ts)
    assert sig_payload == {
        "v": 1,
        "ts": 1700000000,
        "sig": "4a76b8e7cdf3b27ee025e5205c3a6f95a9e26cc0ecbe96b31dafc6fae1edd7f4",
    }

    assert verify_tool_batch(key, tenant, run_id, revision, tool_calls, sig_payload, now=1700000000) is True


@pytest.mark.asyncio
async def test_gateway_loopback_signature_verification_and_tamper_rejection():
    """Gateway verifies loopbackSignature before dispatching tools; fails closed on any mismatch without calling tools."""
    tool_called = False
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="shophive_demo",
    )

    @backend.register_tool(
        name="lookup_order",
        description="Lookup order",
        schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
    )
    def lookup_order(order_id: str):
        nonlocal tool_called
        tool_called = True
        return {"status": "ok"}

    run_id = str(uuid.uuid4())
    tool_calls = [{"id": "tc_1", "tool": "lookup_order", "parameters": {"order_id": "SH-1024"}}]
    key = loopback_key(backend.config.api_key)
    valid_sig = sign_tool_batch(key, "shophive_demo", run_id, 1, tool_calls)

    # 1. Missing signature -> 502 bad_tool_signature
    tool_called = False
    def mock_missing_sig(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": tool_calls,
            "loopbackSignature": None,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_missing_sig))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 2. Tampered tool parameters -> 502 bad_tool_signature
    tool_called = False
    def mock_tampered_params(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": [{"id": "tc_1", "tool": "lookup_order", "parameters": {"order_id": "SH-9999"}}],
            "loopbackSignature": valid_sig,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_tampered_params))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 3. Wrong tenant -> 502 bad_tool_signature
    tool_called = False
    wrong_tenant_sig = sign_tool_batch(key, "other_tenant", run_id, 1, tool_calls)
    def mock_wrong_tenant(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": tool_calls,
            "loopbackSignature": wrong_tenant_sig,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_wrong_tenant))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 4. Wrong revision -> 502 bad_tool_signature
    tool_called = False
    replayed_sig = sign_tool_batch(key, "shophive_demo", run_id, 0, tool_calls)
    def mock_replayed(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": tool_calls,
            "loopbackSignature": replayed_sig,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_replayed))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 5. Expired timestamp (> 300s old) -> 502 bad_tool_signature
    tool_called = False
    expired_sig = sign_tool_batch(key, "shophive_demo", run_id, 1, tool_calls, ts=int(time.time()) - 305)
    def mock_expired(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": tool_calls,
            "loopbackSignature": expired_sig,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_expired))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 6. Invalid version v != 1 -> 502 bad_tool_signature
    tool_called = False
    bad_v_sig = dict(valid_sig, v=2)
    def mock_bad_v(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 1,
            "status": "awaiting_tools",
            "reply": "Checking...",
            "toolCalls": tool_calls,
            "loopbackSignature": bad_v_sig,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_bad_v))
    with pytest.raises(GatewayError) as exc_info:
        await backend.handle_turn({
            "command": "start",
            "protocolVersion": "1",
            "requestId": str(uuid.uuid4()),
            "message": "check order",
            "context": {"page": "orders", "values": {}, "availableTargets": []},
        }, "user_1")
    assert exc_info.value.status == 502
    assert exc_info.value.code == "bad_tool_signature"
    assert tool_called is False

    # 7. Valid signature succeeds and calls tool
    tool_called = False
    step = 0
    def mock_valid(req):
        nonlocal step
        step += 1
        if step == 1:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 1,
                "status": "awaiting_tools",
                "reply": "Checking...",
                "toolCalls": tool_calls,
                "loopbackSignature": valid_sig,
            })
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 2,
            "status": "completed",
            "reply": "Found it",
            "questions": None,
            "actions": None,
        })
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_valid))
    res = await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "check order",
        "context": {"page": "orders", "values": {}, "availableTargets": []},
    }, "user_1")
    assert res["status"] == "completed"
    assert tool_called is True
    assert "loopbackSignature" not in res


from datetime import datetime, timezone
from ghost_cursor.types import ChatSession, ChatMessage


@pytest.mark.asyncio
async def test_types_datetimes_always_utc():
    """ChatSession and ChatMessage __post_init__ ensures tzinfo is timezone.utc even for naive datetimes."""
    now_naive = datetime.now()
    session = ChatSession(
        session_id="s1",
        tenant_id="t1",
        user_id="u1",
        title="Title",
        summary=None,
        created_at=now_naive,
        updated_at=now_naive,
    )
    assert session.created_at.tzinfo == timezone.utc
    assert session.updated_at.tzinfo == timezone.utc
    assert session.metadata["created_at"].endswith("+00:00")
    assert session.metadata["updated_at"].endswith("+00:00")

    msg = ChatMessage(
        message_id="m1",
        session_id="s1",
        role="user",
        content="Hello",
        tool_calls=[],
        client_actions=[],
        token_count=2,
        created_at=now_naive,
    )
    assert msg.created_at.tzinfo == timezone.utc
    assert msg.metadata["created_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_sql_alchemy_chat_store_returns_utc_datetimes(tmp_path):
    """SQLAlchemyChatStore parsed datetimes have tzinfo == timezone.utc."""
    db_file = tmp_path / "utc_test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    store = SQLAlchemyChatStore(engine, tenant_id="tenant_utc")
    await store.create_tables()

    session = await store.create_session("u_utc", "tenant_utc", "New Conversation")
    assert session.created_at.tzinfo == timezone.utc
    assert session.updated_at.tzinfo == timezone.utc
    assert session.metadata["created_at"].endswith("+00:00")

    await store.append_messages(session.session_id, "u_utc", [{
        "role": "user",
        "content": "Hi",
        "token_count": 1,
    }])

    msgs = await store.get_messages(session.session_id, "u_utc")
    assert len(msgs) == 1
    assert msgs[0].created_at.tzinfo == timezone.utc
    assert msgs[0].metadata["created_at"].endswith("+00:00")
    await engine.dispose()


@pytest.mark.asyncio
async def test_first_turn_updates_heuristic_title_when_default():
    """On first user turn when session title is 'New Conversation', title is updated to first 6 words without LLM call."""
    store = InMemoryChatStore(tenant_id="tenant_first_title")
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="tenant_first_title",
    )
    backend.attach_chat_store(store)

    session = await store.create_session("u_1", "tenant_first_title", "New Conversation")
    run_id = str(uuid.uuid4())

    def mock_handler(req):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": run_id,
            "revision": 0,
            "status": "completed",
            "reply": "We have sizes 9, 10, and 11.",
            "questions": None,
            "actions": None,
        })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    res = await backend.handle_turn({
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session.session_id,
        "message": "What sizes are available in store today please?",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }, "u_1")
    assert res["status"] == "completed"

    updated_session = await store.get_session(session.session_id, "u_1")
    assert updated_session is not None
    # First 6 words of "What sizes are available in store today please?"
    assert updated_session.title == "What sizes are available in store"


def test_act_packaging_backend_exports():
    """ACT §8.3 / §9.4 backend module imports parity."""
    from ghost_cursor.backend import GhostCursorBackend, GatewayError
    from ghost_cursor.backend.storage import SQLAlchemyChatStore, InMemoryChatStore, ChatStore

    assert GhostCursorBackend is not None
    assert GatewayError is not None
    assert SQLAlchemyChatStore is not None
    assert InMemoryChatStore is not None
    assert ChatStore is not None


@pytest.mark.asyncio
async def test_canary_in_streamed_delta_never_emitted():
    """If the model response contains the canary, stream_turn fails with disclosure_blocked and emits no canary."""
    from ghost_cursor import BRAIN_CANARY

    def mock_handler(request):
        return httpx.Response(200, json={
            "protocolVersion": "1",
            "runId": str(uuid.uuid4()),
            "revision": 0,
            "status": "completed",
            "reply": f"Leaking canary: {BRAIN_CANARY} in response",
            "questions": None,
            "actions": None,
        })

    backend = GhostCursorBackend(api_key="test-key-shophive-demo-0123456789abcdef")
    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "message": "Hello",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    emitted = []
    with pytest.raises(GatewayError) as exc_info:
        async for chunk in backend.stream_turn(payload, "user_123"):
            emitted.append(chunk)

    assert exc_info.value.status == 502
    assert exc_info.value.code == "disclosure_blocked"
    # Verify that the canary was never emitted in any chunk
    all_emitted_text = "".join(emitted)
    assert BRAIN_CANARY not in all_emitted_text
    assert "event: status" in all_emitted_text
    assert "event: delta" not in all_emitted_text
    assert "event: envelope" not in all_emitted_text


@pytest.mark.asyncio
async def test_stream_turn_emits_status_deltas_and_envelope():
    """stream_turn streams status events (thinking, tool:..., planning), deltas, and final envelope."""
    from ghost_cursor.proxy import loopback_key, sign_tool_batch
    store = InMemoryChatStore()
    backend = GhostCursorBackend(
        api_key="test-key-shophive-demo-0123456789abcdef",
        tenant_id="shophive_demo",
    )
    backend.attach_chat_store(store)

    @backend.register_tool(
        name="lookup_order",
        description="Lookup order status",
        schema={"type": "object", "properties": {"order_id": {"type": "string"}}},
    )
    def lookup_order(order_id: str) -> dict:
        return {"order_id": order_id, "status": "shipped"}

    run_id = str(uuid.uuid4())
    key = loopback_key("test-key-shophive-demo-0123456789abcdef")
    tool_calls = [{"id": "call_1", "tool": "lookup_order", "parameters": {"order_id": "ORD-123"}}]
    sig = sign_tool_batch(key, "shophive_demo", run_id, 0, tool_calls)

    calls = 0
    def mock_handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 0,
                "status": "awaiting_tools",
                "reply": "Looking up...",
                "toolCalls": tool_calls,
                "loopbackSignature": sig,
            })
        else:
            return httpx.Response(200, json={
                "protocolVersion": "1",
                "runId": run_id,
                "revision": 1,
                "status": "completed",
                "reply": "Your order ORD-123 has shipped.",
                "actions": [{"type": "click", "targetId": "track_btn"}],
            })

    backend._get_http_client = lambda: httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    session = await store.create_session("u_1", "shophive_demo", "Order check")
    payload = {
        "command": "start",
        "protocolVersion": "1",
        "requestId": str(uuid.uuid4()),
        "sessionId": session.session_id,
        "message": "Where is my order ORD-123?",
        "context": {"page": "home", "values": {}, "availableTargets": []},
    }

    events = []
    async for chunk in backend.stream_turn(payload, "u_1"):
        events.append(chunk)

    all_output = "".join(events)
    # 1. status: thinking
    assert 'event: status\ndata: {"status": "thinking"}' in all_output
    # 2. status: tool:lookup_order
    assert 'event: status\ndata: {"status": "tool:lookup_order"}' in all_output
    # 3. status: planning
    assert 'event: status\ndata: {"status": "planning"}' in all_output
    # 4. deltas
    assert "event: delta" in all_output
    assert "ORD-123" in all_output
    # 5. envelope
    assert "event: envelope" in all_output
    assert '"status": "completed"' in all_output
    assert '"actions": [{"type": "click", "targetId": "track_btn"}]' in all_output

    # Check session updated
    messages = await store.get_messages(session.session_id, "u_1")
    assert len(messages) == 2
    assert messages[1].role == "assistant"
    assert messages[1].content == "Your order ORD-123 has shipped."












