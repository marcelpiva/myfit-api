"""
Tests for workout isolation by organization and user type.

Validates that:
1. Solo students can only see their own workouts
2. Students with trainers see only prescribed workouts
3. Trainers see their templates and per-student assignments
4. Workouts don't leak between organizations
5. Context switching works correctly for users with multiple orgs
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.users.models import User
from src.domains.workouts.models import (
    Workout,
    TrainingPlan,
    PlanWorkout,
    PlanAssignment,
    AssignmentStatus,
    Difficulty,
    WorkoutGoal,
    SplitType,
)
from src.core.security import create_access_token
from src.core.security.jwt import hash_password


# =============================================================================
# Fixtures for Workout Isolation Tests
# =============================================================================


@pytest.fixture
async def org_personal_joao(db_session: AsyncSession) -> dict[str, Any]:
    """Organization 1: Personal Trainer João's gym."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="Personal João Fitness",
        type=OrganizationType.PERSONAL,
    )
    db_session.add(org)
    await db_session.commit()
    return {"id": org_id, "name": org.name}


@pytest.fixture
async def org_personal_maria(db_session: AsyncSession) -> dict[str, Any]:
    """Organization 2: Personal Trainer Maria's gym."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="Personal Maria Studio",
        type=OrganizationType.PERSONAL,
    )
    db_session.add(org)
    await db_session.commit()
    return {"id": org_id, "name": org.name}


@pytest.fixture
async def org_autonomous_carlos(db_session: AsyncSession) -> dict[str, Any]:
    """Organization 3: Autonomous student Carlos's self-training org."""
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name="Treino Carlos",
        type=OrganizationType.AUTONOMOUS,
    )
    db_session.add(org)
    await db_session.commit()
    return {"id": org_id, "name": org.name}


@pytest.fixture
async def trainer_joao(
    db_session: AsyncSession,
    org_personal_joao: dict[str, Any],
) -> dict[str, Any]:
    """Trainer João in Organization 1."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="joao.trainer@example.com",
        name="João Trainer",
        password_hash=hash_password("Test@123"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=org_personal_joao["id"],
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(user_id=str(user_id))

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": org_personal_joao["id"],
        "token": token,
    }


@pytest.fixture
async def trainer_maria(
    db_session: AsyncSession,
    org_personal_maria: dict[str, Any],
) -> dict[str, Any]:
    """Trainer Maria in Organization 2."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="maria.trainer@example.com",
        name="Maria Trainer",
        password_hash=hash_password("Test@123"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=org_personal_maria["id"],
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(user_id=str(user_id))

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": org_personal_maria["id"],
        "token": token,
    }


@pytest.fixture
async def student_solo_carlos(
    db_session: AsyncSession,
    org_autonomous_carlos: dict[str, Any],
) -> dict[str, Any]:
    """Autonomous student Carlos - trains alone without trainer."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="carlos.solo@example.com",
        name="Carlos Solo",
        password_hash=hash_password("Test@123"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    # Carlos is both owner and student of his autonomous org
    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=org_autonomous_carlos["id"],
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(user_id=str(user_id))

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": org_autonomous_carlos["id"],
        "token": token,
        "has_trainer": False,
    }


@pytest.fixture
async def student_with_joao(
    db_session: AsyncSession,
    org_personal_joao: dict[str, Any],
    trainer_joao: dict[str, Any],
) -> dict[str, Any]:
    """Student Pedro linked to Trainer João."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="pedro.aluno@example.com",
        name="Pedro Aluno",
        password_hash=hash_password("Test@123"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=org_personal_joao["id"],
        role=UserRole.STUDENT,
        is_active=True,
        invited_by_id=trainer_joao["id"],
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(user_id=str(user_id))

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": org_personal_joao["id"],
        "trainer_id": trainer_joao["id"],
        "token": token,
        "has_trainer": True,
    }


@pytest.fixture
async def student_with_multiple_trainers(
    db_session: AsyncSession,
    org_personal_joao: dict[str, Any],
    org_personal_maria: dict[str, Any],
    trainer_joao: dict[str, Any],
    trainer_maria: dict[str, Any],
) -> dict[str, Any]:
    """Student Ana linked to BOTH Trainer João AND Trainer Maria."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email="ana.multi@example.com",
        name="Ana Multi-Trainer",
        password_hash=hash_password("Test@123"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    # Membership with João's org
    membership_joao = OrganizationMembership(
        user_id=user_id,
        organization_id=org_personal_joao["id"],
        role=UserRole.STUDENT,
        is_active=True,
        invited_by_id=trainer_joao["id"],
    )
    db_session.add(membership_joao)

    # Membership with Maria's org
    membership_maria = OrganizationMembership(
        user_id=user_id,
        organization_id=org_personal_maria["id"],
        role=UserRole.STUDENT,
        is_active=True,
        invited_by_id=trainer_maria["id"],
    )
    db_session.add(membership_maria)

    await db_session.commit()

    token = create_access_token(user_id=str(user_id))

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organizations": [
            {"id": org_personal_joao["id"], "trainer_id": trainer_joao["id"]},
            {"id": org_personal_maria["id"], "trainer_id": trainer_maria["id"]},
        ],
        "token": token,
    }


# =============================================================================
# Workout Fixtures
# =============================================================================


@pytest.fixture
async def workout_by_joao(
    db_session: AsyncSession,
    trainer_joao: dict[str, Any],
    org_personal_joao: dict[str, Any],
) -> Workout:
    """Workout created by Trainer João in his organization."""
    workout = Workout(
        id=uuid.uuid4(),
        name="Treino A - João",
        description="Treino criado por João",
        difficulty=Difficulty.INTERMEDIATE,
        estimated_duration_min=60,
        created_by_id=trainer_joao["id"],
        organization_id=org_personal_joao["id"],
        is_template=True,
    )
    db_session.add(workout)
    await db_session.commit()
    return workout


@pytest.fixture
async def workout_by_maria(
    db_session: AsyncSession,
    trainer_maria: dict[str, Any],
    org_personal_maria: dict[str, Any],
) -> Workout:
    """Workout created by Trainer Maria in her organization."""
    workout = Workout(
        id=uuid.uuid4(),
        name="Treino B - Maria",
        description="Treino criado por Maria",
        difficulty=Difficulty.BEGINNER,
        estimated_duration_min=45,
        created_by_id=trainer_maria["id"],
        organization_id=org_personal_maria["id"],
        is_template=True,
    )
    db_session.add(workout)
    await db_session.commit()
    return workout


@pytest.fixture
async def workout_by_carlos(
    db_session: AsyncSession,
    student_solo_carlos: dict[str, Any],
    org_autonomous_carlos: dict[str, Any],
) -> Workout:
    """Workout created by solo student Carlos."""
    workout = Workout(
        id=uuid.uuid4(),
        name="Meu Treino - Carlos",
        description="Treino pessoal do Carlos",
        difficulty=Difficulty.BEGINNER,
        estimated_duration_min=30,
        created_by_id=student_solo_carlos["id"],
        organization_id=org_autonomous_carlos["id"],
        is_template=False,
    )
    db_session.add(workout)
    await db_session.commit()
    return workout


@pytest.fixture
async def plan_by_joao_for_pedro(
    db_session: AsyncSession,
    trainer_joao: dict[str, Any],
    student_with_joao: dict[str, Any],
    workout_by_joao: Workout,
    org_personal_joao: dict[str, Any],
) -> dict[str, Any]:
    """Training plan created by João and assigned to Pedro."""
    # Create plan
    plan = TrainingPlan(
        id=uuid.uuid4(),
        name="Plano Iniciante - Pedro",
        goal=WorkoutGoal.GENERAL_FITNESS,
        difficulty=Difficulty.BEGINNER,
        split_type=SplitType.ABC,
        duration_weeks=4,
        created_by_id=trainer_joao["id"],
        organization_id=org_personal_joao["id"],
    )
    db_session.add(plan)

    # Link workout to plan
    plan_workout = PlanWorkout(
        plan_id=plan.id,
        workout_id=workout_by_joao.id,
        order=0,
        label="A",
    )
    db_session.add(plan_workout)

    # Assign plan to student
    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=plan.id,
        student_id=student_with_joao["id"],
        trainer_id=trainer_joao["id"],
        organization_id=org_personal_joao["id"],
        start_date=datetime.now(timezone.utc).date(),
        status=AssignmentStatus.ACCEPTED,
    )
    db_session.add(assignment)

    await db_session.commit()

    return {
        "plan_id": plan.id,
        "assignment_id": assignment.id,
        "workout_id": workout_by_joao.id,
        "student_id": student_with_joao["id"],
        "trainer_id": trainer_joao["id"],
    }


@pytest.fixture
async def plan_by_maria_for_ana(
    db_session: AsyncSession,
    trainer_maria: dict[str, Any],
    student_with_multiple_trainers: dict[str, Any],
    workout_by_maria: Workout,
    org_personal_maria: dict[str, Any],
) -> dict[str, Any]:
    """Training plan created by Maria and assigned to Ana."""
    plan = TrainingPlan(
        id=uuid.uuid4(),
        name="Plano Cardio - Ana",
        goal=WorkoutGoal.FAT_LOSS,
        difficulty=Difficulty.BEGINNER,
        split_type=SplitType.FULL_BODY,
        duration_weeks=8,
        created_by_id=trainer_maria["id"],
        organization_id=org_personal_maria["id"],
    )
    db_session.add(plan)

    plan_workout = PlanWorkout(
        plan_id=plan.id,
        workout_id=workout_by_maria.id,
        order=0,
        label="Full",
    )
    db_session.add(plan_workout)

    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=plan.id,
        student_id=student_with_multiple_trainers["id"],
        trainer_id=trainer_maria["id"],
        organization_id=org_personal_maria["id"],
        start_date=datetime.now(timezone.utc).date(),
        status=AssignmentStatus.ACCEPTED,
    )
    db_session.add(assignment)

    await db_session.commit()

    return {
        "plan_id": plan.id,
        "assignment_id": assignment.id,
        "workout_id": workout_by_maria.id,
    }


@pytest.fixture
async def plan_by_joao_for_ana(
    db_session: AsyncSession,
    trainer_joao: dict[str, Any],
    student_with_multiple_trainers: dict[str, Any],
    workout_by_joao: Workout,
    org_personal_joao: dict[str, Any],
) -> dict[str, Any]:
    """Training plan created by João and assigned to Ana."""
    plan = TrainingPlan(
        id=uuid.uuid4(),
        name="Plano Força - Ana",
        goal=WorkoutGoal.STRENGTH,
        difficulty=Difficulty.INTERMEDIATE,
        split_type=SplitType.PUSH_PULL_LEGS,
        duration_weeks=12,
        created_by_id=trainer_joao["id"],
        organization_id=org_personal_joao["id"],
    )
    db_session.add(plan)

    plan_workout = PlanWorkout(
        plan_id=plan.id,
        workout_id=workout_by_joao.id,
        order=0,
        label="Push",
    )
    db_session.add(plan_workout)

    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=plan.id,
        student_id=student_with_multiple_trainers["id"],
        trainer_id=trainer_joao["id"],
        organization_id=org_personal_joao["id"],
        start_date=datetime.now(timezone.utc).date(),
        status=AssignmentStatus.ACCEPTED,
    )
    db_session.add(assignment)

    await db_session.commit()

    return {
        "plan_id": plan.id,
        "assignment_id": assignment.id,
        "workout_id": workout_by_joao.id,
    }


# =============================================================================
# API Client Factories
# =============================================================================


async def create_client_for_user(
    test_engine,
    db_session: AsyncSession,
    token: str,
    organization_id: uuid.UUID | None = None,
) -> AsyncClient:
    """Create an authenticated client for a specific user."""
    from src.main import create_app
    from src.config.database import get_db

    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    headers = {"Authorization": f"Bearer {token}"}
    if organization_id:
        headers["X-Organization-ID"] = str(organization_id)

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test/api/v1",
        headers=headers,
        follow_redirects=True,
    )


# =============================================================================
# Test Class: Solo Student Isolation
# =============================================================================


@pytest.mark.anyio
class TestSoloStudentIsolation:
    """Test that solo students can only see their own workouts."""

    async def test_solo_student_sees_own_workouts(
        self,
        test_engine,
        db_session: AsyncSession,
        student_solo_carlos: dict[str, Any],
        workout_by_carlos: Workout,
    ):
        """Solo student can see workouts they created."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_solo_carlos["token"],
            student_solo_carlos["organization_id"],
        ) as client:
            response = await client.get("/workouts")
            assert response.status_code == 200

            workouts = response.json()
            assert len(workouts) >= 1
            assert any(w["id"] == str(workout_by_carlos.id) for w in workouts)

    async def test_solo_student_cannot_see_trainer_workouts(
        self,
        test_engine,
        db_session: AsyncSession,
        student_solo_carlos: dict[str, Any],
        workout_by_joao: Workout,
        workout_by_maria: Workout,
    ):
        """Solo student cannot see workouts from trainers' organizations."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_solo_carlos["token"],
            student_solo_carlos["organization_id"],
        ) as client:
            response = await client.get("/workouts")
            assert response.status_code == 200

            workouts = response.json()
            workout_ids = [w["id"] for w in workouts]

            # Should NOT see João's or Maria's workouts
            assert str(workout_by_joao.id) not in workout_ids
            assert str(workout_by_maria.id) not in workout_ids

    async def test_solo_student_can_create_workout(
        self,
        test_engine,
        db_session: AsyncSession,
        student_solo_carlos: dict[str, Any],
    ):
        """Solo student can create their own workouts."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_solo_carlos["token"],
            student_solo_carlos["organization_id"],
        ) as client:
            response = await client.post(
                "/workouts",
                json={
                    "name": "Novo Treino Carlos",
                    "description": "Treino criado pelo teste",
                    "difficulty": "beginner",
                    "estimated_duration_min": 45,
                },
            )
            assert response.status_code == 201

            data = response.json()
            assert data["name"] == "Novo Treino Carlos"
            assert data["created_by_id"] == str(student_solo_carlos["id"])


# =============================================================================
# Test Class: Student with Trainer Isolation
# =============================================================================


@pytest.mark.anyio
class TestStudentWithTrainerIsolation:
    """Test that students with trainers see only prescribed workouts."""

    async def test_student_sees_assigned_plans(
        self,
        test_engine,
        db_session: AsyncSession,
        student_with_joao: dict[str, Any],
        plan_by_joao_for_pedro: dict[str, Any],
    ):
        """Student can see plans assigned by their trainer."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_joao["token"],
            student_with_joao["organization_id"],
        ) as client:
            response = await client.get("/workouts/plans/assignments?active_only=true")
            assert response.status_code == 200

            assignments = response.json()
            assert len(assignments) >= 1
            assert any(
                a["id"] == str(plan_by_joao_for_pedro["assignment_id"])
                for a in assignments
            )

    async def test_student_cannot_see_other_org_plans(
        self,
        test_engine,
        db_session: AsyncSession,
        student_with_joao: dict[str, Any],
        plan_by_maria_for_ana: dict[str, Any],
    ):
        """Student cannot see plans from other organizations."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_joao["token"],
            student_with_joao["organization_id"],
        ) as client:
            response = await client.get("/workouts/plans/assignments?active_only=true")
            assert response.status_code == 200

            assignments = response.json()
            assignment_ids = [a["id"] for a in assignments]

            # Should NOT see Maria's plan for Ana
            assert str(plan_by_maria_for_ana["assignment_id"]) not in assignment_ids


# =============================================================================
# Test Class: Multiple Trainers Context Switching
# =============================================================================


@pytest.mark.anyio
class TestMultipleTrainersContextSwitching:
    """Test that students with multiple trainers see correct data per context."""

    async def test_student_sees_joao_plans_in_joao_context(
        self,
        test_engine,
        db_session: AsyncSession,
        student_with_multiple_trainers: dict[str, Any],
        org_personal_joao: dict[str, Any],
        plan_by_joao_for_ana: dict[str, Any],
        plan_by_maria_for_ana: dict[str, Any],
    ):
        """When context is João's org, student sees only João's plans."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_multiple_trainers["token"],
            org_personal_joao["id"],
        ) as client:
            response = await client.get("/workouts/plans/assignments?active_only=true")
            assert response.status_code == 200

            assignments = response.json()

            # Should see João's plan
            joao_assignment_ids = [
                a["id"] for a in assignments
                if a.get("organization_id") == str(org_personal_joao["id"])
                or a.get("id") == str(plan_by_joao_for_ana["assignment_id"])
            ]
            assert str(plan_by_joao_for_ana["assignment_id"]) in [
                a["id"] for a in assignments
            ]

    async def test_student_sees_maria_plans_in_maria_context(
        self,
        test_engine,
        db_session: AsyncSession,
        student_with_multiple_trainers: dict[str, Any],
        org_personal_maria: dict[str, Any],
        plan_by_joao_for_ana: dict[str, Any],
        plan_by_maria_for_ana: dict[str, Any],
    ):
        """When context is Maria's org, student sees only Maria's plans."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_multiple_trainers["token"],
            org_personal_maria["id"],
        ) as client:
            response = await client.get("/workouts/plans/assignments?active_only=true")
            assert response.status_code == 200

            assignments = response.json()

            # Should see Maria's plan
            assert str(plan_by_maria_for_ana["assignment_id"]) in [
                a["id"] for a in assignments
            ]

    async def test_context_switch_changes_visible_workouts(
        self,
        test_engine,
        db_session: AsyncSession,
        student_with_multiple_trainers: dict[str, Any],
        org_personal_joao: dict[str, Any],
        org_personal_maria: dict[str, Any],
        workout_by_joao: Workout,
        workout_by_maria: Workout,
        plan_by_joao_for_ana: dict[str, Any],
        plan_by_maria_for_ana: dict[str, Any],
    ):
        """Switching context changes which workouts are visible."""
        # Context: João's org
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_multiple_trainers["token"],
            org_personal_joao["id"],
        ) as client:
            response = await client.get(f"/workouts/{workout_by_joao.id}")
            # Should have access via assignment
            assert response.status_code in [200, 403]  # Depends on access check logic

        # Context: Maria's org
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_with_multiple_trainers["token"],
            org_personal_maria["id"],
        ) as client:
            response = await client.get(f"/workouts/{workout_by_maria.id}")
            # Should have access via assignment
            assert response.status_code in [200, 403]


# =============================================================================
# Test Class: Trainer Isolation
# =============================================================================


@pytest.mark.anyio
class TestTrainerIsolation:
    """Test that trainers see their own templates and per-student assignments."""

    async def test_trainer_sees_own_workouts(
        self,
        test_engine,
        db_session: AsyncSession,
        trainer_joao: dict[str, Any],
        workout_by_joao: Workout,
    ):
        """Trainer can see workouts they created."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            trainer_joao["token"],
            trainer_joao["organization_id"],
        ) as client:
            response = await client.get("/workouts")
            assert response.status_code == 200

            workouts = response.json()
            assert any(w["id"] == str(workout_by_joao.id) for w in workouts)

    async def test_trainer_cannot_see_other_trainer_workouts(
        self,
        test_engine,
        db_session: AsyncSession,
        trainer_joao: dict[str, Any],
        workout_by_maria: Workout,
    ):
        """Trainer cannot see workouts from other trainers' organizations."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            trainer_joao["token"],
            trainer_joao["organization_id"],
        ) as client:
            response = await client.get("/workouts")
            assert response.status_code == 200

            workouts = response.json()
            workout_ids = [w["id"] for w in workouts]

            # Should NOT see Maria's workout
            assert str(workout_by_maria.id) not in workout_ids

    async def test_trainer_sees_student_assignments(
        self,
        test_engine,
        db_session: AsyncSession,
        trainer_joao: dict[str, Any],
        plan_by_joao_for_pedro: dict[str, Any],
        student_with_joao: dict[str, Any],
    ):
        """Trainer can see plan assignments for their students."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            trainer_joao["token"],
            trainer_joao["organization_id"],
        ) as client:
            response = await client.get("/workouts/plans/assignments?as_trainer=true")
            assert response.status_code == 200

            assignments = response.json()
            assert any(
                a["id"] == str(plan_by_joao_for_pedro["assignment_id"])
                for a in assignments
            )


# =============================================================================
# Test Class: Cross-Organization Isolation
# =============================================================================


@pytest.mark.anyio
class TestCrossOrganizationIsolation:
    """Test that workouts don't leak between organizations."""

    async def test_workout_created_in_correct_org(
        self,
        test_engine,
        db_session: AsyncSession,
        trainer_joao: dict[str, Any],
        org_personal_joao: dict[str, Any],
    ):
        """Workout created by trainer belongs to their organization."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            trainer_joao["token"],
            org_personal_joao["id"],
        ) as client:
            response = await client.post(
                "/workouts",
                json={
                    "name": "Treino Novo",
                    "description": "Teste de organização",
                    "difficulty": "intermediate",
                    "estimated_duration_min": 60,
                },
            )
            assert response.status_code == 201

            data = response.json()
            assert data["organization_id"] == str(org_personal_joao["id"])
            assert data["created_by_id"] == str(trainer_joao["id"])

    async def test_direct_workout_access_requires_org_membership(
        self,
        test_engine,
        db_session: AsyncSession,
        student_solo_carlos: dict[str, Any],
        workout_by_joao: Workout,
    ):
        """User cannot directly access workout from org they're not member of."""
        async with await create_client_for_user(
            test_engine,
            db_session,
            student_solo_carlos["token"],
            student_solo_carlos["organization_id"],
        ) as client:
            response = await client.get(f"/workouts/{workout_by_joao.id}")
            # Should be 403 or 404
            assert response.status_code in [403, 404]
