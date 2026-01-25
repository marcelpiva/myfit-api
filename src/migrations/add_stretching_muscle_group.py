"""Add stretching value to muscle_group_enum.

This migration adds the 'stretching' value to the muscle_group_enum
for categorizing flexibility and stretching exercises separately from
strength exercises.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add stretching value to muscle_group_enum."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # PostgreSQL: Check if value already exists in enum
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM pg_enum
                        WHERE enumlabel = 'stretching'
                        AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'muscle_group_enum')
                    )
                """)
            )
            value_exists = result.scalar()

            if not value_exists:
                # Add value to enum
                await conn.execute(
                    text("ALTER TYPE muscle_group_enum ADD VALUE IF NOT EXISTS 'stretching'")
                )
                logger.info("Added 'stretching' value to muscle_group_enum")
            else:
                logger.info("'stretching' value already exists in muscle_group_enum, skipping")
        else:
            # SQLite: No enum types, nothing to migrate
            logger.info("SQLite detected, no enum migration needed")


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
