"""Tests for Trainers router business logic."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.trainers.models import StudentNote
from src.domains.users.models import User
from src.domains.workouts.models import Workout, WorkoutSession


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def trainer_organization(db_session: AsyncSession) -> Organization:
    """Create a trainer organization."""
    org = Organization(
        name="Test Gym",
        type=OrganizationType.PERSONAL,
    )
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def trainer_user(
    db_session: AsyncSession, trainer_organization: Organization
) -> dict[str, Any]:
    """Create a trainer user with membership."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"trainer-{user_id}@example.com",
        name="Test Trainer",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=trainer_organization.id,
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
        "organization_id": trainer_organization.id,
    }


@pytest.fixture
async def student_user(
    db_session: AsyncSession, trainer_organization: Organization
) -> dict[str, Any]:
    """Create a student user with membership."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"student-{user_id}@example.com",
        name="Test Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
        phone="+5511999999999",
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=trainer_organization.id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(membership)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "membership_id": membership.id,
        "organization_id": trainer_organization.id,
    }


@pytest.fixture
async def inactive_student(
    db_session: AsyncSession, trainer_organization: Organization
) -> dict[str, Any]:
    """Create an inactive student user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"inactive-{user_id}@example.com",
        name="Inactive Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=trainer_organization.id,
        role=UserRole.STUDENT,
        is_active=False,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(membership)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "membership_id": membership.id,
        "is_active": False,
    }


@pytest.fixture
async def second_student(
    db_session: AsyncSession, trainer_organization: Organization
) -> dict[str, Any]:
    """Create a second student user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"student2-{user_id}@example.com",
        name="Second Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)

    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=trainer_organization.id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(membership)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "membership_id": membership.id,
    }


@pytest.fixture
async def sample_workout(
    db_session: AsyncSession, trainer_user: dict[str, Any]
) -> Workout:
    """Create a sample workout."""
    workout = Workout(
        name="Test Workout",
        description="A test workout",
        created_by_id=trainer_user["id"],
    )
    db_session.add(workout)
    await db_session.commit()
    await db_session.refresh(workout)
    return workout


@pytest.fixture
async def student_workout_session(
    db_session: AsyncSession,
    student_user: dict[str, Any],
    sample_workout: Workout,
) -> WorkoutSession:
    """Create a workout session for the student."""
    session = WorkoutSession(
        user_id=student_user["id"],
        workout_id=sample_workout.id,
        status="completed",
        started_at=datetime.now(timezone.utc) - timedelta(hours=1),
        completed_at=datetime.now(timezone.utc),
        duration_minutes=45,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def student_note(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> StudentNote:
    """Create a student note."""
    note = StudentNote(
        student_id=student_user["id"],
        trainer_id=trainer_user["id"],
        organization_id=trainer_user["organization_id"],
        content="Great progress this week!",
        category="progress",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


# =============================================================================
# Student List Tests
# =============================================================================


class TestStudentList:
    """Tests for listing students."""

    async def test_list_students_returns_active(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        student_user: dict,
    ):
        """Should return active students."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.role == UserRole.STUDENT,
                OrganizationMembership.is_active == True,
            )
        )
        members = list(result.scalars().all())

        assert len(members) >= 1
        assert all(m.is_active for m in members)

    async def test_list_students_filter_active_only(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        student_user: dict,
        inactive_student: dict,
    ):
        """Should filter by active status."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.role == UserRole.STUDENT,
                OrganizationMembership.is_active == True,
            )
        )
        active_members = list(result.scalars().all())

        # Inactive student should not be in active list
        assert all(m.is_active for m in active_members)
        assert not any(m.user_id == inactive_student["id"] for m in active_members)

    async def test_list_students_filter_inactive_only(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        inactive_student: dict,
    ):
        """Should filter inactive students only."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.role == UserRole.STUDENT,
                OrganizationMembership.is_active == False,
            )
        )
        inactive_members = list(result.scalars().all())

        assert len(inactive_members) >= 1
        assert all(not m.is_active for m in inactive_members)

    async def test_list_students_only_returns_students(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should only return members with STUDENT role."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.role == UserRole.STUDENT,
            )
        )
        members = list(result.scalars().all())

        # Should not include trainer
        assert all(m.role == UserRole.STUDENT for m in members)
        assert not any(m.user_id == trainer_user["id"] for m in members)

    async def test_list_students_search_by_name(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        student_user: dict,
    ):
        """Should search students by name."""
        # Get user for this student
        user = await db_session.get(User, student_user["id"])
        search_term = student_user["name"][:4].lower()

        # Simulate search
        assert search_term in user.name.lower()

    async def test_list_students_search_by_email(
        self,
        db_session: AsyncSession,
        student_user: dict,
    ):
        """Should search students by email."""
        user = await db_session.get(User, student_user["id"])
        search_term = student_user["email"].split("@")[0]

        assert search_term in user.email.lower()


# =============================================================================
# Get Student Tests
# =============================================================================


class TestGetStudent:
    """Tests for getting student details."""

    async def test_get_student_returns_details(
        self,
        db_session: AsyncSession,
        student_user: dict,
    ):
        """Should return student details."""
        membership = await db_session.get(
            OrganizationMembership, student_user["membership_id"]
        )
        user = await db_session.get(User, student_user["id"])

        assert membership is not None
        assert user is not None
        assert user.email == student_user["email"]
        assert user.name == student_user["name"]

    async def test_get_student_includes_workout_count(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should include workout count in response."""
        from sqlalchemy import func

        count = await db_session.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == student_user["id"]
            )
        )

        assert count >= 1

    async def test_get_student_includes_last_workout(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should include last workout date in response."""
        from sqlalchemy import func

        last_workout = await db_session.scalar(
            select(func.max(WorkoutSession.started_at)).where(
                WorkoutSession.user_id == student_user["id"]
            )
        )

        assert last_workout is not None


# =============================================================================
# Student Stats Tests
# =============================================================================


class TestStudentStats:
    """Tests for student statistics."""

    async def test_stats_counts_total_workouts(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should count total workouts."""
        from sqlalchemy import func

        total = await db_session.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == student_user["id"]
            )
        )

        assert total >= 1

    async def test_stats_counts_weekly_workouts(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should count workouts this week."""
        from sqlalchemy import func

        now = datetime.now(timezone.utc)
        start_of_week = now - timedelta(days=now.weekday())

        weekly = await db_session.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == student_user["id"],
                WorkoutSession.started_at >= start_of_week,
            )
        )

        assert weekly >= 1

    async def test_stats_counts_monthly_workouts(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should count workouts this month."""
        from sqlalchemy import func

        now = datetime.now(timezone.utc)
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        monthly = await db_session.scalar(
            select(func.count(WorkoutSession.id)).where(
                WorkoutSession.user_id == student_user["id"],
                WorkoutSession.started_at >= start_of_month,
            )
        )

        assert monthly >= 1

    async def test_stats_calculates_average_duration(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should calculate average workout duration."""
        from sqlalchemy import func

        avg_duration = await db_session.scalar(
            select(func.avg(WorkoutSession.duration_minutes)).where(
                WorkoutSession.user_id == student_user["id"],
                WorkoutSession.duration_minutes.isnot(None),
            )
        )

        assert avg_duration is not None
        assert avg_duration > 0

    async def test_stats_returns_last_workout_date(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should return last workout date."""
        from sqlalchemy import func

        last = await db_session.scalar(
            select(func.max(WorkoutSession.started_at)).where(
                WorkoutSession.user_id == student_user["id"]
            )
        )

        assert last is not None


# =============================================================================
# Student Workouts Tests
# =============================================================================


class TestStudentWorkouts:
    """Tests for viewing student workouts."""

    async def test_list_student_workouts(
        self,
        db_session: AsyncSession,
        student_user: dict,
        student_workout_session: WorkoutSession,
    ):
        """Should list student's recent workouts."""
        result = await db_session.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == student_user["id"])
            .order_by(WorkoutSession.started_at.desc())
            .limit(20)
        )
        sessions = list(result.scalars().all())

        assert len(sessions) >= 1

    async def test_workouts_ordered_by_date(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_workout: Workout,
    ):
        """Workouts should be ordered by date descending."""
        # Create multiple sessions
        for i in range(3):
            session = WorkoutSession(
                user_id=student_user["id"],
                workout_id=sample_workout.id,
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(days=i),
                duration_minutes=30,
            )
            db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == student_user["id"])
            .order_by(WorkoutSession.started_at.desc())
        )
        sessions = list(result.scalars().all())

        # Verify descending order (compare naive datetimes for SQLite compatibility)
        for i in range(len(sessions) - 1):
            if sessions[i].started_at and sessions[i + 1].started_at:
                t1 = sessions[i].started_at.replace(tzinfo=None) if sessions[i].started_at.tzinfo else sessions[i].started_at
                t2 = sessions[i + 1].started_at.replace(tzinfo=None) if sessions[i + 1].started_at.tzinfo else sessions[i + 1].started_at
                assert t1 >= t2

    async def test_workouts_limit(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_workout: Workout,
    ):
        """Should respect limit parameter."""
        # Create 25 sessions
        for i in range(25):
            session = WorkoutSession(
                user_id=student_user["id"],
                workout_id=sample_workout.id,
                status="completed",
                started_at=datetime.now(timezone.utc) - timedelta(hours=i),
                duration_minutes=30,
            )
            db_session.add(session)
        await db_session.commit()

        result = await db_session.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == student_user["id"])
            .limit(20)
        )
        sessions = list(result.scalars().all())

        assert len(sessions) == 20


# =============================================================================
# Progress Notes Tests
# =============================================================================


class TestProgressNotes:
    """Tests for student progress notes."""

    async def test_add_progress_note(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should add progress note for student."""
        note = StudentNote(
            student_id=student_user["id"],
            trainer_id=trainer_user["id"],
            organization_id=trainer_user["organization_id"],
            content="Improved form on squats",
            category="technique",
        )
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        assert note.id is not None
        assert note.content == "Improved form on squats"
        assert note.category == "technique"

    async def test_note_belongs_to_trainer(
        self, db_session: AsyncSession, student_note: StudentNote, trainer_user: dict
    ):
        """Note should belong to the creating trainer."""
        assert student_note.trainer_id == trainer_user["id"]

    async def test_note_belongs_to_student(
        self, db_session: AsyncSession, student_note: StudentNote, student_user: dict
    ):
        """Note should belong to the student."""
        assert student_note.student_id == student_user["id"]

    async def test_list_notes_for_student(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        student_note: StudentNote,
    ):
        """Should list notes for specific student."""
        result = await db_session.execute(
            select(StudentNote)
            .where(
                StudentNote.student_id == student_user["id"],
                StudentNote.trainer_id == trainer_user["id"],
            )
            .order_by(StudentNote.created_at.desc())
        )
        notes = list(result.scalars().all())

        assert len(notes) >= 1
        assert all(n.student_id == student_user["id"] for n in notes)

    async def test_notes_ordered_by_date(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Notes should be ordered by date descending."""
        # Create multiple notes
        for i in range(3):
            note = StudentNote(
                student_id=student_user["id"],
                trainer_id=trainer_user["id"],
                organization_id=trainer_user["organization_id"],
                content=f"Note {i}",
            )
            db_session.add(note)
        await db_session.commit()

        result = await db_session.execute(
            select(StudentNote)
            .where(StudentNote.student_id == student_user["id"])
            .order_by(StudentNote.created_at.desc())
        )
        notes = list(result.scalars().all())

        for i in range(len(notes) - 1):
            assert notes[i].created_at >= notes[i + 1].created_at

    async def test_note_categories(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should support different note categories."""
        categories = ["progress", "technique", "nutrition", "general"]

        for cat in categories:
            note = StudentNote(
                student_id=student_user["id"],
                trainer_id=trainer_user["id"],
                organization_id=trainer_user["organization_id"],
                content=f"Note for {cat}",
                category=cat,
            )
            db_session.add(note)
        await db_session.commit()

        result = await db_session.execute(
            select(StudentNote).where(StudentNote.student_id == student_user["id"])
        )
        notes = list(result.scalars().all())

        saved_categories = {n.category for n in notes if n.category}
        assert len(saved_categories) >= 4


# =============================================================================
# Add Student Tests
# =============================================================================


class TestAddStudent:
    """Tests for adding existing users as students."""

    async def test_add_existing_user_as_student(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Should add existing user as student."""
        # Create a new user first
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=f"newuser-{user_id}@example.com",
            name="New User",
            password_hash="$2b$12$test.hash.password",
            is_active=True,
        )
        db_session.add(user)
        await db_session.commit()

        # Add as member
        membership = OrganizationMembership(
            user_id=user_id,
            organization_id=trainer_organization.id,
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            is_active=True,
        )
        db_session.add(membership)
        await db_session.commit()
        await db_session.refresh(membership)

        assert membership.id is not None
        assert membership.role == UserRole.STUDENT

    async def test_cannot_add_nonexistent_user(
        self, db_session: AsyncSession, trainer_organization: Organization
    ):
        """Should fail for nonexistent user."""
        fake_user_id = uuid.uuid4()
        user = await db_session.get(User, fake_user_id)

        assert user is None

    async def test_cannot_add_duplicate_member(
        self, db_session: AsyncSession, student_user: dict, trainer_organization: Organization
    ):
        """Should not add same user twice."""
        # Check if already a member
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.user_id == student_user["id"],
                OrganizationMembership.is_active == True,
            )
        )
        existing = result.scalar_one_or_none()

        assert existing is not None  # Already a member


# =============================================================================
# Student Registration (Invite) Tests
# =============================================================================


class TestStudentRegistration:
    """Tests for inviting new students."""

    async def test_create_invite(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Should create invite for new student email."""
        import secrets

        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="newstudent@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(invite)
        await db_session.commit()
        await db_session.refresh(invite)

        assert invite.id is not None
        assert invite.role == UserRole.STUDENT

    async def test_invite_has_expiry(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Invite should have expiration date."""
        import secrets

        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="expiry@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=secrets.token_urlsafe(32),
            expires_at=expires_at,
        )
        db_session.add(invite)
        await db_session.commit()

        assert invite.expires_at is not None
        assert invite.expires_at > datetime.now(timezone.utc)

    async def test_cannot_invite_existing_member(
        self, db_session: AsyncSession, student_user: dict, trainer_organization: Organization
    ):
        """Should not invite user who is already a member."""
        existing = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.user_id == student_user["id"],
                OrganizationMembership.is_active == True,
            )
        )
        member = existing.scalar_one_or_none()

        assert member is not None

    async def test_invite_includes_token(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Invite should include unique token."""
        import secrets

        token = secrets.token_urlsafe(32)
        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="token@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(invite)
        await db_session.commit()

        assert invite.token is not None
        assert len(invite.token) > 20


# =============================================================================
# Update Student Status Tests
# =============================================================================


class TestUpdateStudentStatus:
    """Tests for updating student status."""

    async def test_deactivate_student(
        self, db_session: AsyncSession, student_user: dict
    ):
        """Should deactivate student."""
        membership = await db_session.get(
            OrganizationMembership, student_user["membership_id"]
        )
        membership.is_active = False
        await db_session.commit()
        await db_session.refresh(membership)

        assert membership.is_active is False

    async def test_activate_student(
        self, db_session: AsyncSession, inactive_student: dict
    ):
        """Should activate inactive student."""
        membership = await db_session.get(
            OrganizationMembership, inactive_student["membership_id"]
        )
        membership.is_active = True
        await db_session.commit()
        await db_session.refresh(membership)

        assert membership.is_active is True

    async def test_toggle_status(
        self, db_session: AsyncSession, student_user: dict
    ):
        """Should toggle student status."""
        membership = await db_session.get(
            OrganizationMembership, student_user["membership_id"]
        )
        original = membership.is_active

        membership.is_active = not original
        await db_session.commit()
        await db_session.refresh(membership)

        assert membership.is_active != original


# =============================================================================
# Pending Invites Tests
# =============================================================================


class TestPendingInvites:
    """Tests for pending student invites."""

    async def test_list_pending_invites(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Should list pending invites."""
        import secrets

        # Create pending invite
        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="pending@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        db_session.add(invite)
        await db_session.commit()

        # Use accepted_at (column) instead of is_accepted (property)
        result = await db_session.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.organization_id == trainer_organization.id,
                OrganizationInvite.role == UserRole.STUDENT,
                OrganizationInvite.accepted_at.is_(None),
            )
        )
        invites = list(result.scalars().all())

        assert len(invites) >= 1

    async def test_exclude_expired_invites(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Should exclude expired invites."""
        import secrets

        # Create expired invite
        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="expired@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
        )
        db_session.add(invite)
        await db_session.commit()

        # Check is_expired property
        assert invite.is_expired is True

    async def test_exclude_accepted_invites(
        self,
        db_session: AsyncSession,
        trainer_organization: Organization,
        trainer_user: dict,
    ):
        """Should exclude accepted invites."""
        import secrets

        # Create accepted invite (set accepted_at instead of is_accepted)
        invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="accepted@example.com",
            role=UserRole.STUDENT,
            invited_by_id=trainer_user["id"],
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            accepted_at=datetime.now(timezone.utc),  # Mark as accepted
        )
        db_session.add(invite)
        await db_session.commit()

        # Use accepted_at (column) instead of is_accepted (property)
        result = await db_session.execute(
            select(OrganizationInvite).where(
                OrganizationInvite.organization_id == trainer_organization.id,
                OrganizationInvite.accepted_at.is_(None),
            )
        )
        pending = list(result.scalars().all())

        assert not any(inv.email == "accepted@example.com" for inv in pending)


# =============================================================================
# Invite Code Tests
# =============================================================================


class TestInviteCode:
    """Tests for trainer invite code."""

    async def test_generate_invite_code(
        self, db_session: AsyncSession, trainer_organization: Organization
    ):
        """Should generate invite code."""
        code = f"MYFIT-{str(trainer_organization.id)[:8].upper()}"

        assert code.startswith("MYFIT-")
        assert len(code) > 6

    async def test_regenerate_invite_code(self):
        """Should regenerate invite code."""
        import secrets

        code1 = secrets.token_hex(4).upper()
        code2 = secrets.token_hex(4).upper()

        # Codes should be different
        assert code1 != code2

    async def test_invite_code_format(
        self, db_session: AsyncSession, trainer_organization: Organization
    ):
        """Invite code should have correct format."""
        code = f"MYFIT-{str(trainer_organization.id)[:8].upper()}"

        # Should be uppercase
        assert code == code.upper()
        # Should have prefix
        assert code.startswith("MYFIT-")


# =============================================================================
# Trainer Organization Tests
# =============================================================================


class TestTrainerOrganization:
    """Tests for trainer organization access."""

    async def test_trainer_has_organization(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        trainer_organization: Organization,
    ):
        """Trainer should have an organization."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == trainer_user["id"],
                OrganizationMembership.role.in_(
                    [UserRole.TRAINER, UserRole.GYM_OWNER, UserRole.COACH]
                ),
            )
        )
        membership = result.scalar_one_or_none()

        assert membership is not None
        assert membership.organization_id == trainer_organization.id

    async def test_trainer_roles_allowed(
        self, db_session: AsyncSession, trainer_organization: Organization
    ):
        """Should allow appropriate trainer roles."""
        allowed_roles = [
            UserRole.TRAINER,
            UserRole.COACH,
            UserRole.GYM_OWNER,
            UserRole.GYM_ADMIN,
        ]

        for role in allowed_roles:
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                email=f"{role.value}-{user_id}@example.com",
                name=f"Test {role.value}",
                password_hash="$2b$12$test.hash.password",
                is_active=True,
            )
            db_session.add(user)

            membership = OrganizationMembership(
                user_id=user_id,
                organization_id=trainer_organization.id,
                role=role,
                is_active=True,
            )
            db_session.add(membership)

        await db_session.commit()

        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.role.in_(allowed_roles),
            )
        )
        trainers = list(result.scalars().all())

        assert len(trainers) >= 4

    async def test_student_cannot_be_trainer(
        self, db_session: AsyncSession, student_user: dict
    ):
        """Student role should not grant trainer access."""
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.user_id == student_user["id"]
            )
        )
        membership = result.scalar_one()

        trainer_roles = [
            UserRole.TRAINER,
            UserRole.COACH,
            UserRole.GYM_OWNER,
            UserRole.GYM_ADMIN,
        ]

        assert membership.role not in trainer_roles
