"""Add AUTONOMOUS value to organization_type_enum.

This migration adds the 'autonomous' organization type that allows students
to create and manage their own workouts independently, without a trainer.

For new installations, this value will be included automatically.
For existing installations, run this script to add the enum value.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add AUTONOMOUS value to organization_type_enum."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # Check if the enum value already exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'autonomous'
                        AND enumtypid = (
                            SELECT oid FROM pg_type WHERE typname = 'organization_type_enum'
                        )
                    )
                """)
            )
            value_exists = result.scalar()

            if not value_exists:
                # Add the new enum value
                await conn.execute(
                    text("""
                        ALTER TYPE organization_type_enum ADD VALUE IF NOT EXISTS 'autonomous'
                    """)
                )
                logger.info("Added 'autonomous' value to organization_type_enum")
            else:
                logger.info("'autonomous' value already exists in organization_type_enum, skipping")
        else:
            # SQLite uses VARCHAR, no enum type to modify
            logger.info("SQLite does not use enum types, skipping migration")


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
