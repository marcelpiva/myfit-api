"""
Migration: Add aerobic exercise fields to workout_exercises table.

Adds ExerciseMode enum and aerobic-specific fields for duration, interval, and distance modes.

Run this script to add the new columns to an existing database:
    python -m src.migrations.add_aerobic_exercise_fields

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


async def check_enum_exists(conn, enum_name: str) -> bool:
    """Check if a PostgreSQL enum type exists."""
    try:
        result = await conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = :enum_name"),
            {"enum_name": enum_name},
        )
        return result.fetchone() is not None
    except Exception:
        return False


async def upgrade():
    """Add aerobic exercise fields to workout_exercises table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "workout_exercises")

        # Create ExerciseMode enum (PostgreSQL only)
        if not await check_enum_exists(conn, "exercise_mode_enum"):
            try:
                await conn.execute(
                    text("CREATE TYPE exercise_mode_enum AS ENUM ('strength', 'duration', 'interval', 'distance')")
                )
                print("Created enum: exercise_mode_enum")
            except Exception as e:
                # SQLite doesn't support enums, skip
                if "syntax" not in str(e).lower():
                    print(f"Note: Could not create enum (may be SQLite): {e}")

        # Add exercise_mode column
        if "exercise_mode" not in existing_columns:
            try:
                # PostgreSQL with enum
                await conn.execute(
                    text("ALTER TABLE workout_exercises ADD COLUMN exercise_mode exercise_mode_enum DEFAULT 'strength' NOT NULL")
                )
            except Exception:
                # SQLite fallback (use VARCHAR)
                await conn.execute(
                    text("ALTER TABLE workout_exercises ADD COLUMN exercise_mode VARCHAR(20) DEFAULT 'strength' NOT NULL")
                )
            print("Added column: exercise_mode")
        else:
            print("Column exercise_mode already exists, skipping.")

        # Add duration_minutes column (Duration mode: total time in minutes)
        if "duration_minutes" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN duration_minutes INTEGER")
            )
            print("Added column: duration_minutes")
        else:
            print("Column duration_minutes already exists, skipping.")

        # Add intensity column (Duration mode: low, moderate, high, max)
        if "intensity" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN intensity VARCHAR(20)")
            )
            print("Added column: intensity")
        else:
            print("Column intensity already exists, skipping.")

        # Add work_seconds column (Interval mode: work interval duration)
        if "work_seconds" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN work_seconds INTEGER")
            )
            print("Added column: work_seconds")
        else:
            print("Column work_seconds already exists, skipping.")

        # Add interval_rest_seconds column (Interval mode: rest between intervals)
        if "interval_rest_seconds" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN interval_rest_seconds INTEGER")
            )
            print("Added column: interval_rest_seconds")
        else:
            print("Column interval_rest_seconds already exists, skipping.")

        # Add rounds column (Interval mode: number of rounds)
        if "rounds" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN rounds INTEGER")
            )
            print("Added column: rounds")
        else:
            print("Column rounds already exists, skipping.")

        # Add distance_km column (Distance mode: distance in kilometers)
        if "distance_km" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN distance_km FLOAT")
            )
            print("Added column: distance_km")
        else:
            print("Column distance_km already exists, skipping.")

        # Add target_pace_min_per_km column (Distance mode: target pace)
        if "target_pace_min_per_km" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE workout_exercises ADD COLUMN target_pace_min_per_km FLOAT")
            )
            print("Added column: target_pace_min_per_km")
        else:
            print("Column target_pace_min_per_km already exists, skipping.")

    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
