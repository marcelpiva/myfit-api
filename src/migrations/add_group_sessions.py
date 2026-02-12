"""Add group session support to appointments.

This migration adds:
- is_group BOOLEAN DEFAULT FALSE to appointments
- max_participants INTEGER NULL to appointments
- appointment_participants table for group session members

For new installations, these will be created automatically by create_all().
For existing installations, run this script to add the fields and table.
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


async def _column_exists(conn, table_name: str, column_name: str, is_postgres: bool) -> bool:
    if is_postgres:
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.columns"
                f"  WHERE table_name = '{table_name}' AND column_name = '{column_name}'"
                ")"
            )
        )
        return result.scalar()
    else:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        cols = [row[1] for row in result.fetchall()]
        return column_name in cols


async def _add_column_if_missing(conn, table_name: str, column_name: str,
                                  pg_type: str, sqlite_type: str, is_postgres: bool):
    exists = await _column_exists(conn, table_name, column_name, is_postgres)
    if exists:
        logger.info(f"  {table_name}.{column_name} already exists, skipping")
        return

    if is_postgres:
        await conn.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {pg_type}")
        )
    else:
        await conn.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {sqlite_type}")
        )
    logger.info(f"  Added {table_name}.{column_name}")


async def migrate(database_url: str) -> None:
    """Add group session columns and appointment_participants table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # 1. Add is_group column to appointments
        logger.info("Adding group session columns to appointments...")

        await _add_column_if_missing(
            conn, "appointments", "is_group",
            "BOOLEAN NOT NULL DEFAULT false",
            "INTEGER NOT NULL DEFAULT 0",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "appointments", "max_participants",
            "INTEGER",
            "INTEGER",
            is_postgres,
        )

        # 2. Create appointment_participants table
        if not await _table_exists(conn, "appointment_participants", is_postgres):
            if is_postgres:
                await conn.execute(text("""
                    CREATE TABLE appointment_participants (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        appointment_id UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
                        student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        attendance_status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
                        service_plan_id UUID REFERENCES service_plans(id) ON DELETE SET NULL,
                        is_complimentary BOOLEAN NOT NULL DEFAULT false,
                        notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_appointment_participants_appointment_id "
                    "ON appointment_participants(appointment_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_appointment_participants_student_id "
                    "ON appointment_participants(student_id)"
                ))
            else:
                await conn.execute(text("""
                    CREATE TABLE appointment_participants (
                        id TEXT PRIMARY KEY,
                        appointment_id TEXT NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,
                        student_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        attendance_status TEXT NOT NULL DEFAULT 'scheduled',
                        service_plan_id TEXT REFERENCES service_plans(id) ON DELETE SET NULL,
                        is_complimentary INTEGER NOT NULL DEFAULT 0,
                        notes TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))

            logger.info("Created appointment_participants table")
        else:
            logger.info("appointment_participants table already exists, skipping")

    await engine.dispose()
    logger.info("Migration add_group_sessions completed successfully")


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
