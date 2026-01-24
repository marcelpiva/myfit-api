"""Add exercise_feedbacks table for student feedback on exercises.

This migration creates the exercise_feedbacks table that allows students
to provide feedback on exercises during workout sessions:
- liked: positive feedback
- disliked: negative feedback
- swap: request to swap the exercise

For new installations, this table will be created automatically by create_all().
For existing installations, run this script to add the table.
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Add exercise_feedbacks table."""
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
                        WHERE table_name = 'exercise_feedbacks'
                    )
                """)
            )
            table_exists = result.scalar()
        else:
            result = await conn.execute(
                text("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='exercise_feedbacks'
                """)
            )
            table_exists = result.fetchone() is not None

        if table_exists:
            logger.info("Table exercise_feedbacks already exists, skipping")
            return

        if is_postgres:
            # Create enum type for feedback types
            await conn.execute(
                text("""
                    DO $$ BEGIN
                        CREATE TYPE exercise_feedback_type_enum AS ENUM ('liked', 'disliked', 'swap');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
            )

            # Create table
            await conn.execute(
                text("""
                    CREATE TABLE exercise_feedbacks (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        session_id UUID NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
                        workout_exercise_id UUID NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
                        exercise_id UUID NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                        student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        feedback_type exercise_feedback_type_enum NOT NULL,
                        comment TEXT,
                        trainer_response TEXT,
                        responded_at TIMESTAMPTZ,
                        replacement_exercise_id UUID REFERENCES exercises(id) ON DELETE SET NULL,
                        organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("""
                    CREATE INDEX ix_exercise_feedbacks_session_id ON exercise_feedbacks(session_id);
                    CREATE INDEX ix_exercise_feedbacks_student_id ON exercise_feedbacks(student_id);
                    CREATE INDEX ix_exercise_feedbacks_feedback_type ON exercise_feedbacks(feedback_type);
                    CREATE INDEX ix_exercise_feedbacks_responded_at ON exercise_feedbacks(responded_at) WHERE responded_at IS NULL;
                """)
            )
        else:
            # SQLite version
            await conn.execute(
                text("""
                    CREATE TABLE exercise_feedbacks (
                        id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL REFERENCES workout_sessions(id) ON DELETE CASCADE,
                        workout_exercise_id TEXT NOT NULL REFERENCES workout_exercises(id) ON DELETE CASCADE,
                        exercise_id TEXT NOT NULL REFERENCES exercises(id) ON DELETE CASCADE,
                        student_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        feedback_type TEXT NOT NULL CHECK(feedback_type IN ('liked', 'disliked', 'swap')),
                        comment TEXT,
                        trainer_response TEXT,
                        responded_at DATETIME,
                        replacement_exercise_id TEXT REFERENCES exercises(id) ON DELETE SET NULL,
                        organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            )

            # Create indexes
            await conn.execute(
                text("CREATE INDEX ix_exercise_feedbacks_session_id ON exercise_feedbacks(session_id)")
            )
            await conn.execute(
                text("CREATE INDEX ix_exercise_feedbacks_student_id ON exercise_feedbacks(student_id)")
            )

        logger.info("Created exercise_feedbacks table")


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
