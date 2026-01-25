"""
Migration: Add plan_snapshot column to plan_assignments table.

This column stores an independent copy of the plan data at assignment time,
ensuring the student's prescription is isolated from changes to the original model.

Run this script to add the new column to an existing database:
    python -m src.migrations.add_plan_snapshot

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
    """Add plan_snapshot column to plan_assignments table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "plan_assignments")

        # Add plan_snapshot column (JSON/JSONB for storing the complete plan copy)
        if "plan_snapshot" not in existing_columns:
            # Use JSONB for PostgreSQL (better performance and indexing)
            # SQLite will interpret this as TEXT which works fine for JSON
            try:
                await conn.execute(
                    text("ALTER TABLE plan_assignments ADD COLUMN plan_snapshot JSONB")
                )
            except Exception:
                # Fallback for SQLite
                await conn.execute(
                    text("ALTER TABLE plan_assignments ADD COLUMN plan_snapshot JSON")
                )
            print("Added column: plan_snapshot")
        else:
            print("Column plan_snapshot already exists")

    print("Plan snapshot migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
