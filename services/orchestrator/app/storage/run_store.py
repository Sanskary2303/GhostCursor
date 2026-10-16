"""
Run Store Implementations

PostgreSQL and in-memory run stores for ephemeral run state management.
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Optional, Tuple

from ..models.run import RunState, RunStore

logger = logging.getLogger(__name__)


class RunBusyError(Exception):
    pass


class InMemoryRunStore(RunStore):
    """
    In-memory run store for testing and development.
    NOT suitable for production use.
    """

    def __init__(self):
        self._runs: Dict[str, RunState] = {}
        self._index_by_request: Dict[str, str] = {}  # (tenant:subject:requestId) -> runId
        self._locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def create_pending(self, run: RunState) -> Optional[str]:
        """Atomically register a pending run (revision -1). Returns run ID or None if conflict."""
        async with self._global_lock:
            key = f"{run.tenant}:{run.subject}:{run.request_id}"
            if key in self._index_by_request:
                return None
            self._runs[run.id] = run
            self._index_by_request[key] = run.id
            return run.id

    @asynccontextmanager
    async def locked(
        self, run_id: str, tenant: str, subject: str
    ) -> AsyncIterator[Tuple[Optional[RunState], Callable[[RunState], Awaitable[None]]]]:
        """In-memory per-run locking via asyncio.Lock"""
        async with self._global_lock:
            if run_id not in self._locks:
                self._locks[run_id] = asyncio.Lock()
            lock = self._locks[run_id]

        async with lock:
            run_state = self._runs.get(run_id)
            if run_state and (run_state.tenant != tenant or run_state.subject != subject):
                run_state = None

            async def save(run: RunState) -> None:
                await self.save(run)

            yield run_state, save

    async def save(self, run: RunState) -> None:
        async with self._global_lock:
            self._runs[run.id] = run
            key = f"{run.tenant}:{run.subject}:{run.request_id}"
            self._index_by_request[key] = run.id

    async def get(self, run_id: str) -> Optional[RunState]:
        return self._runs.get(run_id)

    async def get_by_request_id(self, tenant: str, subject: str, request_id: str) -> Optional[RunState]:
        key = f"{tenant}:{subject}:{request_id}"
        run_id = self._index_by_request.get(key)
        if run_id:
            return await self.get(run_id)
        return None

    async def delete(self, run_id: str) -> None:
        async with self._global_lock:
            run = self._runs.pop(run_id, None)
            if run:
                key = f"{run.tenant}:{run.subject}:{run.request_id}"
                self._index_by_request.pop(key, None)
            self._locks.pop(run_id, None)


class PostgreSQLRunStore(RunStore):
    """
    PostgreSQL run store for production use.
    Uses JSONB for run state, with transactional locking and revision checks.
    """

    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        timeout: float = 5.0,
        command_timeout: float = 30.0,
        lock_timeout: str = "3s",
    ):
        self.database_url = database_url
        self.pool_size = pool_size
        self.timeout = timeout
        self.command_timeout = command_timeout
        self.lock_timeout = lock_timeout
        self._pool = None

    async def initialize(self) -> None:
        """Create connection pool"""
        try:
            import asyncpg

            # Lock is held during the model call, which is a known scaling limit.
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=self.pool_size,
                timeout=self.timeout,
                command_timeout=self.command_timeout,
            )
            logger.info("PostgreSQL run store initialized")
        except ImportError:
            logger.error("asyncpg not installed. Install with: pip install asyncpg")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL run store: {e}")
            raise

    async def create_pending(self, run: RunState) -> Optional[str]:
        """Atomically insert a pending row (revision -1). Returns run ID or None if conflict."""
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        data = run.to_db_dict()
        run_uuid = uuid.UUID(run.id) if isinstance(run.id, str) else run.id
        req_uuid = uuid.UUID(run.request_id) if isinstance(run.request_id, str) else run.request_id

        async with self._pool.acquire(timeout=self.timeout) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ghost_runs (id, tenant, subject, request_id, expires_at, data)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (tenant, subject, request_id) DO NOTHING
                RETURNING id
                """,
                run_uuid,
                run.tenant,
                run.subject,
                req_uuid,
                run.expires_at,
                json.dumps(data),
            )
            if row:
                return str(row["id"])
            return None

    @asynccontextmanager
    async def locked(
        self, run_id: str, tenant: str, subject: str
    ) -> AsyncIterator[Tuple[Optional[RunState], Callable[[RunState], Awaitable[None]]]]:
        """
        Transactional lock for an individual run using SELECT FOR UPDATE with lock_timeout.
        """
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        try:
            run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        except (ValueError, AttributeError):
            async def noop_save(run: RunState) -> None:
                pass

            yield None, noop_save
            return

        # Lock is held during the model call, which is a known scaling limit.
        async with self._pool.acquire(timeout=self.timeout) as conn:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL lock_timeout = '{self.lock_timeout}'")
                import asyncpg
                try:
                    row = await conn.fetchrow(
                        """
                        SELECT data FROM ghost_runs
                        WHERE id = $1 AND tenant = $2 AND subject = $3
                        FOR UPDATE
                        """,
                        run_uuid,
                        tenant,
                        subject,
                    )
                except asyncpg.exceptions.LockNotAvailableError as e:
                    raise RunBusyError() from e

                run_state: Optional[RunState] = None
                if row:
                    raw_data = row["data"]
                    data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
                    run_state = RunState.from_db_dict(data)

                async def save(run: RunState) -> None:
                    data_dict = run.to_db_dict()
                    r_uuid = uuid.UUID(run.id) if isinstance(run.id, str) else run.id
                    await conn.execute(
                        """
                        UPDATE ghost_runs
                        SET data = $2, expires_at = $3
                        WHERE id = $1
                        """,
                        r_uuid,
                        json.dumps(data_dict),
                        run.expires_at,
                    )

                yield run_state, save

    async def save(self, run: RunState) -> None:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        data = run.to_db_dict()
        run_uuid = uuid.UUID(run.id) if isinstance(run.id, str) else run.id
        req_uuid = uuid.UUID(run.request_id) if isinstance(run.request_id, str) else run.request_id

        async with self._pool.acquire(timeout=self.timeout) as conn:
            res = await conn.execute(
                """
                UPDATE ghost_runs
                SET data = $2, expires_at = $3
                WHERE id = $1
                """,
                run_uuid,
                json.dumps(data),
                run.expires_at,
            )
            if res == "UPDATE 0":
                await conn.execute(
                    """
                    INSERT INTO ghost_runs (id, tenant, subject, request_id, expires_at, data)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (tenant, subject, request_id) DO UPDATE SET
                        data = $6,
                        expires_at = $5
                    """,
                    run_uuid,
                    run.tenant,
                    run.subject,
                    req_uuid,
                    run.expires_at,
                    json.dumps(data),
                )

    async def get(self, run_id: str) -> Optional[RunState]:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        try:
            run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        except (ValueError, AttributeError):
            return None

        async with self._pool.acquire(timeout=self.timeout) as conn:
            row = await conn.fetchrow(
                """
                SELECT data FROM ghost_runs
                WHERE id = $1
                """,
                run_uuid,
            )

            if not row:
                return None

            raw_data = row["data"]
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            return RunState.from_db_dict(data)

    async def get_by_request_id(self, tenant: str, subject: str, request_id: str) -> Optional[RunState]:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        try:
            req_uuid = uuid.UUID(request_id) if isinstance(request_id, str) else request_id
        except (ValueError, AttributeError):
            return None

        async with self._pool.acquire(timeout=self.timeout) as conn:
            row = await conn.fetchrow(
                """
                SELECT data FROM ghost_runs
                WHERE tenant = $1 AND subject = $2 AND request_id = $3
                """,
                tenant,
                subject,
                req_uuid,
            )

            if not row:
                return None

            raw_data = row["data"]
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            return RunState.from_db_dict(data)

    async def delete(self, run_id: str) -> None:
        if not self._pool:
            raise RuntimeError("Run store not initialized")

        try:
            run_uuid = uuid.UUID(run_id) if isinstance(run_id, str) else run_id
        except (ValueError, AttributeError):
            return

        async with self._pool.acquire(timeout=self.timeout) as conn:
            await conn.execute(
                "DELETE FROM ghost_runs WHERE id = $1",
                run_uuid,
            )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None