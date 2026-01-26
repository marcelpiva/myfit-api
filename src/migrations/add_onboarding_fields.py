"""Add onboarding profile fields to users table.

This migration adds fields for student and trainer onboarding data:
- Trainer: specialties, years_of_experience
- Student: fitness_goal, experience_level, weight_kg, age, weekly_frequency, injuries
- onboarding_completed: tracking flag

For new installations, these fields will be created automatically by create_all().
For existing installations, run this script to add the fields.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add onboarding fields to users table."""
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
                        WHERE table_name = 'users' AND column_name = 'onboarding_completed'
                    )
                """)
            )
            column_exists = result.scalar()

            if column_exists:
                logger.info("Onboarding columns already exist, skipping")
                return

            # Trainer onboarding fields
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN specialties VARCHAR(500)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN years_of_experience INTEGER")
            )

            # Student onboarding fields
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN fitness_goal VARCHAR(50)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN fitness_goal_other VARCHAR(200)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN experience_level VARCHAR(20)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN weight_kg FLOAT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN age INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN weekly_frequency INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN injuries VARCHAR(500)")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN injuries_other VARCHAR(200)")
            )

            # Onboarding completion tracking
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE")
            )

        else:
            # SQLite version
            result = await conn.execute(
                text("PRAGMA table_info(users)")
            )
            columns = [row[1] for row in result.fetchall()]

            if "onboarding_completed" in columns:
                logger.info("Onboarding columns already exist, skipping")
                return

            # Trainer onboarding fields
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN specialties TEXT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN years_of_experience INTEGER")
            )

            # Student onboarding fields
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN fitness_goal TEXT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN fitness_goal_other TEXT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN experience_level TEXT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN weight_kg REAL")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN age INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN weekly_frequency INTEGER")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN injuries TEXT")
            )
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN injuries_other TEXT")
            )

            # Onboarding completion tracking
            await conn.execute(
                text("ALTER TABLE users ADD COLUMN onboarding_completed INTEGER NOT NULL DEFAULT 0")
            )

        logger.info("Added onboarding fields to users table")


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
