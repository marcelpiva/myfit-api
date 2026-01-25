"""Add CREF (professional registration) fields to users table.

This migration adds fields for Brazilian personal trainer certification:
- cref: The CREF registration number
- cref_verified: Whether the CREF has been verified
- cref_verified_at: When the CREF was verified

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add CREF fields to users table."""
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
                        WHERE table_name = 'users' AND column_name = 'cref'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("Column cref already exists, skipping")
                return

            # Add cref column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref VARCHAR(20)")
            )

            # Add cref_verified column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref_verified BOOLEAN NOT NULL DEFAULT FALSE")
            )

            # Add cref_verified_at column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref_verified_at TIMESTAMPTZ")
            )

            # Create index for faster lookups
            await conn.execute(
                text("CREATE INDEX ix_users_cref ON users(cref) WHERE cref IS NOT NULL")
            )

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(users)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "cref" in columns:
                logger.info("Column cref already exists, skipping")
                return

            # Add cref column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref TEXT")
            )

            # Add cref_verified column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref_verified INTEGER NOT NULL DEFAULT 0")
            )

            # Add cref_verified_at column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN cref_verified_at TEXT")
            )

            # Create index
            await conn.execute(
                text("CREATE INDEX ix_users_cref ON users(cref)")
            )

        logger.info("Added CREF fields to users table")


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
