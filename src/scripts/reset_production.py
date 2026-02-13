"""
Script para reset do banco de dados de producao.
Mantem os feeds de exercicios (tabela exercises) intactos.
"""
import asyncio
import os
import sys

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = structlog.get_logger(__name__)

# URL do banco de producao (passar via variavel de ambiente)
DATABASE_URL = os.getenv("DATABASE_URL_PROD", "").replace("postgresql://", "postgresql+asyncpg://")


# Tabelas a serem limpas (em ordem para respeitar foreign keys)
TABLES_TO_TRUNCATE = [
    # Tabelas de sessao e feedback (dependem de outras)
    "exercise_feedbacks",
    "session_messages",
    "trainer_adjustments",
    "workout_session_sets",
    "workout_sessions",

    # Notas e prescricoes
    "prescription_notes",
    "student_notes",

    # Assignments e relacionamentos
    "plan_assignments",
    "workout_assignments",

    # Estrutura de treinos (dependem de workouts/plans)
    "plan_workouts",
    "workout_exercises",

    # Treinos e planos
    "workouts",
    "training_plans",

    # Organizacoes
    "organization_invites",
    "organization_memberships",
    "organizations",

    # Usuarios
    "user_settings",
    "device_tokens",
    "users",

    # Outras tabelas que podem existir
    "checkins",
    "body_measurements",
    "progress_photos",
    "weight_records",
    "nutrition_logs",
    "meal_plans",
    "chat_messages",
    "chat_rooms",
    "notifications",
    "achievements",
    "user_achievements",
    "streaks",
    "subscription_plans",
    "subscriptions",
    "payments",
]


async def list_tables():
    """Listar tabelas existentes no banco."""
    logger.info("listing_production_tables")

    engine = create_async_engine(DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        # Listar todas as tabelas
        result = await conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]

        logger.info("tables_found", count=len(tables))
        for table in tables:
            # Contar registros
            try:
                count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = count_result.scalar()
                logger.info("table_row_count", table=table, count=count)
            except Exception as e:
                logger.error("table_count_failed", table=table, error=str(e))

    await engine.dispose()
    return tables


async def reset_database():
    """Reset do banco mantendo os exercicios."""
    logger.info("production_database_reset_started")

    engine = create_async_engine(DATABASE_URL, echo=False)

    # 1. Verificacoes iniciais
    async with engine.connect() as conn:
        # Verificar se a tabela exercises existe
        result = await conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'exercises'
            )
        """))
        exercises_exists = result.scalar()

        if not exercises_exists:
            logger.error("exercises_table_not_found")
            return

        # Verificar quantos exercicios existem
        result = await conn.execute(text("SELECT COUNT(*) FROM exercises"))
        exercise_count = result.scalar()
        logger.info("exercises_found", count=exercise_count)

        # Verificar quantos usuarios existem
        try:
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            logger.info("users_to_remove", count=user_count)
        except Exception:
            user_count = 0

    # 2. Confirmacao
    logger.warning("database_reset_confirmation_required",
                   message="This will DELETE all data EXCEPT exercises")
    confirm = input("Digite 'CONFIRMAR' para prosseguir: ")

    if confirm != "CONFIRMAR":
        logger.info("reset_cancelled")
        await engine.dispose()
        return

    logger.info("reset_confirmed")

    # 3. Truncar cada tabela em transacoes separadas
    for table in TABLES_TO_TRUNCATE:
        try:
            async with engine.begin() as conn:
                # Desabilitar triggers para esta transacao
                await conn.execute(text("SET session_replication_role = 'replica';"))
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                await conn.execute(text("SET session_replication_role = 'origin';"))
            logger.info("table_truncated", table=table)
        except Exception as e:
            error_str = str(e)
            if "does not exist" in error_str or "UndefinedTableError" in error_str:
                logger.debug("table_not_found", table=table)
            else:
                logger.error("table_truncate_failed", table=table, error=error_str[:80])

    # 4. Verificar exercicios apos reset
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM exercises"))
        final_exercise_count = result.scalar()

    logger.info("production_database_reset_completed", exercises_kept=final_exercise_count)

    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        asyncio.run(list_tables())
    else:
        asyncio.run(reset_database())
