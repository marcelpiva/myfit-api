"""Remove user_type field from users table.

This migration removes the user_type field since we now use
organization_members.role to determine user type.

For new installations, this field should not exist.
For existing installations, run this script to remove the field.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Remove user_type field from users table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if is_postgres:
            # Check if column exists
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.columns
                        WHERE table_name = 'users' AND column_name = 'user_type'
                    )
                """)
            )
            column_exists = result.scalar()

            if not column_exists:
                logger.info("Column user_type does not exist, skipping")
                return

            # Drop index first
            await conn.execute(
                text("DROP INDEX IF EXISTS ix_users_user_type")
            )

            # Remove user_type column
            await conn.execute(
                text("ALTER TABLE users DROP COLUMN user_type")
            )

            # Drop enum type
            await conn.execute(
                text("DROP TYPE IF EXISTS user_type_enum")
            )

        else:
            # SQLite version - SQLite doesn't support DROP COLUMN easily
            # Check if column exists
            result = await conn.execute(
                text("PRAGMA table_info(users)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "user_type" not in columns:
                logger.info("Column user_type does not exist, skipping")
                return

            # For SQLite, we need to recreate the table without the column
            # This is complex, so we'll just leave the column for SQLite
            logger.warning("SQLite detected - column removal not supported, skipping")
            return

        logger.info("Removed user_type field from users table")


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
