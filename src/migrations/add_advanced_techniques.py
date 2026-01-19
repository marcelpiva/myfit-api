"""
Migration: Add advanced exercise techniques fields to workout_exercises table.

Run this script to add the new columns to an existing database:
    python -m src.migrations.add_advanced_techniques

For new installations, these columns will be created automatically by create_all().
"""
import asyncio

from sqlalchemy import text

from src.config.database import engine


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
    """Add new columns to workout_exercises table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "workout_exercises")

        # Add execution_instructions column
        if "execution_instructions" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN execution_instructions TEXT")
            )
            print("Added column: execution_instructions")

        # Add isometric_seconds column
        if "isometric_seconds" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN isometric_seconds INTEGER")
            )
            print("Added column: isometric_seconds")

        # Add technique_type column with default value
        if "technique_type" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN technique_type VARCHAR(20) DEFAULT 'normal' NOT NULL")
            )
            print("Added column: technique_type")

        # Add exercise_group_id column
        if "exercise_group_id" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN exercise_group_id VARCHAR(50)")
            )
            print("Added column: exercise_group_id")

        # Add exercise_group_order column with default value
        if "exercise_group_order" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN exercise_group_order INTEGER DEFAULT 0 NOT NULL")
            )
            print("Added column: exercise_group_order")

    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
