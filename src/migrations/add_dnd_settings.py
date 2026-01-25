"""Add Do Not Disturb settings to user_settings table.

This migration adds DND settings for notification quiet hours.

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add DND fields to user_settings table."""
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
                        WHERE table_name = 'user_settings' AND column_name = 'dnd_enabled'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("DND columns already exist, skipping")
                return

            # Add dnd_enabled column
            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_enabled BOOLEAN NOT NULL DEFAULT false
                """)
            )

            # Add dnd_start_time column
            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_start_time VARCHAR(5) NULL
                """)
            )

            # Add dnd_end_time column
            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_end_time VARCHAR(5) NULL
                """)
            )

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(user_settings)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "dnd_enabled" in columns:
                logger.info("DND columns already exist, skipping")
                return

            # Add columns
            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_enabled INTEGER NOT NULL DEFAULT 0
                """)
            )

            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_start_time TEXT NULL
                """)
            )

            await conn.execute(
                text("""
                    ALTER TABLE user_settings
                    ADD COLUMN dnd_end_time TEXT NULL
                """)
            )

        logger.info("Added DND settings to user_settings table")


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
