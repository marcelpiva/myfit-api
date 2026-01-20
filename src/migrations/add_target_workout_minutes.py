"""
Migration: Add target_workout_minutes column to training_plans table.

Run this script to add the new column to an existing database:
    python -m src.migrations.add_target_workout_minutes

For new installations, this column will be created automatically by create_all().
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
    """Add target_workout_minutes column to training_plans table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "training_plans")

        # Add target_workout_minutes column
        if "target_workout_minutes" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE training_plans ADD COLUMN target_workout_minutes INTEGER")
            )
            print("Added column: target_workout_minutes")
        else:
            print("Column target_workout_minutes already exists, skipping.")

    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
