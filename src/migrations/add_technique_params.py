"""
Migration: Add structured technique parameters to workout_exercises table.

Run this script to add the new columns to an existing database:
    python -m src.migrations.add_technique_params

For new installations, these columns will be created automatically by create_all().
"""
import asyncio

import structlog
from sqlalchemy import text

from src.config.database import engine

logger = structlog.get_logger(__name__)


async def get_existing_columns(conn, table_name: str) -> set:
    """Get existing columns for a table, works with both SQLite and PostgreSQL."""
    # Try PostgreSQL first
    try:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        columns = {row[0] for row in result.fetchall()}
        if columns:
            return columns
    except Exception:
        pass

    # Fall back to SQLite
    try:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in result.fetchall()}
    except Exception:
        pass

    return set()


async def upgrade():
    """Add structured technique parameter columns to workout_exercises table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "workout_exercises")

        # Add drop_count column (Dropset: number of drops 2-5)
        if "drop_count" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN drop_count INTEGER")
            )
            logger.info("added_column", column="drop_count")
        else:
            logger.info("column_already_exists", column="drop_count")

        # Add rest_between_drops column (Dropset: seconds between drops)
        if "rest_between_drops" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN rest_between_drops INTEGER")
            )
            logger.info("added_column", column="rest_between_drops")
        else:
            logger.info("column_already_exists", column="rest_between_drops")

        # Add pause_duration column (Rest-Pause/Cluster: pause in seconds)
        if "pause_duration" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN pause_duration INTEGER")
            )
            logger.info("added_column", column="pause_duration")
        else:
            logger.info("column_already_exists", column="pause_duration")

        # Add mini_set_count column (Cluster: number of mini-sets)
        if "mini_set_count" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN mini_set_count INTEGER")
            )
            logger.info("added_column", column="mini_set_count")
        else:
            logger.info("column_already_exists", column="mini_set_count")

    logger.info("migration_completed_successfully")


if __name__ == "__main__":
    asyncio.run(upgrade())
