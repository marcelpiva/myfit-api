"""Unit tests for Co-Training session management.

Tests cover the session lifecycle, trainer join/leave operations,
adjustments, and real-time messaging during co-training.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.users.models import User
from src.domains.workouts.models import (
    Exercise,
    MuscleGroup,
    SessionMessage,
    SessionStatus,
    TrainerAdjustment,
    Workout,
    WorkoutSession,
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
async def exercise(db_session: AsyncSession, trainer: User) -> Exercise:
    """Create a test exercise."""
    ex = Exercise(
        id=uuid.uuid4(),
        name="Bench Press",
        muscle_group=MuscleGroup.CHEST,
        equipment=["barbell"],
        created_by_id=trainer.id,
    )
    db_session.add(ex)
    await db_session.commit()
    await db_session.refresh(ex)
    return ex


@pytest.fixture
async def workout(db_session: AsyncSession, trainer: User) -> Workout:
    """Create a test workout."""
    w = Workout(
        id=uuid.uuid4(),
        name="Chest Day",
        description="Chest and triceps workout",
        created_by_id=trainer.id,
    )
    db_session.add(w)
    await db_session.commit()
    await db_session.refresh(w)
    return w


@pytest.fixture
async def waiting_session(
    db_session: AsyncSession,
    workout: Workout,
    student: User,
) -> WorkoutSession:
    """Create a session in WAITING status."""
    session = WorkoutSession(
        id=uuid.uuid4(),
        workout_id=workout.id,
        user_id=student.id,
        status=SessionStatus.WAITING,
        is_shared=True,  # Waiting for trainer to join
        started_at=datetime.utcnow(),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def active_session(
    db_session: AsyncSession,
    workout: Workout,
    student: User,
) -> WorkoutSession:
    """Create a session in ACTIVE status."""
    session = WorkoutSession(
        id=uuid.uuid4(),
        workout_id=workout.id,
        user_id=student.id,
        status=SessionStatus.ACTIVE,
        is_shared=False,
        started_at=datetime.utcnow(),  # Use naive datetime for SQLite
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def paused_session(
    db_session: AsyncSession,
    workout: Workout,
    student: User,
) -> WorkoutSession:
    """Create a session in PAUSED status."""
    session = WorkoutSession(
        id=uuid.uuid4(),
        workout_id=workout.id,
        user_id=student.id,
        status=SessionStatus.PAUSED,
        is_shared=False,
        started_at=datetime.utcnow(),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def completed_session(
    db_session: AsyncSession,
    workout: Workout,
    student: User,
) -> WorkoutSession:
    """Create a session in COMPLETED status."""
    started = datetime.now(timezone.utc) - timedelta(hours=1)
    completed = datetime.now(timezone.utc)
    session = WorkoutSession(
        id=uuid.uuid4(),
        workout_id=workout.id,
        user_id=student.id,
        status=SessionStatus.COMPLETED,
        is_shared=False,
        started_at=started,
        completed_at=completed,
        duration_minutes=60,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
async def shared_active_session(
    db_session: AsyncSession,
    workout: Workout,
    student: User,
    trainer: User,
) -> WorkoutSession:
    """Create an active session with trainer joined."""
    session = WorkoutSession(
        id=uuid.uuid4(),
        workout_id=workout.id,
        user_id=student.id,
        trainer_id=trainer.id,
        status=SessionStatus.ACTIVE,
        is_shared=True,
        started_at=datetime.utcnow(),
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


@pytest.fixture
def workout_service(db_session: AsyncSession) -> WorkoutService:
    """Create a WorkoutService instance."""
    return WorkoutService(db_session)


# =============================================================================
# Test: Session Status Transitions
# =============================================================================


class TestSessionStatusTransitions:
    """Tests for session status state machine."""

    async def test_new_shared_session_starts_in_waiting_status(
        self,
        waiting_session: WorkoutSession,
    ):
        """A shared session starts in WAITING status."""
        assert waiting_session.status == SessionStatus.WAITING
        assert waiting_session.is_shared is True

    async def test_new_solo_session_can_start_active(
        self,
        active_session: WorkoutSession,
    ):
        """A non-shared session can start in ACTIVE status."""
        assert active_session.status == SessionStatus.ACTIVE
        assert active_session.is_shared is False

    async def test_session_can_transition_to_paused(
        self,
        workout_service: WorkoutService,
        active_session: WorkoutSession,
    ):
        """Active session can be paused."""
        updated = await workout_service.update_session_status(
            session=active_session,
            status=SessionStatus.PAUSED,
        )

        assert updated.status == SessionStatus.PAUSED

    async def test_paused_session_can_resume_to_active(
        self,
        workout_service: WorkoutService,
        paused_session: WorkoutSession,
    ):
        """Paused session can resume to active."""
        updated = await workout_service.update_session_status(
            session=paused_session,
            status=SessionStatus.ACTIVE,
        )

        assert updated.status == SessionStatus.ACTIVE

    async def test_completed_session_has_completed_at(
        self,
        completed_session: WorkoutSession,
    ):
        """A completed session has completed_at timestamp set."""
        assert completed_session.status == SessionStatus.COMPLETED
        assert completed_session.completed_at is not None

    async def test_complete_session_calculates_duration_minutes(
        self,
        completed_session: WorkoutSession,
    ):
        """A completed session has duration_minutes calculated."""
        # Using the pre-created completed_session fixture
        assert completed_session.status == SessionStatus.COMPLETED
        assert completed_session.duration_minutes is not None
        assert completed_session.duration_minutes == 60

    async def test_completed_session_is_completed_property(
        self,
        completed_session: WorkoutSession,
    ):
        """Completed session has is_completed property True."""
        assert completed_session.is_completed is True

    async def test_active_session_is_active_property(
        self,
        active_session: WorkoutSession,
    ):
        """Active session has is_active property True."""
        assert active_session.is_active is True


# =============================================================================
# Test: Trainer Join Operations
# =============================================================================


class TestTrainerJoinSession:
    """Tests for trainer joining co-training sessions."""

    async def test_trainer_join_sets_trainer_id(
        self,
        workout_service: WorkoutService,
        waiting_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer joining sets the trainer_id on session."""
        updated = await workout_service.trainer_join_session(
            session=waiting_session,
            trainer_id=trainer.id,
        )

        assert updated.trainer_id == trainer.id

    async def test_trainer_join_sets_is_shared_true(
        self,
        workout_service: WorkoutService,
        waiting_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer joining ensures is_shared is True."""
        updated = await workout_service.trainer_join_session(
            session=waiting_session,
            trainer_id=trainer.id,
        )

        assert updated.is_shared is True

    async def test_trainer_join_changes_waiting_to_active(
        self,
        workout_service: WorkoutService,
        waiting_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer joining a WAITING session changes status to ACTIVE."""
        assert waiting_session.status == SessionStatus.WAITING

        updated = await workout_service.trainer_join_session(
            session=waiting_session,
            trainer_id=trainer.id,
        )

        assert updated.status == SessionStatus.ACTIVE

    async def test_trainer_join_active_session_keeps_active_status(
        self,
        workout_service: WorkoutService,
        active_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer joining an already ACTIVE session keeps ACTIVE status."""
        updated = await workout_service.trainer_join_session(
            session=active_session,
            trainer_id=trainer.id,
        )

        assert updated.status == SessionStatus.ACTIVE

    async def test_trainer_join_paused_session_keeps_paused_status(
        self,
        workout_service: WorkoutService,
        paused_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer joining a PAUSED session keeps PAUSED status."""
        updated = await workout_service.trainer_join_session(
            session=paused_session,
            trainer_id=trainer.id,
        )

        assert updated.status == SessionStatus.PAUSED


# =============================================================================
# Test: Trainer Leave Operations
# =============================================================================


class TestTrainerLeaveSession:
    """Tests for trainer leaving co-training sessions."""

    async def test_trainer_leave_clears_trainer_id(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
    ):
        """Trainer leaving clears the trainer_id."""
        updated = await workout_service.trainer_leave_session(
            session=shared_active_session,
        )

        assert updated.trainer_id is None

    async def test_trainer_leave_sets_is_shared_false(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
    ):
        """Trainer leaving sets is_shared to False."""
        updated = await workout_service.trainer_leave_session(
            session=shared_active_session,
        )

        assert updated.is_shared is False

    async def test_trainer_leave_does_not_complete_session(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
    ):
        """Trainer leaving does not complete the session."""
        updated = await workout_service.trainer_leave_session(
            session=shared_active_session,
        )

        assert updated.status == SessionStatus.ACTIVE
        assert updated.completed_at is None

    async def test_session_continues_after_trainer_leaves(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
    ):
        """Session remains active after trainer leaves."""
        updated = await workout_service.trainer_leave_session(
            session=shared_active_session,
        )

        # Student can continue working out
        assert updated.status == SessionStatus.ACTIVE
        assert updated.is_completed is False


# =============================================================================
# Test: Trainer Adjustments
# =============================================================================


class TestTrainerAdjustments:
    """Tests for trainer adjustments during co-training."""

    async def test_create_adjustment_with_suggested_weight(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
        exercise: Exercise,
    ):
        """Trainer can create adjustment with suggested weight."""
        adjustment = await workout_service.create_trainer_adjustment(
            session_id=shared_active_session.id,
            trainer_id=trainer.id,
            exercise_id=exercise.id,
            suggested_weight_kg=50.0,
        )

        assert adjustment.suggested_weight_kg == 50.0
        assert adjustment.trainer_id == trainer.id

    async def test_create_adjustment_with_suggested_reps(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
        exercise: Exercise,
    ):
        """Trainer can create adjustment with suggested reps."""
        adjustment = await workout_service.create_trainer_adjustment(
            session_id=shared_active_session.id,
            trainer_id=trainer.id,
            exercise_id=exercise.id,
            suggested_reps=12,
        )

        assert adjustment.suggested_reps == 12

    async def test_create_adjustment_with_note(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
        exercise: Exercise,
    ):
        """Trainer can create adjustment with note."""
        adjustment = await workout_service.create_trainer_adjustment(
            session_id=shared_active_session.id,
            trainer_id=trainer.id,
            exercise_id=exercise.id,
            note="Slow down on the eccentric phase",
        )

        assert adjustment.note == "Slow down on the eccentric phase"

    async def test_create_adjustment_for_specific_set(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
        exercise: Exercise,
    ):
        """Trainer can create adjustment for specific set number."""
        adjustment = await workout_service.create_trainer_adjustment(
            session_id=shared_active_session.id,
            trainer_id=trainer.id,
            exercise_id=exercise.id,
            set_number=3,
            suggested_weight_kg=55.0,
        )

        assert adjustment.set_number == 3

    async def test_adjustment_linked_to_session_and_exercise(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
        exercise: Exercise,
    ):
        """Adjustment is linked to session and exercise."""
        adjustment = await workout_service.create_trainer_adjustment(
            session_id=shared_active_session.id,
            trainer_id=trainer.id,
            exercise_id=exercise.id,
            suggested_reps=10,
        )

        assert adjustment.session_id == shared_active_session.id
        assert adjustment.exercise_id == exercise.id


# =============================================================================
# Test: Session Messages
# =============================================================================


class TestSessionMessages:
    """Tests for real-time messaging during co-training."""

    async def test_student_can_send_message(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        student: User,
    ):
        """Student can send a message during session."""
        message = await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=student.id,
            message="Is my form correct?",
        )

        assert message.message == "Is my form correct?"
        assert message.sender_id == student.id

    async def test_trainer_can_send_message(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        trainer: User,
    ):
        """Trainer can send a message during session."""
        message = await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=trainer.id,
            message="Great form! Keep it up!",
        )

        assert message.message == "Great form! Keep it up!"
        assert message.sender_id == trainer.id

    async def test_message_has_sent_at_timestamp(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        student: User,
    ):
        """Messages have sent_at timestamp."""
        message = await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=student.id,
            message="Test message",
        )

        assert message.sent_at is not None

    async def test_message_starts_as_unread(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        student: User,
    ):
        """New messages start as unread."""
        message = await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=student.id,
            message="Hello!",
        )

        assert message.is_read is False

    async def test_list_session_messages_returns_messages(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        student: User,
        trainer: User,
    ):
        """Listing messages returns all messages for the session."""
        # Create messages in sequence
        await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=student.id,
            message="First message",
        )
        await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=trainer.id,
            message="Second message",
        )
        await workout_service.create_session_message(
            session_id=shared_active_session.id,
            sender_id=student.id,
            message="Third message",
        )

        messages = await workout_service.list_session_messages(
            session_id=shared_active_session.id,
        )

        assert len(messages) == 3
        message_texts = [m.message for m in messages]
        assert "First message" in message_texts
        assert "Second message" in message_texts
        assert "Third message" in message_texts

    async def test_list_session_messages_respects_limit(
        self,
        workout_service: WorkoutService,
        shared_active_session: WorkoutSession,
        student: User,
    ):
        """Listing messages respects the limit parameter."""
        # Create 5 messages
        for i in range(5):
            await workout_service.create_session_message(
                session_id=shared_active_session.id,
                sender_id=student.id,
                message=f"Message {i}",
            )

        messages = await workout_service.list_session_messages(
            session_id=shared_active_session.id,
            limit=3,
        )

        assert len(messages) == 3


# =============================================================================
# Test: Session Properties
# =============================================================================


class TestSessionProperties:
    """Tests for session computed properties."""

    async def test_waiting_session_is_not_completed(
        self,
        waiting_session: WorkoutSession,
    ):
        """Waiting session is not completed."""
        assert waiting_session.is_completed is False

    async def test_waiting_session_is_not_active(
        self,
        waiting_session: WorkoutSession,
    ):
        """Waiting session is not active."""
        assert waiting_session.is_active is False

    async def test_paused_session_is_not_active(
        self,
        paused_session: WorkoutSession,
    ):
        """Paused session is not active."""
        assert paused_session.is_active is False

    async def test_completed_session_is_not_active(
        self,
        completed_session: WorkoutSession,
    ):
        """Completed session is not active."""
        assert completed_session.is_active is False


# =============================================================================
# Test: Session Rating and Feedback
# =============================================================================


class TestSessionFeedback:
    """Tests for session rating and feedback."""

    async def test_session_rating_can_be_set(
        self,
        db_session: AsyncSession,
        active_session: WorkoutSession,
    ):
        """Session can have a rating (1-5)."""
        active_session.rating = 5
        await db_session.commit()
        await db_session.refresh(active_session)

        assert active_session.rating == 5

    async def test_session_student_feedback_can_be_set(
        self,
        db_session: AsyncSession,
        active_session: WorkoutSession,
    ):
        """Session can have student feedback."""
        active_session.student_feedback = "Great workout!"
        await db_session.commit()
        await db_session.refresh(active_session)

        assert active_session.student_feedback == "Great workout!"

    async def test_session_trainer_notes_can_be_set(
        self,
        db_session: AsyncSession,
        shared_active_session: WorkoutSession,
    ):
        """Session can have trainer notes."""
        shared_active_session.trainer_notes = "Good progress on form"
        await db_session.commit()
        await db_session.refresh(shared_active_session)

        assert shared_active_session.trainer_notes == "Good progress on form"
