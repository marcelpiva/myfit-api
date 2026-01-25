"""Add status field to training_plans table.

This migration adds the status field to support draft/publish workflow
for training plans.

For new installations, this field will be created automatically by create_all().
For existing installations, run this script to add the field.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add status field to training_plans table."""
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
                        WHERE table_name = 'training_plans' AND column_name = 'status'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("Column status already exists, skipping")
                return

            # Create enum type
            await conn.execute(
                text("""
                    DO $$ BEGIN
                        CREATE TYPE plan_status_enum AS ENUM ('draft', 'published', 'archived');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
            )

            # Add status column with default 'published' (backwards compatible)
            await conn.execute(
                text("""
                    ALTER TABLE training_plans
                    ADD COLUMN status plan_status_enum NOT NULL DEFAULT 'published'
                """)
            )

            # Create index for faster lookups by status
            await conn.execute(
                text("CREATE INDEX ix_training_plans_status ON training_plans(status)")
            )

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(training_plans)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "status" in columns:
                logger.info("Column status already exists, skipping")
                return

            # Add status column with default 'published'
            await conn.execute(
                text("""
                    ALTER TABLE training_plans
                    ADD COLUMN status TEXT NOT NULL DEFAULT 'published'
                    CHECK(status IN ('draft', 'published', 'archived'))
                """)
            )

            # Create index
            await conn.execute(
                text("CREATE INDEX ix_training_plans_status ON training_plans(status)")
            )

        logger.info("Added status field to training_plans table")


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
