"""Add email verification table.

This migration creates the email_verifications table for storing
verification codes sent during registration and password reset.

For new installations, this table will be created automatically by create_all().
For existing installations, run this script to add the table.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add email verification table."""
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
                        WHERE table_name = 'email_verifications'
                    )
                """)
            )
            table_exists = result.scalar()

            if table_exists:
                logger.info("Table email_verifications already exists, skipping")
                return

            # Create table
            await conn.execute(
                text("""
                    CREATE TABLE email_verifications (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        email VARCHAR(255) NOT NULL,
                        code VARCHAR(6) NOT NULL,
                        purpose VARCHAR(50) NOT NULL,
                        is_used BOOLEAN NOT NULL DEFAULT FALSE,
                        expires_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_email_verifications_email ON email_verifications(email)")
            )
            await conn.execute(
                text("""
                    CREATE INDEX ix_email_verifications_lookup ON email_verifications(email, code, purpose)
                    WHERE is_used = FALSE
                """)
            )

        else:
            # SQLite version
            # Check if table exists
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='email_verifications'")
            )
            table_exists = result.fetchone() is not None

            if table_exists:
                logger.info("Table email_verifications already exists, skipping")
                return

            # Create table
            await conn.execute(
                text("""
                    CREATE TABLE email_verifications (
                        id TEXT PRIMARY KEY,
                        email TEXT NOT NULL,
                        code TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        is_used INTEGER NOT NULL DEFAULT 0,
                        expires_at TEXT NOT NULL,
                        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_email_verifications_email ON email_verifications(email)")
            )

        logger.info("Created email_verifications table")


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
