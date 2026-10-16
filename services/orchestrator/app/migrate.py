"""
Database Migration Runner for Ghost Cursor Orchestrator
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)


async def run_migrations(database_url: str | None = None) -> None:
    """Run all SQL migrations in services/orchestrator/migrations against database_url"""
    db_url = database_url or os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required to run migrations")

    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    if not migrations_dir.exists():
        raise RuntimeError(f"Migrations directory not found: {migrations_dir}")

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        logger.info("No migration files found.")
        return

    conn = await asyncpg.connect(db_url)
    try:
        for sql_file in sql_files:
            logger.info(f"Applying migration: {sql_file.name}")
            sql = sql_file.read_text(encoding="utf-8")
            await conn.execute(sql)
            logger.info(f"Applied migration: {sql_file.name}")
    finally:
        await conn.close()


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_migrations())


if __name__ == "__main__":
    main()

