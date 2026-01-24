"""Unit tests for Prescription Notes - bidirectional communication.

Tests cover note creation, access control, read tracking,
and the different context types (PLAN, WORKOUT, EXERCISE, SESSION).
"""

import uuid
from datetime import datetime, timezone

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
    NoteAuthorRole,
    NoteContextType,
    PrescriptionNote,
    TrainingPlan,
    Workout,
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
async def trainer_note_on_plan(
    db_session: AsyncSession,
    trainer: User,
    training_plan: TrainingPlan,
    organization: Organization,
) -> PrescriptionNote:
    """Create a trainer note on a plan."""
    note = PrescriptionNote(
        id=uuid.uuid4(),
        context_type=NoteContextType.PLAN,
        context_id=training_plan.id,
        author_id=trainer.id,
        author_role=NoteAuthorRole.TRAINER,
        content="Focus on form this week",
        organization_id=organization.id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
async def student_note_on_plan(
    db_session: AsyncSession,
    student: User,
    training_plan: TrainingPlan,
    organization: Organization,
) -> PrescriptionNote:
    """Create a student note on a plan."""
    note = PrescriptionNote(
        id=uuid.uuid4(),
        context_type=NoteContextType.PLAN,
        context_id=training_plan.id,
        author_id=student.id,
        author_role=NoteAuthorRole.STUDENT,
        content="I understand, will focus on form!",
        organization_id=organization.id,
    )
    db_session.add(note)
    await db_session.commit()
    await db_session.refresh(note)
    return note


@pytest.fixture
def workout_service(db_session: AsyncSession) -> WorkoutService:
    """Create a WorkoutService instance."""
    return WorkoutService(db_session)


# =============================================================================
# Test: Note Creation
# =============================================================================


class TestPrescriptionNoteCreation:
    """Tests for creating prescription notes."""

    async def test_create_note_with_plan_context(
        self,
        workout_service: WorkoutService,
        trainer: User,
        training_plan: TrainingPlan,
        organization: Organization,
    ):
        """Trainer can create a note on a plan context."""
        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Increase intensity next week",
            organization_id=organization.id,
        )

        assert note.context_type == NoteContextType.PLAN
        assert note.context_id == training_plan.id
        assert note.author_id == trainer.id
        assert note.content == "Increase intensity next week"

    async def test_create_note_with_workout_context(
        self,
        workout_service: WorkoutService,
        trainer: User,
        workout: Workout,
        organization: Organization,
    ):
        """Trainer can create a note on a workout context."""
        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.WORKOUT,
            context_id=workout.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Add extra set on bench press",
            organization_id=organization.id,
        )

        assert note.context_type == NoteContextType.WORKOUT
        assert note.context_id == workout.id

    async def test_create_note_with_session_context(
        self,
        workout_service: WorkoutService,
        trainer: User,
        organization: Organization,
    ):
        """Trainer can create a note on a session context."""
        session_id = uuid.uuid4()  # Simulated session ID

        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.SESSION,
            context_id=session_id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Great workout today!",
            organization_id=organization.id,
        )

        assert note.context_type == NoteContextType.SESSION
        assert note.context_id == session_id

    async def test_create_note_with_exercise_context(
        self,
        workout_service: WorkoutService,
        trainer: User,
        organization: Organization,
    ):
        """Trainer can create a note on an exercise context."""
        exercise_id = uuid.uuid4()  # Simulated exercise ID

        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.EXERCISE,
            context_id=exercise_id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Keep elbows tucked",
            organization_id=organization.id,
        )

        assert note.context_type == NoteContextType.EXERCISE
        assert note.context_id == exercise_id

    async def test_note_defaults_to_not_pinned(
        self,
        workout_service: WorkoutService,
        trainer: User,
        training_plan: TrainingPlan,
        organization: Organization,
    ):
        """Notes default to not pinned."""
        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Test note",
            organization_id=organization.id,
        )

        assert note.is_pinned is False

    async def test_note_can_be_created_as_pinned(
        self,
        workout_service: WorkoutService,
        trainer: User,
        training_plan: TrainingPlan,
        organization: Organization,
    ):
        """Notes can be created as pinned."""
        note = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Important note",
            is_pinned=True,
            organization_id=organization.id,
        )

        assert note.is_pinned is True


# =============================================================================
# Test: Bidirectional Communication
# =============================================================================


class TestBidirectionalCommunication:
    """Tests for trainer-student bidirectional notes."""

    async def test_trainer_creates_note_for_student(
        self,
        trainer_note_on_plan: PrescriptionNote,
        trainer: User,
    ):
        """Trainer can create a note addressed to student."""
        assert trainer_note_on_plan.author_id == trainer.id
        assert trainer_note_on_plan.author_role == NoteAuthorRole.TRAINER

    async def test_student_replies_to_trainer_note(
        self,
        workout_service: WorkoutService,
        student: User,
        training_plan: TrainingPlan,
        trainer_note_on_plan: PrescriptionNote,
        organization: Organization,
    ):
        """Student can reply to trainer's note on the same context."""
        # Student creates a reply note on the same plan
        reply = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=student.id,
            author_role=NoteAuthorRole.STUDENT,
            content="Thanks for the feedback, I'll work on that!",
            organization_id=organization.id,
        )

        assert reply.author_role == NoteAuthorRole.STUDENT
        assert reply.context_id == trainer_note_on_plan.context_id

    async def test_list_notes_shows_both_trainer_and_student(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        student_note_on_plan: PrescriptionNote,
        training_plan: TrainingPlan,
    ):
        """Listing notes returns both trainer and student notes."""
        notes = await workout_service.list_prescription_notes(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
        )

        assert len(notes) == 2
        author_roles = {n.author_role for n in notes}
        assert NoteAuthorRole.TRAINER in author_roles
        assert NoteAuthorRole.STUDENT in author_roles


# =============================================================================
# Test: Read Tracking
# =============================================================================


class TestReadTracking:
    """Tests for note read status tracking."""

    async def test_note_starts_as_unread(
        self,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Notes start as unread."""
        assert trainer_note_on_plan.read_at is None
        assert trainer_note_on_plan.read_by_id is None

    async def test_mark_note_as_read_sets_timestamp(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        student: User,
    ):
        """Marking note as read sets read_at timestamp."""
        updated = await workout_service.mark_note_as_read(
            note=trainer_note_on_plan,
            user_id=student.id,
        )

        assert updated.read_at is not None

    async def test_mark_note_as_read_sets_read_by(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        student: User,
    ):
        """Marking note as read sets read_by_id."""
        updated = await workout_service.mark_note_as_read(
            note=trainer_note_on_plan,
            user_id=student.id,
        )

        assert updated.read_by_id == student.id


# =============================================================================
# Test: Note Retrieval
# =============================================================================


class TestNoteRetrieval:
    """Tests for retrieving notes."""

    async def test_get_note_by_id_returns_note(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Can retrieve note by ID."""
        found = await workout_service.get_prescription_note_by_id(
            trainer_note_on_plan.id
        )

        assert found is not None
        assert found.id == trainer_note_on_plan.id

    async def test_get_note_by_id_returns_none_for_invalid(
        self,
        workout_service: WorkoutService,
    ):
        """Returns None for non-existent note."""
        fake_id = uuid.uuid4()
        found = await workout_service.get_prescription_note_by_id(fake_id)

        assert found is None

    async def test_get_note_loads_author_relationship(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        trainer: User,
    ):
        """Note retrieval loads author relationship."""
        found = await workout_service.get_prescription_note_by_id(
            trainer_note_on_plan.id
        )

        assert found is not None
        assert found.author is not None
        assert found.author.id == trainer.id


# =============================================================================
# Test: Note Listing
# =============================================================================


class TestNoteListing:
    """Tests for listing notes with filters."""

    async def test_list_notes_by_context(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        training_plan: TrainingPlan,
    ):
        """Can list notes by context type and ID."""
        notes = await workout_service.list_prescription_notes(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
        )

        assert len(notes) >= 1
        assert trainer_note_on_plan.id in [n.id for n in notes]

    async def test_list_notes_excludes_other_contexts(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
        workout: Workout,
    ):
        """Listing by context excludes notes from other contexts."""
        notes = await workout_service.list_prescription_notes(
            context_type=NoteContextType.WORKOUT,
            context_id=workout.id,
        )

        # Should not include the plan note
        assert trainer_note_on_plan.id not in [n.id for n in notes]

    async def test_pinned_notes_sorted_first(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        trainer: User,
        training_plan: TrainingPlan,
        organization: Organization,
    ):
        """Pinned notes are sorted before non-pinned."""
        # Create regular note
        regular_note = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Regular note",
            is_pinned=False,
            organization_id=organization.id,
        )

        # Create pinned note
        pinned_note = await workout_service.create_prescription_note(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
            author_id=trainer.id,
            author_role=NoteAuthorRole.TRAINER,
            content="Pinned note",
            is_pinned=True,
            organization_id=organization.id,
        )

        notes = await workout_service.list_prescription_notes(
            context_type=NoteContextType.PLAN,
            context_id=training_plan.id,
        )

        # Pinned should come first
        assert notes[0].is_pinned is True


# =============================================================================
# Test: Note Update
# =============================================================================


class TestNoteUpdate:
    """Tests for updating notes."""

    async def test_update_note_content(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Can update note content."""
        new_content = "Updated: Focus on tempo"

        updated = await workout_service.update_prescription_note(
            note=trainer_note_on_plan,
            content=new_content,
        )

        assert updated.content == new_content

    async def test_update_note_pin_status(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Can pin/unpin a note."""
        assert trainer_note_on_plan.is_pinned is False

        updated = await workout_service.update_prescription_note(
            note=trainer_note_on_plan,
            is_pinned=True,
        )

        assert updated.is_pinned is True

    async def test_update_preserves_other_fields(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Updating one field preserves others."""
        original_content = trainer_note_on_plan.content

        updated = await workout_service.update_prescription_note(
            note=trainer_note_on_plan,
            is_pinned=True,
        )

        assert updated.content == original_content


# =============================================================================
# Test: Note Deletion
# =============================================================================


class TestNoteDeletion:
    """Tests for deleting notes."""

    async def test_delete_note(
        self,
        workout_service: WorkoutService,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Can delete a note."""
        note_id = trainer_note_on_plan.id

        await workout_service.delete_prescription_note(trainer_note_on_plan)

        # Verify deletion
        found = await workout_service.get_prescription_note_by_id(note_id)
        assert found is None


# =============================================================================
# Test: Access Control (Author Role)
# =============================================================================


class TestNoteAccessControl:
    """Tests for note access control."""

    async def test_note_has_correct_author(
        self,
        trainer_note_on_plan: PrescriptionNote,
        trainer: User,
    ):
        """Note is linked to correct author."""
        assert trainer_note_on_plan.author_id == trainer.id

    async def test_trainer_note_has_trainer_role(
        self,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """Trainer notes have TRAINER author_role."""
        assert trainer_note_on_plan.author_role == NoteAuthorRole.TRAINER

    async def test_student_note_has_student_role(
        self,
        student_note_on_plan: PrescriptionNote,
    ):
        """Student notes have STUDENT author_role."""
        assert student_note_on_plan.author_role == NoteAuthorRole.STUDENT

    async def test_note_belongs_to_organization(
        self,
        trainer_note_on_plan: PrescriptionNote,
        organization: Organization,
    ):
        """Note is scoped to correct organization."""
        assert trainer_note_on_plan.organization_id == organization.id


# =============================================================================
# Test: Context Types
# =============================================================================


class TestContextTypes:
    """Tests for different note context types."""

    async def test_plan_context_type(
        self,
        trainer_note_on_plan: PrescriptionNote,
    ):
        """PLAN context type for training plan notes."""
        assert trainer_note_on_plan.context_type == NoteContextType.PLAN

    async def test_all_context_types_are_valid(self):
        """All context types are defined."""
        assert NoteContextType.PLAN.value == "plan"
        assert NoteContextType.WORKOUT.value == "workout"
        assert NoteContextType.EXERCISE.value == "exercise"
        assert NoteContextType.SESSION.value == "session"

    async def test_all_author_roles_are_valid(self):
        """All author roles are defined."""
        assert NoteAuthorRole.TRAINER.value == "trainer"
        assert NoteAuthorRole.STUDENT.value == "student"
