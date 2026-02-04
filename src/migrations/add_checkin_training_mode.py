"""Add training_mode column to check_ins table.

Adds:
- training_mode column (VARCHAR(20), nullable) - 'in_person' or 'online'
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add training_mode column to check_ins."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'check_ins' AND column_name = 'training_mode'
                    )
                """)
            )
            col_exists = result.scalar()

            if not col_exists:
                await conn.execute(
                    text("""
                        ALTER TABLE check_ins
                        ADD COLUMN training_mode VARCHAR(20)
                    """)
                )
                logger.info("Added training_mode column to check_ins")
            else:
                logger.info("training_mode column already exists, skipping")
        else:
            # SQLite
            try:
                await conn.execute(
                    text("ALTER TABLE check_ins ADD COLUMN training_mode TEXT")
                )
                logger.info("Added training_mode column (SQLite)")
            except Exception:
                logger.info("training_mode column already exists (SQLite)")


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
