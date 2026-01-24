"""Add acknowledged_at column and auto-accept plan assignments.

This migration:
1. Adds the acknowledged_at column to track when students view their assignments
2. Updates existing PENDING assignments to ACCEPTED (auto-accept workflow)

For new installations, this column will be created automatically by create_all().
For existing installations, run this script to add the column and migrate data.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add acknowledged_at column and auto-accept pending assignments."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # First, check if the table exists
        if is_postgres:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'plan_assignments'
                    )
                """)
            )
            table_exists = result.scalar()
        else:
            result = await conn.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='plan_assignments'
                """)
            )
            table_exists = result.fetchone() is not None

        if not table_exists:
            logger.info("Table plan_assignments does not exist, skipping migration")
            return

        # Check if acknowledged_at column already exists
        if is_postgres:
            result = await conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'plan_assignments' AND column_name = 'acknowledged_at'
                """)
            )
            column_exists = result.fetchone() is not None
        else:
            result = await conn.execute(
                text("PRAGMA table_info(plan_assignments)")
            )
            columns = [row[1] for row in result.fetchall()]
            column_exists = "acknowledged_at" in columns

        if not column_exists:
            # Add acknowledged_at column
            if is_postgres:
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN acknowledged_at TIMESTAMPTZ
                    """)
                )
            else:
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN acknowledged_at DATETIME
                    """)
                )
            logger.info("Added acknowledged_at column to plan_assignments table")
        else:
            logger.info("acknowledged_at column already exists, skipping column creation")

        # Migrate pending assignments to accepted (auto-accept workflow)
        # This ensures existing pending assignments are now accepted
        if is_postgres:
            result = await conn.execute(
                text("""
                    UPDATE plan_assignments
                    SET status = 'accepted', accepted_at = NOW()
                    WHERE status = 'pending'
                    RETURNING id
                """)
            )
            updated_count = len(result.fetchall())
        else:
            # SQLite doesn't support RETURNING, so we count first
            result = await conn.execute(
                text("SELECT COUNT(*) FROM plan_assignments WHERE status = 'pending'")
            )
            updated_count = result.scalar() or 0

            await conn.execute(
                text("""
                    UPDATE plan_assignments
                    SET status = 'accepted', accepted_at = datetime('now')
                    WHERE status = 'pending'
                """)
            )

        if updated_count > 0:
            logger.info(f"Updated {updated_count} pending assignments to accepted status")
        else:
            logger.info("No pending assignments to migrate")


async def main():
    """Run migration with default database URL."""
    import os
    from pathlib import Path

    # Load .env file if it exists
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

    # Convert postgres:// or postgresql:// to postgresql+asyncpg://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
