"""
Unit tests for Ghost Cursor Python Backend SDK
"""

import pytest
import asyncio
import hmac
import hashlib
import json
import time
from pydantic import BaseModel, Field

from ghost_cursor import (
    GhostCursorBackend,
    InMemoryChatStore,
    BrainLoader,
    ToolRegistry,
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
