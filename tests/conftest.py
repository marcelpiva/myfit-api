"""Test configuration and fixtures for MyFit API."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.database import Base, get_db
from src.main import create_app

# Test database URL - use SQLite in-memory for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


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
