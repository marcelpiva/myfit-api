"""
Script para alinhar constraints de nullable na produção com os modelos.

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

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def get_async_url(url: str) -> str:
    """Converte URL para formato async."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def main():
    """Alinha nullable constraints na produção."""
    prod_url = os.getenv("DATABASE_URL_PROD")

    if not prod_url:
        print("Erro: DATABASE_URL_PROD não definida")
        return

    engine = create_async_engine(get_async_url(prod_url), echo=False)

    print("=" * 60)
    print("ALINHANDO NULLABLE CONSTRAINTS NA PRODUÇÃO")
    print("=" * 60)

    async with engine.begin() as conn:
        # 1. workout_exercises.exercise_mode: deve ser NOT NULL (default='strength')
        print("\n1. workout_exercises.exercise_mode -> NOT NULL")
        try:
            # Primeiro, preenche valores NULL com default
            result = await conn.execute(
                text("UPDATE workout_exercises SET exercise_mode = 'strength' WHERE exercise_mode IS NULL")
            )
            print(f"   Atualizados {result.rowcount} registros com valor default 'strength'")

            # Agora altera para NOT NULL
            await conn.execute(
                text("ALTER TABLE workout_exercises ALTER COLUMN exercise_mode SET NOT NULL")
            )
            print("   Constraint alterada para NOT NULL")
        except Exception as e:
            print(f"   Erro: {e}")

        # 2. workout_exercises.technique_type: já é NOT NULL na PROD (OK)
        print("\n2. workout_exercises.technique_type -> NOT NULL (já está correto)")

        # 3. workout_exercises.exercise_group_order: já é NOT NULL na PROD (OK)
        print("\n3. workout_exercises.exercise_group_order -> NOT NULL (já está correto)")

        # 4. workouts.created_by_id: deve permitir NULL
        print("\n4. workouts.created_by_id -> NULL (permitir)")
        try:
            await conn.execute(
                text("ALTER TABLE workouts ALTER COLUMN created_by_id DROP NOT NULL")
            )
            print("   Constraint alterada para permitir NULL")
        except Exception as e:
            if "does not exist" in str(e).lower() or "no not-null" in str(e).lower():
                print("   Já permite NULL")
            else:
                print(f"   Erro: {e}")

    await engine.dispose()

    print("\n" + "=" * 60)
    print("ALINHAMENTO CONCLUÍDO")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
