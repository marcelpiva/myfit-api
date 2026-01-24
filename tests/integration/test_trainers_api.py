"""Integration tests for trainers API endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
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
from src.domains.workouts.models import Workout, WorkoutSession, SessionStatus, Difficulty


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def student_membership(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> OrganizationMembership:
    """Create a student membership in the trainer's organization."""
    # Create a student user
    student_user = User(
        id=uuid.uuid4(),
        email=f"student-{uuid.uuid4()}@example.com",
        name="Test Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(student_user)
    await db_session.flush()

    # Create student membership in the trainer's organization
    membership = OrganizationMembership(
        user_id=student_user.id,
        organization_id=sample_user["organization_id"],
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(membership)
    return membership


@pytest.fixture
async def inactive_student_membership(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> OrganizationMembership:
    """Create an inactive student membership."""
    student_user = User(
        id=uuid.uuid4(),
        email=f"inactive-student-{uuid.uuid4()}@example.com",
        name="Inactive Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(student_user)
    await db_session.flush()

    membership = OrganizationMembership(
        user_id=student_user.id,
        organization_id=sample_user["organization_id"],
        role=UserRole.STUDENT,
        is_active=False,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(membership)
    return membership


@pytest.fixture
async def sample_workout_for_sessions(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Workout:
    """Create a workout for sessions."""
    workout = Workout(
        name="Test Workout",
        difficulty=Difficulty.INTERMEDIATE,
        is_template=False,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(workout)
    await db_session.commit()
    await db_session.refresh(workout)
    return workout


@pytest.fixture
async def student_with_workouts(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    student_membership: OrganizationMembership,
    sample_workout_for_sessions: Workout,
) -> OrganizationMembership:
    """Create a student with workout sessions."""
    # Create some workout sessions for the student
    for i in range(3):
        session = WorkoutSession(
            user_id=student_membership.user_id,
            workout_id=sample_workout_for_sessions.id,
            status=SessionStatus.COMPLETED,
            started_at=datetime.now(timezone.utc) - timedelta(days=i),
            completed_at=datetime.now(timezone.utc) - timedelta(days=i, hours=-1),
            duration_minutes=45 + i * 5,
        )
        db_session.add(session)

    await db_session.commit()
    await db_session.refresh(student_membership)
    return student_membership


@pytest.fixture
async def pending_invite(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> OrganizationInvite:
    """Create a pending student invite."""
    invite = OrganizationInvite(
        organization_id=sample_user["organization_id"],
        email="pending-student@example.com",
        role=UserRole.STUDENT,
        token=f"test-token-{uuid.uuid4()}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        invited_by_id=sample_user["id"],
    )
    db_session.add(invite)
    await db_session.commit()
    await db_session.refresh(invite)
    return invite


@pytest.fixture
async def expired_invite(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> OrganizationInvite:
    """Create an expired invite."""
    invite = OrganizationInvite(
        organization_id=sample_user["organization_id"],
        email="expired-invite@example.com",
        role=UserRole.STUDENT,
        token=f"expired-token-{uuid.uuid4()}",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        invited_by_id=sample_user["id"],
    )
    db_session.add(invite)
    await db_session.commit()
    await db_session.refresh(invite)
    return invite


@pytest.fixture
async def student_note(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    student_membership: OrganizationMembership,
) -> StudentNote:
    """Create a progress note for a student."""
    note = StudentNote(
        student_id=student_membership.user_id,
        trainer_id=sample_user["id"],
        organization_id=sample_user["organization_id"],
        content="Student is progressing well with bench press.",
        category="progress",
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


# =============================================================================
# List Students Tests
# =============================================================================


class TestListStudents:
    """Tests for GET /api/v1/trainers/students."""

    async def test_list_students_authenticated(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Authenticated trainer can list their students."""
        response = await authenticated_client.get("/api/v1/trainers/students")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify student data structure
        student = data[0]
        assert "id" in student
        assert "user_id" in student
        assert "name" in student
        assert "email" in student
        assert "is_active" in student
        assert "workouts_count" in student

    async def test_list_students_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/trainers/students")

        assert response.status_code == 401

    async def test_list_students_empty(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns empty list when no students exist."""
        response = await authenticated_client.get("/api/v1/trainers/students")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_students_filter_active(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
        inactive_student_membership: OrganizationMembership,
    ):
        """Can filter students by active status."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students", params={"status": "active"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(student["is_active"] for student in data)

    async def test_list_students_filter_inactive(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
        inactive_student_membership: OrganizationMembership,
    ):
        """Can filter students by inactive status."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students", params={"status": "inactive"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(not student["is_active"] for student in data)

    async def test_list_students_search_by_name(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Can search students by name."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students", params={"q": "Test Student"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_list_students_pagination(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students", params={"limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1


# =============================================================================
# Get Student Tests
# =============================================================================


class TestGetStudent:
    """Tests for GET /api/v1/trainers/students/{student_id}."""

    async def test_get_student_success(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Trainer can get their own student by membership ID."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_membership.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(student_membership.id)
        assert data["user_id"] == str(student_membership.user_id)
        assert "name" in data
        assert "email" in data
        assert "workouts_count" in data

    async def test_get_student_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{fake_id}"
        )

        assert response.status_code == 404

    async def test_get_student_different_org(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Returns 404 for student in different organization."""
        # Create a different organization
        other_org = Organization(
            name="Other Gym",
            type=OrganizationType.GYM,
        )
        db_session.add(other_org)
        await db_session.flush()

        # Create student in different org
        other_student = User(
            id=uuid.uuid4(),
            email="other-student@example.com",
            name="Other Student",
            password_hash="$2b$12$test.hash.password",
            is_active=True,
        )
        db_session.add(other_student)
        await db_session.flush()

        other_membership = OrganizationMembership(
            user_id=other_student.id,
            organization_id=other_org.id,
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(other_membership)
        await db_session.commit()

        # Try to access student from different org
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{other_membership.id}"
        )

        assert response.status_code == 404


# =============================================================================
# Get Student Stats Tests
# =============================================================================


class TestGetStudentStats:
    """Tests for GET /api/v1/trainers/students/{student_id}/stats."""

    async def test_get_student_stats_success(
        self,
        authenticated_client: AsyncClient,
        student_with_workouts: OrganizationMembership,
    ):
        """Trainer can get student statistics."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_with_workouts.id}/stats"
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_workouts" in data
        assert "workouts_this_week" in data
        assert "workouts_this_month" in data
        assert "average_duration_minutes" in data
        assert "streak_days" in data
        assert data["total_workouts"] >= 3

    async def test_get_student_stats_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{fake_id}/stats"
        )

        assert response.status_code == 404

    async def test_get_student_stats_custom_days(
        self,
        authenticated_client: AsyncClient,
        student_with_workouts: OrganizationMembership,
    ):
        """Can specify custom days parameter."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_with_workouts.id}/stats",
            params={"days": 7},
        )

        assert response.status_code == 200


# =============================================================================
# Get Student Progress Tests
# =============================================================================


class TestGetStudentProgress:
    """Tests for GET /api/v1/trainers/students/{student_id}/progress."""

    async def test_get_student_progress_success(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Trainer can get student progress summary."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_membership.id}/progress"
        )

        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data
        assert "total_sessions" in data
        assert "streak_days" in data
        assert "notes" in data
        assert isinstance(data["notes"], list)

    async def test_get_student_progress_with_notes(
        self,
        authenticated_client: AsyncClient,
        student_note: StudentNote,
        student_membership: OrganizationMembership,
    ):
        """Progress includes trainer notes."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_membership.id}/progress"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["notes"]) >= 1
        note = data["notes"][0]
        assert "content" in note
        assert "category" in note

    async def test_get_student_progress_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{fake_id}/progress"
        )

        assert response.status_code == 404


# =============================================================================
# Progress Notes Tests
# =============================================================================


class TestProgressNotes:
    """Tests for progress notes endpoints."""

    async def test_add_progress_note_success(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Trainer can add a progress note."""
        payload = {
            "content": "Great improvement on squats today!",
            "category": "progress",
        }

        response = await authenticated_client.post(
            f"/api/v1/trainers/students/{student_membership.id}/progress/notes",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == payload["content"]
        assert data["category"] == payload["category"]
        assert "id" in data
        assert "created_at" in data

    async def test_add_progress_note_minimal(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Can add note without category."""
        payload = {"content": "Quick note about form."}

        response = await authenticated_client.post(
            f"/api/v1/trainers/students/{student_membership.id}/progress/notes",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == payload["content"]
        assert data["category"] is None

    async def test_list_progress_notes(
        self,
        authenticated_client: AsyncClient,
        student_note: StudentNote,
        student_membership: OrganizationMembership,
    ):
        """Trainer can list progress notes for a student."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_membership.id}/progress/notes"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_add_note_student_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        payload = {"content": "Note for nonexistent student."}

        response = await authenticated_client.post(
            f"/api/v1/trainers/students/{fake_id}/progress/notes",
            json=payload,
        )

        assert response.status_code == 404


# =============================================================================
# Student Workouts Tests
# =============================================================================


class TestStudentWorkouts:
    """Tests for GET /api/v1/trainers/students/{student_id}/workouts."""

    async def test_get_student_workouts_success(
        self,
        authenticated_client: AsyncClient,
        student_with_workouts: OrganizationMembership,
    ):
        """Trainer can list student's workout sessions."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_with_workouts.id}/workouts"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3
        # Verify workout session structure
        session = data[0]
        assert "id" in session
        assert "started_at" in session
        assert "status" in session

    async def test_get_student_workouts_empty(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Returns empty list for student with no workouts."""
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{student_membership.id}/workouts"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_student_workouts_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/trainers/students/{fake_id}/workouts"
        )

        assert response.status_code == 404


# =============================================================================
# Pending Invites Tests
# =============================================================================


class TestListPendingInvites:
    """Tests for GET /api/v1/trainers/students/pending-invites."""

    @pytest.mark.xfail(
        reason="SQLite stores naive datetimes, is_expired property compares with "
        "timezone-aware datetime causing TypeError. Works in PostgreSQL."
    )
    async def test_list_pending_invites_success(
        self,
        authenticated_client: AsyncClient,
        pending_invite: OrganizationInvite,
    ):
        """Trainer can list pending student invites."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students/pending-invites"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify invite structure
        invite = data[0]
        assert "id" in invite
        assert "email" in invite
        assert "role" in invite
        assert invite["role"] == "student"

    @pytest.mark.xfail(
        reason="SQLite stores naive datetimes, is_expired property compares with "
        "timezone-aware datetime causing TypeError. Works in PostgreSQL."
    )
    async def test_list_pending_invites_excludes_expired(
        self,
        authenticated_client: AsyncClient,
        expired_invite: OrganizationInvite,
    ):
        """Expired invites are not included."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students/pending-invites"
        )

        assert response.status_code == 200
        data = response.json()
        # Expired invite should not appear
        expired_emails = [inv["email"] for inv in data]
        assert expired_invite.email not in expired_emails

    async def test_list_pending_invites_empty(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns empty list when no pending invites."""
        response = await authenticated_client.get(
            "/api/v1/trainers/students/pending-invites"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# Register Student (Send Invite) Tests
# =============================================================================


class TestRegisterStudent:
    """Tests for POST /api/v1/trainers/students/register."""

    @pytest.mark.xfail(
        reason="SQLite stores naive datetimes, is_expired property compares with "
        "timezone-aware datetime causing TypeError. Works in PostgreSQL."
    )
    async def test_register_student_success(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Trainer can invite a new student."""
        payload = {
            "name": "New Student",
            "email": f"new-student-{uuid.uuid4()}@example.com",
            "phone": "+5511999999999",
            "goal": "Build muscle",
            "notes": "Beginner level",
        }

        response = await authenticated_client.post(
            "/api/v1/trainers/students/register",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == payload["email"]
        assert data["role"] == "student"
        assert "token" in data

    @pytest.mark.xfail(
        reason="SQLite stores naive datetimes, is_expired property compares with "
        "timezone-aware datetime causing TypeError. Works in PostgreSQL."
    )
    async def test_register_student_minimal(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can register student with only required fields."""
        payload = {
            "name": "Minimal Student",
            "email": f"minimal-{uuid.uuid4()}@example.com",
        }

        response = await authenticated_client.post(
            "/api/v1/trainers/students/register",
            json=payload,
        )

        assert response.status_code == 201

    @pytest.mark.xfail(
        reason="SQLite stores naive datetimes, is_expired property compares with "
        "timezone-aware datetime causing TypeError. Works in PostgreSQL."
    )
    async def test_register_student_duplicate_invite(
        self,
        authenticated_client: AsyncClient,
        pending_invite: OrganizationInvite,
    ):
        """Returns 409 for duplicate pending invite."""
        payload = {
            "name": "Duplicate Student",
            "email": pending_invite.email,
        }

        response = await authenticated_client.post(
            "/api/v1/trainers/students/register",
            json=payload,
        )

        assert response.status_code == 409


# =============================================================================
# Invite Code Tests
# =============================================================================


class TestInviteCode:
    """Tests for invite code endpoints."""

    async def test_get_invite_code_success(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Trainer can get their invite code."""
        response = await authenticated_client.get("/api/v1/trainers/my-invite-code")

        assert response.status_code == 200
        data = response.json()
        assert "code" in data
        assert "url" in data
        assert data["code"].startswith("MYFIT-")

    async def test_regenerate_invite_code(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Trainer can regenerate their invite code."""
        response = await authenticated_client.post("/api/v1/trainers/my-invite-code")

        assert response.status_code == 201
        data = response.json()
        assert "code" in data
        assert "url" in data
        assert "expires_at" in data

    async def test_send_invite_email(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Trainer can send invite email."""
        payload = {"email": f"invite-email-{uuid.uuid4()}@example.com"}

        response = await authenticated_client.post(
            "/api/v1/trainers/my-invite-code/send",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "invite_id" in data


# =============================================================================
# Update Student Status Tests
# =============================================================================


class TestUpdateStudentStatus:
    """Tests for PATCH /api/v1/trainers/students/{student_user_id}/status."""

    async def test_deactivate_student(
        self,
        authenticated_client: AsyncClient,
        student_membership: OrganizationMembership,
    ):
        """Trainer can deactivate a student."""
        response = await authenticated_client.patch(
            f"/api/v1/trainers/students/{student_membership.user_id}/status",
            params={"is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_activate_student(
        self,
        authenticated_client: AsyncClient,
        inactive_student_membership: OrganizationMembership,
    ):
        """Trainer can activate an inactive student."""
        response = await authenticated_client.patch(
            f"/api/v1/trainers/students/{inactive_student_membership.user_id}/status",
            params={"is_active": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    async def test_update_status_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent student."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.patch(
            f"/api/v1/trainers/students/{fake_id}/status",
            params={"is_active": False},
        )

        assert response.status_code == 404
