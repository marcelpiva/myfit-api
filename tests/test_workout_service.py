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
