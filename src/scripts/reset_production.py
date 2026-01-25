"""
Script para reset do banco de dados de produção.
Mantém os feeds de exercícios (tabela exercises) intactos.
"""
import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


# URL do banco de produção (passar via variável de ambiente)
import os
DATABASE_URL = os.getenv("DATABASE_URL_PROD", "").replace("postgresql://", "postgresql+asyncpg://")


# Tabelas a serem limpas (em ordem para respeitar foreign keys)
TABLES_TO_TRUNCATE = [
    # Tabelas de sessão e feedback (dependem de outras)
    "exercise_feedbacks",
    "session_messages",
    "trainer_adjustments",
    "workout_session_sets",
    "workout_sessions",

    # Notas e prescrições
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

    # Organizações
    "organization_invites",
    "organization_memberships",
    "organizations",

    # Usuários
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
    print("=" * 60)
    print("VERIFICANDO TABELAS NO BANCO DE PRODUÇÃO")
    print("=" * 60)
    print()

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

        print(f"Tabelas encontradas ({len(tables)}):")
        for table in tables:
            # Contar registros
            try:
                count_result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = count_result.scalar()
                print(f"  - {table}: {count} registros")
            except Exception as e:
                print(f"  - {table}: erro ao contar ({e})")

    await engine.dispose()
    return tables


async def reset_database():
    """Reset do banco mantendo os exercícios."""
    print("=" * 60)
    print("RESET DO BANCO DE DADOS DE PRODUÇÃO")
    print("=" * 60)
    print()

    engine = create_async_engine(DATABASE_URL, echo=False)

    # 1. Verificações iniciais
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
            print("ERRO: A tabela 'exercises' não existe no banco de produção!")
            return

        # Verificar quantos exercícios existem
        result = await conn.execute(text("SELECT COUNT(*) FROM exercises"))
        exercise_count = result.scalar()
        print(f"Exercícios encontrados: {exercise_count}")

        # Verificar quantos usuários existem
        try:
            result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            user_count = result.scalar()
            print(f"Usuários a serem removidos: {user_count}")
        except Exception:
            user_count = 0

    # 2. Confirmação
    print()
    print("ATENÇÃO: Este script vai APAGAR todos os dados do banco")
    print("EXCETO os exercícios (feeds de exercícios).")
    print()
    confirm = input("Digite 'CONFIRMAR' para prosseguir: ")

    if confirm != "CONFIRMAR":
        print("Operação cancelada.")
        await engine.dispose()
        return

    print()
    print("Iniciando reset...")
    print()

    # 3. Truncar cada tabela em transações separadas
    for table in TABLES_TO_TRUNCATE:
        try:
            async with engine.begin() as conn:
                # Desabilitar triggers para esta transação
                await conn.execute(text("SET session_replication_role = 'replica';"))
                await conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                await conn.execute(text("SET session_replication_role = 'origin';"))
            print(f"  ✓ {table}")
        except Exception as e:
            error_str = str(e)
            if "does not exist" in error_str or "UndefinedTableError" in error_str:
                print(f"  - {table} (não existe)")
            else:
                print(f"  ✗ {table}: {error_str[:80]}")

    # 4. Verificar exercícios após reset
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT COUNT(*) FROM exercises"))
        final_exercise_count = result.scalar()

    print()
    print("=" * 60)
    print("RESET CONCLUÍDO!")
    print("=" * 60)
    print(f"Exercícios mantidos: {final_exercise_count}")
    print()

    await engine.dispose()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        asyncio.run(list_tables())
    else:
        asyncio.run(reset_database())
