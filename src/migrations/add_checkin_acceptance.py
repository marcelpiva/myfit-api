"""Add pending_acceptance status and acceptance fields to check_ins table.

Adds:
- 'pending_acceptance' value to checkin_status_enum
- initiated_by column (UUID FK to users)
- accepted_at column (timestamptz)
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add pending_acceptance status and acceptance fields."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # 1. Add pending_acceptance to checkin_status_enum
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'pending_acceptance'
                        AND enumtypid = (
                            SELECT oid FROM pg_type WHERE typname = 'checkin_status_enum'
                        )
                    )
                """)
            )
            value_exists = result.scalar()

            if not value_exists:
                await conn.execute(
                    text("""
                        ALTER TYPE checkin_status_enum ADD VALUE IF NOT EXISTS 'pending_acceptance'
                    """)
                )
                logger.info("Added 'pending_acceptance' to checkin_status_enum")
            else:
                logger.info("'pending_acceptance' already exists, skipping")

            # 2. Add initiated_by column
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'check_ins' AND column_name = 'initiated_by'
                    )
                """)
            )
            col_exists = result.scalar()

            if not col_exists:
                await conn.execute(
                    text("""
                        ALTER TABLE check_ins
                        ADD COLUMN initiated_by UUID REFERENCES users(id) ON DELETE SET NULL
                    """)
                )
                logger.info("Added initiated_by column to check_ins")
            else:
                logger.info("initiated_by column already exists, skipping")

            # 3. Add accepted_at column
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'check_ins' AND column_name = 'accepted_at'
                    )
                """)
            )
            col_exists = result.scalar()

            if not col_exists:
                await conn.execute(
                    text("""
                        ALTER TABLE check_ins
                        ADD COLUMN accepted_at TIMESTAMPTZ
                    """)
                )
                logger.info("Added accepted_at column to check_ins")
            else:
                logger.info("accepted_at column already exists, skipping")

        else:
            # SQLite
            try:
                await conn.execute(
                    text("ALTER TABLE check_ins ADD COLUMN initiated_by TEXT")
                )
                logger.info("Added initiated_by column (SQLite)")
            except Exception:
                logger.info("initiated_by column already exists (SQLite)")

            try:
                await conn.execute(
                    text("ALTER TABLE check_ins ADD COLUMN accepted_at TEXT")
                )
                logger.info("Added accepted_at column (SQLite)")
            except Exception:
                logger.info("accepted_at column already exists (SQLite)")


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
