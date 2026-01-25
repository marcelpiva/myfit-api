"""Workout service with database operations."""
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
from src.domains.workouts.schemas import ActiveSessionResponse


class WorkoutService:
    """Service for handling workout operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _strip_copy_prefixes(self, name: str) -> str:
        """Recursively strip 'Copy of', 'Copia de', 'Cópia de' prefixes from a name."""
        copy_prefixes = ['copy of ', 'copia de ', 'cópia de ']
        lower_name = name.lower()

        for prefix in copy_prefixes:
            if lower_name.startswith(prefix):
                # Recursively strip in case of "Copy of Copy of ..."
                return self._strip_copy_prefixes(name[len(prefix):].strip())

        return name

    def _get_next_copy_name(self, original_name: str, existing_names: list[str]) -> str:
        """Generate next copy name like 'Name (2)', 'Name (3)', etc.

        This method extracts the base name from the original (removing any existing
        'Copy of' prefix or numbered suffix), then finds the next available number.
        """
        # Pattern to match: "Name" or "Name (N)" where N is a number
        pattern = r'^(.*?)(?:\s*\((\d+)\))?$'
        match = re.match(pattern, original_name.strip())

        if match:
            base_name = match.group(1).strip()
            # Recursively remove "Copy of" prefixes
            base_name = self._strip_copy_prefixes(base_name)
        else:
            base_name = self._strip_copy_prefixes(original_name)

        # Find highest existing number for this base name
        max_num = 1
        for name in existing_names:
            name_match = re.match(pattern, name.strip())
            if name_match:
                existing_base = name_match.group(1).strip()
                # Also strip copy prefixes from existing names for comparison
                existing_base = self._strip_copy_prefixes(existing_base)

                if existing_base.lower() == base_name.lower():
                    num = int(name_match.group(2)) if name_match.group(2) else 1
                    max_num = max(max_num, num)

        return f"{base_name} ({max_num + 1})"

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
        query = select(Exercise)

        # Filter by public or user's custom exercises
        if user_id:
            query = query.where(
                or_(
                    Exercise.is_public == True,
                    Exercise.created_by_id == user_id,
                )
            )
        else:
            query = query.where(Exercise.is_public == True)

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

        # Filter by user's workouts or organization or public templates
        conditions = [Workout.created_by_id == user_id]
        if organization_id:
            conditions.append(Workout.organization_id == organization_id)
        conditions.append(and_(Workout.is_template == True, Workout.is_public == True))

        query = query.where(or_(*conditions))

        if templates_only:
            query = query.where(Workout.is_template == True)

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
        # Delete related exercises first to avoid ORM cascade issues
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
            # Advanced technique fields
            execution_instructions=execution_instructions,
            group_instructions=group_instructions,
            isometric_seconds=isometric_seconds,
            technique_type=technique_type,
            exercise_group_id=exercise_group_id,
            exercise_group_order=exercise_group_order,
            # Structured technique parameters
            drop_count=drop_count,
            rest_between_drops=rest_between_drops,
            pause_duration=pause_duration,
            mini_set_count=mini_set_count,
            # Exercise mode (strength vs aerobic)
            exercise_mode=exercise_mode,
            # Aerobic exercise fields
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
    ) -> Workout:
        """Duplicate a workout for another user."""
        # Generate a numbered name if no custom name provided
        if not new_name:
            existing_workouts = await self.list_workouts(
                user_id=new_owner_id,
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
                # Advanced technique fields
                execution_instructions=we.execution_instructions,
                group_instructions=we.group_instructions,
                isometric_seconds=we.isometric_seconds,
                technique_type=we.technique_type,
                exercise_group_id=we.exercise_group_id,
                exercise_group_order=we.exercise_group_order,
                # Structured technique parameters
                drop_count=we.drop_count,
                rest_between_drops=we.rest_between_drops,
                pause_duration=we.pause_duration,
                mini_set_count=we.mini_set_count,
                # Exercise mode (strength vs aerobic)
                exercise_mode=we.exercise_mode,
                # Aerobic exercise fields
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
            query = query.where(WorkoutAssignment.is_active == True)

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
            query = query.where(WorkoutAssignment.is_active == True)

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

    # Session operations

    async def get_session_by_id(
        self,
        session_id: uuid.UUID,
    ) -> WorkoutSession | None:
        """Get a session by ID."""
        result = await self.db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.id == session_id)
            .options(
                selectinload(WorkoutSession.sets),
                selectinload(WorkoutSession.workout),
            )
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WorkoutSession]:
        """List sessions for a user."""
        result = await self.db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == user_id)
            .options(selectinload(WorkoutSession.workout))
            .order_by(WorkoutSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def start_session(
        self,
        user_id: uuid.UUID,
        workout_id: uuid.UUID,
        assignment_id: uuid.UUID | None = None,
        is_shared: bool = False,
    ) -> WorkoutSession:
        """Start a new workout session.

        Args:
            user_id: The ID of the user starting the session.
            workout_id: The ID of the workout.
            assignment_id: Optional assignment ID.
            is_shared: If True, creates a co-training session in 'waiting' status.
        """
        session = WorkoutSession(
            workout_id=workout_id,
            user_id=user_id,
            assignment_id=assignment_id,
            is_shared=is_shared,
            status=SessionStatus.WAITING if is_shared else SessionStatus.ACTIVE,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def complete_session(
        self,
        session: WorkoutSession,
        notes: str | None = None,
        rating: int | None = None,
    ) -> WorkoutSession:
        """Complete a workout session."""
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        if session.started_at:
            # Normalize datetimes for SQLite compatibility (naive datetime)
            completed = session.completed_at.replace(tzinfo=None)
            started = session.started_at.replace(tzinfo=None) if session.started_at.tzinfo else session.started_at
            delta = completed - started
            session.duration_minutes = int(delta.total_seconds() / 60)
        if notes is not None:
            session.notes = notes
        if rating is not None:
            session.rating = rating

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def add_session_set(
        self,
        session_id: uuid.UUID,
        exercise_id: uuid.UUID,
        set_number: int,
        reps_completed: int,
        weight_kg: float | None = None,
        duration_seconds: int | None = None,
        notes: str | None = None,
    ) -> WorkoutSessionSet:
        """Record a set during a session."""
        session_set = WorkoutSessionSet(
            session_id=session_id,
            exercise_id=exercise_id,
            set_number=set_number,
            reps_completed=reps_completed,
            weight_kg=weight_kg,
            duration_seconds=duration_seconds,
            notes=notes,
        )
        self.db.add(session_set)
        await self.db.commit()
        await self.db.refresh(session_set)
        return session_set

    # Plan operations

    async def get_plan_by_id(self, plan_id: uuid.UUID) -> TrainingPlan | None:
        """Get a plan by ID with workouts."""
        result = await self.db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.id == plan_id)
            .options(
                selectinload(TrainingPlan.plan_workouts)
                .selectinload(PlanWorkout.workout)
                .selectinload(Workout.exercises)
                .selectinload(WorkoutExercise.exercise)
            )
        )
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        templates_only: bool = False,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TrainingPlan]:
        """List plans for a user."""
        query = select(TrainingPlan).options(
            selectinload(TrainingPlan.plan_workouts)
        )

        if templates_only:
            # Show public templates + user's own templates
            conditions = [
                and_(TrainingPlan.is_template == True, TrainingPlan.is_public == True),
                and_(TrainingPlan.created_by_id == user_id, TrainingPlan.is_template == True),
            ]
            if organization_id:
                conditions.append(
                    and_(TrainingPlan.organization_id == organization_id, TrainingPlan.is_template == True)
                )
            query = query.where(or_(*conditions))
        else:
            # Show only user's own plans (not templates from others)
            conditions = [TrainingPlan.created_by_id == user_id]
            if organization_id:
                conditions.append(TrainingPlan.organization_id == organization_id)
            query = query.where(or_(*conditions))

        if search:
            query = query.where(TrainingPlan.name.ilike(f"%{search}%"))

        query = query.order_by(TrainingPlan.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_catalog_templates(
        self,
        exclude_user_id: uuid.UUID,
        search: str | None = None,
        goal: WorkoutGoal | None = None,
        difficulty: Difficulty | None = None,
        split_type: SplitType | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Get public catalog templates excluding user's own."""
        from src.domains.users.models import User

        query = (
            select(TrainingPlan, User.name.label("creator_name"))
            .join(User, TrainingPlan.created_by_id == User.id, isouter=True)
            .options(selectinload(TrainingPlan.plan_workouts))
            .where(
                TrainingPlan.is_template == True,
                TrainingPlan.is_public == True,
                or_(
                    TrainingPlan.created_by_id == None,  # System templates
                    TrainingPlan.created_by_id != exclude_user_id,  # Other users' templates
                ),
            )
        )

        if search:
            query = query.where(TrainingPlan.name.ilike(f"%{search}%"))
        if goal:
            query = query.where(TrainingPlan.goal == goal)
        if difficulty:
            query = query.where(TrainingPlan.difficulty == difficulty)
        if split_type:
            query = query.where(TrainingPlan.split_type == split_type)

        query = query.order_by(TrainingPlan.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)

        templates = []
        for row in result.all():
            plan = row[0]
            creator_name = row[1]
            templates.append({
                "id": plan.id,
                "name": plan.name,
                "goal": plan.goal,
                "difficulty": plan.difficulty,
                "split_type": plan.split_type,
                "duration_weeks": plan.duration_weeks,
                "workout_count": len(plan.plan_workouts),
                "creator_name": creator_name,
                "created_by_id": plan.created_by_id,
                "created_at": plan.created_at,
            })
        return templates

    async def generate_plan_with_ai(
        self,
        user_id: uuid.UUID,
        goal: WorkoutGoal,
        difficulty: Difficulty,
        days_per_week: int,
        minutes_per_session: int,
        equipment: str,
        injuries: list[str] | None = None,
        preferences: str = "mixed",
        duration_weeks: int = 8,
    ) -> dict:
        """Generate a training plan structure using AI/rules-based logic."""
        # Determine split type based on days per week
        split_type = self._determine_split_type(days_per_week)

        # Generate workout structure based on split
        workout_structure = self._generate_workout_structure(
            split_type=split_type,
            days_per_week=days_per_week,
            goal=goal,
        )

        # Get available exercises
        all_exercises = await self.list_exercises(user_id=user_id, limit=500)

        # Filter exercises based on equipment and injuries
        filtered_exercises = self._filter_exercises(
            exercises=all_exercises,
            equipment=equipment,
            injuries=injuries or [],
        )

        # Generate workouts with exercises
        workouts = []
        for idx, workout_info in enumerate(workout_structure):
            exercises = self._select_exercises_for_workout(
                available_exercises=filtered_exercises,
                target_muscles=workout_info["muscles"],
                goal=goal,
                difficulty=difficulty,
                minutes_available=minutes_per_session,
                preferences=preferences,
            )
            workouts.append({
                "label": workout_info["label"],
                "name": workout_info["name"],
                "order": idx,
                "exercises": exercises,
                "target_muscles": workout_info["muscles"],
            })

        # Generate plan name
        goal_names = {
            WorkoutGoal.HYPERTROPHY: "Hipertrofia",
            WorkoutGoal.STRENGTH: "Força",
            WorkoutGoal.FAT_LOSS: "Emagrecimento",
            WorkoutGoal.ENDURANCE: "Resistência",
            WorkoutGoal.GENERAL_FITNESS: "Condicionamento",
            WorkoutGoal.FUNCTIONAL: "Funcional",
        }
        plan_name = f"Plano {goal_names.get(goal, 'Treino')} {days_per_week}x"

        return {
            "name": plan_name,
            "description": f"Plano de {duration_weeks} semanas focado em {goal_names.get(goal, 'treino').lower()}.",
            "goal": goal,
            "difficulty": difficulty,
            "split_type": split_type,
            "duration_weeks": duration_weeks,
            "workouts": workouts,
            "message": "Plano gerado com base nas suas preferências. Revise os treinos e faça ajustes conforme necessário.",
        }

    def _determine_split_type(self, days_per_week: int) -> SplitType:
        """Determine best split type based on training frequency."""
        if days_per_week <= 2:
            return SplitType.FULL_BODY
        elif days_per_week == 3:
            return SplitType.ABC
        elif days_per_week == 4:
            return SplitType.UPPER_LOWER
        elif days_per_week == 5:
            return SplitType.ABCDE
        else:
            return SplitType.PUSH_PULL_LEGS

    def _generate_workout_structure(
        self,
        split_type: SplitType,
        days_per_week: int,
        goal: WorkoutGoal,
    ) -> list[dict]:
        """Generate workout structure based on split type."""
        structures = {
            SplitType.FULL_BODY: [
                {"label": "A", "name": "Treino Full Body A", "muscles": ["chest", "back", "shoulders", "legs", "arms"]},
                {"label": "B", "name": "Treino Full Body B", "muscles": ["chest", "back", "shoulders", "legs", "arms"]},
            ],
            SplitType.UPPER_LOWER: [
                {"label": "A", "name": "Treino Superior A", "muscles": ["chest", "back", "shoulders", "arms"]},
                {"label": "B", "name": "Treino Inferior A", "muscles": ["legs", "glutes", "calves"]},
                {"label": "C", "name": "Treino Superior B", "muscles": ["chest", "back", "shoulders", "arms"]},
                {"label": "D", "name": "Treino Inferior B", "muscles": ["legs", "glutes", "calves"]},
            ],
            SplitType.PUSH_PULL_LEGS: [
                {"label": "A", "name": "Treino Push (Empurrar)", "muscles": ["chest", "shoulders", "triceps"]},
                {"label": "B", "name": "Treino Pull (Puxar)", "muscles": ["back", "biceps"]},
                {"label": "C", "name": "Treino Legs (Pernas)", "muscles": ["legs", "glutes", "calves"]},
                {"label": "D", "name": "Treino Push B", "muscles": ["chest", "shoulders", "triceps"]},
                {"label": "E", "name": "Treino Pull B", "muscles": ["back", "biceps"]},
                {"label": "F", "name": "Treino Legs B", "muscles": ["legs", "glutes", "calves"]},
            ],
            SplitType.ABC: [
                {"label": "A", "name": "Treino Peito e Tríceps", "muscles": ["chest", "triceps"]},
                {"label": "B", "name": "Treino Costas e Bíceps", "muscles": ["back", "biceps"]},
                {"label": "C", "name": "Treino Pernas e Ombros", "muscles": ["legs", "shoulders"]},
            ],
            SplitType.ABCDE: [
                {"label": "A", "name": "Treino Peito", "muscles": ["chest"]},
                {"label": "B", "name": "Treino Costas", "muscles": ["back"]},
                {"label": "C", "name": "Treino Ombros", "muscles": ["shoulders"]},
                {"label": "D", "name": "Treino Pernas", "muscles": ["legs", "glutes"]},
                {"label": "E", "name": "Treino Braços", "muscles": ["biceps", "triceps"]},
            ],
        }

        structure = structures.get(split_type, structures[SplitType.ABC])
        return structure[:days_per_week]

    def _filter_exercises(
        self,
        exercises: list[Exercise],
        equipment: str,
        injuries: list[str],
    ) -> list[Exercise]:
        """Filter exercises based on equipment and injuries."""
        # Equipment mapping
        equipment_filters = {
            "full_gym": None,  # No filter, all equipment available
            "home_basic": ["bodyweight", "resistance_band"],
            "home_dumbbells": ["bodyweight", "dumbbells", "resistance_band"],
            "home_full": ["bodyweight", "dumbbells", "barbell", "bench", "resistance_band"],
            "bodyweight": ["bodyweight"],
        }

        allowed_equipment = equipment_filters.get(equipment)

        filtered = []
        for exercise in exercises:
            # Check equipment
            if allowed_equipment is not None:
                exercise_equipment = exercise.equipment or []
                if not exercise_equipment:  # No equipment specified = bodyweight
                    pass
                elif not any(eq in allowed_equipment for eq in exercise_equipment):
                    continue

            # Check injuries (skip exercises that target injured areas)
            injury_mapping = {
                "shoulder": [MuscleGroup.SHOULDERS],
                "knee": [MuscleGroup.QUADRICEPS, MuscleGroup.HAMSTRINGS],
                "back": [MuscleGroup.BACK],
                "wrist": [MuscleGroup.FOREARMS],
            }

            skip = False
            for injury in injuries:
                injury_lower = injury.lower()
                if injury_lower in injury_mapping:
                    affected_muscles = injury_mapping[injury_lower]
                    if exercise.muscle_group in affected_muscles:
                        skip = True
                        break

            if not skip:
                filtered.append(exercise)

        return filtered

    def _select_exercises_for_workout(
        self,
        available_exercises: list[Exercise],
        target_muscles: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        minutes_available: int,
        preferences: str,
    ) -> list[dict]:
        """Select exercises for a workout based on targets and constraints."""
        # Map muscle names to MuscleGroup enum
        muscle_mapping = {
            "chest": MuscleGroup.CHEST,
            "back": MuscleGroup.BACK,
            "shoulders": MuscleGroup.SHOULDERS,
            "legs": MuscleGroup.QUADRICEPS,
            "glutes": MuscleGroup.GLUTES,
            "calves": MuscleGroup.CALVES,
            "arms": MuscleGroup.BICEPS,
            "biceps": MuscleGroup.BICEPS,
            "triceps": MuscleGroup.TRICEPS,
            "abs": MuscleGroup.ABS,
            "hamstrings": MuscleGroup.HAMSTRINGS,
            "forearms": MuscleGroup.FOREARMS,
        }

        # Determine number of exercises based on time
        exercises_per_workout = min(8, max(4, minutes_available // 8))

        # Sets and reps based on goal
        goal_config = {
            WorkoutGoal.HYPERTROPHY: {"sets": 4, "reps": "8-12", "rest": 90},
            WorkoutGoal.STRENGTH: {"sets": 5, "reps": "3-5", "rest": 180},
            WorkoutGoal.FAT_LOSS: {"sets": 3, "reps": "12-15", "rest": 45},
            WorkoutGoal.ENDURANCE: {"sets": 3, "reps": "15-20", "rest": 30},
            WorkoutGoal.GENERAL_FITNESS: {"sets": 3, "reps": "10-12", "rest": 60},
            WorkoutGoal.FUNCTIONAL: {"sets": 3, "reps": "10-12", "rest": 60},
        }
        config = goal_config.get(goal, goal_config[WorkoutGoal.GENERAL_FITNESS])

        import random
        import uuid as uuid_module

        selected = []
        exercises_per_muscle = max(1, exercises_per_workout // len(target_muscles))
        used_exercise_ids = set()

        # For advanced difficulty with hypertrophy, we'll add techniques
        use_advanced_techniques = (
            difficulty == Difficulty.ADVANCED and
            goal in [WorkoutGoal.HYPERTROPHY, WorkoutGoal.STRENGTH]
        )

        for muscle_idx, muscle_name in enumerate(target_muscles):
            muscle_group = muscle_mapping.get(muscle_name)
            if not muscle_group:
                continue

            # Find exercises for this muscle group
            muscle_exercises = [
                ex for ex in available_exercises
                if ex.muscle_group == muscle_group and ex.id not in used_exercise_ids
            ]

            if not muscle_exercises:
                continue

            random.shuffle(muscle_exercises)

            # Decide technique for this muscle group
            technique_type = "normal"
            group_id = None
            execution_instructions = None
            isometric_seconds = None

            if use_advanced_techniques:
                technique_roll = random.random()

                # 30% chance of dropset for last exercise of the muscle group
                if technique_roll < 0.3:
                    technique_type = "dropset"
                    execution_instructions = "Reduza a carga em 20-30% a cada drop. Faça 2-3 drops."
                # 20% chance of bi-set (need 2+ exercises)
                elif technique_roll < 0.5 and len(muscle_exercises) >= 2:
                    technique_type = "superset"
                    group_id = str(uuid_module.uuid4())
                # 15% chance of isometric hold
                elif technique_roll < 0.65:
                    technique_type = "normal"
                    isometric_seconds = random.choice([3, 5, 7])
                    execution_instructions = f"Pause por {isometric_seconds}s na contração máxima."
                # 10% chance of rest-pause
                elif technique_roll < 0.75:
                    technique_type = "rest_pause"
                    execution_instructions = "Faça até a falha, descanse 10-15s, repita 2-3 vezes."

            # For bi-set/tri-set, add multiple exercises with same group_id
            if technique_type == "superset" and len(muscle_exercises) >= 2:
                group_order = 0
                for ex in muscle_exercises[:2]:  # Bi-set = 2 exercises
                    selected.append({
                        "exercise_id": ex.id,
                        "name": ex.name,
                        "muscle_group": ex.muscle_group,
                        "sets": config["sets"],
                        "reps": config["reps"],
                        "rest_seconds": 0 if group_order < 1 else config["rest"],
                        "order": len(selected),
                        "reason": f"Bi-set para {muscle_name}",
                        "technique_type": technique_type,
                        "exercise_group_id": group_id,
                        "exercise_group_order": group_order,
                        "execution_instructions": "Sem descanso entre exercícios do bi-set.",
                        "isometric_seconds": None,
                    })
                    used_exercise_ids.add(ex.id)
                    group_order += 1
            else:
                # Normal or single-exercise technique
                for i, ex in enumerate(muscle_exercises[:exercises_per_muscle]):
                    # Apply technique only to last exercise of the muscle group
                    apply_technique = (i == exercises_per_muscle - 1) and technique_type != "normal"

                    selected.append({
                        "exercise_id": ex.id,
                        "name": ex.name,
                        "muscle_group": ex.muscle_group,
                        "sets": config["sets"],
                        "reps": config["reps"],
                        "rest_seconds": config["rest"],
                        "order": len(selected),
                        "reason": f"Exercício para {muscle_name}" + (f" com {technique_type}" if apply_technique else ""),
                        "technique_type": technique_type if apply_technique else "normal",
                        "exercise_group_id": None,
                        "exercise_group_order": 0,
                        "execution_instructions": execution_instructions if apply_technique else None,
                        "isometric_seconds": isometric_seconds if apply_technique and isometric_seconds else None,
                    })
                    used_exercise_ids.add(ex.id)

        return selected

    async def create_plan(
        self,
        created_by_id: uuid.UUID,
        name: str,
        goal: WorkoutGoal = WorkoutGoal.HYPERTROPHY,
        difficulty: Difficulty = Difficulty.INTERMEDIATE,
        split_type: SplitType = SplitType.ABC,
        description: str | None = None,
        duration_weeks: int | None = None,
        target_workout_minutes: int | None = None,
        is_template: bool = False,
        is_public: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> TrainingPlan:
        """Create a new training plan."""
        plan = TrainingPlan(
            name=name,
            description=description,
            goal=goal,
            difficulty=difficulty,
            split_type=split_type,
            duration_weeks=duration_weeks,
            target_workout_minutes=target_workout_minutes,
            is_template=is_template,
            is_public=is_public,
            created_by_id=created_by_id,
            organization_id=organization_id,
        )
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def update_plan(
        self,
        plan: TrainingPlan,
        name: str | None = None,
        description: str | None = None,
        goal: WorkoutGoal | None = None,
        difficulty: Difficulty | None = None,
        split_type: SplitType | None = None,
        duration_weeks: int | None = None,
        clear_duration_weeks: bool = False,
        target_workout_minutes: int | None = None,
        is_template: bool | None = None,
        is_public: bool | None = None,
        # Diet fields
        include_diet: bool | None = None,
        diet_type: str | None = None,
        daily_calories: int | None = None,
        protein_grams: int | None = None,
        carbs_grams: int | None = None,
        fat_grams: int | None = None,
        meals_per_day: int | None = None,
        diet_notes: str | None = None,
    ) -> TrainingPlan:
        """Update a plan."""
        if name is not None:
            plan.name = name
        if description is not None:
            plan.description = description
        if goal is not None:
            plan.goal = goal
        if difficulty is not None:
            plan.difficulty = difficulty
        if split_type is not None:
            plan.split_type = split_type
        if clear_duration_weeks:
            plan.duration_weeks = None
        elif duration_weeks is not None:
            plan.duration_weeks = duration_weeks
        if target_workout_minutes is not None:
            plan.target_workout_minutes = target_workout_minutes
        if is_template is not None:
            plan.is_template = is_template
        if is_public is not None:
            plan.is_public = is_public
        # Diet fields
        if include_diet is not None:
            plan.include_diet = include_diet
        if diet_type is not None:
            plan.diet_type = diet_type
        if daily_calories is not None:
            plan.daily_calories = daily_calories
        if protein_grams is not None:
            plan.protein_grams = protein_grams
        if carbs_grams is not None:
            plan.carbs_grams = carbs_grams
        if fat_grams is not None:
            plan.fat_grams = fat_grams
        if meals_per_day is not None:
            plan.meals_per_day = meals_per_day
        if diet_notes is not None:
            plan.diet_notes = diet_notes

        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def delete_plan(self, plan: TrainingPlan) -> None:
        """Delete a plan."""
        await self.db.delete(plan)
        await self.db.commit()

    async def add_workout_to_plan(
        self,
        plan_id: uuid.UUID,
        workout_id: uuid.UUID,
        label: str = "A",
        order: int = 0,
        day_of_week: int | None = None,
    ) -> PlanWorkout:
        """Add a workout to a plan."""
        plan_workout = PlanWorkout(
            plan_id=plan_id,
            workout_id=workout_id,
            label=label,
            order=order,
            day_of_week=day_of_week,
        )
        self.db.add(plan_workout)
        await self.db.commit()
        await self.db.refresh(plan_workout)
        return plan_workout

    async def remove_workout_from_plan(
        self,
        plan_workout_id: uuid.UUID,
    ) -> None:
        """Remove a workout from a plan."""
        result = await self.db.execute(
            select(PlanWorkout).where(PlanWorkout.id == plan_workout_id)
        )
        plan_workout = result.scalar_one_or_none()
        if plan_workout:
            await self.db.delete(plan_workout)
            await self.db.commit()

    async def duplicate_plan(
        self,
        plan: TrainingPlan,
        new_owner_id: uuid.UUID,
        new_name: str | None = None,
        duplicate_workouts: bool = True,
        source_template_id: uuid.UUID | None = None,
    ) -> TrainingPlan:
        """Duplicate a plan for another user.

        Args:
            source_template_id: If provided, marks this as an import from catalog.
                               Pass the original plan's ID to track the import origin.
        """
        # Generate a numbered name if no custom name provided
        if not new_name:
            existing_plans = await self.list_plans(
                user_id=new_owner_id,
                limit=500,
            )
            existing_names = [p.name for p in existing_plans]
            new_name = self._get_next_copy_name(plan.name, existing_names)

        new_plan = TrainingPlan(
            name=new_name,
            description=plan.description,
            goal=plan.goal,
            difficulty=plan.difficulty,
            split_type=plan.split_type,
            duration_weeks=plan.duration_weeks,
            # Copy diet configuration
            include_diet=plan.include_diet,
            diet_type=plan.diet_type,
            daily_calories=plan.daily_calories,
            protein_grams=plan.protein_grams,
            carbs_grams=plan.carbs_grams,
            fat_grams=plan.fat_grams,
            meals_per_day=plan.meals_per_day,
            diet_notes=plan.diet_notes,
            # Flags
            is_template=False,
            is_public=False,
            created_by_id=new_owner_id,
            source_template_id=source_template_id,  # Track import origin if provided
        )
        self.db.add(new_plan)
        await self.db.flush()

        # Copy plan workouts (and optionally duplicate workouts)
        for pw in plan.plan_workouts:
            if duplicate_workouts:
                # Duplicate the workout itself (keeping the original name)
                new_workout = await self.duplicate_workout(
                    pw.workout,
                    new_owner_id,
                    new_name=pw.workout.name,
                )
                workout_id = new_workout.id
            else:
                # Reference the same workout
                workout_id = pw.workout_id

            new_pw = PlanWorkout(
                plan_id=new_plan.id,
                workout_id=workout_id,
                label=pw.label,
                order=pw.order,
                day_of_week=pw.day_of_week,
            )
            self.db.add(new_pw)

        await self.db.commit()
        await self.db.refresh(new_plan)
        return new_plan

    # Plan assignment operations

    async def get_plan_assignment_by_id(
        self,
        assignment_id: uuid.UUID,
    ) -> PlanAssignment | None:
        """Get a plan assignment by ID."""
        result = await self.db.execute(
            select(PlanAssignment)
            .where(PlanAssignment.id == assignment_id)
            .options(selectinload(PlanAssignment.plan))
        )
        return result.scalar_one_or_none()

    async def list_student_plan_assignments(
        self,
        student_id: uuid.UUID,
        active_only: bool = True,
        prescribed_only: bool = True,
        organization_id: uuid.UUID | None = None,
    ) -> list[PlanAssignment]:
        """List plan assignments for a student.

        When active_only=True, only returns assignments that are both:
        - is_active == True
        - status == ACCEPTED (student has accepted the plan)

        When prescribed_only=True (default), only returns assignments where
        trainer_id != student_id, meaning only plans prescribed by a trainer
        (not self-assigned plans).

        When organization_id is provided, only returns assignments from that
        organization (useful when student has multiple trainers).
        """
        query = select(PlanAssignment).where(
            PlanAssignment.student_id == student_id
        ).options(
            selectinload(PlanAssignment.plan)
            .selectinload(TrainingPlan.plan_workouts)
            .selectinload(PlanWorkout.workout)
            .selectinload(Workout.exercises)
        )

        # Filter to only show plans prescribed by trainers (not self-assigned)
        if prescribed_only:
            query = query.where(PlanAssignment.trainer_id != student_id)

        # Filter by organization (when student has multiple trainers)
        if organization_id:
            query = query.where(PlanAssignment.organization_id == organization_id)

        if active_only:
            query = query.where(
                PlanAssignment.is_active == True,
                # Include both pending and accepted assignments
                PlanAssignment.status.in_([AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]),
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_trainer_plan_assignments(
        self,
        trainer_id: uuid.UUID,
        active_only: bool = True,
        student_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> list[PlanAssignment]:
        """List plan assignments created by a trainer.

        Args:
            trainer_id: The trainer's user ID
            active_only: If True, only return active assignments
            student_id: If provided, filter by specific student
            organization_id: If provided, filter by organization
        """
        query = select(PlanAssignment).where(
            PlanAssignment.trainer_id == trainer_id
        ).options(
            selectinload(PlanAssignment.plan)
            .selectinload(TrainingPlan.plan_workouts)
            .selectinload(PlanWorkout.workout)
            .selectinload(Workout.exercises)
        )

        if student_id:
            query = query.where(PlanAssignment.student_id == student_id)

        if organization_id:
            query = query.where(PlanAssignment.organization_id == organization_id)

        if active_only:
            query = query.where(PlanAssignment.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _create_plan_snapshot(self, plan: TrainingPlan) -> dict:
        """Create a complete snapshot of a plan for independent prescription.

        This creates an isolated copy of all plan data so that later changes
        to the original plan don't affect students who already have this prescription.
        """
        snapshot = {
            "id": str(plan.id),
            "name": plan.name,
            "description": plan.description,
            "goal": plan.goal.value if plan.goal else None,
            "difficulty": plan.difficulty.value if plan.difficulty else None,
            "split_type": plan.split_type.value if plan.split_type else None,
            "duration_weeks": plan.duration_weeks,
            "target_workout_minutes": plan.target_workout_minutes,
            # Diet configuration
            "include_diet": plan.include_diet,
            "diet_type": plan.diet_type,
            "daily_calories": plan.daily_calories,
            "protein_grams": plan.protein_grams,
            "carbs_grams": plan.carbs_grams,
            "fat_grams": plan.fat_grams,
            "meals_per_day": plan.meals_per_day,
            "diet_notes": plan.diet_notes,
            # Snapshot metadata
            "snapshot_created_at": datetime.now(timezone.utc).isoformat(),
            # Workouts with exercises
            "workouts": [],
        }

        for pw in plan.plan_workouts:
            workout = pw.workout
            workout_snapshot = {
                "id": str(workout.id),
                "name": workout.name,
                "description": workout.description,
                "difficulty": workout.difficulty.value if workout.difficulty else None,
                "estimated_duration_min": workout.estimated_duration_min,
                "target_muscles": workout.target_muscles,
                "tags": workout.tags,
                "label": pw.label,
                "order": pw.order,
                "day_of_week": pw.day_of_week,
                "exercises": [],
            }

            for we in workout.exercises:
                exercise_snapshot = {
                    "id": str(we.id),
                    "exercise_id": str(we.exercise_id),
                    "order": we.order,
                    "sets": we.sets,
                    "reps": we.reps,
                    "rest_seconds": we.rest_seconds,
                    "notes": we.notes,
                    # Advanced technique fields
                    "technique_type": we.technique_type.value if we.technique_type else None,
                    "exercise_group_id": str(we.exercise_group_id) if we.exercise_group_id else None,
                    "exercise_group_order": we.exercise_group_order,
                    "execution_instructions": we.execution_instructions,
                    "drop_set_drops": we.drop_set_drops,
                    "rest_pause_rests": we.rest_pause_rests,
                    "cluster_reps": we.cluster_reps,
                    "cluster_rest": we.cluster_rest,
                    "isometric_seconds": we.isometric_seconds,
                    # Exercise mode and aerobic fields
                    "exercise_mode": we.exercise_mode.value if we.exercise_mode else None,
                    "duration_minutes": we.duration_minutes,
                    "distance_meters": we.distance_meters,
                    "work_seconds": we.work_seconds,
                    "rest_interval_seconds": we.rest_interval_seconds,
                    "intervals": we.intervals,
                    "target_calories": we.target_calories,
                    "target_heart_rate_min": we.target_heart_rate_min,
                    "target_heart_rate_max": we.target_heart_rate_max,
                    "target_pace_min_per_km": we.target_pace_min_per_km,
                    "intensity_level": we.intensity_level,
                    "hold_seconds": we.hold_seconds,
                    # Exercise info (denormalized for offline/display)
                    "exercise": {
                        "id": str(we.exercise.id),
                        "name": we.exercise.name,
                        "muscle_group": we.exercise.muscle_group.value if we.exercise.muscle_group else None,
                        "equipment": we.exercise.equipment,
                        "video_url": we.exercise.video_url,
                        "image_url": we.exercise.image_url,
                    } if we.exercise else None,
                }
                workout_snapshot["exercises"].append(exercise_snapshot)

            snapshot["workouts"].append(workout_snapshot)

        return snapshot

    async def create_plan_assignment(
        self,
        plan_id: uuid.UUID,
        student_id: uuid.UUID,
        trainer_id: uuid.UUID,
        start_date: date,
        end_date: date | None = None,
        notes: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> PlanAssignment:
        """Create a plan assignment with independent copy.

        Plans are auto-accepted (no approval workflow). The student will
        receive a notification and can acknowledge they've seen it.

        Creates an independent snapshot of the plan data so that later
        modifications to the original plan don't affect this prescription.
        """
        # Load plan with full data for snapshot
        plan = await self.get_plan_by_id(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        # Create independent snapshot
        plan_snapshot = self._create_plan_snapshot(plan)

        assignment = PlanAssignment(
            plan_id=plan_id,
            student_id=student_id,
            trainer_id=trainer_id,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
            organization_id=organization_id,
            # Auto-accept: no approval workflow needed
            status=AssignmentStatus.ACCEPTED,
            accepted_at=datetime.now(timezone.utc),
            # Store independent copy of plan data
            plan_snapshot=plan_snapshot,
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def acknowledge_plan_assignment(
        self,
        assignment: PlanAssignment,
    ) -> PlanAssignment:
        """Mark a plan assignment as acknowledged by the student."""
        assignment.acknowledged_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def update_plan_assignment(
        self,
        assignment: PlanAssignment,
        start_date: date | None = None,
        end_date: date | None = None,
        is_active: bool | None = None,
        notes: str | None = None,
    ) -> PlanAssignment:
        """Update a plan assignment."""
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

    # Co-Training operations

    async def trainer_join_session(
        self,
        session: WorkoutSession,
        trainer_id: uuid.UUID,
    ) -> WorkoutSession:
        """Trainer joins a session for co-training."""
        session.trainer_id = trainer_id
        session.is_shared = True
        if session.status == SessionStatus.WAITING:
            session.status = SessionStatus.ACTIVE

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def trainer_leave_session(
        self,
        session: WorkoutSession,
    ) -> WorkoutSession:
        """Trainer leaves a co-training session."""
        session.trainer_id = None
        session.is_shared = False

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def update_session_status(
        self,
        session: WorkoutSession,
        status: SessionStatus,
    ) -> WorkoutSession:
        """Update session status."""
        session.status = status

        if status == SessionStatus.COMPLETED:
            session.completed_at = datetime.now(timezone.utc)
            if session.started_at:
                delta = session.completed_at - session.started_at
                session.duration_minutes = int(delta.total_seconds() / 60)

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def create_trainer_adjustment(
        self,
        session_id: uuid.UUID,
        trainer_id: uuid.UUID,
        exercise_id: uuid.UUID,
        set_number: int | None = None,
        suggested_weight_kg: float | None = None,
        suggested_reps: int | None = None,
        note: str | None = None,
    ) -> TrainerAdjustment:
        """Create a trainer adjustment during co-training."""
        adjustment = TrainerAdjustment(
            session_id=session_id,
            trainer_id=trainer_id,
            exercise_id=exercise_id,
            set_number=set_number,
            suggested_weight_kg=suggested_weight_kg,
            suggested_reps=suggested_reps,
            note=note,
        )
        self.db.add(adjustment)
        await self.db.commit()
        await self.db.refresh(adjustment)
        return adjustment

    async def create_session_message(
        self,
        session_id: uuid.UUID,
        sender_id: uuid.UUID,
        message: str,
    ) -> SessionMessage:
        """Create a message during co-training session."""
        session_message = SessionMessage(
            session_id=session_id,
            sender_id=sender_id,
            message=message,
        )
        self.db.add(session_message)
        await self.db.commit()
        await self.db.refresh(session_message)
        return session_message

    async def list_session_messages(
        self,
        session_id: uuid.UUID,
        limit: int = 50,
    ) -> list[SessionMessage]:
        """List messages from a session."""
        query = (
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .options(selectinload(SessionMessage.sender))
            .order_by(SessionMessage.sent_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        return list(reversed(messages))  # Return oldest first

    async def list_active_sessions(
        self,
        trainer_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> list[ActiveSessionResponse]:
        """List active sessions for students (trainer view)."""
        from src.domains.organizations.models import OrganizationMembership
        from src.domains.users.models import User, UserRole

        # Get students that this trainer can see
        students_query = (
            select(User.id, User.name, User.avatar_url)
            .join(
                OrganizationMembership,
                OrganizationMembership.user_id == User.id,
            )
            .where(
                and_(
                    OrganizationMembership.role == UserRole.STUDENT,
                    OrganizationMembership.is_active == True,
                )
            )
        )

        if organization_id:
            students_query = students_query.where(
                OrganizationMembership.organization_id == organization_id
            )

        students_result = await self.db.execute(students_query)
        student_data = {row[0]: {"name": row[1], "avatar_url": row[2]} for row in students_result.all()}

        if not student_data:
            return []

        # Get active sessions for these students
        sessions_query = (
            select(WorkoutSession)
            .where(
                and_(
                    WorkoutSession.user_id.in_(student_data.keys()),
                    WorkoutSession.status.in_([SessionStatus.WAITING, SessionStatus.ACTIVE, SessionStatus.PAUSED]),
                    WorkoutSession.completed_at.is_(None),
                )
            )
            .options(
                selectinload(WorkoutSession.workout).selectinload(Workout.exercises),
                selectinload(WorkoutSession.sets),
            )
            .order_by(WorkoutSession.started_at.desc())
        )

        sessions_result = await self.db.execute(sessions_query)
        sessions = sessions_result.scalars().all()

        return [
            ActiveSessionResponse(
                id=s.id,
                workout_id=s.workout_id,
                workout_name=s.workout.name if s.workout else "",
                user_id=s.user_id,
                student_name=student_data.get(s.user_id, {}).get("name", ""),
                student_avatar=student_data.get(s.user_id, {}).get("avatar_url"),
                trainer_id=s.trainer_id,
                is_shared=s.is_shared,
                status=s.status,
                started_at=s.started_at,
                total_exercises=len(s.workout.exercises) if s.workout else 0,
                completed_sets=len(s.sets) if s.sets else 0,
            )
            for s in sessions
        ]

    # Prescription Note operations

    async def create_prescription_note(
        self,
        context_type: NoteContextType,
        context_id: uuid.UUID,
        author_id: uuid.UUID,
        author_role: NoteAuthorRole,
        content: str,
        is_pinned: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> PrescriptionNote:
        """Create a new prescription note."""
        note = PrescriptionNote(
            context_type=context_type,
            context_id=context_id,
            author_id=author_id,
            author_role=author_role,
            content=content,
            is_pinned=is_pinned,
            organization_id=organization_id,
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def get_prescription_note_by_id(
        self,
        note_id: uuid.UUID,
    ) -> PrescriptionNote | None:
        """Get a prescription note by ID."""
        result = await self.db.execute(
            select(PrescriptionNote)
            .where(PrescriptionNote.id == note_id)
            .options(selectinload(PrescriptionNote.author))
        )
        return result.scalar_one_or_none()

    async def list_prescription_notes(
        self,
        context_type: NoteContextType,
        context_id: uuid.UUID,
        include_children: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> list[PrescriptionNote]:
        """List prescription notes for a given context.

        Args:
            context_type: Type of context (plan, workout, exercise, session)
            context_id: ID of the context object
            include_children: If True and context_type is 'plan', also include workout/exercise notes
            organization_id: Optional org filter
        """
        query = (
            select(PrescriptionNote)
            .where(
                and_(
                    PrescriptionNote.context_type == context_type,
                    PrescriptionNote.context_id == context_id,
                )
            )
            .options(selectinload(PrescriptionNote.author))
            .order_by(PrescriptionNote.is_pinned.desc(), PrescriptionNote.created_at.desc())
        )

        if organization_id:
            query = query.where(PrescriptionNote.organization_id == organization_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_notes_for_student(
        self,
        student_id: uuid.UUID,
        context_type: NoteContextType | None = None,
        unread_only: bool = False,
        limit: int = 50,
    ) -> list[PrescriptionNote]:
        """List notes relevant to a student (notes from trainers on their assignments).

        SECURITY FIX: VULN-6 - Now properly filters notes based on student access.
        Only returns notes on contexts the student has access to:
        - SESSION: Sessions where student is the user_id
        - PLAN: Plans assigned to the student via WorkoutAssignment
        - WORKOUT: Workouts assigned to the student
        - EXERCISE: Workout exercises in workouts assigned to the student
        """
        # Build subqueries to find context_ids the student has access to
        # For SESSION context: sessions where user_id == student_id
        session_ids_subquery = (
            select(WorkoutSession.id)
            .where(WorkoutSession.user_id == student_id)
        ).scalar_subquery()

        # For WORKOUT context: workouts assigned to the student
        workout_assignment_ids_subquery = (
            select(WorkoutAssignment.workout_id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

        # For PLAN context: plans with assignments to the student
        plan_ids_subquery = (
            select(TrainingPlan.id)
            .join(WorkoutAssignment, WorkoutAssignment.plan_id == TrainingPlan.id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

        # For EXERCISE context: workout_exercises in workouts assigned to the student
        exercise_ids_subquery = (
            select(WorkoutExercise.id)
            .join(Workout, WorkoutExercise.workout_id == Workout.id)
            .join(WorkoutAssignment, WorkoutAssignment.workout_id == Workout.id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

        # Build the main query with OR conditions for each context type
        access_conditions = or_(
            and_(
                PrescriptionNote.context_type == NoteContextType.SESSION,
                PrescriptionNote.context_id.in_(session_ids_subquery),
            ),
            and_(
                PrescriptionNote.context_type == NoteContextType.WORKOUT,
                PrescriptionNote.context_id.in_(workout_assignment_ids_subquery),
            ),
            and_(
                PrescriptionNote.context_type == NoteContextType.PLAN,
                PrescriptionNote.context_id.in_(plan_ids_subquery),
            ),
            and_(
                PrescriptionNote.context_type == NoteContextType.EXERCISE,
                PrescriptionNote.context_id.in_(exercise_ids_subquery),
            ),
        )

        query = (
            select(PrescriptionNote)
            .where(
                PrescriptionNote.author_role == NoteAuthorRole.TRAINER,
                access_conditions,
            )
            .options(selectinload(PrescriptionNote.author))
            .order_by(PrescriptionNote.is_pinned.desc(), PrescriptionNote.created_at.desc())
            .limit(limit)
        )

        if context_type:
            query = query.where(PrescriptionNote.context_type == context_type)

        if unread_only:
            query = query.where(PrescriptionNote.read_at.is_(None))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_prescription_note(
        self,
        note: PrescriptionNote,
        content: str | None = None,
        is_pinned: bool | None = None,
    ) -> PrescriptionNote:
        """Update a prescription note."""
        if content is not None:
            note.content = content
        if is_pinned is not None:
            note.is_pinned = is_pinned

        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def mark_note_as_read(
        self,
        note: PrescriptionNote,
        user_id: uuid.UUID,
    ) -> PrescriptionNote:
        """Mark a note as read by a user."""
        note.read_at = datetime.now(timezone.utc)
        note.read_by_id = user_id
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def delete_prescription_note(
        self,
        note: PrescriptionNote,
    ) -> None:
        """Delete a prescription note."""
        await self.db.delete(note)
        await self.db.commit()

    async def count_unread_notes(
        self,
        context_type: NoteContextType,
        context_id: uuid.UUID,
        for_role: NoteAuthorRole,
    ) -> int:
        """Count unread notes for a given context.

        Args:
            context_type: Type of context
            context_id: ID of the context
            for_role: The role of the person counting (e.g., STUDENT counts TRAINER notes)
        """
        # A student would count unread trainer notes, and vice versa
        author_role_to_count = (
            NoteAuthorRole.TRAINER if for_role == NoteAuthorRole.STUDENT else NoteAuthorRole.STUDENT
        )

        query = select(PrescriptionNote).where(
            and_(
                PrescriptionNote.context_type == context_type,
                PrescriptionNote.context_id == context_id,
                PrescriptionNote.author_role == author_role_to_count,
                PrescriptionNote.read_at.is_(None),
            )
        )

        result = await self.db.execute(query)
        return len(result.scalars().all())

    async def validate_context_access(
        self,
        context_type: NoteContextType,
        context_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        """Validate if a user has access to a given context.

        Returns True if user can access the context, False otherwise.

        Access rules:
        - PLAN: User is the creator OR has an active assignment
        - WORKOUT: User is the creator OR has an active assignment
        - SESSION: User is the session owner OR the trainer
        - EXERCISE: Always accessible (exercises are reference data)
        """
        if context_type == NoteContextType.EXERCISE:
            # Exercises are reference data, always accessible
            return True

        if context_type == NoteContextType.PLAN:
            # Check if user created the plan
            plan = await self.get_plan_by_id(context_id)
            if plan and plan.created_by_id == user_id:
                return True

            # Check if user has an assignment to this plan
            query = select(PlanAssignment).where(
                and_(
                    PlanAssignment.plan_id == context_id,
                    or_(
                        PlanAssignment.student_id == user_id,
                        PlanAssignment.trainer_id == user_id,
                    ),
                    PlanAssignment.is_active == True,
                )
            )
            result = await self.db.execute(query)
            assignment = result.scalar_one_or_none()
            return assignment is not None

        if context_type == NoteContextType.WORKOUT:
            # Check if user created the workout
            workout = await self.get_workout_by_id(context_id)
            if workout and workout.created_by_id == user_id:
                return True

            # Check if user has an assignment to this workout
            query = select(WorkoutAssignment).where(
                and_(
                    WorkoutAssignment.workout_id == context_id,
                    or_(
                        WorkoutAssignment.student_id == user_id,
                        WorkoutAssignment.trainer_id == user_id,
                    ),
                )
            )
            result = await self.db.execute(query)
            assignment = result.scalar_one_or_none()
            return assignment is not None

        if context_type == NoteContextType.SESSION:
            # Check if user is session owner or trainer
            session = await self.get_session_by_id(context_id)
            if session:
                return session.user_id == user_id or session.trainer_id == user_id
            return False

        return False

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
        # Get sessions where the trainer has access
        # For now, filter by organization or student directly
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
