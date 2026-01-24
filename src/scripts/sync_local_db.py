"""
Script para sincronizar o banco local com a estrutura esperada.

Ações:
1. Remove tabelas órfãs (antigas versões de program -> plan)
2. Aplica migrações faltantes
3. Verifica consistência

Uso:
    python -m src.scripts.sync_local_db
"""

import asyncio

from sqlalchemy import text

from src.config.database import engine


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
    """Remove tabelas órfãs que não são mais usadas."""
    orphan_tables = [
        "workout_programs",
        "program_workouts",
        "program_assignments",
    ]

    print("\n=== Removendo tabelas órfãs ===")
    for table in orphan_tables:
        if await table_exists(conn, table):
            await conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
            print(f"  Removida: {table}")
        else:
            print(f"  Não existe: {table}")


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
    """Aplica migração add_aerobic_exercise_fields."""
    print("\n=== Migrando: add_aerobic_exercise_fields ===")

    existing = await get_columns(conn, "workout_exercises")

    # Create enum if not exists
    if not await check_enum_exists(conn, "exercise_mode_enum"):
        try:
            await conn.execute(
                text("CREATE TYPE exercise_mode_enum AS ENUM ('strength', 'duration', 'interval', 'distance')")
            )
            print("  Criado enum: exercise_mode_enum")
        except Exception as e:
            print(f"  Enum já existe ou erro: {e}")

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
                print(f"  Adicionada coluna: {col_name}")
            except Exception as e:
                print(f"  Erro em {col_name}: {e}")
        else:
            print(f"  Já existe: {col_name}")


async def apply_invite_tracking_migration(conn):
    """Aplica migração add_invite_tracking."""
    print("\n=== Migrando: add_invite_tracking ===")

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
                print(f"  Adicionada coluna: {col_name}")
            except Exception as e:
                print(f"  Erro em {col_name}: {e}")
        else:
            print(f"  Já existe: {col_name}")


async def apply_advanced_techniques_migration(conn):
    """Aplica migração add_advanced_techniques."""
    print("\n=== Migrando: add_advanced_techniques ===")

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
                print(f"  Adicionada coluna: {col_name}")
            except Exception as e:
                print(f"  Erro em {col_name}: {e}")
        else:
            print(f"  Já existe: {col_name}")


async def apply_technique_params_migration(conn):
    """Aplica migração add_technique_params."""
    print("\n=== Migrando: add_technique_params ===")

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
                print(f"  Adicionada coluna: {col_name}")
            except Exception as e:
                print(f"  Erro em {col_name}: {e}")
        else:
            print(f"  Já existe: {col_name}")


async def verify_schema(conn):
    """Verifica se o schema está correto."""
    print("\n=== Verificação final ===")

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
        status = "OK" if exists else "FALTA"
        print(f"  {table}: {status}")
        if not exists:
            all_ok = False

    # Check orphan tables are gone
    orphan_tables = ["workout_programs", "program_workouts", "program_assignments"]
    for table in orphan_tables:
        exists = await table_exists(conn, table)
        if exists:
            print(f"  AVISO: {table} ainda existe (órfã)")
            all_ok = False

    return all_ok


async def main():
    """Executa sincronização do banco local."""
    print("=" * 60)
    print("SINCRONIZAÇÃO DO BANCO LOCAL")
    print("=" * 60)

    async with engine.begin() as conn:
        # 1. Remove tabelas órfãs
        await drop_orphan_tables(conn)

        # 2. Aplica migrações
        await apply_advanced_techniques_migration(conn)
        await apply_technique_params_migration(conn)
        await apply_aerobic_fields_migration(conn)
        await apply_invite_tracking_migration(conn)

        # 3. Verifica
        all_ok = await verify_schema(conn)

        print("\n" + "=" * 60)
        if all_ok:
            print("SINCRONIZAÇÃO CONCLUÍDA COM SUCESSO!")
        else:
            print("SINCRONIZAÇÃO CONCLUÍDA COM AVISOS")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
