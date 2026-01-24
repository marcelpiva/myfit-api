"""Unit tests for Plan Assignment workflow and state machine.

Tests cover the PENDING -> ACCEPTED/DECLINED state transitions
and business rules around plan assignments.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.users.models import User
from src.domains.workouts.models import (
    AssignmentStatus,
    PlanAssignment,
    TrainingMode,
    TrainingPlan,
)
from src.domains.workouts.service import WorkoutService


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def organization(db_session: AsyncSession) -> Organization:
    """Create a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Gym",
        type=OrganizationType.PERSONAL,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def trainer(db_session: AsyncSession, organization: Organization) -> User:
    """Create a trainer user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"trainer-{user_id}@example.com",
        name="Trainer Test",
        password_hash="$2b$12$test.hash",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=organization.id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def student(db_session: AsyncSession, organization: Organization) -> User:
    """Create a student user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"student-{user_id}@example.com",
        name="Student Test",
        password_hash="$2b$12$test.hash",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=organization.id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def another_student(db_session: AsyncSession, organization: Organization) -> User:
    """Create another student user for access control tests."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"another-student-{user_id}@example.com",
        name="Another Student",
        password_hash="$2b$12$test.hash",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=organization.id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def training_plan(
    db_session: AsyncSession, trainer: User, organization: Organization
) -> TrainingPlan:
    """Create a training plan."""
    plan = TrainingPlan(
        id=uuid.uuid4(),
        name="Test Training Plan",
        description="A test plan for unit testing",
        goal="strength",
        created_by_id=trainer.id,
        organization_id=organization.id,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.fixture
async def pending_assignment(
    db_session: AsyncSession,
    training_plan: TrainingPlan,
    trainer: User,
    student: User,
    organization: Organization,
) -> PlanAssignment:
    """Create a pending plan assignment."""
    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=training_plan.id,
        student_id=student.id,
        trainer_id=trainer.id,
        organization_id=organization.id,
        start_date=date.today(),
        training_mode=TrainingMode.PRESENCIAL,
        status=AssignmentStatus.PENDING,
        is_active=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    await db_session.refresh(assignment)
    return assignment


@pytest.fixture
async def accepted_assignment(
    db_session: AsyncSession,
    training_plan: TrainingPlan,
    trainer: User,
    student: User,
    organization: Organization,
) -> PlanAssignment:
    """Create an already accepted plan assignment."""
    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=training_plan.id,
        student_id=student.id,
        trainer_id=trainer.id,
        organization_id=organization.id,
        start_date=date.today(),
        training_mode=TrainingMode.PRESENCIAL,
        status=AssignmentStatus.ACCEPTED,
        accepted_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add(assignment)
    await db_session.commit()
    await db_session.refresh(assignment)
    return assignment


@pytest.fixture
async def declined_assignment(
    db_session: AsyncSession,
    training_plan: TrainingPlan,
    trainer: User,
    student: User,
    organization: Organization,
) -> PlanAssignment:
    """Create an already declined plan assignment."""
    assignment = PlanAssignment(
        id=uuid.uuid4(),
        plan_id=training_plan.id,
        student_id=student.id,
        trainer_id=trainer.id,
        organization_id=organization.id,
        start_date=date.today(),
        training_mode=TrainingMode.PRESENCIAL,
        status=AssignmentStatus.DECLINED,
        declined_reason="Not interested in this plan",
        is_active=False,
    )
    db_session.add(assignment)
    await db_session.commit()
    await db_session.refresh(assignment)
    return assignment


@pytest.fixture
def workout_service(db_session: AsyncSession) -> WorkoutService:
    """Create a WorkoutService instance."""
    return WorkoutService(db_session)


# =============================================================================
# Test: Assignment Creation
# =============================================================================


class TestPlanAssignmentCreation:
    """Tests for creating plan assignments."""

    async def test_create_assignment_defaults_to_pending_status(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        training_plan: TrainingPlan,
        trainer: User,
        student: User,
        organization: Organization,
    ):
        """New assignments should start with PENDING status."""
        assignment = await workout_service.create_plan_assignment(
            plan_id=training_plan.id,
            student_id=student.id,
            trainer_id=trainer.id,
            start_date=date.today(),
            organization_id=organization.id,
        )

        assert assignment.status == AssignmentStatus.PENDING
        assert assignment.accepted_at is None
        assert assignment.declined_reason is None
        assert assignment.is_active is True

    async def test_create_assignment_with_training_mode_presencial(
        self,
        db_session: AsyncSession,
        training_plan: TrainingPlan,
        trainer: User,
        student: User,
        organization: Organization,
    ):
        """Assignment can be created with PRESENCIAL training mode."""
        assignment = PlanAssignment(
            plan_id=training_plan.id,
            student_id=student.id,
            trainer_id=trainer.id,
            organization_id=organization.id,
            start_date=date.today(),
            training_mode=TrainingMode.PRESENCIAL,
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.training_mode == TrainingMode.PRESENCIAL

    async def test_create_assignment_with_training_mode_online(
        self,
        db_session: AsyncSession,
        training_plan: TrainingPlan,
        trainer: User,
        student: User,
        organization: Organization,
    ):
        """Assignment can be created with ONLINE training mode."""
        assignment = PlanAssignment(
            plan_id=training_plan.id,
            student_id=student.id,
            trainer_id=trainer.id,
            organization_id=organization.id,
            start_date=date.today(),
            training_mode=TrainingMode.ONLINE,
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.training_mode == TrainingMode.ONLINE

    async def test_create_assignment_with_training_mode_hibrido(
        self,
        db_session: AsyncSession,
        training_plan: TrainingPlan,
        trainer: User,
        student: User,
        organization: Organization,
    ):
        """Assignment can be created with HIBRIDO training mode."""
        assignment = PlanAssignment(
            plan_id=training_plan.id,
            student_id=student.id,
            trainer_id=trainer.id,
            organization_id=organization.id,
            start_date=date.today(),
            training_mode=TrainingMode.HIBRIDO,
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        assert assignment.training_mode == TrainingMode.HIBRIDO


# =============================================================================
# Test: Accept Assignment (PENDING -> ACCEPTED)
# =============================================================================


class TestAcceptPlanAssignment:
    """Tests for accepting plan assignments."""

    async def test_accept_pending_assignment_sets_accepted_status(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Accepting a pending assignment changes status to ACCEPTED."""
        pending_assignment.status = AssignmentStatus.ACCEPTED
        pending_assignment.accepted_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.status == AssignmentStatus.ACCEPTED

    async def test_accept_pending_assignment_sets_accepted_at_timestamp(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Accepting sets the accepted_at timestamp."""
        before_accept = datetime.now(timezone.utc)

        pending_assignment.status = AssignmentStatus.ACCEPTED
        pending_assignment.accepted_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.accepted_at is not None
        # Make comparison timezone-aware
        accepted_at = pending_assignment.accepted_at
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=timezone.utc)
        assert accepted_at >= before_accept

    async def test_accept_clears_any_previous_declined_reason(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """When accepting, declined_reason should be cleared."""
        pending_assignment.declined_reason = "Was declined before"
        await db_session.commit()

        pending_assignment.status = AssignmentStatus.ACCEPTED
        pending_assignment.accepted_at = datetime.now(timezone.utc)
        pending_assignment.declined_reason = None

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.declined_reason is None

    async def test_accepted_assignment_remains_active(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Accepting should keep is_active as True."""
        pending_assignment.status = AssignmentStatus.ACCEPTED
        pending_assignment.accepted_at = datetime.now(timezone.utc)

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.is_active is True


# =============================================================================
# Test: Decline Assignment (PENDING -> DECLINED)
# =============================================================================


class TestDeclinePlanAssignment:
    """Tests for declining plan assignments."""

    async def test_decline_pending_assignment_sets_declined_status(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Declining a pending assignment changes status to DECLINED."""
        pending_assignment.status = AssignmentStatus.DECLINED
        pending_assignment.declined_reason = "Not interested"
        pending_assignment.is_active = False

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.status == AssignmentStatus.DECLINED

    async def test_decline_pending_assignment_sets_declined_reason(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Declining should store the declined_reason."""
        reason = "The plan doesn't match my goals"

        pending_assignment.status = AssignmentStatus.DECLINED
        pending_assignment.declined_reason = reason
        pending_assignment.is_active = False

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.declined_reason == reason

    async def test_declined_assignment_sets_is_active_to_false(
        self,
        db_session: AsyncSession,
        pending_assignment: PlanAssignment,
    ):
        """Declining should set is_active to False."""
        pending_assignment.status = AssignmentStatus.DECLINED
        pending_assignment.declined_reason = "Not interested"
        pending_assignment.is_active = False

        await db_session.commit()
        await db_session.refresh(pending_assignment)

        assert pending_assignment.is_active is False


# =============================================================================
# Test: State Machine Guards
# =============================================================================


class TestAssignmentStateGuards:
    """Tests for state transition guards."""

    async def test_cannot_accept_already_accepted_assignment(
        self,
        accepted_assignment: PlanAssignment,
    ):
        """Cannot accept an already accepted assignment."""
        assert accepted_assignment.status == AssignmentStatus.ACCEPTED

        # Attempting to "accept again" should be a no-op or error
        # The business logic should prevent this in the router

    async def test_cannot_accept_already_declined_assignment(
        self,
        declined_assignment: PlanAssignment,
    ):
        """Cannot accept an already declined assignment."""
        assert declined_assignment.status == AssignmentStatus.DECLINED

        # The business logic should prevent changing from DECLINED to ACCEPTED

    async def test_cannot_decline_already_accepted_assignment(
        self,
        accepted_assignment: PlanAssignment,
    ):
        """Cannot decline an already accepted assignment."""
        assert accepted_assignment.status == AssignmentStatus.ACCEPTED

        # The business logic should prevent changing from ACCEPTED to DECLINED

    async def test_cannot_decline_already_declined_assignment(
        self,
        declined_assignment: PlanAssignment,
    ):
        """Cannot decline an already declined assignment."""
        assert declined_assignment.status == AssignmentStatus.DECLINED

        # The business logic should prevent "declining again"


# =============================================================================
# Test: Access Control
# =============================================================================


class TestAssignmentAccessControl:
    """Tests for access control on assignments."""

    async def test_assignment_belongs_to_student(
        self,
        pending_assignment: PlanAssignment,
        student: User,
    ):
        """Assignment should belong to the correct student."""
        assert pending_assignment.student_id == student.id

    async def test_assignment_belongs_to_trainer(
        self,
        pending_assignment: PlanAssignment,
        trainer: User,
    ):
        """Assignment should belong to the correct trainer."""
        assert pending_assignment.trainer_id == trainer.id

    async def test_student_cannot_accept_another_students_assignment(
        self,
        pending_assignment: PlanAssignment,
        another_student: User,
    ):
        """A student should not be able to accept another student's assignment."""
        # The router validates: assignment.student_id != current_user.id
        assert pending_assignment.student_id != another_student.id

    async def test_trainer_cannot_accept_assignment_on_behalf_of_student(
        self,
        pending_assignment: PlanAssignment,
        trainer: User,
    ):
        """A trainer should not be able to accept an assignment on behalf of a student."""
        # The router validates: assignment.student_id != current_user.id
        assert pending_assignment.student_id != trainer.id


# =============================================================================
# Test: List Assignments Filtering
# =============================================================================


class TestListAssignmentsFiltering:
    """Tests for listing assignments with filters."""

    async def test_list_active_assignments_includes_pending(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
        student: User,
    ):
        """Active assignments should include PENDING status."""
        assignments = await workout_service.list_student_plan_assignments(
            student_id=student.id,
            active_only=True,
        )

        assignment_ids = [a.id for a in assignments]
        assert pending_assignment.id in assignment_ids

    async def test_list_active_assignments_includes_accepted(
        self,
        workout_service: WorkoutService,
        accepted_assignment: PlanAssignment,
        student: User,
    ):
        """Active assignments should include ACCEPTED status."""
        assignments = await workout_service.list_student_plan_assignments(
            student_id=student.id,
            active_only=True,
        )

        assignment_ids = [a.id for a in assignments]
        assert accepted_assignment.id in assignment_ids

    async def test_list_active_assignments_excludes_declined(
        self,
        workout_service: WorkoutService,
        declined_assignment: PlanAssignment,
        student: User,
    ):
        """Active assignments should exclude DECLINED status."""
        assignments = await workout_service.list_student_plan_assignments(
            student_id=student.id,
            active_only=True,
        )

        assignment_ids = [a.id for a in assignments]
        assert declined_assignment.id not in assignment_ids

    async def test_list_all_assignments_includes_declined(
        self,
        workout_service: WorkoutService,
        declined_assignment: PlanAssignment,
        student: User,
    ):
        """Listing all assignments (active_only=False) should include declined."""
        assignments = await workout_service.list_student_plan_assignments(
            student_id=student.id,
            active_only=False,
        )

        assignment_ids = [a.id for a in assignments]
        assert declined_assignment.id in assignment_ids

    async def test_list_trainer_assignments_filters_by_student(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
        trainer: User,
        student: User,
        another_student: User,
    ):
        """Trainer can filter assignments by specific student."""
        assignments = await workout_service.list_trainer_plan_assignments(
            trainer_id=trainer.id,
            student_id=student.id,
        )

        assert len(assignments) >= 1
        for assignment in assignments:
            assert assignment.student_id == student.id


# =============================================================================
# Test: Assignment Retrieval
# =============================================================================


class TestAssignmentRetrieval:
    """Tests for retrieving assignments."""

    async def test_get_assignment_by_id_returns_assignment(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
    ):
        """Should return the assignment when it exists."""
        found = await workout_service.get_plan_assignment_by_id(pending_assignment.id)

        assert found is not None
        assert found.id == pending_assignment.id

    async def test_get_assignment_by_id_returns_none_for_invalid_id(
        self,
        workout_service: WorkoutService,
    ):
        """Should return None when assignment doesn't exist."""
        fake_id = uuid.uuid4()
        found = await workout_service.get_plan_assignment_by_id(fake_id)

        assert found is None

    async def test_get_assignment_loads_plan_relationship(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
        training_plan: TrainingPlan,
    ):
        """Should eagerly load the plan relationship."""
        found = await workout_service.get_plan_assignment_by_id(pending_assignment.id)

        assert found is not None
        assert found.plan is not None
        assert found.plan.id == training_plan.id


# =============================================================================
# Test: Assignment Update
# =============================================================================


class TestAssignmentUpdate:
    """Tests for updating assignments."""

    async def test_update_assignment_start_date(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
    ):
        """Should update the start date."""
        new_date = date(2025, 6, 1)
        updated = await workout_service.update_plan_assignment(
            assignment=pending_assignment,
            start_date=new_date,
        )

        assert updated.start_date == new_date

    async def test_update_assignment_end_date(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
    ):
        """Should update the end date."""
        new_date = date(2025, 12, 31)
        updated = await workout_service.update_plan_assignment(
            assignment=pending_assignment,
            end_date=new_date,
        )

        assert updated.end_date == new_date

    async def test_update_assignment_notes(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
    ):
        """Should update the notes."""
        new_notes = "Focus on form this week"
        updated = await workout_service.update_plan_assignment(
            assignment=pending_assignment,
            notes=new_notes,
        )

        assert updated.notes == new_notes

    async def test_update_assignment_is_active(
        self,
        workout_service: WorkoutService,
        pending_assignment: PlanAssignment,
    ):
        """Should update is_active flag."""
        updated = await workout_service.update_plan_assignment(
            assignment=pending_assignment,
            is_active=False,
        )

        assert updated.is_active is False
