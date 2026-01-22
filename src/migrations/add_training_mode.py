"""Add training_mode column to plan_assignments table.

This migration adds the training_mode enum column that differentiates between:
- presencial: In-person training with trainer present
- online: Online consulting, student trains alone
- hibrido: Hybrid - some sessions in-person, some online

For new installations, this column will be created automatically by create_all().
For existing installations, run this script to add the column.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add training_mode column to plan_assignments table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # First, check if the table exists
        if is_postgres:
            # PostgreSQL: Check if table exists
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
            # SQLite: Check if table exists
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

        # Check if column already exists
        if is_postgres:
            # PostgreSQL: Query information_schema
            result = await conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'plan_assignments' AND column_name = 'training_mode'
                """)
            )
            column_exists = result.fetchone() is not None
        else:
            # SQLite: Use PRAGMA
            result = await conn.execute(
                text("PRAGMA table_info(plan_assignments)")
            )
            columns = [row[1] for row in result.fetchall()]
            column_exists = "training_mode" in columns

        if not column_exists:
            if is_postgres:
                # PostgreSQL: Create enum type and add column
                await conn.execute(
                    text("""
                        DO $$ BEGIN
                            CREATE TYPE training_mode_enum AS ENUM ('presencial', 'online', 'hibrido');
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                    """)
                )
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN training_mode training_mode_enum NOT NULL DEFAULT 'presencial'
                    """)
                )
            else:
                # SQLite: Use VARCHAR (no enum support)
                await conn.execute(
                    text("""
                        ALTER TABLE plan_assignments
                        ADD COLUMN training_mode VARCHAR(20) NOT NULL DEFAULT 'presencial'
                    """)
                )
            logger.info("Added training_mode column to plan_assignments table")
        else:
            logger.info("training_mode column already exists, skipping")


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

    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
