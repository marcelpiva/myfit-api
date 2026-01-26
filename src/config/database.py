from contextvars import ContextVar
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config.settings import settings

# Context variable to hold current tenant
current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def _get_async_database_url(url: str) -> str:
    """Convert database URL to async-compatible format.

    Hosting providers typically give postgresql:// URLs, but SQLAlchemy async
    requires postgresql+asyncpg:// for the asyncpg driver.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# Get async-compatible database URL
_database_url = _get_async_database_url(settings.DATABASE_URL)

# Create async engine with appropriate settings for the database type
_is_sqlite = _database_url.startswith("sqlite")

if _is_sqlite:
    engine = create_async_engine(
        _database_url,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        _database_url,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables.

    This imports all models to ensure they are registered with SQLAlchemy's
    metadata before creating the tables.
    """
    # Import all models to register them with Base.metadata
    from src.domains import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Add missing enum values for PostgreSQL (enums don't auto-update with create_all)
    if not _is_sqlite:
        await _sync_enum_values()

    # Run pending migrations (for columns added to existing tables)
    await _run_pending_migrations()


async def _run_pending_migrations() -> None:
    """Run any pending migrations for existing tables.

    SQLAlchemy's create_all() doesn't add columns to existing tables,
    so we need to run migrations manually. Each migration runs with
    a fresh connection to avoid transaction state issues.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    migrations = [
        # (column_name, table_name, column_definition, default_value)
        # Users table
        ("user_type", "users", "VARCHAR(20)", "'student'"),
        ("auth_provider", "users", "VARCHAR(20)", "'email'"),
        ("google_id", "users", "VARCHAR(255)", None),
        ("apple_id", "users", "VARCHAR(255)", None),
        ("cref", "users", "VARCHAR(20)", None),
        ("cref_verified", "users", "BOOLEAN", "FALSE"),
        ("cref_verified_at", "users", "TIMESTAMP", None),
        ("is_verified", "users", "BOOLEAN", "FALSE"),
        # Plan assignments table
        ("training_mode", "plan_assignments", "VARCHAR(20)", "'presencial'"),
        ("acknowledged_at", "plan_assignments", "TIMESTAMP", None),
        ("plan_snapshot", "plan_assignments", "JSONB", None),
        ("version", "plan_assignments", "INTEGER", "1"),
        ("last_version_viewed", "plan_assignments", "INTEGER", None),
        ("status", "plan_assignments", "VARCHAR(20)", "'accepted'"),
        ("accepted_at", "plan_assignments", "TIMESTAMP", None),
        ("declined_reason", "plan_assignments", "TEXT", None),
        # User settings table
        ("dnd_enabled", "user_settings", "BOOLEAN", "FALSE"),
        ("dnd_start_time", "user_settings", "TIME", None),
        ("dnd_end_time", "user_settings", "TIME", None),
        # Training plans table
        ("status", "training_plans", "VARCHAR(20)", "'published'"),
    ]

    # Create a separate engine for migrations to avoid connection state issues
    migration_engine = create_async_engine(_database_url, pool_pre_ping=True)

    try:
        for column_name, table_name, column_type, default_value in migrations:
            try:
                async with migration_engine.connect() as conn:
                    # Check if column exists
                    result = await conn.execute(
                        text("""
                            SELECT column_name FROM information_schema.columns
                            WHERE table_name = :table_name AND column_name = :column_name
                        """),
                        {"table_name": table_name, "column_name": column_name},
                    )
                    row = result.fetchone()
                    await conn.commit()

                    if row is None:
                        # Column doesn't exist, add it in a new transaction
                        async with migration_engine.connect() as conn2:
                            default_clause = f" DEFAULT {default_value}" if default_value else ""
                            sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}{default_clause}"
                            await conn2.execute(text(sql))
                            await conn2.commit()
                            print(f"Added column {table_name}.{column_name}")
            except Exception as e:
                # Column might already exist or other error - continue with next
                err_str = str(e)
                if "already exists" not in err_str.lower():
                    print(f"Migration note ({table_name}.{column_name}): {e}")

        # Data fixes: correct invalid enum values
        data_fixes = [
            # Fix 'active' -> 'published' for training_plans.status
            ("UPDATE training_plans SET status = 'published' WHERE status = 'active'", "training_plans.status active->published"),
        ]

        for sql, description in data_fixes:
            try:
                async with migration_engine.connect() as conn:
                    result = await conn.execute(text(sql))
                    await conn.commit()
                    if result.rowcount > 0:
                        print(f"Data fix ({description}): {result.rowcount} rows updated")
            except Exception as e:
                print(f"Data fix note ({description}): {e}")

    finally:
        await migration_engine.dispose()


async def _sync_enum_values() -> None:
    """Add missing enum values to PostgreSQL enums.

    PostgreSQL enums don't automatically update when model enums change.
    This function adds any missing values.
    """
    from sqlalchemy import text

    # Define expected enum values
    enum_updates = [
        ("exercise_mode_enum", ["strength", "duration", "interval", "distance", "stretching"]),
    ]

    async with engine.begin() as conn:
        for enum_name, expected_values in enum_updates:
            # Get current enum values
            result = await conn.execute(
                text(f"""
                    SELECT enumlabel FROM pg_enum
                    WHERE enumtypid = (SELECT oid FROM pg_type WHERE typname = :enum_name)
                """),
                {"enum_name": enum_name},
            )
            current_values = {row[0] for row in result.fetchall()}

            # Add missing values
            for value in expected_values:
                if value not in current_values:
                    print(f"Adding '{value}' to {enum_name}...")
                    await conn.execute(
                        text(f"ALTER TYPE {enum_name} ADD VALUE '{value}'")
                    )
                    print(f"Successfully added '{value}' to {enum_name}")
