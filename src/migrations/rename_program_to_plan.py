"""
Migration: Rename 'program' tables and columns to 'plan' (training plans).

Renames:
- workout_programs -> training_plans
- program_workouts -> plan_workouts
- program_assignments -> plan_assignments
- program_id columns -> plan_id

Run this script to migrate an existing database:
    python -m src.migrations.rename_program_to_plan

For new installations, the new names will be used automatically.
"""
import asyncio

import structlog
from sqlalchemy import text

from src.config.database import engine

logger = structlog.get_logger(__name__)


async def table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    # Try PostgreSQL first
    try:
        result = await conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = :table_name
                )
                """
            ),
            {"table_name": table_name},
        )
        row = result.fetchone()
        if row and row[0]:
            return True
    except Exception:
        pass

    # Fall back to SQLite
    try:
        result = await conn.execute(
            text(
                """
                SELECT name FROM sqlite_master
                WHERE type='table' AND name=:table_name
                """
            ),
            {"table_name": table_name},
        )
        return result.fetchone() is not None
    except Exception:
        pass

    return False


async def column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    # Try PostgreSQL first
    try:
        result = await conn.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.columns
                    WHERE table_name = :table_name AND column_name = :column_name
                )
                """
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        row = result.fetchone()
        if row:
            return row[0]
    except Exception:
        pass

    # Fall back to SQLite
    try:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = {row[1] for row in result.fetchall()}
        return column_name in columns
    except Exception:
        pass

    return False


async def upgrade():
    """Rename program tables and columns to plan."""
    async with engine.begin() as conn:
        # Check if migration is needed (old tables exist)
        has_old_tables = await table_exists(conn, "workout_programs")
        has_new_tables = await table_exists(conn, "training_plans")

        if has_new_tables and not has_old_tables:
            logger.info("migration_already_completed", reason="new tables exist")
            return

        if not has_old_tables and not has_new_tables:
            logger.info("no_tables_to_migrate", reason="fresh installation will use new names")
            return

        logger.info("starting_migration", direction="program -> plan")

        # 1. Rename workout_programs -> training_plans
        if await table_exists(conn, "workout_programs"):
            await conn.execute(
                text("ALTER TABLE workout_programs RENAME TO training_plans")
            )
            logger.info("renamed_table", old_name="workout_programs", new_name="training_plans")

        # 2. Rename program_workouts -> plan_workouts
        if await table_exists(conn, "program_workouts"):
            await conn.execute(
                text("ALTER TABLE program_workouts RENAME TO plan_workouts")
            )
            logger.info("renamed_table", old_name="program_workouts", new_name="plan_workouts")

            # Rename program_id column in plan_workouts
            if await column_exists(conn, "plan_workouts", "program_id"):
                await conn.execute(
                    text("ALTER TABLE plan_workouts RENAME COLUMN program_id TO plan_id")
                )
                logger.info("renamed_column", table="plan_workouts", old_name="program_id", new_name="plan_id")

        # 3. Rename program_assignments -> plan_assignments
        if await table_exists(conn, "program_assignments"):
            await conn.execute(
                text("ALTER TABLE program_assignments RENAME TO plan_assignments")
            )
            logger.info("renamed_table", old_name="program_assignments", new_name="plan_assignments")

            # Rename program_id column in plan_assignments
            if await column_exists(conn, "plan_assignments", "program_id"):
                await conn.execute(
                    text("ALTER TABLE plan_assignments RENAME COLUMN program_id TO plan_id")
                )
                logger.info("renamed_column", table="plan_assignments", old_name="program_id", new_name="plan_id")

    logger.info("migration_completed_successfully")


async def downgrade():
    """Revert: rename plan tables back to program."""
    async with engine.begin() as conn:
        logger.info("starting_downgrade", direction="plan -> program")

        # Revert plan_assignments -> program_assignments
        if await table_exists(conn, "plan_assignments"):
            if await column_exists(conn, "plan_assignments", "plan_id"):
                await conn.execute(
                    text("ALTER TABLE plan_assignments RENAME COLUMN plan_id TO program_id")
                )
                logger.info("renamed_column", table="plan_assignments", old_name="plan_id", new_name="program_id")
            await conn.execute(
                text("ALTER TABLE plan_assignments RENAME TO program_assignments")
            )
            logger.info("renamed_table", old_name="plan_assignments", new_name="program_assignments")

        # Revert plan_workouts -> program_workouts
        if await table_exists(conn, "plan_workouts"):
            if await column_exists(conn, "plan_workouts", "plan_id"):
                await conn.execute(
                    text("ALTER TABLE plan_workouts RENAME COLUMN plan_id TO program_id")
                )
                logger.info("renamed_column", table="plan_workouts", old_name="plan_id", new_name="program_id")
            await conn.execute(
                text("ALTER TABLE plan_workouts RENAME TO program_workouts")
            )
            logger.info("renamed_table", old_name="plan_workouts", new_name="program_workouts")

        # Revert training_plans -> workout_programs
        if await table_exists(conn, "training_plans"):
            await conn.execute(
                text("ALTER TABLE training_plans RENAME TO workout_programs")
            )
            logger.info("renamed_table", old_name="training_plans", new_name="workout_programs")

    logger.info("downgrade_completed_successfully")


if __name__ == "__main__":
    asyncio.run(upgrade())
