"""Add service_plans table and link billing/schedule/checkin.

Creates:
- service_plans table (full ServicePlan model)
- serviceplantype enum (recurring, package, drop_in, free_trial)
- sessiontype enum (scheduled, makeup, extra, trial)
- attendancestatus enum (scheduled, attended, missed, late_cancelled)

Adds to appointments:
- service_plan_id (UUID FK, nullable)
- payment_id (UUID FK, nullable)
- session_type (VARCHAR, default 'scheduled')
- attendance_status (VARCHAR, default 'scheduled')
- is_complimentary (BOOLEAN, default false)

Adds to check_ins:
- appointment_id (UUID FK, nullable)
- service_plan_id (UUID FK, nullable)
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
    """Create service_plans table and add linking columns."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # ── 1. Create service_plans table ──
        if not await _table_exists(conn, "service_plans", is_postgres):
            if is_postgres:
                # Create enum types (IF NOT EXISTS for safety)
                await conn.execute(text("""
                    DO $$ BEGIN
                        CREATE TYPE serviceplantype AS ENUM (
                            'recurring', 'package', 'drop_in', 'free_trial'
                        );
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$
                """))

                await conn.execute(text("""
                    CREATE TABLE service_plans (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        trainer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                        name VARCHAR(255) NOT NULL,
                        description TEXT,
                        plan_type VARCHAR(20) NOT NULL,
                        amount_cents INTEGER NOT NULL DEFAULT 0,
                        currency VARCHAR(3) NOT NULL DEFAULT 'BRL',
                        sessions_per_week INTEGER,
                        recurrence_type VARCHAR(20),
                        billing_day INTEGER,
                        schedule_config JSONB,
                        total_sessions INTEGER,
                        remaining_sessions INTEGER,
                        package_expiry_date DATE,
                        per_session_cents INTEGER,
                        start_date DATE NOT NULL,
                        end_date DATE,
                        is_active BOOLEAN NOT NULL DEFAULT true,
                        auto_renew BOOLEAN NOT NULL DEFAULT false,
                        notes TEXT,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                """))

                # Indexes
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_service_plans_student_id ON service_plans(student_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_service_plans_trainer_id ON service_plans(trainer_id)"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_service_plans_is_active ON service_plans(is_active)"
                ))
            else:
                # SQLite
                await conn.execute(text("""
                    CREATE TABLE service_plans (
                        id TEXT PRIMARY KEY,
                        student_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        trainer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
                        name TEXT NOT NULL,
                        description TEXT,
                        plan_type TEXT NOT NULL,
                        amount_cents INTEGER NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'BRL',
                        sessions_per_week INTEGER,
                        recurrence_type TEXT,
                        billing_day INTEGER,
                        schedule_config TEXT,
                        total_sessions INTEGER,
                        remaining_sessions INTEGER,
                        package_expiry_date TEXT,
                        per_session_cents INTEGER,
                        start_date TEXT NOT NULL,
                        end_date TEXT,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        auto_renew INTEGER NOT NULL DEFAULT 0,
                        notes TEXT,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now'))
                    )
                """))

            logger.info("Created service_plans table")
        else:
            logger.info("service_plans table already exists, skipping")

        # ── 2. Add columns to appointments ──
        logger.info("Adding columns to appointments...")

        if is_postgres:
            # Create enum types for session_type and attendance_status
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE sessiontype AS ENUM (
                        'scheduled', 'makeup', 'extra', 'trial'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$
            """))
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE attendancestatus AS ENUM (
                        'scheduled', 'attended', 'missed', 'late_cancelled'
                    );
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$
            """))

        await _add_column_if_missing(
            conn, "appointments", "service_plan_id",
            "UUID REFERENCES service_plans(id) ON DELETE SET NULL",
            "TEXT REFERENCES service_plans(id) ON DELETE SET NULL",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "appointments", "payment_id",
            "UUID REFERENCES payments(id) ON DELETE SET NULL",
            "TEXT REFERENCES payments(id) ON DELETE SET NULL",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "appointments", "session_type",
            "VARCHAR(20) NOT NULL DEFAULT 'scheduled'",
            "TEXT NOT NULL DEFAULT 'scheduled'",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "appointments", "attendance_status",
            "VARCHAR(20) NOT NULL DEFAULT 'scheduled'",
            "TEXT NOT NULL DEFAULT 'scheduled'",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "appointments", "is_complimentary",
            "BOOLEAN NOT NULL DEFAULT false",
            "INTEGER NOT NULL DEFAULT 0",
            is_postgres,
        )

        # ── 3. Add service_plan_id to payments ──
        logger.info("Adding columns to payments...")

        await _add_column_if_missing(
            conn, "payments", "service_plan_id",
            "UUID REFERENCES service_plans(id) ON DELETE SET NULL",
            "TEXT REFERENCES service_plans(id) ON DELETE SET NULL",
            is_postgres,
        )

        # ── 4. Add columns to check_ins ──
        logger.info("Adding columns to check_ins...")

        await _add_column_if_missing(
            conn, "check_ins", "appointment_id",
            "UUID REFERENCES appointments(id) ON DELETE SET NULL",
            "TEXT REFERENCES appointments(id) ON DELETE SET NULL",
            is_postgres,
        )
        await _add_column_if_missing(
            conn, "check_ins", "service_plan_id",
            "UUID REFERENCES service_plans(id) ON DELETE SET NULL",
            "TEXT REFERENCES service_plans(id) ON DELETE SET NULL",
            is_postgres,
        )

    await engine.dispose()
    logger.info("Migration add_service_plans completed successfully")


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
