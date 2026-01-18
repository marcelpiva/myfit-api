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
