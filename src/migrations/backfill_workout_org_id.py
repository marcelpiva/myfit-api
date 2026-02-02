"""Backfill organization_id on workouts and plans that have NULL values.

Workouts/plans created before the org isolation fix may have organization_id = NULL.
This migration assigns them to the correct organization based on the creator's
organization memberships.

Strategy:
- For each workout/plan with organization_id IS NULL:
  - Look up the creator's active organization memberships
  - If the creator has exactly 1 membership, assign that org
  - If the creator has multiple memberships, assign the one where they are
    a trainer (role = 'trainer' or 'owner'), since templates are typically
    created by trainers
  - If no trainer membership found, assign the first membership (autonomous org)
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def _get_best_org_id(conn, user_id):
    """Find the best organization_id for a user based on their memberships."""
    memberships = await conn.execute(
        text("""
            SELECT om.organization_id, om.role
            FROM organization_memberships om
            WHERE om.user_id = :user_id AND om.is_active = true
            ORDER BY
                CASE om.role
                    WHEN 'gym_owner' THEN 1
                    WHEN 'trainer' THEN 2
                    WHEN 'coach' THEN 3
                    ELSE 4
                END
        """),
        {"user_id": user_id},
    )
    rows = memberships.fetchall()
    if not rows:
        return None
    return rows[0][0]


async def _backfill_table(conn, table_name: str, id_col: str = "id") -> int:
    """Backfill organization_id for a given table."""
    result = await conn.execute(
        text(f"""
            SELECT {id_col}, created_by_id, name
            FROM {table_name}
            WHERE organization_id IS NULL
        """)
    )
    null_rows = result.fetchall()

    if not null_rows:
        logger.info(f"No {table_name} with NULL organization_id found, skipping")
        return 0

    logger.info(f"Found {len(null_rows)} {table_name} with NULL organization_id")

    updated = 0
    for row_id, created_by_id, name in null_rows:
        org_id = await _get_best_org_id(conn, created_by_id)

        if not org_id:
            logger.warning(
                f"No active memberships for user {created_by_id}, "
                f"skipping {table_name} {row_id} ({name})"
            )
            continue

        await conn.execute(
            text(f"""
                UPDATE {table_name}
                SET organization_id = :org_id
                WHERE {id_col} = :row_id
            """),
            {"org_id": org_id, "row_id": row_id},
        )
        logger.info(f"Updated {table_name} {row_id} ({name}) -> org {org_id}")
        updated += 1

    logger.info(f"Backfilled organization_id on {updated}/{len(null_rows)} {table_name}")
    return updated


async def migrate(database_url: str) -> None:
    """Backfill organization_id on workouts and plans with NULL values."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if not is_postgres:
            logger.info("Skipping backfill for non-postgres DB")
            return

        await _backfill_table(conn, "workouts")
        await _backfill_table(conn, "training_plans")


async def main():
    """Run migration with default database URL."""
    import os
    from pathlib import Path

    try:
        from dotenv import load_dotenv
        env_path = Path(__file__).parent.parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass

    database_url = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./myfit.db"
    )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    await migrate(database_url)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
