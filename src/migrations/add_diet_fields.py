"""
Migration: Add diet configuration fields to workout_programs table.

Run this script to add the new columns to an existing database:
    python -m src.migrations.add_diet_fields

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
    """Add new diet columns to workout_programs table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "workout_programs")

        # Add include_diet column with default value
        if "include_diet" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN include_diet BOOLEAN DEFAULT FALSE NOT NULL")
            )
            print("Added column: include_diet")

        # Add diet_type column
        if "diet_type" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN diet_type VARCHAR(50)")
            )
            print("Added column: diet_type")

        # Add daily_calories column
        if "daily_calories" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN daily_calories INTEGER")
            )
            print("Added column: daily_calories")

        # Add protein_grams column
        if "protein_grams" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN protein_grams INTEGER")
            )
            print("Added column: protein_grams")

        # Add carbs_grams column
        if "carbs_grams" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN carbs_grams INTEGER")
            )
            print("Added column: carbs_grams")

        # Add fat_grams column
        if "fat_grams" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN fat_grams INTEGER")
            )
            print("Added column: fat_grams")

        # Add meals_per_day column
        if "meals_per_day" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN meals_per_day INTEGER")
            )
            print("Added column: meals_per_day")

        # Add diet_notes column
        if "diet_notes" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_programs ADD COLUMN diet_notes TEXT")
            )
            print("Added column: diet_notes")

    print("Diet fields migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
