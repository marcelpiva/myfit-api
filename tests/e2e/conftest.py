"""
E2E Test Configuration and Fixtures for SAGA Tests.

IMPORTANT: These tests must ONLY run in local or development environments.
NEVER run these tests against production databases or APIs.

Uses SQLite in-memory database for fast, isolated test execution.
"""

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Environment validation - CRITICAL for safety
ALLOWED_ENVIRONMENTS = {"local", "development", "test", "testing"}

# In-memory SQLite database for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def validate_environment():
    """Validate that we're not running against production."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env not in ALLOWED_ENVIRONMENTS:
        raise RuntimeError(
            f"E2E tests can only run in {ALLOWED_ENVIRONMENTS}. "
            f"Current environment: {env}"
        )

    # Additional safety checks
    db_url = os.getenv("DATABASE_URL", "")
    if "prod" in db_url.lower() or "production" in db_url.lower():
        raise RuntimeError("E2E tests cannot run against production database!")


# Run validation at import time
validate_environment()


# =============================================================================
# SQLite Compatibility - Map PostgreSQL types to SQLite equivalents
# =============================================================================

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    def visit_JSONB(self, type_, **kw):
        return self.visit_JSON(type_, **kw)
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB


# =============================================================================
# Database Fixtures - In-Memory SQLite
# =============================================================================


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio backend for tests."""
    return "asyncio"


@pytest.fixture(scope="function")
async def test_engine():
    """Create a test database engine with in-memory SQLite."""
    from src.config.database import Base

    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Enable foreign key support for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
    from src.main import create_app
    from src.config.database import get_db

    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        follow_redirects=True,
    ) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# SAGA Test Data - Standard test users and organizations
# =============================================================================

TEST_PERSONAL = {
    "name": "João Silva",
    "email": "joao.personal@example.com",
    "password": "Test@123",
}

TEST_STUDENT = {
    "name": "Maria Santos",
    "email": "maria.aluna@example.com",
    "password": "Test@456",
}

TEST_ORGANIZATION = {
    "name": "Studio Fitness Teste",
    "type": "personal",
    "description": "Treinos personalizados para testes",
    "phone": "(11) 99999-9999",
}

TEST_PLAN = {
    "name": "Plano Teste Iniciante",
    "goal": "general_fitness",
    "difficulty": "beginner",
    "split_type": "abc",
    "duration_weeks": 4,
}


# =============================================================================
# SAGA Fixtures - Complete user journeys
# =============================================================================


@pytest.fixture
async def personal_trainer_setup(
    db_session: AsyncSession,
) -> dict[str, Any]:
    """
    Create a complete Personal Trainer setup for SAGA tests.

    Returns dict with:
    - user: Personal trainer user data
    - organization: Organization data
    - token: Auth token for API calls
    """
    from src.domains.users.models import User
    from src.domains.organizations.models import (
        Organization,
        OrganizationMembership,
        OrganizationType,
        UserRole,
    )
    from src.core.security import create_access_token
    from src.core.security.jwt import hash_password

    # Create organization
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name=TEST_ORGANIZATION["name"],
        type=OrganizationType.PERSONAL,
        description=TEST_ORGANIZATION["description"],
        phone=TEST_ORGANIZATION["phone"],
    )
    db_session.add(org)

    # Create personal trainer user
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=TEST_PERSONAL["email"],
        name=TEST_PERSONAL["name"],
        password_hash=hash_password(TEST_PERSONAL["password"]),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    # Create membership with TRAINER role
    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=org_id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()

    # Generate auth token
    token = create_access_token(user_id=str(user_id))

    return {
        "user": {
            "id": user_id,
            "email": user.email,
            "name": user.name,
        },
        "organization": {
            "id": org_id,
            "name": org.name,
        },
        "token": token,
    }


@pytest.fixture
async def student_setup(
    db_session: AsyncSession,
    personal_trainer_setup: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a complete Student setup linked to a Personal Trainer.

    Returns dict with:
    - user: Student user data
    - membership: Organization membership data
    - token: Auth token for API calls
    - trainer: Reference to the personal trainer
    """
    from src.domains.users.models import User
    from src.domains.organizations.models import OrganizationMembership, UserRole
    from src.core.security import create_access_token
    from src.core.security.jwt import hash_password

    org_id = personal_trainer_setup["organization"]["id"]

    # Create student user
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=TEST_STUDENT["email"],
        name=TEST_STUDENT["name"],
        password_hash=hash_password(TEST_STUDENT["password"]),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    # Create membership with STUDENT role
    membership_id = uuid.uuid4()
    membership = OrganizationMembership(
        id=membership_id,
        user_id=user_id,
        organization_id=org_id,
        role=UserRole.STUDENT,
        is_active=True,
        invited_by_id=personal_trainer_setup["user"]["id"],
    )
    db_session.add(membership)

    await db_session.commit()

    # Generate auth token
    token = create_access_token(user_id=str(user_id))

    return {
        "user": {
            "id": user_id,
            "email": user.email,
            "name": user.name,
        },
        "membership": {
            "id": membership_id,
            "organization_id": org_id,
            "role": "student",
        },
        "token": token,
        "trainer": personal_trainer_setup,
    }


@pytest.fixture
async def training_plan_setup(
    db_session: AsyncSession,
    personal_trainer_setup: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a complete training plan with workouts and exercises.

    Returns dict with:
    - plan: Training plan data
    - workouts: List of workouts with exercises
    """
    from src.domains.workouts.models import (
        TrainingPlan,
        Workout,
        PlanWorkout,
        Exercise,
        WorkoutExercise,
        WorkoutGoal,
        Difficulty,
        SplitType,
        MuscleGroup,
    )

    trainer_id = personal_trainer_setup["user"]["id"]
    org_id = personal_trainer_setup["organization"]["id"]

    # Create training plan
    plan_id = uuid.uuid4()
    plan = TrainingPlan(
        id=plan_id,
        name=TEST_PLAN["name"],
        description="Plano para iniciantes focado em condicionamento geral",
        goal=WorkoutGoal.GENERAL_FITNESS,
        difficulty=Difficulty.BEGINNER,
        split_type=SplitType.ABC,
        duration_weeks=TEST_PLAN["duration_weeks"],
        is_template=False,
        is_public=False,
        created_by_id=trainer_id,
        organization_id=org_id,
    )
    db_session.add(plan)

    # Create exercises (system exercises)
    exercises = []
    exercise_data = [
        ("Supino Reto com Barra", MuscleGroup.CHEST),
        ("Crucifixo com Halteres", MuscleGroup.CHEST),
        ("Tríceps Pulley", MuscleGroup.TRICEPS),
        ("Puxada Frontal", MuscleGroup.BACK),
        ("Remada Curvada", MuscleGroup.BACK),
        ("Rosca Direta", MuscleGroup.BICEPS),
        ("Agachamento Livre", MuscleGroup.QUADRICEPS),
        ("Leg Press 45°", MuscleGroup.QUADRICEPS),
        ("Desenvolvimento com Halteres", MuscleGroup.SHOULDERS),
    ]

    for name, muscle_group in exercise_data:
        exercise = Exercise(
            id=uuid.uuid4(),
            name=name,
            muscle_group=muscle_group,
            is_custom=False,
            is_public=True,
        )
        db_session.add(exercise)
        exercises.append(exercise)

    # Create workouts
    workouts_data = [
        {
            "name": "Treino A - Peito e Tríceps",
            "label": "A",
            "exercises": exercises[0:3],  # Chest and triceps
        },
        {
            "name": "Treino B - Costas e Bíceps",
            "label": "B",
            "exercises": exercises[3:6],  # Back and biceps
        },
        {
            "name": "Treino C - Pernas e Ombros",
            "label": "C",
            "exercises": exercises[6:9],  # Legs and shoulders
        },
    ]

    workouts = []
    for i, workout_info in enumerate(workouts_data):
        # Create workout
        workout = Workout(
            id=uuid.uuid4(),
            name=workout_info["name"],
            description=f"Treino {workout_info['label']} do plano iniciante",
            difficulty=Difficulty.BEGINNER,
            estimated_duration_min=60,
            created_by_id=trainer_id,
            organization_id=org_id,
        )
        db_session.add(workout)

        # Link workout to plan
        plan_workout = PlanWorkout(
            plan_id=plan_id,
            workout_id=workout.id,
            order=i,
            label=workout_info["label"],
        )
        db_session.add(plan_workout)

        # Add exercises to workout
        workout_exercises = []
        for j, exercise in enumerate(workout_info["exercises"]):
            we = WorkoutExercise(
                workout_id=workout.id,
                exercise_id=exercise.id,
                order=j,
                sets=4,
                reps="10-12",
                rest_seconds=90,
            )
            db_session.add(we)
            workout_exercises.append({
                "exercise_id": exercise.id,
                "name": exercise.name,
                "sets": 4,
                "reps": "10-12",
            })

        workouts.append({
            "id": workout.id,
            "name": workout.name,
            "label": workout_info["label"],
            "exercises": workout_exercises,
        })

    await db_session.commit()

    return {
        "plan": {
            "id": plan_id,
            "name": plan.name,
            "goal": TEST_PLAN["goal"],
            "difficulty": TEST_PLAN["difficulty"],
            "duration_weeks": TEST_PLAN["duration_weeks"],
        },
        "workouts": workouts,
        "trainer_id": trainer_id,
        "organization_id": org_id,
    }


@pytest.fixture
async def plan_assignment_setup(
    db_session: AsyncSession,
    training_plan_setup: dict[str, Any],
    student_setup: dict[str, Any],
) -> dict[str, Any]:
    """
    Create a plan assignment (student with assigned plan).

    Returns dict with:
    - assignment: Plan assignment data
    - plan: Training plan data
    - student: Student data
    - trainer: Trainer data
    """
    from src.domains.workouts.models import PlanAssignment, AssignmentStatus, TrainingMode

    plan_id = training_plan_setup["plan"]["id"]
    student_id = student_setup["user"]["id"]  # PlanAssignment uses user_id, not membership_id
    trainer_id = student_setup["trainer"]["user"]["id"]
    org_id = student_setup["trainer"]["organization"]["id"]

    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=plan_id,
        student_id=student_id,
        trainer_id=trainer_id,
        organization_id=org_id,
        start_date=datetime.now(timezone.utc).date(),
        end_date=(datetime.now(timezone.utc) + timedelta(weeks=4)).date(),
        status=AssignmentStatus.PENDING,
        training_mode=TrainingMode.PRESENCIAL,
        notes="Foco em técnica nas primeiras semanas",
    )
    db_session.add(assignment)
    await db_session.commit()

    return {
        "assignment": {
            "id": assignment.id,
            "status": "pending",
            "training_mode": "presencial",
        },
        "plan": training_plan_setup["plan"],
        "workouts": training_plan_setup["workouts"],
        "student": student_setup,
        "trainer": student_setup["trainer"],
    }


@pytest.fixture
async def active_workout_session_setup(
    db_session: AsyncSession,
    plan_assignment_setup: dict[str, Any],
) -> dict[str, Any]:
    """
    Create an active workout session for co-training tests.

    Returns dict with:
    - session: Workout session data
    - workout: Current workout data
    - assignment: Plan assignment data
    """
    from src.domains.workouts.models import (
        WorkoutSession,
        SessionStatus,
        PlanAssignment,
        AssignmentStatus,
    )

    # First, accept the plan assignment
    assignment_id = plan_assignment_setup["assignment"]["id"]
    assignment = await db_session.get(PlanAssignment, assignment_id)
    assignment.status = AssignmentStatus.ACCEPTED
    assignment.accepted_at = datetime.now(timezone.utc)

    student_id = plan_assignment_setup["student"]["user"]["id"]
    trainer_id = plan_assignment_setup["trainer"]["user"]["id"]
    workout = plan_assignment_setup["workouts"][0]  # Treino A

    # Create active session with trainer already joined (for co-training tests)
    # Note: assignment_id is None because WorkoutSession references workout_assignments
    # (WorkoutAssignment), not plan_assignments (PlanAssignment)
    session = WorkoutSession(
        id=uuid.uuid4(),
        user_id=student_id,
        trainer_id=trainer_id,  # Trainer already in session for co-training
        workout_id=workout["id"],
        assignment_id=None,  # WorkoutAssignment not created in this fixture
        status=SessionStatus.ACTIVE,
        started_at=datetime.now(timezone.utc),
        is_shared=True,  # Enable co-training
    )
    db_session.add(session)
    await db_session.commit()

    return {
        "session": {
            "id": session.id,
            "status": "active",
            "is_shared": True,
            "started_at": session.started_at,
        },
        "workout": workout,
        "assignment": plan_assignment_setup["assignment"],
        "student": plan_assignment_setup["student"],
        "trainer": plan_assignment_setup["trainer"],
    }


# =============================================================================
# API Client Fixtures
# =============================================================================


@pytest.fixture
async def personal_client(
    test_engine,
    db_session,
    personal_trainer_setup: dict[str, Any],
) -> AsyncClient:
    """Create an authenticated API client for the Personal Trainer."""
    from src.main import create_app
    from src.config.database import get_db

    app = create_app()
    token = personal_trainer_setup["token"]

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True,
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def student_client(
    test_engine,
    db_session,
    student_setup: dict[str, Any],
) -> AsyncClient:
    """Create an authenticated API client for the Student."""
    from src.main import create_app
    from src.config.database import get_db

    app = create_app()
    token = student_setup["token"]

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        headers={"Authorization": f"Bearer {token}"},
        follow_redirects=True,
    ) as client:
        yield client

    app.dependency_overrides.clear()


# =============================================================================
# Mock Fixtures for External Services
# =============================================================================


@pytest.fixture
def mock_email_service():
    """Mock email service to prevent actual email sending."""
    with patch("src.core.email.EmailService.send_email", new_callable=AsyncMock) as mock:
        mock.return_value = True
        yield mock


@pytest.fixture
def mock_push_notification():
    """Mock push notification service (placeholder - service not implemented yet)."""
    # Push notification service not yet implemented, so just yield None
    yield None
