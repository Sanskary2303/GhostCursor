import os

os.environ.setdefault(
    "GHOST_TENANT_KEYS",
    '{"test-key-shophive-demo-0123456789abcdef": "shophive_demo"}',
)
os.environ.setdefault("GHOST_PROVIDER", "mock")
os.environ.setdefault("GHOST_STORE", "memory")
os.environ.setdefault(
    "GHOST_CURSOR_API_KEY",
    "test-key-shophive-demo-0123456789abcdef",
)
os.environ.setdefault("GHOST_RATE_LIMIT_PER_MIN", "100000")

import pytest
from services.orchestrator.app.main import create_app
from services.orchestrator.app.storage.run_store import InMemoryRunStore
from services.orchestrator.app.llm.vertex import MockVertexAIClient
import services.orchestrator.app.main as main_mod


@pytest.fixture
def auth_headers():
    return {
        "Authorization": "Bearer test-key-shophive-demo-0123456789abcdef",
        "X-Ghost-Subject": "user_demo_123",
        "Content-Type": "application/json",
    }


@pytest.fixture
def store():
    return InMemoryRunStore()


@pytest.fixture
def run_store(store):
    return store


@pytest.fixture
def provider():
    return MockVertexAIClient()


@pytest.fixture
def tenant_keys():
    return {"test-key-shophive-demo-0123456789abcdef": "shophive_demo"}


@pytest.fixture
def app(store, provider, tenant_keys):
    return create_app(store=store, provider=provider, tenant_keys=tenant_keys)


@pytest.fixture(autouse=True)
def fresh_app(app, store, provider, monkeypatch):
    monkeypatch.setattr(main_mod, "app", app)
    try:
        import services.orchestrator.tests.test_orchestrator as test_orch
        monkeypatch.setattr(test_orch, "app", app)
    except (ImportError, AttributeError):
        pass
    try:
        import services.orchestrator.tests.test_pg_store as test_pg
        monkeypatch.setattr(test_pg, "app", app)
    except (ImportError, AttributeError):
        pass
    return app
