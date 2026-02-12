"""Add appointment reminder tracking columns to appointments table.

This migration adds two boolean columns to track which reminders
have already been sent for each appointment:
- reminder_24h_sent: True if the 24-hour reminder was sent
- reminder_1h_sent: True if the 1-hour reminder was sent

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add reminder tracking columns to appointments table."""
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
                        WHERE table_name = 'appointments' AND column_name = 'reminder_24h_sent'
                    )
                """)
            )
            col_exists = result.scalar()

            if col_exists:
                logger.info("Reminder columns already exist, skipping")
                return

            # Add reminder_24h_sent column
            await conn.execute(
                text("""
                    ALTER TABLE appointments
                    ADD COLUMN reminder_24h_sent BOOLEAN NOT NULL DEFAULT false
                """)
            )
            logger.info("Added reminder_24h_sent column to appointments")

            # Add reminder_1h_sent column
            await conn.execute(
                text("""
                    ALTER TABLE appointments
                    ADD COLUMN reminder_1h_sent BOOLEAN NOT NULL DEFAULT false
                """)
            )
            logger.info("Added reminder_1h_sent column to appointments")

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(appointments)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "reminder_24h_sent" in columns:
                logger.info("Reminder columns already exist, skipping")
                return

            # Add columns
            await conn.execute(
                text("""
                    ALTER TABLE appointments
                    ADD COLUMN reminder_24h_sent INTEGER NOT NULL DEFAULT 0
                """)
            )
            logger.info("Added reminder_24h_sent column (SQLite)")

            await conn.execute(
                text("""
                    ALTER TABLE appointments
                    ADD COLUMN reminder_1h_sent INTEGER NOT NULL DEFAULT 0
                """)
            )
            logger.info("Added reminder_1h_sent column (SQLite)")

        logger.info("Added reminder tracking columns to appointments table")


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
