"""
Tests for PostgreSQL Run Store with Transactional Locking (Step 23)
"""

import asyncio
from contextlib import asynccontextmanager
import os
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from services.orchestrator.app.main import app
import services.orchestrator.app.main as main_mod
from services.orchestrator.app.migrate import run_migrations
from services.orchestrator.app.models.run import RunState
from services.orchestrator.app.storage.run_store import PostgreSQLRunStore

TEST_DB_URL = os.getenv("GHOST_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="GHOST_TEST_DATABASE_URL not set, skipping PostgreSQL run store tests",
)


@asynccontextmanager
async def get_test_pg_store():
    """Context manager that migrates database and provides a clean PostgreSQLRunStore"""
    await run_migrations(TEST_DB_URL)
    store = PostgreSQLRunStore(TEST_DB_URL, pool_size=5, timeout=5.0, command_timeout=30.0)
    await store.initialize()

    # Truncate table for test isolation
    async with store._pool.acquire() as conn:
        await conn.execute("DELETE FROM ghost_runs")

    try:
        yield store
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_pg_store_lifecycle_and_migration(auth_headers, monkeypatch):
    """Test explicit migration, atomic pending create, locked context manager, and orchestrator integration"""
    async with get_test_pg_store() as pg_store:
        monkeypatch.setattr(main_mod, "run_store", pg_store)

        tenant = "shophive_demo"
        subject = "user_demo_123"
        req_id = str(uuid.uuid4())

        # 1. Test create_pending
        run = RunState(
            tenant=tenant,
            subject=subject,
            request_id=req_id,
            revision=-1,
            start_payload={"test": "payload"},
        )
        inserted_id = await pg_store.create_pending(run)
        assert inserted_id == run.id

        # Duplicate create_pending returns None
        dup_inserted = await pg_store.create_pending(run)
        assert dup_inserted is None

        # Verify pending state in database
        loaded = await pg_store.get_by_request_id(tenant, subject, req_id)
        assert loaded is not None
        assert loaded.id == run.id
        assert loaded.revision == -1

        # 2. Test locked context manager
        async with pg_store.locked(run.id, tenant, subject) as (locked_run, save):
            assert locked_run is not None
            assert locked_run.revision == -1
            locked_run.revision = 0
            locked_run.status = "awaiting_actions"
            await save(locked_run)

        reloaded = await pg_store.get(run.id)
        assert reloaded is not None
        assert reloaded.revision == 0
        assert reloaded.status == "awaiting_actions"

        # 3. Test through HTTP API
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create run
            create_payload = {
                "protocolVersion": "1",
                "requestId": str(uuid.uuid4()),
                "message": "Turn on dark mode",
                "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
            }
            create_res = await client.post("/v1/runs", json=create_payload, headers=auth_headers)
            assert create_res.status_code == 200
            run_data = create_res.json()
            assert run_data["revision"] == 0
            run_id = run_data["runId"]

            # Continue run
            continue_payload = {
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "actions",
                "results": [
                    {"id": a["id"], "ok": True, "output": {}}
                    for a in run_data["actions"]
                ],
            }
            cont_res = await client.post(
                f"/v1/runs/{run_id}/continue",
                json=continue_payload,
                headers=auth_headers,
            )
            assert cont_res.status_code == 200
            cont_data = cont_res.json()
            assert cont_data["revision"] == 1
            assert cont_data["status"] == "completed"


@pytest.mark.asyncio
async def test_pg_store_concurrent_continues_conflict(auth_headers, monkeypatch):
    """Two concurrent continues at the same revision result in one 200 and one 409 stale_revision"""
    async with get_test_pg_store() as pg_store:
        monkeypatch.setattr(main_mod, "run_store", pg_store)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create run
            create_payload = {
                "protocolVersion": "1",
                "requestId": str(uuid.uuid4()),
                "message": "Turn on dark mode",
                "context": {"page": "home", "values": {}, "availableTargets": ["theme.toggle"]},
            }
            create_res = await client.post("/v1/runs", json=create_payload, headers=auth_headers)
            assert create_res.status_code == 200
            run_data = create_res.json()
            run_id = run_data["runId"]
            assert run_data["revision"] == 0
            actions = run_data["actions"]

            # 2. Prepare two continuation requests at the same revision (0) but with distinct event IDs
            payload1 = {
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "actions",
                "results": [{"id": a["id"], "ok": True, "output": {}} for a in actions],
            }
            payload2 = {
                "protocolVersion": "1",
                "eventId": str(uuid.uuid4()),
                "revision": 0,
                "kind": "actions",
                "results": [{"id": a["id"], "ok": True, "output": {}} for a in actions],
            }

            # 3. Fire both concurrently
            res1, res2 = await asyncio.gather(
                client.post(f"/v1/runs/{run_id}/continue", json=payload1, headers=auth_headers),
                client.post(f"/v1/runs/{run_id}/continue", json=payload2, headers=auth_headers),
            )

            status_codes = sorted([res1.status_code, res2.status_code])
            assert status_codes == [200, 409], f"Expected [200, 409], got {[res1.status_code, res2.status_code]}"

            error_res = res1 if res1.status_code == 409 else res2
            err_data = error_res.json()
            err_msg = err_data.get("error") or err_data.get("detail")
            assert err_msg in ("stale_revision", "run_finished", "in_progress", "event_conflict")

            # 4. Verify in database that revision was incremented exactly once
            final_run = await pg_store.get(run_id)
            assert final_run is not None
            assert final_run.revision == 1
