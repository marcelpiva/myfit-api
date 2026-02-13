"""Fix consultancy_listings.professional_id FK: users(id) -> professional_profiles(id).

The original migration incorrectly referenced users(id) but the SQLAlchemy model
relationship is with ProfessionalProfile, so the FK must point to professional_profiles(id).
"""
import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


async def migrate(database_url: str) -> None:
    """Fix the professional_id foreign key on consultancy_listings."""
    engine = create_async_engine(database_url)

    async with engine.begin() as conn:
        is_postgres = "postgresql" in database_url or "postgres" in database_url

        if not is_postgres:
            # SQLite doesn't support ALTER TABLE DROP CONSTRAINT;
            # the table is likely fresh anyway, skip.
            logger.info("SQLite: skipping FK fix (not supported)")
            await engine.dispose()
            return

        # Check if the table exists
        result = await conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_name = 'consultancy_listings'"
                ")"
            )
        )
        if not result.scalar():
            logger.info("consultancy_listings does not exist, skipping FK fix")
            await engine.dispose()
            return

        # Find the existing FK constraint name that references users(id)
        result = await conn.execute(
            text("""
                SELECT tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.constraint_column_usage ccu
                  ON tc.constraint_name = ccu.constraint_name
                WHERE tc.table_name = 'consultancy_listings'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND ccu.table_name = 'users'
                  AND ccu.column_name = 'id'
                  AND tc.constraint_name LIKE '%professional_id%'
            """)
        )
        row = result.first()

        if row is None:
            # No FK to users found on professional_id — might already be fixed
            # or the constraint name doesn't contain 'professional_id'.
            # Try a broader search.
            result = await conn.execute(
                text("""
                    SELECT kcu.constraint_name
                    FROM information_schema.key_column_usage kcu
                    JOIN information_schema.table_constraints tc
                      ON kcu.constraint_name = tc.constraint_name
                    JOIN information_schema.constraint_column_usage ccu
                      ON tc.constraint_name = ccu.constraint_name
                    WHERE kcu.table_name = 'consultancy_listings'
                      AND kcu.column_name = 'professional_id'
                      AND tc.constraint_type = 'FOREIGN KEY'
                      AND ccu.table_name = 'users'
                """)
            )
            row = result.first()

        if row is None:
            logger.info("FK already points to professional_profiles or not found, skipping")
            await engine.dispose()
            return

        constraint_name = row[0]
        logger.info(f"Dropping old FK constraint: {constraint_name}")

        await conn.execute(
            text(f"ALTER TABLE consultancy_listings DROP CONSTRAINT {constraint_name}")
        )
        await conn.execute(
            text(
                "ALTER TABLE consultancy_listings "
                "ADD CONSTRAINT consultancy_listings_professional_id_fkey "
                "FOREIGN KEY (professional_id) REFERENCES professional_profiles(id) ON DELETE CASCADE"
            )
        )
        logger.info("FK updated: professional_id now references professional_profiles(id)")

    await engine.dispose()
    logger.info("Migration fix_consultancy_listing_fk completed")
