"""
Migration: Add metadata and tracking columns to organization_invites table.

Run this script to add the new columns to an existing database:
    python -m src.migrations.add_invite_tracking

For new installations, these columns will be created automatically by create_all().
"""
import asyncio

from sqlalchemy import text

from src.config.database import engine


async def get_existing_columns(conn, table_name: str) -> set:
    """Get existing columns for a table, works with both SQLite and PostgreSQL."""
    # Try PostgreSQL first
    try:
        result = await conn.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = :table_name
                """
            ),
            {"table_name": table_name},
        )
        columns = {row[0] for row in result.fetchall()}
        if columns:
            return columns
    except Exception:
        pass

    # Fall back to SQLite
    try:
        result = await conn.execute(text(f"PRAGMA table_info({table_name})"))
        return {row[1] for row in result.fetchall()}
    except Exception:
        pass

    return set()


async def index_exists(conn, index_name: str) -> bool:
    """Check if an index exists in the database."""
    # Try PostgreSQL first
    try:
        result = await conn.execute(
            text(
                """
                SELECT 1 FROM pg_indexes WHERE indexname = :index_name
                """
            ),
            {"index_name": index_name},
        )
        return result.fetchone() is not None
    except Exception:
        pass

    # Fall back to SQLite
    try:
        result = await conn.execute(
            text(
                """
                SELECT 1 FROM sqlite_master WHERE type='index' AND name = :index_name
                """
            ),
            {"index_name": index_name},
        )
        return result.fetchone() is not None
    except Exception:
        pass

    return False


async def upgrade():
    """Add metadata and tracking columns to organization_invites table."""
    async with engine.begin() as conn:
        existing_columns = await get_existing_columns(conn, "organization_invites")

        # Add student_info column (JSONB for PostgreSQL) - stores name, phone, goal, notes
        if "student_info" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE organization_invites ADD COLUMN student_info JSONB")
            )
            print("Added column: student_info")
        else:
            print("Column student_info already exists, skipping.")

        # Add resend_count column
        if "resend_count" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE organization_invites ADD COLUMN resend_count INTEGER DEFAULT 0 NOT NULL")
            )
            print("Added column: resend_count")
        else:
            print("Column resend_count already exists, skipping.")

        # Add last_resent_at column
        if "last_resent_at" not in existing_columns:
            await conn.execute(
                text("ALTER TABLE organization_invites ADD COLUMN last_resent_at TIMESTAMP WITH TIME ZONE")
            )
            print("Added column: last_resent_at")
        else:
            print("Column last_resent_at already exists, skipping.")

        # Add unique partial index for pending invites (PostgreSQL only)
        if not await index_exists(conn, "ix_unique_pending_invite"):
            try:
                await conn.execute(
                    text(
                        """
                        CREATE UNIQUE INDEX ix_unique_pending_invite
                        ON organization_invites (organization_id, email)
                        WHERE accepted_at IS NULL
                        """
                    )
                )
                print("Added unique partial index: ix_unique_pending_invite")
            except Exception as e:
                print(f"Could not create unique partial index (may not be supported): {e}")
        else:
            print("Index ix_unique_pending_invite already exists, skipping.")

    print("Migration completed successfully!")


if __name__ == "__main__":
    asyncio.run(upgrade())
