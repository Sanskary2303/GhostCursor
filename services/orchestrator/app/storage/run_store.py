"""
Run Store Implementations

PostgreSQL and in-memory run stores for ephemeral run state management.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from ..models.run import RunState, RunStore

logger = logging.getLogger(__name__)


class InMemoryRunStore(RunStore):
    """
    In-memory run store for testing and development.
    NOT suitable for production use.
    """

    def __init__(self):
        self._runs: Dict[str, RunState] = {}
        self._index_by_request: Dict[str, str] = {}  # (tenant:subject:requestId) -> runId

    async def save(self, run: RunState) -> None:
        self._runs[run.id] = run
        key = f"{run.tenant}:{run.subject}:{run.request_id}"
        self._index_by_request[key] = run.id

    async def get(self, run_id: str) -> Optional[RunState]:
        run = self._runs.get(run_id)
        if run and run.is_expired:
            return None  # Treat expired runs as 410 Gone
        return run

    async def get_by_request_id(self, tenant: str, subject: str, request_id: str) -> Optional[RunState]:
        key = f"{tenant}:{subject}:{request_id}"
        run_id = self._index_by_request.get(key)
        if run_id:
            return await self.get(run_id)
        return None

    async def delete(self, run_id: str) -> None:
        run = self._runs.pop(run_id, None)
        if run:
            key = f"{run.tenant}:{run.subject}:{run.request_id}"
            self._index_by_request.pop(key, None)


class PostgreSQLRunStore(RunStore):
    """
    PostgreSQL run store for production use.
    Uses JSONB for run state, with transactional locking and revision checks.

    NOTE: The baseline serializes a run with SELECT FOR UPDATE and may hold
    the transaction during model generation. This is a known scaling limitation.
    Production should use short transactional claims/leases.
    """

    def __init__(self, database_url: str, pool_size: int = 5, lock_timeout_seconds: int = 3):
        self.database_url = database_url
        self.pool_size = pool_size
        self.lock_timeout_seconds = lock_timeout_seconds
        self._pool = None

    async def initialize(self) -> None:
        """Create connection pool and ensure schema exists"""
        try:
            import asyncpg
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=self.pool_size,
                command_timeout=60,
            )

            # Create table if not exists (explicit migration mode recommended)
            async with self._pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ghost_runs (
                        id UUID PRIMARY KEY,
                        tenant VARCHAR(64) NOT NULL,
                        subject VARCHAR(128) NOT NULL,
                        request_id UUID NOT NULL,
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        data JSONB NOT NULL,
                        UNIQUE (tenant, subject, request_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ghost_runs_expiry ON ghost_runs(expires_at);
                    CREATE INDEX IF NOT EXISTS idx_ghost_runs_tenant_subject ON ghost_runs(tenant, subject);
                """)

            logger.info("PostgreSQL run store initialized")
        except ImportError:
            logger.error("asyncpg not installed. Install with: pip install asyncpg")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL run store: {e}")
            raise

    async def save(self, run: RunState) -> None:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        data = run.to_db_dict()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ghost_runs (id, tenant, subject, request_id, expires_at, data)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (id) DO UPDATE SET
                    data = $6,
                    expires_at = $5
                """,
                run.id,
                run.tenant,
                run.subject,
                run.request_id,
                run.expires_at,
                json.dumps(data),
            )

    async def get(self, run_id: str) -> Optional[RunState]:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        async with self._pool.acquire() as conn:
            # Use SELECT FOR UPDATE for transactional locking
            row = await conn.fetchrow(
                """
                SELECT data FROM ghost_runs
                WHERE id = $1 AND expires_at > NOW()
                FOR UPDATE NOWAIT
                """,
                run_id,
            )

            if not row:
                return None

            data = json.loads(row["data"])
            return RunState.from_db_dict(data)

    async def get_by_request_id(self, tenant: str, subject: str, request_id: str) -> Optional[RunState]:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT data FROM ghost_runs
                WHERE tenant = $1 AND subject = $2 AND request_id = $3
                AND expires_at > NOW()
                """,
                tenant,
                subject,
                request_id,
            )

            if not row:
                return None

            data = json.loads(row["data"])
            return RunState.from_db_dict(data)

    async def delete(self, run_id: str) -> None:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM ghost_runs WHERE id = $1",
                run_id,
            )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None