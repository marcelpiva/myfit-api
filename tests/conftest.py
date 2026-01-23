"""Test configuration and fixtures for MyFit API."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import JSON, event
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.database import Base, get_db
from src.main import create_app

# Test database URL - use SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# =============================================================================
# SQLite Compatibility - Map PostgreSQL types to SQLite equivalents
# =============================================================================


# Monkey-patch JSONB to use JSON for SQLite
# This allows models using JSONB to work with SQLite in tests
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    def visit_JSONB(self, type_, **kw):
        return self.visit_JSON(type_, **kw)
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio backend for tests."""
    return "asyncio"


@pytest.fixture(scope="function")
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Import all models to register them
    from src.domains import models  # noqa: F401

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture(scope="function")
async def client(test_engine, db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with database session override."""
    app = create_app()

    # Override the database dependency
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Generate a sample user ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_organization_id() -> uuid.UUID:
    """Generate a sample organization ID."""
    return uuid.uuid4()


@pytest.fixture
async def sample_user(db_session: AsyncSession, sample_organization_id: uuid.UUID) -> dict[str, Any]:
    """Create a sample user in the database."""
    from src.domains.users.models import User
    from src.domains.organizations.models import Organization, OrganizationMembership, UserRole, OrganizationType

    # Create organization first
    org = Organization(
        id=sample_organization_id,
        name="Test Organization",
        type=OrganizationType.PERSONAL,
    )
    db_session.add(org)

    # Create user
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"test-{user_id}@example.com",
        name="Test User",
        password_hash="$2b$12$test.hash.password",  # Not a real hash
        is_active=True,
    )
    db_session.add(user)

    # Create membership
    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=sample_organization_id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": sample_organization_id,
    }


@pytest.fixture
async def sample_workout_program(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
) -> dict[str, Any]:
    """Create a sample workout program in the database."""
    from src.domains.workouts.models import WorkoutProgram

    program = WorkoutProgram(
        name="Test Program",
        description="A test workout program",
        goal="strength",
        difficulty="intermediate",
        split_type="push_pull_legs",
        duration_weeks=8,
        is_template=True,
        is_public=False,
        created_by_id=sample_user["id"],
        source_template_id=uuid.uuid4(),  # Simulate imported program
    )
    db_session.add(program)
    await db_session.commit()
    await db_session.refresh(program)

    return {
        "id": program.id,
        "name": program.name,
        "source_template_id": program.source_template_id,
        "created_by_id": program.created_by_id,
    }


# =============================================================================
# Mock Fixtures for External Services
# =============================================================================


@pytest.fixture
def mock_redis():
    """Mock Redis client for token blacklisting."""
    blacklist = set()

    async def mock_add_to_blacklist(token: str, expires_in: int = 3600):
        blacklist.add(token)

    async def mock_is_blacklisted(token: str) -> bool:
        return token in blacklist

    with patch("src.core.redis.add_to_blacklist", side_effect=mock_add_to_blacklist):
        with patch("src.core.redis.is_blacklisted", side_effect=mock_is_blacklisted):
            yield blacklist


@pytest.fixture
def mock_email():
    """Mock email service for all email sending operations."""
    with patch("src.core.email.send_email", new_callable=AsyncMock) as mock:
        mock.return_value = {"id": "mock-email-id", "status": "sent"}
        yield mock


@pytest.fixture
def mock_s3():
    """Mock AWS S3 for file uploads."""
    mock_client = MagicMock()
    mock_client.upload_fileobj = MagicMock(return_value=None)
    mock_client.generate_presigned_url = MagicMock(
        return_value="https://s3.example.com/mock-file"
    )
    with patch("boto3.client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_openai():
    """Mock OpenAI client for AI workout suggestions."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"exercises": [], "notes": "AI generated"}'))
    ]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    with patch("openai.AsyncOpenAI", return_value=mock_client):
        yield mock_client


# =============================================================================
# Additional Test Data Fixtures
# =============================================================================


@pytest.fixture
async def inactive_user(
    db_session: AsyncSession, sample_organization_id: uuid.UUID
) -> dict[str, Any]:
    """Create an inactive user in the database."""
    from src.domains.users.models import User

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"inactive-{user_id}@example.com",
        name="Inactive User",
        password_hash="$2b$12$test.hash.password",
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "is_active": False,
    }


@pytest.fixture
async def user_with_points(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> dict[str, Any]:
    """Create a user with gamification points."""
    from src.domains.gamification.models import UserPoints

    user_points = UserPoints(
        user_id=sample_user["id"],
        total_points=500,
        level=3,
        current_streak=5,
        longest_streak=10,
        last_activity_at=datetime.utcnow() - timedelta(days=1),
    )
    db_session.add(user_points)
    await db_session.commit()
    await db_session.refresh(user_points)

    return {
        **sample_user,
        "points": user_points.total_points,
        "level": user_points.level,
        "current_streak": user_points.current_streak,
        "longest_streak": user_points.longest_streak,
    }
