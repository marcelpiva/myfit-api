"""Add social login fields to users table.

This migration adds fields for Google and Apple Sign-In:
- auth_provider: Enum indicating how the user registered (email, google, apple)
- google_id: Unique Google user ID
- apple_id: Unique Apple user ID

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add social login fields to users table."""
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
                        WHERE table_name = 'users' AND column_name = 'auth_provider'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("Column auth_provider already exists, skipping")
                return

            # Create enum type for auth provider
            await conn.execute(
                text("""
                    DO $$ BEGIN
                        CREATE TYPE auth_provider_enum AS ENUM ('email', 'google', 'apple');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
            )

            # Add auth_provider column with default 'email'
            await conn.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN auth_provider auth_provider_enum NOT NULL DEFAULT 'email'
                """)
            )

            # Add google_id column
            await conn.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN google_id VARCHAR(255) UNIQUE
                """)
            )

            # Add apple_id column
            await conn.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN apple_id VARCHAR(255) UNIQUE
                """)
            )

            # Create indexes for faster lookups
            await conn.execute(
                text("CREATE INDEX ix_users_google_id ON users(google_id) WHERE google_id IS NOT NULL")
            )
            await conn.execute(
                text("CREATE INDEX ix_users_apple_id ON users(apple_id) WHERE apple_id IS NOT NULL")
            )

        else:
            # SQLite version
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(users)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "auth_provider" in columns:
                logger.info("Column auth_provider already exists, skipping")
                return

            # Add auth_provider column
            await conn.execute(
                text("""
                    ALTER TABLE users
                    ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'email'
                    CHECK(auth_provider IN ('email', 'google', 'apple'))
                """)
            )

            # Add google_id column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN google_id TEXT UNIQUE")
            )

            # Add apple_id column
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN apple_id TEXT UNIQUE")
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_users_google_id ON users(google_id)")
            )
            await conn.execute(
                text("CREATE INDEX ix_users_apple_id ON users(apple_id)")
            )

        logger.info("Added social login fields to users table")


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
