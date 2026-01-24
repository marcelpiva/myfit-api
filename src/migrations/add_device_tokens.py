"""Add device_tokens table for FCM push notifications.

This migration creates the device_tokens table that stores FCM tokens
for sending push notifications to mobile devices.

For new installations, this table will be created automatically by create_all().
For existing installations, run this script to add the table.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add device_tokens table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # Check if table already exists
        if is_postgres:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'device_tokens'
                    )
                """)
            )
            table_exists = result.scalar()
        else:
            result = await conn.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='device_tokens'
                """)
            )
            table_exists = result.fetchone() is not None

        if table_exists:
            logger.info("Table device_tokens already exists, skipping")
            return

        if is_postgres:
            # Create enum type for device platform
            await conn.execute(
                text("""
                    DO $$ BEGIN
                        CREATE TYPE device_platform_enum AS ENUM ('ios', 'android');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
            )

            # Create table
            await conn.execute(
                text("""
                    CREATE TABLE device_tokens (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        token VARCHAR(500) NOT NULL UNIQUE,
                        platform device_platform_enum NOT NULL,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        last_used_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("""
                    CREATE INDEX ix_device_tokens_user_id ON device_tokens(user_id);
                    CREATE INDEX ix_device_tokens_token ON device_tokens(token);
                    CREATE INDEX ix_device_tokens_is_active ON device_tokens(is_active) WHERE is_active = TRUE;
                """)
            )
        else:
            # SQLite version
            await conn.execute(
                text("""
                    CREATE TABLE device_tokens (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        token VARCHAR(500) NOT NULL UNIQUE,
                        platform TEXT NOT NULL CHECK(platform IN ('ios', 'android')),
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        last_used_at DATETIME,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_device_tokens_user_id ON device_tokens(user_id)")
            )
            await conn.execute(
                text("CREATE UNIQUE INDEX ix_device_tokens_token ON device_tokens(token)")
            )

        logger.info("Created device_tokens table")


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
