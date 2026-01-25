"""
Add 'stretching' value to exercise_mode_enum in PostgreSQL.

Run with:
    python -m src.scripts.add_stretching_enum
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from src.config.database import engine


async def add_stretching_enum():
    """Add 'stretching' to exercise_mode_enum if not exists."""
    async with engine.begin() as conn:
        # Check if 'stretching' already exists in the enum
        result = await conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_enum
                    WHERE enumlabel = 'stretching'
                    AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'exercise_mode_enum')
                )
            """)
        )
        exists = result.scalar()

        if not exists:
            print("Adding 'stretching' to exercise_mode_enum...")
            await conn.execute(
                text("ALTER TYPE exercise_mode_enum ADD VALUE 'stretching'")
            )
            print("Successfully added 'stretching' to exercise_mode_enum")
        else:
            print("'stretching' already exists in exercise_mode_enum")


async def main():
    print("=" * 60)
    print("Add Stretching Enum Value Script")
    print("=" * 60)
    await add_stretching_enum()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
