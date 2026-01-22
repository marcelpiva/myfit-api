"""Add co-training fields to workout_sessions table.

This migration adds:
- trainer_id: References the trainer when co-training
- is_shared: Indicates if this is a shared (co-training) session
- student_feedback: Feedback from student
- trainer_notes: Notes from trainer
- status: Session status (waiting, started, completed, cancelled)

For new installations, these columns are created automatically by create_all().
For existing installations, run this script to add the columns.
"""
import asyncio
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add co-training fields to workout_sessions table."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        # Check database type
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        # Check if the table exists
        if is_postgres:
            result = await conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = 'workout_sessions'
                    )
                """)
            )
            table_exists = result.scalar()
        else:
            result = await conn.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='workout_sessions'
                """)
            )
            table_exists = result.fetchone() is not None

        if not table_exists:
            logger.info("Table workout_sessions does not exist, skipping migration")
            return

        # Define columns to add
        columns_to_add = [
            ("trainer_id", "UUID REFERENCES users(id) ON DELETE SET NULL", "UUID"),
            ("is_shared", "BOOLEAN NOT NULL DEFAULT FALSE", "BOOLEAN DEFAULT FALSE"),
            ("student_feedback", "TEXT", "TEXT"),
            ("trainer_notes", "TEXT", "TEXT"),
        ]

        for col_name, postgres_type, sqlite_type in columns_to_add:
            # Check if column exists
            if is_postgres:
                result = await conn.execute(
                    text(f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = 'workout_sessions' AND column_name = '{col_name}'
                    """)
                )
                column_exists = result.fetchone() is not None
            else:
                result = await conn.execute(
                    text("PRAGMA table_info(workout_sessions)")
                )
                columns = [row[1] for row in result.fetchall()]
                column_exists = col_name in columns

            if not column_exists:
                col_type = postgres_type if is_postgres else sqlite_type
                await conn.execute(
                    text(f"ALTER TABLE workout_sessions ADD COLUMN {col_name} {col_type}")
                )
                logger.info(f"Added {col_name} column to workout_sessions table")
            else:
                logger.info(f"{col_name} column already exists, skipping")

        # Add status enum if not exists (for PostgreSQL)
        if is_postgres:
            # Check if status column exists
            result = await conn.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'workout_sessions' AND column_name = 'status'
                """)
            )
            status_exists = result.fetchone() is not None

            if not status_exists:
                # Create enum type if not exists
                await conn.execute(
                    text("""
                        DO $$ BEGIN
                            CREATE TYPE session_status_enum AS ENUM ('waiting', 'started', 'completed', 'cancelled');
                        EXCEPTION
                            WHEN duplicate_object THEN null;
                        END $$;
                    """)
                )
                await conn.execute(
                    text("""
                        ALTER TABLE workout_sessions
                        ADD COLUMN status session_status_enum NOT NULL DEFAULT 'waiting'
                    """)
                )
                logger.info("Added status column to workout_sessions table")


async def main():
    """Run migration with default database URL."""
    import os

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

    # Convert postgres:// to postgresql:// if needed
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
