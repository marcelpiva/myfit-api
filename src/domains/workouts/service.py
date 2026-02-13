"""Workout service with database operations.

This is the main entry point that composes all workout sub-services via mixins:
- ExerciseServiceMixin: Exercise CRUD and feedback operations
- PlanServiceMixin: Plan CRUD, assignments, versioning, notes, AI generation
- SessionServiceMixin: Session CRUD, co-training, auto-expiration, active sessions
"""
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.workouts.exercise_service import ExerciseServiceMixin
from src.domains.workouts.models import (
    AssignmentStatus,
    Difficulty,
    Exercise,
    ExerciseFeedback,
    ExerciseFeedbackType,
    ExerciseMode,
    MuscleGroup,
    NoteAuthorRole,
    NoteContextType,
    PlanAssignment,
    PlanVersion,
    PlanWorkout,
    PrescriptionNote,
    SessionMessage,
    SessionStatus,
    SplitType,
    TechniqueType,
    TrainerAdjustment,
    TrainingPlan,
    Workout,
    WorkoutAssignment,
    WorkoutExercise,
    WorkoutGoal,
    WorkoutSession,
    WorkoutSessionSet,
)
from src.domains.workouts.plan_service import PlanServiceMixin
from src.domains.workouts.schemas import ActiveSessionResponse
from src.domains.workouts.session_service import SessionServiceMixin


class WorkoutService(ExerciseServiceMixin, PlanServiceMixin, SessionServiceMixin):
    """Service for handling workout operations.

    Composes exercise, plan, and session operations via mixins.
    Workout CRUD and assignment operations are defined directly here.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _strip_copy_prefixes(self, name: str) -> str:
        """Recursively strip 'Copy of', 'Copia de', 'Copia de' prefixes from a name."""
        copy_prefixes = ['copy of ', 'copia de ', 'cópia de ']
        lower_name = name.lower()

        for prefix in copy_prefixes:
            if lower_name.startswith(prefix):
                # Recursively strip in case of "Copy of Copy of ..."
                return self._strip_copy_prefixes(name[len(prefix):].strip())

        return name

    def _get_next_copy_name(self, original_name: str, existing_names: list[str]) -> str:
        """Generate next copy name like 'Name (2)', 'Name (3)', etc."""
        pattern = r'^(.*?)(?:\s*\((\d+)\))?$'
        match = re.match(pattern, original_name.strip())

        if match:
            base_name = match.group(1).strip()
            base_name = self._strip_copy_prefixes(base_name)
        else:
            base_name = self._strip_copy_prefixes(original_name)

        # Find highest existing number for this base name
        max_num = 1
        for name in existing_names:
            name_match = re.match(pattern, name.strip())
            if name_match:
                existing_base = name_match.group(1).strip()
                existing_base = self._strip_copy_prefixes(existing_base)

                if existing_base.lower() == base_name.lower():
                    num = int(name_match.group(2)) if name_match.group(2) else 1
                    max_num = max(max_num, num)

        return f"{base_name} ({max_num + 1})"

    # Workout operations

    async def get_workout_by_id(self, workout_id: uuid.UUID) -> Workout | None:
        """Get a workout by ID with exercises."""
        result = await self.db.execute(
            select(Workout)
            .where(Workout.id == workout_id)
            .options(selectinload(Workout.exercises).selectinload(WorkoutExercise.exercise))
        )
        return result.scalar_one_or_none()

    async def list_workouts(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        templates_only: bool = False,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Workout]:
        """List workouts for a user."""
        query = select(Workout).options(
            selectinload(Workout.exercises)
        )

        # Filter by user's workouts within the organization, or public templates
        if organization_id:
            query = query.where(
                or_(
                    and_(
                        Workout.created_by_id == user_id,
                        Workout.organization_id == organization_id,
                    ),
                    and_(Workout.is_template == True, Workout.is_public == True),  # noqa: E712
                )
            )
        else:
            query = query.where(
                or_(
                    and_(
                        Workout.created_by_id == user_id,
                        Workout.organization_id.is_(None),
                    ),
                    and_(Workout.is_template == True, Workout.is_public == True),  # noqa: E712
                )
            )

        if templates_only:
            query = query.where(Workout.is_template == True)  # noqa: E712

        if search:
            query = query.where(Workout.name.ilike(f"%{search}%"))

        query = query.order_by(Workout.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_workout(
        self,
        created_by_id: uuid.UUID,
        name: str,
        difficulty: Difficulty = Difficulty.INTERMEDIATE,
        description: str | None = None,
        estimated_duration_min: int = 60,
        target_muscles: list[str] | None = None,
        tags: list[str] | None = None,
        is_template: bool = False,
        is_public: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> Workout:
        """Create a new workout."""
        workout = Workout(
            name=name,
            description=description,
            difficulty=difficulty,
            estimated_duration_min=estimated_duration_min,
            target_muscles=target_muscles,
            tags=tags,
            is_template=is_template,
            is_public=is_public,
            created_by_id=created_by_id,
            organization_id=organization_id,
        )
        self.db.add(workout)
        await self.db.commit()
        await self.db.refresh(workout)
        return workout

    async def update_workout(
        self,
        workout: Workout,
        name: str | None = None,
        description: str | None = None,
        difficulty: Difficulty | None = None,
        estimated_duration_min: int | None = None,
        target_muscles: list[str] | None = None,
        tags: list[str] | None = None,
        is_template: bool | None = None,
        is_public: bool | None = None,
    ) -> Workout:
        """Update a workout."""
        if name is not None:
            workout.name = name
        if description is not None:
            workout.description = description
        if difficulty is not None:
            workout.difficulty = difficulty
        if estimated_duration_min is not None:
            workout.estimated_duration_min = estimated_duration_min
        if target_muscles is not None:
            workout.target_muscles = target_muscles
        if tags is not None:
            workout.tags = tags
        if is_template is not None:
            workout.is_template = is_template
        if is_public is not None:
            workout.is_public = is_public

        await self.db.commit()
        await self.db.refresh(workout)
        return workout

    async def delete_workout(self, workout: Workout) -> None:
        """Delete a workout and its related exercises."""
        await self.db.execute(
            delete(WorkoutExercise).where(WorkoutExercise.workout_id == workout.id)
        )
        await self.db.delete(workout)
        await self.db.commit()

    async def add_exercise_to_workout(
        self,
        workout_id: uuid.UUID,
        exercise_id: uuid.UUID,
        order: int = 0,
        sets: int = 3,
        reps: str = "10-12",
        rest_seconds: int = 60,
        notes: str | None = None,
        superset_with: uuid.UUID | None = None,
        # Advanced technique fields
        execution_instructions: str | None = None,
        group_instructions: str | None = None,
        isometric_seconds: int | None = None,
        technique_type: TechniqueType = TechniqueType.NORMAL,
        exercise_group_id: str | None = None,
        exercise_group_order: int = 0,
        # Structured technique parameters
        drop_count: int | None = None,
        rest_between_drops: int | None = None,
        pause_duration: int | None = None,
        mini_set_count: int | None = None,
        # Exercise mode (strength vs aerobic)
        exercise_mode: ExerciseMode = ExerciseMode.STRENGTH,
        # Aerobic exercise fields
        duration_minutes: int | None = None,
        intensity: str | None = None,
        work_seconds: int | None = None,
        interval_rest_seconds: int | None = None,
        rounds: int | None = None,
        distance_km: float | None = None,
        target_pace_min_per_km: float | None = None,
    ) -> WorkoutExercise:
        """Add an exercise to a workout."""
        workout_exercise = WorkoutExercise(
            workout_id=workout_id,
            exercise_id=exercise_id,
            order=order,
            sets=sets,
            reps=reps,
            rest_seconds=rest_seconds,
            notes=notes,
            superset_with=superset_with,
            execution_instructions=execution_instructions,
            group_instructions=group_instructions,
            isometric_seconds=isometric_seconds,
            technique_type=technique_type,
            exercise_group_id=exercise_group_id,
            exercise_group_order=exercise_group_order,
            drop_count=drop_count,
            rest_between_drops=rest_between_drops,
            pause_duration=pause_duration,
            mini_set_count=mini_set_count,
            exercise_mode=exercise_mode,
            duration_minutes=duration_minutes,
            intensity=intensity,
            work_seconds=work_seconds,
            interval_rest_seconds=interval_rest_seconds,
            rounds=rounds,
            distance_km=distance_km,
            target_pace_min_per_km=target_pace_min_per_km,
        )
        self.db.add(workout_exercise)
        await self.db.commit()
        await self.db.refresh(workout_exercise)
        return workout_exercise

    async def remove_exercise_from_workout(
        self,
        workout_exercise_id: uuid.UUID,
    ) -> None:
        """Remove an exercise from a workout."""
        result = await self.db.execute(
            select(WorkoutExercise).where(WorkoutExercise.id == workout_exercise_id)
        )
        workout_exercise = result.scalar_one_or_none()
        if workout_exercise:
            await self.db.delete(workout_exercise)
            await self.db.commit()

    async def duplicate_workout(
        self,
        workout: Workout,
        new_owner_id: uuid.UUID,
        new_name: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> Workout:
        """Duplicate a workout for another user."""
        if not new_name:
            existing_workouts = await self.list_workouts(
                user_id=new_owner_id,
                organization_id=organization_id,
                limit=500,
            )
            existing_names = [w.name for w in existing_workouts]
            new_name = self._get_next_copy_name(workout.name, existing_names)

        new_workout = Workout(
            name=new_name,
            description=workout.description,
            difficulty=workout.difficulty,
            estimated_duration_min=workout.estimated_duration_min,
            target_muscles=workout.target_muscles,
            tags=workout.tags,
            is_template=False,
            is_public=False,
            created_by_id=new_owner_id,
            organization_id=organization_id,
        )
        self.db.add(new_workout)
        await self.db.flush()

        # Copy exercises
        for we in workout.exercises:
            new_we = WorkoutExercise(
                workout_id=new_workout.id,
                exercise_id=we.exercise_id,
                order=we.order,
                sets=we.sets,
                reps=we.reps,
                rest_seconds=we.rest_seconds,
                notes=we.notes,
                superset_with=we.superset_with,
                execution_instructions=we.execution_instructions,
                group_instructions=we.group_instructions,
                isometric_seconds=we.isometric_seconds,
                technique_type=we.technique_type,
                exercise_group_id=we.exercise_group_id,
                exercise_group_order=we.exercise_group_order,
                drop_count=we.drop_count,
                rest_between_drops=we.rest_between_drops,
                pause_duration=we.pause_duration,
                mini_set_count=we.mini_set_count,
                exercise_mode=we.exercise_mode,
                duration_minutes=we.duration_minutes,
                intensity=we.intensity,
                work_seconds=we.work_seconds,
                interval_rest_seconds=we.interval_rest_seconds,
                rounds=we.rounds,
                distance_km=we.distance_km,
                target_pace_min_per_km=we.target_pace_min_per_km,
            )
            self.db.add(new_we)

        await self.db.commit()
        await self.db.refresh(new_workout)
        return new_workout

    # Assignment operations

    async def get_assignment_by_id(
        self,
        assignment_id: uuid.UUID,
    ) -> WorkoutAssignment | None:
        """Get an assignment by ID."""
        result = await self.db.execute(
            select(WorkoutAssignment)
            .where(WorkoutAssignment.id == assignment_id)
            .options(selectinload(WorkoutAssignment.workout))
        )
        return result.scalar_one_or_none()

    async def list_student_assignments(
        self,
        student_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[WorkoutAssignment]:
        """List assignments for a student."""
        query = select(WorkoutAssignment).where(
            WorkoutAssignment.student_id == student_id
        ).options(selectinload(WorkoutAssignment.workout))

        if active_only:
            query = query.where(WorkoutAssignment.is_active == True)  # noqa: E712

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_trainer_assignments(
        self,
        trainer_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[WorkoutAssignment]:
        """List assignments created by a trainer."""
        query = select(WorkoutAssignment).where(
            WorkoutAssignment.trainer_id == trainer_id
        ).options(selectinload(WorkoutAssignment.workout))

        if active_only:
            query = query.where(WorkoutAssignment.is_active == True)  # noqa: E712

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_assignment(
        self,
        workout_id: uuid.UUID,
        student_id: uuid.UUID,
        trainer_id: uuid.UUID,
        start_date: date,
        end_date: date | None = None,
        notes: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> WorkoutAssignment:
        """Create a workout assignment."""
        assignment = WorkoutAssignment(
            workout_id=workout_id,
            student_id=student_id,
            trainer_id=trainer_id,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
            organization_id=organization_id,
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def update_assignment(
        self,
        assignment: WorkoutAssignment,
        start_date: date | None = None,
        end_date: date | None = None,
        is_active: bool | None = None,
        notes: str | None = None,
    ) -> WorkoutAssignment:
        """Update an assignment."""
        if start_date is not None:
            assignment.start_date = start_date
        if end_date is not None:
            assignment.end_date = end_date
        if is_active is not None:
            assignment.is_active = is_active
        if notes is not None:
            assignment.notes = notes

        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment
