"""Add late cancellation policy columns to trainer_settings table.

This migration adds two columns to trainer_settings to support
configurable late cancellation policies:
- late_cancel_window_hours: Number of hours before session that counts as "late" (default 24)
- late_cancel_policy: Action to take on late cancel - 'charge', 'warn', or 'block' (default 'warn')

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add late cancellation policy columns to trainer_settings table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # Check if column already exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'trainer_settings' AND column_name = 'late_cancel_window_hours'
                    )
                """)
            )
            col_exists = result.scalar()

            if col_exists:
                logger.info("Late cancel policy columns already exist, skipping")
                return

            # Add late_cancel_window_hours column
            await conn.execute(
                text("""
                    ALTER TABLE trainer_settings
                    ADD COLUMN late_cancel_window_hours INTEGER NOT NULL DEFAULT 24
                """)
            )
            logger.info("Added late_cancel_window_hours column to trainer_settings")

            # Add late_cancel_policy column
            await conn.execute(
                text("""
                    ALTER TABLE trainer_settings
                    ADD COLUMN late_cancel_policy VARCHAR(10) NOT NULL DEFAULT 'warn'
                """)
            )
            logger.info("Added late_cancel_policy column to trainer_settings")

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(trainer_settings)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "late_cancel_window_hours" in columns:
                logger.info("Late cancel policy columns already exist, skipping")
                return

            # Add columns
            await conn.execute(
                text("""
                    ALTER TABLE trainer_settings
                    ADD COLUMN late_cancel_window_hours INTEGER NOT NULL DEFAULT 24
                """)
            )
            logger.info("Added late_cancel_window_hours column (SQLite)")

            await conn.execute(
                text("""
                    ALTER TABLE trainer_settings
                    ADD COLUMN late_cancel_policy VARCHAR(10) NOT NULL DEFAULT 'warn'
                """)
            )
            logger.info("Added late_cancel_policy column (SQLite)")

        logger.info("Added late cancellation policy columns to trainer_settings table")


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
