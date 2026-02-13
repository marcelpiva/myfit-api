"""
Add 'stretching' value to exercise_mode_enum in PostgreSQL.

Run with:
    python -m src.scripts.add_stretching_enum
"""

import asyncio
import os
import sys
from pathlib import Path

import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text
from src.config.database import engine

logger = structlog.get_logger(__name__)


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
            logger.info("adding_enum_value", enum_type="exercise_mode_enum", value="stretching")
            await conn.execute(
                text("ALTER TYPE exercise_mode_enum ADD VALUE 'stretching'")
            )
            logger.info("enum_value_added", enum_type="exercise_mode_enum", value="stretching")
        else:
            logger.info("enum_value_exists", enum_type="exercise_mode_enum", value="stretching")


async def main():
    logger.info("add_stretching_enum_script_started")
    await add_stretching_enum()
    logger.info("add_stretching_enum_script_completed")


if __name__ == "__main__":
    asyncio.run(main())
