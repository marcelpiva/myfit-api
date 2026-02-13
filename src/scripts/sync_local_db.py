"""
Script para sincronizar o banco local com a estrutura esperada.

Acoes:
1. Remove tabelas orfas (antigas versoes de program -> plan)
2. Aplica migracoes faltantes
3. Verifica consistencia

Uso:
    python -m src.scripts.sync_local_db
"""

import asyncio

import structlog
from sqlalchemy import text

from src.config.database import engine

logger = structlog.get_logger(__name__)


async def table_exists(conn, table_name: str) -> bool:
    """Check if a table exists."""
    result = await conn.execute(
        text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :table_name
            )
        """),
        {"table_name": table_name}
    )
    return result.scalar()


async def drop_orphan_tables(conn):
    """Remove tabelas orfas que nao sao mais usadas."""
    orphan_tables = [
        "workout_programs",
        "program_workouts",
        "program_assignments",
    ]

    logger.info("removing_orphan_tables")
    for table in orphan_tables:
        if await table_exists(conn, table):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            logger.info("table_removed", table=table)
        else:
            logger.debug("table_not_found", table=table)


async def get_columns(conn, table_name: str) -> set:
    """Get existing columns for a table."""
    result = await conn.execute(
        text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name AND table_schema = 'public'
        """),
        {"table_name": table_name}
    )
    return {row[0] for row in result.fetchall()}


async def check_enum_exists(conn, enum_name: str) -> bool:
    """Check if a PostgreSQL enum type exists."""
    result = await conn.execute(
        text("SELECT 1 FROM pg_type WHERE typname = :enum_name"),
        {"enum_name": enum_name}
    )
    return result.fetchone() is not None


async def apply_aerobic_fields_migration(conn):
    """Aplica migracao add_aerobic_exercise_fields."""
    logger.info("applying_migration", migration="add_aerobic_exercise_fields")

    existing = await get_columns(conn, "workout_exercises")

    # Create enum if not exists
    if not await check_enum_exists(conn, "exercise_mode_enum"):
        try:
            await conn.execute(
                text("CREATE TYPE exercise_mode_enum AS ENUM ('strength', 'duration', 'interval', 'distance')")
            )
            logger.info("enum_created", enum_type="exercise_mode_enum")
        except Exception as e:
            logger.warning("enum_creation_failed", enum_type="exercise_mode_enum", error=str(e))

    columns_to_add = [
        ("exercise_mode", "exercise_mode_enum DEFAULT 'strength' NOT NULL"),
        ("duration_minutes", "INTEGER"),
        ("intensity", "VARCHAR(20)"),
        ("work_seconds", "INTEGER"),
        ("interval_rest_seconds", "INTEGER"),
        ("rounds", "INTEGER"),
        ("distance_km", "FLOAT"),
        ("target_pace_min_per_km", "FLOAT"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing:
            try:
                await conn.execute(
                    text(f"ALTER TABLE workout_exercises ADD COLUMN {col_name} {col_type}")
                )
                logger.info("column_added", table="workout_exercises", column=col_name)
            except Exception as e:
                logger.error("column_add_failed", table="workout_exercises", column=col_name, error=str(e))
        else:
            logger.debug("column_exists", table="workout_exercises", column=col_name)


async def apply_invite_tracking_migration(conn):
    """Aplica migracao add_invite_tracking."""
    logger.info("applying_migration", migration="add_invite_tracking")

    existing = await get_columns(conn, "organization_invites")

    columns_to_add = [
        ("student_info", "JSONB"),
        ("resend_count", "INTEGER DEFAULT 0 NOT NULL"),
        ("last_resent_at", "TIMESTAMP WITH TIME ZONE"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing:
            try:
                await conn.execute(
                    text(f"ALTER TABLE organization_invites ADD COLUMN {col_name} {col_type}")
                )
                logger.info("column_added", table="organization_invites", column=col_name)
            except Exception as e:
                logger.error("column_add_failed", table="organization_invites", column=col_name, error=str(e))
        else:
            logger.debug("column_exists", table="organization_invites", column=col_name)


async def apply_advanced_techniques_migration(conn):
    """Aplica migracao add_advanced_techniques."""
    logger.info("applying_migration", migration="add_advanced_techniques")

    existing = await get_columns(conn, "workout_exercises")

    columns_to_add = [
        ("execution_instructions", "TEXT"),
        ("isometric_seconds", "INTEGER"),
        ("technique_type", "VARCHAR(20) DEFAULT 'normal' NOT NULL"),
        ("exercise_group_id", "VARCHAR(50)"),
        ("exercise_group_order", "INTEGER DEFAULT 0 NOT NULL"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing:
            try:
                await conn.execute(
                    text(f"ALTER TABLE workout_exercises ADD COLUMN {col_name} {col_type}")
                )
                logger.info("column_added", table="workout_exercises", column=col_name)
            except Exception as e:
                logger.error("column_add_failed", table="workout_exercises", column=col_name, error=str(e))
        else:
            logger.debug("column_exists", table="workout_exercises", column=col_name)


async def apply_technique_params_migration(conn):
    """Aplica migracao add_technique_params."""
    logger.info("applying_migration", migration="add_technique_params")

    existing = await get_columns(conn, "workout_exercises")

    columns_to_add = [
        ("drop_count", "INTEGER"),
        ("rest_between_drops", "INTEGER"),
        ("pause_duration", "INTEGER"),
        ("mini_set_count", "INTEGER"),
    ]

    for col_name, col_type in columns_to_add:
        if col_name not in existing:
            try:
                await conn.execute(
                    text(f"ALTER TABLE workout_exercises ADD COLUMN {col_name} {col_type}")
                )
                logger.info("column_added", table="workout_exercises", column=col_name)
            except Exception as e:
                logger.error("column_add_failed", table="workout_exercises", column=col_name, error=str(e))
        else:
            logger.debug("column_exists", table="workout_exercises", column=col_name)


async def verify_schema(conn):
    """Verifica se o schema esta correto."""
    logger.info("verifying_schema")

    # Check tables exist
    required_tables = [
        "training_plans",
        "plan_workouts",
        "plan_assignments",
        "workout_exercises",
        "organization_invites",
    ]

    all_ok = True
    for table in required_tables:
        exists = await table_exists(conn, table)
        if exists:
            logger.info("table_check_ok", table=table)
        else:
            logger.error("table_missing", table=table)
            all_ok = False

    # Check orphan tables are gone
    orphan_tables = ["workout_programs", "program_workouts", "program_assignments"]
    for table in orphan_tables:
        exists = await table_exists(conn, table)
        if exists:
            logger.warning("orphan_table_still_exists", table=table)
            all_ok = False

    return all_ok


async def main():
    """Executa sincronizacao do banco local."""
    logger.info("sync_local_db_started")

    async with engine.begin() as conn:
        # 1. Remove tabelas orfas
        await drop_orphan_tables(conn)

        # 2. Aplica migracoes
        await apply_advanced_techniques_migration(conn)
        await apply_technique_params_migration(conn)
        await apply_aerobic_fields_migration(conn)
        await apply_invite_tracking_migration(conn)

        # 3. Verifica
        all_ok = await verify_schema(conn)

        if all_ok:
            logger.info("sync_local_db_completed_successfully")
        else:
            logger.warning("sync_local_db_completed_with_warnings")


if __name__ == "__main__":
    asyncio.run(main())
