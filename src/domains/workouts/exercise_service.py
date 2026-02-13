"""Exercise-related service operations."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.workouts.models import (
    Exercise,
    ExerciseFeedback,
    ExerciseFeedbackType,
    MuscleGroup,
    WorkoutExercise,
)


class ExerciseServiceMixin:
    """Mixin providing exercise-related operations for WorkoutService."""

    db: AsyncSession

    # Exercise operations

    async def get_exercise_by_id(self, exercise_id: uuid.UUID) -> Exercise | None:
        """Get an exercise by ID."""
        result = await self.db.execute(
            select(Exercise).where(Exercise.id == exercise_id)
        )
        return result.scalar_one_or_none()

    async def list_exercises(
        self,
        user_id: uuid.UUID | None = None,
        muscle_group: MuscleGroup | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Exercise]:
        """List exercises with filters."""
        from sqlalchemy import or_

        query = select(Exercise)

        # Filter by public or user's custom exercises
        if user_id:
            query = query.where(
                or_(
                    Exercise.is_public == True,  # noqa: E712
                    Exercise.created_by_id == user_id,
                )
            )
        else:
            query = query.where(Exercise.is_public == True)  # noqa: E712

        if muscle_group:
            # Handle "legs" as a composite group that includes quadriceps, hamstrings, calves
            if muscle_group == MuscleGroup.LEGS:
                leg_groups = MuscleGroup.get_leg_groups()
                query = query.where(Exercise.muscle_group.in_(leg_groups))
            else:
                query = query.where(Exercise.muscle_group == muscle_group)

        if search:
            query = query.where(Exercise.name.ilike(f"%{search}%"))

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_exercise(
        self,
        created_by_id: uuid.UUID,
        name: str,
        muscle_group: MuscleGroup,
        description: str | None = None,
        secondary_muscles: list[str] | None = None,
        equipment: list[str] | None = None,
        video_url: str | None = None,
        image_url: str | None = None,
        instructions: str | None = None,
        is_public: bool = False,
    ) -> Exercise:
        """Create a custom exercise."""
        exercise = Exercise(
            name=name,
            description=description,
            muscle_group=muscle_group,
            secondary_muscles=secondary_muscles,
            equipment=equipment,
            video_url=video_url,
            image_url=image_url,
            instructions=instructions,
            is_custom=True,
            is_public=is_public,
            created_by_id=created_by_id,
        )
        self.db.add(exercise)
        await self.db.commit()
        await self.db.refresh(exercise)
        return exercise

    async def update_exercise(
        self,
        exercise: Exercise,
        name: str | None = None,
        description: str | None = None,
        muscle_group: MuscleGroup | None = None,
        secondary_muscles: list[str] | None = None,
        equipment: list[str] | None = None,
        video_url: str | None = None,
        image_url: str | None = None,
        instructions: str | None = None,
    ) -> Exercise:
        """Update an exercise."""
        if name is not None:
            exercise.name = name
        if description is not None:
            exercise.description = description
        if muscle_group is not None:
            exercise.muscle_group = muscle_group
        if secondary_muscles is not None:
            exercise.secondary_muscles = secondary_muscles
        if equipment is not None:
            exercise.equipment = equipment
        if video_url is not None:
            exercise.video_url = video_url
        if image_url is not None:
            exercise.image_url = image_url
        if instructions is not None:
            exercise.instructions = instructions

        await self.db.commit()
        await self.db.refresh(exercise)
        return exercise

    # Exercise Feedback operations

    async def get_workout_exercise_by_id(
        self,
        workout_exercise_id: uuid.UUID,
    ) -> WorkoutExercise | None:
        """Get a workout exercise by ID."""
        result = await self.db.execute(
            select(WorkoutExercise)
            .where(WorkoutExercise.id == workout_exercise_id)
            .options(selectinload(WorkoutExercise.exercise))
        )
        return result.scalar_one_or_none()

    async def create_exercise_feedback(
        self,
        session_id: uuid.UUID,
        workout_exercise_id: uuid.UUID,
        exercise_id: uuid.UUID,
        student_id: uuid.UUID,
        feedback_type: ExerciseFeedbackType,
        comment: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> ExerciseFeedback:
        """Create feedback for an exercise during a workout session."""
        feedback = ExerciseFeedback(
            session_id=session_id,
            workout_exercise_id=workout_exercise_id,
            exercise_id=exercise_id,
            student_id=student_id,
            feedback_type=feedback_type,
            comment=comment,
            organization_id=organization_id,
        )
        self.db.add(feedback)
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def get_exercise_feedback_by_id(
        self,
        feedback_id: uuid.UUID,
    ) -> ExerciseFeedback | None:
        """Get an exercise feedback by ID."""
        result = await self.db.execute(
            select(ExerciseFeedback)
            .where(ExerciseFeedback.id == feedback_id)
            .options(
                selectinload(ExerciseFeedback.exercise),
                selectinload(ExerciseFeedback.replacement_exercise),
            )
        )
        return result.scalar_one_or_none()

    async def list_exercise_feedbacks_for_session(
        self,
        session_id: uuid.UUID,
    ) -> list[ExerciseFeedback]:
        """List all exercise feedbacks for a workout session."""
        result = await self.db.execute(
            select(ExerciseFeedback)
            .where(ExerciseFeedback.session_id == session_id)
            .options(
                selectinload(ExerciseFeedback.exercise),
                selectinload(ExerciseFeedback.replacement_exercise),
            )
            .order_by(ExerciseFeedback.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_pending_swap_requests(
        self,
        trainer_id: uuid.UUID,
        student_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> list[ExerciseFeedback]:
        """List pending swap requests for a trainer to respond to.

        Returns feedbacks with type=SWAP that haven't been responded to yet.
        """
        query = (
            select(ExerciseFeedback)
            .where(
                ExerciseFeedback.feedback_type == ExerciseFeedbackType.SWAP,
                ExerciseFeedback.responded_at.is_(None),
            )
            .options(
                selectinload(ExerciseFeedback.exercise),
                selectinload(ExerciseFeedback.session),
                selectinload(ExerciseFeedback.student),
            )
            .order_by(ExerciseFeedback.created_at.desc())
        )

        if student_id:
            query = query.where(ExerciseFeedback.student_id == student_id)

        if organization_id:
            query = query.where(ExerciseFeedback.organization_id == organization_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def respond_to_exercise_feedback(
        self,
        feedback: ExerciseFeedback,
        trainer_response: str,
        replacement_exercise_id: uuid.UUID | None = None,
    ) -> ExerciseFeedback:
        """Trainer responds to an exercise feedback (especially swap requests)."""
        feedback.trainer_response = trainer_response
        feedback.responded_at = datetime.now(timezone.utc)
        if replacement_exercise_id:
            feedback.replacement_exercise_id = replacement_exercise_id

        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback
