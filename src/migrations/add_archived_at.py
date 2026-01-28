"""Add archived_at field to organizations table.

This migration adds the archived_at field for tracking when an organization
was archived (e.g., when the personal trainer removes their profile).

For new installations, this field will be created automatically by create_all().
For existing installations, run this script to add the field.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add archived_at field to organizations table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # Check if column already exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'organizations' AND column_name = 'archived_at'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("Column archived_at already exists, skipping")
                return

            # Add archived_at column
            await conn.execute(
                text("ALTER TABLE organizations ADD COLUMN archived_at TIMESTAMPTZ")
            )

            # Create index for faster filtering of archived organizations
            await conn.execute(
                text("CREATE INDEX ix_organizations_archived_at ON organizations(archived_at) WHERE archived_at IS NOT NULL")
            )

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(organizations)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "archived_at" in columns:
                logger.info("Column archived_at already exists, skipping")
                return

            # Add archived_at column
            await conn.execute(
                text("ALTER TABLE organizations ADD COLUMN archived_at TEXT")
            )

            # Create index
            await conn.execute(
                text("CREATE INDEX ix_organizations_archived_at ON organizations(archived_at)")
            )

        logger.info("Added archived_at field to organizations table")


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
