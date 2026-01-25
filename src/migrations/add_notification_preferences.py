"""Add notification_preferences table.

This migration adds the notification_preferences table for granular
notification control per user.

For new installations, this table will be created automatically by create_all().
For existing installations, run this script to add the table.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add notification_preferences table."""
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
                        WHERE table_name = 'notification_preferences'
                    )
                """)
            )
            table_exists = result.scalar()

            if table_exists:
                logger.info("Table notification_preferences already exists, skipping")
                return

            # Create notification_category enum if not exists
            await conn.execute(
                text("""
                    DO $$ BEGIN
                        CREATE TYPE notification_category_enum AS ENUM (
                            'workouts', 'progress', 'messages', 'organization',
                            'payments', 'appointments', 'system'
                        );
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
            )

            # Create notification_preferences table
            await conn.execute(
                text("""
                    CREATE TABLE notification_preferences (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        notification_type VARCHAR(50) NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT true,
                        push_enabled BOOLEAN NOT NULL DEFAULT true,
                        email_enabled BOOLEAN NOT NULL DEFAULT false,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        UNIQUE(user_id, notification_type)
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_notification_preferences_user_id ON notification_preferences(user_id)")
            )

        else:
            # SQLite version
            # Check if table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='notification_preferences'")
            )
            if result.fetchone():
                logger.info("Table notification_preferences already exists, skipping")
                return

            # Create table
            await conn.execute(
                text("""
                    CREATE TABLE notification_preferences (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        notification_type TEXT NOT NULL,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        push_enabled INTEGER NOT NULL DEFAULT 1,
                        email_enabled INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, notification_type)
                    )
                """)
            )

            # Create index
            await conn.execute(
                text("CREATE INDEX ix_notification_preferences_user_id ON notification_preferences(user_id)")
            )

        logger.info("Created notification_preferences table")


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
