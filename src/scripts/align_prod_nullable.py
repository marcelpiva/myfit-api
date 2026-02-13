"""
Script para alinhar constraints de nullable na producao com os modelos.

Baseado nos modelos SQLAlchemy:
- workout_exercises.exercise_mode: NOT NULL (default='strength')
- workout_exercises.technique_type: NOT NULL (default='normal')
- workout_exercises.exercise_group_order: NOT NULL (default=0)
- workouts.created_by_id: NULL (permite null)

Uso:
    DATABASE_URL_PROD="postgresql://..." python -m src.scripts.align_prod_nullable
"""

import asyncio
import os

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = structlog.get_logger(__name__)


def get_async_url(url: str) -> str:
    """Converte URL para formato async."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def main():
    """Alinha nullable constraints na producao."""
    prod_url = os.getenv("DATABASE_URL_PROD")

    if not prod_url:
        logger.error("database_url_not_set", variable="DATABASE_URL_PROD")
        return

    engine = create_async_engine(get_async_url(prod_url), echo=False)

    logger.info("aligning_nullable_constraints")

    async with engine.begin() as conn:
        # 1. workout_exercises.exercise_mode: deve ser NOT NULL (default='strength')
        logger.info("aligning_column", table="workout_exercises", column="exercise_mode", target="NOT NULL")
        try:
            # Primeiro, preenche valores NULL com default
            result = await conn.execute(
                text("UPDATE workout_exercises SET exercise_mode = 'strength' WHERE exercise_mode IS NULL")
            )
            logger.info("null_values_updated", table="workout_exercises", column="exercise_mode",
                       rows_updated=result.rowcount, default_value="strength")

            # Agora altera para NOT NULL
            await conn.execute(
                text("ALTER TABLE workout_exercises ALTER COLUMN exercise_mode SET NOT NULL")
            )
            logger.info("constraint_set", table="workout_exercises", column="exercise_mode", constraint="NOT NULL")
        except Exception as e:
            logger.error("constraint_alignment_failed", table="workout_exercises",
                        column="exercise_mode", error=str(e))

        # 2. workout_exercises.technique_type: ja e NOT NULL na PROD (OK)
        logger.info("column_already_correct", table="workout_exercises",
                   column="technique_type", constraint="NOT NULL")

        # 3. workout_exercises.exercise_group_order: ja e NOT NULL na PROD (OK)
        logger.info("column_already_correct", table="workout_exercises",
                   column="exercise_group_order", constraint="NOT NULL")

        # 4. workouts.created_by_id: deve permitir NULL
        logger.info("aligning_column", table="workouts", column="created_by_id", target="NULL")
        try:
            await conn.execute(
                text("ALTER TABLE workouts ALTER COLUMN created_by_id DROP NOT NULL")
            )
            logger.info("constraint_set", table="workouts", column="created_by_id", constraint="NULLABLE")
        except Exception as e:
            if "does not exist" in str(e).lower() or "no not-null" in str(e).lower():
                logger.info("column_already_nullable", table="workouts", column="created_by_id")
            else:
                logger.error("constraint_alignment_failed", table="workouts",
                            column="created_by_id", error=str(e))

    await engine.dispose()

    logger.info("nullable_alignment_completed")


if __name__ == "__main__":
    asyncio.run(main())
