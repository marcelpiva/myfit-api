"""Add session_evaluations table for post-session feedback.

This migration creates:
- session_evaluations table with rating, difficulty, energy_level fields
- evaluatorrole and difficultylevel enum types (PostgreSQL)

For new installations, these will be created automatically by create_all().
For existing installations, run this script to add the table.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def _table_exists(conn, table_name: str, is_postgres: bool) -> bool:
    if is_postgres:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                f"  WHERE table_name = '{table_name}'"
                ")"
            )
        )
        return result.scalar()
    else:
        result = await conn.execute(
            text(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            )
        )
        return result.first() is not None


async def migrate(database_url: str) -> None:
    """Create session_evaluations table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if not await _table_exists(conn, "session_evaluations", is_postgres):
            if is_postgres:
                # Create enum types
                await conn.execute(text("""
                    DO $$ BEGIN
                        CREATE TYPE evaluatorrole AS ENUM ('trainer', 'student');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$
                """))
                await conn.execute(text("""
                    DO $$ BEGIN
                        CREATE TYPE difficultylevel AS ENUM ('too_easy', 'just_right', 'too_hard');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$
                """))

                await conn.execute(text("""
                    CREATE TABLE session_evaluations (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        appointment_id UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
                        evaluator_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        evaluator_role VARCHAR(20) NOT NULL,
                        overall_rating INTEGER NOT NULL,
                        difficulty VARCHAR(20),
                        energy_level INTEGER,
                        notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_session_evaluations_appointment_id "
                    "ON session_evaluations(appointment_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE session_evaluations (
                        id TEXT PRIMARY KEY,
                        appointment_id TEXT NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
                        evaluator_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        evaluator_role TEXT NOT NULL,
                        overall_rating INTEGER NOT NULL,
                        difficulty TEXT,
                        energy_level INTEGER,
                        notes TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))

            logger.info("Created session_evaluations table")
        else:
            logger.info("session_evaluations table already exists, skipping")

    await engine.dispose()
    logger.info("Migration add_session_evaluations completed successfully")


async def main():
    """Run migration with default database URL."""
    import os
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./myfit.db"
    )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
