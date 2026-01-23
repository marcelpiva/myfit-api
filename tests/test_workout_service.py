"""Tests for the workout service."""

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.workouts.models import TrainingPlan
from src.domains.workouts.service import WorkoutService


class TestDuplicatePlan:
    """Tests for the duplicate_plan method."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    @pytest.fixture
    async def imported_plan(
        self,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ) -> TrainingPlan:
        """Create a program that was imported from marketplace (has source_template_id)."""
        template_id = uuid.uuid4()
        program = TrainingPlan(
            name="Imported Program",
            description="This program was imported from the marketplace",
            goal="strength",
            difficulty="intermediate",
            split_type="push_pull_legs",
            duration_weeks=8,
            is_template=True,
            is_public=False,
            created_by_id=sample_user["id"],
            source_template_id=template_id,  # This marks it as imported
        )
        db_session.add(program)
        await db_session.commit()
        await db_session.refresh(program)
        return program

    @pytest.fixture
    async def local_plan(
        self,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ) -> TrainingPlan:
        """Create a locally created program (no source_template_id)."""
        program = TrainingPlan(
            name="Local Program",
            description="This program was created locally",
            goal="hypertrophy",
            difficulty="beginner",
            split_type="full_body",
            duration_weeks=4,
            is_template=True,
            is_public=False,
            created_by_id=sample_user["id"],
            source_template_id=None,  # Local program
        )
        db_session.add(program)
        await db_session.commit()
        await db_session.refresh(program)
        return program

    async def test_duplicate_imported_plan_clears_source_template_id(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """
        Bug fix test: When duplicating an imported program, the new program
        should NOT have source_template_id set.

        This ensures duplicated programs don't show the "Importado" badge.
        """
        # Act: Duplicate the imported program
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=sample_user["id"],
            new_name="Duplicated Program",
        )

        # Assert: The duplicated program should NOT have source_template_id
        assert new_plan.source_template_id is None, (
            "Duplicated program should not inherit source_template_id. "
            "This would incorrectly show the 'Importado' badge."
        )

    async def test_duplicate_local_plan_keeps_source_template_id_none(
        self,
        workout_service: WorkoutService,
        local_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """Local programs should remain without source_template_id after duplication."""
        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=local_plan,
            new_owner_id=sample_user["id"],
            new_name="Duplicated Local Program",
        )

        # Assert
        assert new_plan.source_template_id is None

    async def test_duplicate_plan_copies_basic_fields(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """Duplicated program should copy all basic fields except source_template_id."""
        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=sample_user["id"],
        )

        # Assert: Basic fields should be copied (name is auto-generated with number)
        assert "Imported Program" in new_plan.name  # Base name preserved
        assert new_plan.description == imported_plan.description
        assert new_plan.goal == imported_plan.goal
        assert new_plan.difficulty == imported_plan.difficulty
        assert new_plan.split_type == imported_plan.split_type
        assert new_plan.duration_weeks == imported_plan.duration_weeks

    async def test_duplicate_plan_with_custom_name(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """Duplicated program should use custom name if provided."""
        custom_name = "My Custom Program Name"

        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=sample_user["id"],
            new_name=custom_name,
        )

        # Assert
        assert new_plan.name == custom_name

    async def test_duplicate_plan_sets_new_owner(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
    ):
        """Duplicated program should be owned by the specified user."""
        new_owner_id = uuid.uuid4()

        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=new_owner_id,
        )

        # Assert
        assert new_plan.created_by_id == new_owner_id

    async def test_duplicate_plan_is_not_template_or_public(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """Duplicated programs should not be templates or public by default."""
        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=sample_user["id"],
        )

        # Assert
        assert new_plan.is_template is False
        assert new_plan.is_public is False

    async def test_duplicate_plan_creates_new_id(
        self,
        workout_service: WorkoutService,
        imported_plan: TrainingPlan,
        sample_user: dict[str, Any],
    ):
        """Duplicated program should have a new unique ID."""
        # Act
        new_plan = await workout_service.duplicate_plan(
            plan=imported_plan,
            new_owner_id=sample_user["id"],
        )

        # Assert
        assert new_plan.id != imported_plan.id
        assert new_plan.id is not None


class TestDuplicateNaming:
    """Tests for the numbered naming scheme when duplicating workouts/programs."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    def test_get_next_copy_name_first_copy(self, workout_service: WorkoutService):
        """First copy should be 'Name (2)'."""
        result = workout_service._get_next_copy_name(
            original_name="Treino A",
            existing_names=["Treino A"],
        )
        assert result == "Treino A (2)"

    def test_get_next_copy_name_subsequent_copy(self, workout_service: WorkoutService):
        """Subsequent copies should increment the number."""
        result = workout_service._get_next_copy_name(
            original_name="Treino A",
            existing_names=["Treino A", "Treino A (2)", "Treino A (3)"],
        )
        assert result == "Treino A (4)"

    def test_get_next_copy_name_removes_copy_of_prefix(self, workout_service: WorkoutService):
        """Should remove 'Copy of' prefix and use clean base name."""
        result = workout_service._get_next_copy_name(
            original_name="Copy of Treino A",
            existing_names=["Treino A"],
        )
        assert result == "Treino A (2)"

    def test_get_next_copy_name_removes_copia_de_prefix(self, workout_service: WorkoutService):
        """Should remove 'Copia de' prefix (Portuguese)."""
        result = workout_service._get_next_copy_name(
            original_name="Copia de Treino B",
            existing_names=["Treino B"],
        )
        assert result == "Treino B (2)"

    def test_get_next_copy_name_handles_copy_of_copy_of(self, workout_service: WorkoutService):
        """Should handle 'Copy of Copy of' by extracting base name."""
        result = workout_service._get_next_copy_name(
            original_name="Copy of Copy of Treino A",
            existing_names=["Treino A", "Treino A (2)"],
        )
        # Should strip "Copy of" prefix and find "Copy of Treino A" -> "Treino A"
        assert result == "Treino A (3)"

    def test_get_next_copy_name_no_existing(self, workout_service: WorkoutService):
        """First copy when no existing names should be '(2)'."""
        result = workout_service._get_next_copy_name(
            original_name="Novo Treino",
            existing_names=[],
        )
        assert result == "Novo Treino (2)"

    def test_get_next_copy_name_case_insensitive(self, workout_service: WorkoutService):
        """Name matching should be case insensitive."""
        result = workout_service._get_next_copy_name(
            original_name="TREINO A",
            existing_names=["treino a", "Treino A (2)"],
        )
        assert result == "TREINO A (3)"

    def test_get_next_copy_name_with_numbers_in_name(self, workout_service: WorkoutService):
        """Should handle names that already have numbers (but not in parentheses)."""
        result = workout_service._get_next_copy_name(
            original_name="Treino 1",
            existing_names=["Treino 1", "Treino 1 (2)"],
        )
        assert result == "Treino 1 (3)"

    def test_get_next_copy_name_skips_gaps(self, workout_service: WorkoutService):
        """Should find the max number and increment, even with gaps."""
        result = workout_service._get_next_copy_name(
            original_name="Treino A",
            existing_names=["Treino A", "Treino A (5)"],  # Gap: no (2), (3), (4)
        )
        assert result == "Treino A (6)"

    def test_get_next_copy_name_with_special_characters(self, workout_service: WorkoutService):
        """Should handle names with special characters."""
        result = workout_service._get_next_copy_name(
            original_name="Treino - Upper & Lower",
            existing_names=["Treino - Upper & Lower"],
        )
        assert result == "Treino - Upper & Lower (2)"

    def test_get_next_copy_name_unicode(self, workout_service: WorkoutService):
        """Should handle unicode characters in names."""
        result = workout_service._get_next_copy_name(
            original_name="Treino Força",
            existing_names=["Treino Força", "Treino Força (2)"],
        )
        assert result == "Treino Força (3)"

    def test_get_next_copy_name_with_parentheses_in_middle(self, workout_service: WorkoutService):
        """Should handle names with parentheses that aren't copy numbers."""
        result = workout_service._get_next_copy_name(
            original_name="Push (Advanced)",
            existing_names=["Push (Advanced)", "Push (Advanced) (2)"],
        )
        assert result == "Push (Advanced) (3)"

    def test_get_next_copy_name_empty_string(self, workout_service: WorkoutService):
        """Should handle empty original name gracefully."""
        result = workout_service._get_next_copy_name(
            original_name="",
            existing_names=[],
        )
        assert result == " (2)"

    def test_strip_copy_prefixes_removes_nested_prefixes(self, workout_service: WorkoutService):
        """Should strip nested copy prefixes recursively."""
        result = workout_service._strip_copy_prefixes("Copy of Copia de Treino A")
        assert result == "Treino A"


class TestListExercises:
    """Tests for list_exercises method with muscle group filtering."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    @pytest.fixture
    async def sample_exercises(
        self,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Create sample exercises for different muscle groups."""
        from src.domains.workouts.models import Exercise, MuscleGroup

        exercises = []
        muscle_groups = [
            MuscleGroup.CHEST,
            MuscleGroup.QUADRICEPS,
            MuscleGroup.HAMSTRINGS,
            MuscleGroup.CALVES,
            MuscleGroup.BACK,
        ]

        for i, mg in enumerate(muscle_groups):
            exercise = Exercise(
                name=f"Test Exercise {mg.value}",
                muscle_group=mg,
                is_public=True,
                is_custom=False,
            )
            db_session.add(exercise)
            exercises.append(exercise)

        await db_session.commit()
        for ex in exercises:
            await db_session.refresh(ex)
        return exercises

    @pytest.mark.asyncio
    async def test_list_exercises_filter_by_chest(
        self,
        workout_service: WorkoutService,
        sample_exercises: list,
    ):
        """Should filter exercises by chest muscle group."""
        from src.domains.workouts.models import MuscleGroup

        result = await workout_service.list_exercises(
            muscle_group=MuscleGroup.CHEST
        )

        assert all(ex.muscle_group == MuscleGroup.CHEST for ex in result)

    @pytest.mark.asyncio
    async def test_list_exercises_legs_includes_all_leg_groups(
        self,
        workout_service: WorkoutService,
        sample_exercises: list,
    ):
        """Filtering by LEGS should include quadriceps, hamstrings, calves."""
        from src.domains.workouts.models import MuscleGroup

        result = await workout_service.list_exercises(
            muscle_group=MuscleGroup.LEGS
        )

        # Should find exercises from all leg muscle groups
        muscle_groups_found = {ex.muscle_group for ex in result}
        leg_groups = {MuscleGroup.QUADRICEPS, MuscleGroup.HAMSTRINGS, MuscleGroup.CALVES, MuscleGroup.LEGS}

        # All found groups should be leg groups
        assert all(mg in leg_groups for mg in muscle_groups_found)

    @pytest.mark.asyncio
    async def test_list_exercises_with_search(
        self,
        workout_service: WorkoutService,
        sample_exercises: list,
    ):
        """Should filter exercises by search term."""
        result = await workout_service.list_exercises(search="chest")

        assert all("chest" in ex.name.lower() for ex in result)

    @pytest.mark.asyncio
    async def test_list_exercises_pagination(
        self,
        workout_service: WorkoutService,
        sample_exercises: list,
    ):
        """Should support limit and offset pagination."""
        all_exercises = await workout_service.list_exercises(limit=100)
        paginated = await workout_service.list_exercises(limit=2, offset=0)

        assert len(paginated) <= 2

    @pytest.mark.asyncio
    async def test_list_exercises_user_custom_exercises(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
    ):
        """Should include user's custom exercises along with public ones."""
        from src.domains.workouts.models import Exercise, MuscleGroup

        # Create a private custom exercise for the user
        custom_exercise = Exercise(
            name="My Custom Exercise",
            muscle_group=MuscleGroup.CHEST,
            is_public=False,
            is_custom=True,
            created_by_id=sample_user["id"],
        )
        db_session.add(custom_exercise)
        await db_session.commit()

        result = await workout_service.list_exercises(
            user_id=sample_user["id"],
            muscle_group=MuscleGroup.CHEST,
        )

        # Should include the custom exercise
        exercise_ids = [ex.id for ex in result]
        assert custom_exercise.id in exercise_ids


class TestSessionOperations:
    """Tests for workout session operations."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    @pytest.fixture
    async def sample_workout(
        self,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Create a sample workout for session tests."""
        from src.domains.workouts.models import Workout

        workout = Workout(
            name="Test Workout",
            created_by_id=sample_user["id"],
        )
        db_session.add(workout)
        await db_session.commit()
        await db_session.refresh(workout)
        return workout

    @pytest.mark.asyncio
    async def test_start_session_creates_active_session(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Starting a session should create it with ACTIVE status."""
        from src.domains.workouts.models import SessionStatus

        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
        )

        assert session.id is not None
        assert session.status == SessionStatus.ACTIVE
        assert session.started_at is not None

    @pytest.mark.asyncio
    async def test_start_shared_session_creates_waiting_status(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Starting a shared (co-training) session should have WAITING status."""
        from src.domains.workouts.models import SessionStatus

        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
            is_shared=True,
        )

        assert session.status == SessionStatus.WAITING
        assert session.is_shared is True

    @pytest.mark.asyncio
    async def test_complete_session_sets_completed_at(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Completing a session should set completed_at timestamp."""
        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
        )

        completed = await workout_service.complete_session(session)

        assert completed.completed_at is not None

    @pytest.mark.asyncio
    async def test_complete_session_calculates_duration(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Completing a session should calculate duration in minutes."""
        from datetime import datetime, timedelta

        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
        )

        # Simulate session started 45 minutes ago
        session.started_at = datetime.utcnow() - timedelta(minutes=45)
        await db_session.commit()

        completed = await workout_service.complete_session(session)

        # Duration should be approximately 45 minutes
        assert completed.duration_minutes is not None
        assert 44 <= completed.duration_minutes <= 46

    @pytest.mark.asyncio
    async def test_complete_session_with_notes_and_rating(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Completing a session should save notes and rating."""
        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
        )

        completed = await workout_service.complete_session(
            session,
            notes="Great workout!",
            rating=5,
        )

        assert completed.notes == "Great workout!"
        assert completed.rating == 5

    @pytest.mark.asyncio
    async def test_add_session_set_records_data(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
        sample_workout,
    ):
        """Should record set data during a session."""
        from src.domains.workouts.models import Exercise, MuscleGroup

        # Create an exercise
        exercise = Exercise(
            name="Bench Press",
            muscle_group=MuscleGroup.CHEST,
            is_public=True,
        )
        workout_service.db.add(exercise)
        await workout_service.db.commit()
        await workout_service.db.refresh(exercise)

        session = await workout_service.start_session(
            user_id=sample_user["id"],
            workout_id=sample_workout.id,
        )

        session_set = await workout_service.add_session_set(
            session_id=session.id,
            exercise_id=exercise.id,
            set_number=1,
            reps_completed=10,
            weight_kg=80.0,
        )

        assert session_set.id is not None
        assert session_set.reps_completed == 10
        assert session_set.weight_kg == 80.0
        assert session_set.set_number == 1


class TestDuplicateWorkout:
    """Tests for the duplicate_workout method."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    @pytest.fixture
    async def workout_with_exercises(
        self,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Create a workout with exercises."""
        from src.domains.workouts.models import (
            Exercise,
            MuscleGroup,
            Workout,
            WorkoutExercise,
        )

        # Create exercise
        exercise = Exercise(
            name="Bench Press",
            muscle_group=MuscleGroup.CHEST,
            is_public=True,
        )
        db_session.add(exercise)
        await db_session.flush()

        # Create workout
        workout = Workout(
            name="Chest Day",
            description="Full chest workout",
            estimated_duration_min=60,
            is_template=True,
            is_public=True,
            created_by_id=sample_user["id"],
        )
        db_session.add(workout)
        await db_session.flush()

        # Add exercise to workout
        workout_exercise = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise.id,
            order=1,
            sets=3,
            reps="10-12",
            rest_seconds=90,
        )
        db_session.add(workout_exercise)
        await db_session.commit()

        # Refresh with relationships
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select

        result = await db_session.execute(
            select(Workout)
            .where(Workout.id == workout.id)
            .options(selectinload(Workout.exercises))
        )
        return result.scalar_one()

    @pytest.mark.asyncio
    async def test_duplicate_workout_creates_new_workout(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should create a new workout with a new ID."""
        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        assert new_workout.id != workout_with_exercises.id
        assert new_workout.id is not None

    @pytest.mark.asyncio
    async def test_duplicate_workout_copies_basic_fields(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should copy basic fields from original workout."""
        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        assert new_workout.description == workout_with_exercises.description
        assert new_workout.estimated_duration_min == workout_with_exercises.estimated_duration_min

    @pytest.mark.asyncio
    async def test_duplicate_workout_uses_numbered_name(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should generate a numbered name for duplicate."""
        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        # Should have the original name with a number
        assert "Chest Day" in new_workout.name
        assert "(" in new_workout.name

    @pytest.mark.asyncio
    async def test_duplicate_workout_custom_name(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should use custom name if provided."""
        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
            new_name="My Custom Chest Day",
        )

        assert new_workout.name == "My Custom Chest Day"

    @pytest.mark.asyncio
    async def test_duplicate_workout_sets_new_owner(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
    ):
        """Should set the new owner ID."""
        new_owner_id = uuid.uuid4()

        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=new_owner_id,
        )

        assert new_workout.created_by_id == new_owner_id

    @pytest.mark.asyncio
    async def test_duplicate_workout_not_template_or_public(
        self,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Duplicated workout should not be a template or public."""
        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        assert new_workout.is_template is False
        assert new_workout.is_public is False

    @pytest.mark.asyncio
    async def test_duplicate_workout_copies_exercises(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should copy all exercises from original workout."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from src.domains.workouts.models import Workout

        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        # Fetch with exercises
        result = await db_session.execute(
            select(Workout)
            .where(Workout.id == new_workout.id)
            .options(selectinload(Workout.exercises))
        )
        new_workout_with_exercises = result.scalar_one()

        assert len(new_workout_with_exercises.exercises) == len(workout_with_exercises.exercises)

    @pytest.mark.asyncio
    async def test_duplicate_workout_copies_exercise_details(
        self,
        db_session: AsyncSession,
        workout_service: WorkoutService,
        workout_with_exercises,
        sample_user: dict[str, Any],
    ):
        """Should copy exercise details like sets, reps, rest."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from src.domains.workouts.models import Workout

        new_workout = await workout_service.duplicate_workout(
            workout=workout_with_exercises,
            new_owner_id=sample_user["id"],
        )

        # Fetch with exercises
        result = await db_session.execute(
            select(Workout)
            .where(Workout.id == new_workout.id)
            .options(selectinload(Workout.exercises))
        )
        new_workout_with_exercises = result.scalar_one()

        original_ex = workout_with_exercises.exercises[0]
        new_ex = new_workout_with_exercises.exercises[0]

        assert new_ex.sets == original_ex.sets
        assert new_ex.reps == original_ex.reps
        assert new_ex.rest_seconds == original_ex.rest_seconds
        assert new_ex.exercise_id == original_ex.exercise_id


class TestExerciseOperations:
    """Tests for exercise CRUD operations."""

    @pytest.fixture
    async def workout_service(self, db_session: AsyncSession) -> WorkoutService:
        """Create a workout service instance."""
        return WorkoutService(db_session)

    @pytest.mark.asyncio
    async def test_create_exercise(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
    ):
        """Should create a custom exercise."""
        from src.domains.workouts.models import MuscleGroup

        exercise = await workout_service.create_exercise(
            created_by_id=sample_user["id"],
            name="Custom Squat Variation",
            muscle_group=MuscleGroup.QUADRICEPS,
            description="A custom squat variation",
        )

        assert exercise.id is not None
        assert exercise.name == "Custom Squat Variation"
        assert exercise.muscle_group == MuscleGroup.QUADRICEPS
        assert exercise.is_custom is True
        assert exercise.created_by_id == sample_user["id"]

    @pytest.mark.asyncio
    async def test_create_exercise_with_all_fields(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
    ):
        """Should create exercise with all optional fields."""
        from src.domains.workouts.models import MuscleGroup

        exercise = await workout_service.create_exercise(
            created_by_id=sample_user["id"],
            name="Full Exercise",
            muscle_group=MuscleGroup.CHEST,
            description="Full description",
            secondary_muscles=["triceps", "shoulders"],
            equipment=["barbell", "bench"],
            video_url="https://example.com/video",
            image_url="https://example.com/image",
            instructions="Step by step instructions",
        )

        assert exercise.secondary_muscles == ["triceps", "shoulders"]
        assert exercise.equipment == ["barbell", "bench"]
        assert exercise.video_url == "https://example.com/video"

    @pytest.mark.asyncio
    async def test_update_exercise(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
    ):
        """Should update exercise fields."""
        from src.domains.workouts.models import MuscleGroup

        exercise = await workout_service.create_exercise(
            created_by_id=sample_user["id"],
            name="Original Name",
            muscle_group=MuscleGroup.CHEST,
        )

        updated = await workout_service.update_exercise(
            exercise=exercise,
            name="Updated Name",
            description="New description",
        )

        assert updated.name == "Updated Name"
        assert updated.description == "New description"

    @pytest.mark.asyncio
    async def test_get_exercise_by_id(
        self,
        workout_service: WorkoutService,
        sample_user: dict[str, Any],
    ):
        """Should retrieve exercise by ID."""
        from src.domains.workouts.models import MuscleGroup

        exercise = await workout_service.create_exercise(
            created_by_id=sample_user["id"],
            name="Test Exercise",
            muscle_group=MuscleGroup.BACK,
        )

        found = await workout_service.get_exercise_by_id(exercise.id)

        assert found is not None
        assert found.id == exercise.id
        assert found.name == "Test Exercise"

    @pytest.mark.asyncio
    async def test_get_exercise_by_id_not_found(
        self,
        workout_service: WorkoutService,
    ):
        """Should return None for non-existent exercise."""
        found = await workout_service.get_exercise_by_id(uuid.uuid4())

        assert found is None
