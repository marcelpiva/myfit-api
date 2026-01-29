"""Backfill organization_id on workouts that have NULL values.

Workouts created before the create_workout fix may have organization_id = NULL.
This migration assigns them to the correct organization based on the creator's
organization memberships.

Strategy:
- For each workout with organization_id IS NULL:
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


async def migrate(database_url: str) -> None:
    """Backfill organization_id on workouts with NULL values."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if not is_postgres:
            logger.info("Skipping backfill_workout_org_id for non-postgres DB")
            return

        # Find workouts with NULL organization_id
        result = await conn.execute(
            text("""
                SELECT w.id, w.created_by_id, w.name
                FROM workouts w
                WHERE w.organization_id IS NULL
            """)
        )
        null_workouts = result.fetchall()

        if not null_workouts:
            logger.info("No workouts with NULL organization_id found, skipping")
            return

        logger.info(f"Found {len(null_workouts)} workouts with NULL organization_id")

        updated = 0
        for workout_id, created_by_id, workout_name in null_workouts:
            # Find the creator's org memberships
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
                {"user_id": created_by_id},
            )
            membership_rows = memberships.fetchall()

            if not membership_rows:
                logger.warning(
                    f"No active memberships for user {created_by_id}, "
                    f"skipping workout {workout_id} ({workout_name})"
                )
                continue

            # Pick the best org: prefer trainer/owner role
            org_id = membership_rows[0][0]

            await conn.execute(
                text("""
                    UPDATE workouts
                    SET organization_id = :org_id
                    WHERE id = :workout_id
                """),
                {"org_id": org_id, "workout_id": workout_id},
            )
            logger.info(
                f"Updated workout {workout_id} ({workout_name}) -> org {org_id}"
            )
            updated += 1

        logger.info(f"Backfilled organization_id on {updated}/{len(null_workouts)} workouts")


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
