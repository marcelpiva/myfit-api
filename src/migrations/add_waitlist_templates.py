"""Add waitlist_entries and session_templates tables."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Create waitlist_entries and session_templates tables."""
    engine = create_async_engine(database_url, pool_pre_ping=True)

    try:
        async with engine.connect() as conn:
            # Check if tables already exist
            result = await conn.execute(
                text("SELECT tablename FROM pg_tables WHERE tablename = 'waitlist_entries'")
            )
            if result.fetchone():
                logger.info("waitlist_entries table already exists, skipping")
                await conn.commit()

                # Still check session_templates
                result2 = await conn.execute(
                    text("SELECT tablename FROM pg_tables WHERE tablename = 'session_templates'")
                )
                if result2.fetchone():
                    logger.info("session_templates table already exists, skipping")
                    await conn.commit()
                    return

            # Drop stale native enum if a previous failed deploy created it
            await conn.execute(text("DROP TYPE IF EXISTS waitliststatus CASCADE"))

            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS waitlist_entries (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    student_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    trainer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    preferred_day_of_week INTEGER,
                    preferred_time_start TIME,
                    preferred_time_end TIME,
                    notes TEXT,
                    status VARCHAR(20) NOT NULL DEFAULT 'waiting',
                    offered_appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
                    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP
                )
            """))

            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_waitlist_entries_student_id ON waitlist_entries(student_id)
            """))
            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_waitlist_entries_trainer_id ON waitlist_entries(trainer_id)
            """))

            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS session_templates (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    trainer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    name VARCHAR(200) NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    start_time TIME NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 60,
                    workout_type VARCHAR(20),
                    is_group BOOLEAN NOT NULL DEFAULT FALSE,
                    max_participants INTEGER,
                    notes TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP
                )
            """))

            await conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_session_templates_trainer_id ON session_templates(trainer_id)
            """))

            await conn.commit()
            logger.info("add_waitlist_templates migration completed")

    except Exception as e:
        logger.error("add_waitlist_templates migration error: %s", e)
        raise
    finally:
        await engine.dispose()
