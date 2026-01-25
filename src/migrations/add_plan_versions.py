"""Add plan_versions table and version tracking to plan_assignments.

This migration adds:
1. plan_versions table for storing version history
2. version and last_version_viewed columns to plan_assignments

For new installations, these will be created automatically by create_all().
For existing installations, run this script to add them.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add plan versions table and columns."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # Check if table already exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'plan_versions'
                    )
                """)
            )
            table_exists = result.scalar()

            if not table_exists:
                # Create plan_versions table
                await conn.execute(
                    text("""
                        CREATE TABLE plan_versions (
                            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                            assignment_id UUID NOT NULL REFERENCES plan_assignments(id) ON DELETE CASCADE,
                            version INTEGER NOT NULL,
                            snapshot JSONB NOT NULL,
                            changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            changed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
                            change_description VARCHAR(500) NULL
                        )
                    """)
                )

                # Create indexes
                await conn.execute(
                    text("CREATE INDEX ix_plan_versions_assignment_id ON plan_versions(assignment_id)")
                )
                await conn.execute(
                    text("CREATE INDEX ix_plan_versions_assignment_version ON plan_versions(assignment_id, version)")
                )

                logger.info("Created plan_versions table")

            # Check if version column exists in plan_assignments
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'plan_assignments' AND column_name = 'version'
                    )
                """)
            )
            column_exists = result.scalar()

            if not column_exists:
                # Add version column
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN version INTEGER NOT NULL DEFAULT 1
                    """)
                )

                # Add last_version_viewed column
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN last_version_viewed INTEGER NULL
                    """)
                )

                logger.info("Added version columns to plan_assignments")

        else:
            # SQLite version
            # Check if table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='plan_versions'")
            )
            if not result.fetchone():
                # Create table
                await conn.execute(
                    text("""
                        CREATE TABLE plan_versions (
                            id TEXT PRIMARY KEY,
                            assignment_id TEXT NOT NULL REFERENCES plan_assignments(id) ON DELETE CASCADE,
                            version INTEGER NOT NULL,
                            snapshot TEXT NOT NULL,
                            changed_at TEXT DEFAULT (datetime('now')),
                            changed_by_id TEXT REFERENCES users(id) ON DELETE SET NULL,
                            change_description TEXT NULL
                        )
                    """)
                )

                # Create indexes
                await conn.execute(
                    text("CREATE INDEX ix_plan_versions_assignment_id ON plan_versions(assignment_id)")
                )
                await conn.execute(
                    text("CREATE INDEX ix_plan_versions_assignment_version ON plan_versions(assignment_id, version)")
                )

                logger.info("Created plan_versions table")

            # Check if version column exists
            result = await conn.execute(
                text("PRAGMA table_info(plan_assignments)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "version" not in columns:
                # Add columns
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN version INTEGER NOT NULL DEFAULT 1
                    """)
                )

                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN last_version_viewed INTEGER NULL
                    """)
                )

                logger.info("Added version columns to plan_assignments")


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
