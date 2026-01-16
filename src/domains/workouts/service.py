"""Workout service with database operations."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.workouts.models import (
    Difficulty,
    Exercise,
    MuscleGroup,
    ProgramAssignment,
    ProgramWorkout,
    SplitType,
    Workout,
    WorkoutAssignment,
    WorkoutExercise,
    WorkoutGoal,
    WorkoutProgram,
    WorkoutSession,
    WorkoutSessionSet,
)


class WorkoutService:
    """Service for handling workout operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

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
        """Delete a workout."""
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
        new_workout = Workout(
            name=new_name or f"Copy of {workout.name}",
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
    ) -> WorkoutSession:
        """Start a new workout session."""
        session = WorkoutSession(
            workout_id=workout_id,
            user_id=user_id,
            assignment_id=assignment_id,
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
        session.completed_at = datetime.utcnow()
        if session.started_at:
            delta = session.completed_at - session.started_at
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

    # Program operations

    async def get_program_by_id(self, program_id: uuid.UUID) -> WorkoutProgram | None:
        """Get a program by ID with workouts."""
        result = await self.db.execute(
            select(WorkoutProgram)
            .where(WorkoutProgram.id == program_id)
            .options(
                selectinload(WorkoutProgram.program_workouts)
                .selectinload(ProgramWorkout.workout)
                .selectinload(Workout.exercises)
                .selectinload(WorkoutExercise.exercise)
            )
        )
        return result.scalar_one_or_none()

    async def list_programs(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        templates_only: bool = False,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkoutProgram]:
        """List programs for a user."""
        query = select(WorkoutProgram).options(
            selectinload(WorkoutProgram.program_workouts)
        )

        if templates_only:
            # Show public templates + user's own templates
            conditions = [
                and_(WorkoutProgram.is_template == True, WorkoutProgram.is_public == True),
                and_(WorkoutProgram.created_by_id == user_id, WorkoutProgram.is_template == True),
            ]
            if organization_id:
                conditions.append(
                    and_(WorkoutProgram.organization_id == organization_id, WorkoutProgram.is_template == True)
                )
            query = query.where(or_(*conditions))
        else:
            # Show only user's own programs (not templates from others)
            conditions = [WorkoutProgram.created_by_id == user_id]
            if organization_id:
                conditions.append(WorkoutProgram.organization_id == organization_id)
            query = query.where(or_(*conditions))

        if search:
            query = query.where(WorkoutProgram.name.ilike(f"%{search}%"))

        query = query.order_by(WorkoutProgram.created_at.desc()).limit(limit).offset(offset)
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
            select(WorkoutProgram, User.name.label("creator_name"))
            .join(User, WorkoutProgram.created_by_id == User.id, isouter=True)
            .options(selectinload(WorkoutProgram.program_workouts))
            .where(
                WorkoutProgram.is_template == True,
                WorkoutProgram.is_public == True,
                WorkoutProgram.created_by_id != exclude_user_id,
            )
        )

        if search:
            query = query.where(WorkoutProgram.name.ilike(f"%{search}%"))
        if goal:
            query = query.where(WorkoutProgram.goal == goal)
        if difficulty:
            query = query.where(WorkoutProgram.difficulty == difficulty)
        if split_type:
            query = query.where(WorkoutProgram.split_type == split_type)

        query = query.order_by(WorkoutProgram.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)

        templates = []
        for row in result.all():
            program = row[0]
            creator_name = row[1]
            templates.append({
                "id": program.id,
                "name": program.name,
                "goal": program.goal,
                "difficulty": program.difficulty,
                "split_type": program.split_type,
                "duration_weeks": program.duration_weeks,
                "workout_count": len(program.program_workouts),
                "creator_name": creator_name,
                "created_at": program.created_at,
            })
        return templates

    async def generate_program_with_ai(
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
        """Generate a workout program structure using AI/rules-based logic."""
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
            })

        # Generate program name
        goal_names = {
            WorkoutGoal.HYPERTROPHY: "Hipertrofia",
            WorkoutGoal.STRENGTH: "Força",
            WorkoutGoal.FAT_LOSS: "Emagrecimento",
            WorkoutGoal.ENDURANCE: "Resistência",
            WorkoutGoal.GENERAL_FITNESS: "Condicionamento",
            WorkoutGoal.SPORT_SPECIFIC: "Desempenho",
        }
        program_name = f"Programa {goal_names.get(goal, 'Treino')} {days_per_week}x"

        return {
            "name": program_name,
            "description": f"Programa de {duration_weeks} semanas focado em {goal_names.get(goal, 'treino').lower()}.",
            "goal": goal,
            "difficulty": difficulty,
            "split_type": split_type,
            "duration_weeks": duration_weeks,
            "workouts": workouts,
            "message": "Programa gerado com base nas suas preferências. Revise os treinos e faça ajustes conforme necessário.",
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
            return SplitType.PPL

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
            SplitType.PPL: [
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
                "back": [MuscleGroup.LOWER_BACK, MuscleGroup.LATS, MuscleGroup.TRAPS],
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
            "back": MuscleGroup.LATS,
            "shoulders": MuscleGroup.SHOULDERS,
            "legs": MuscleGroup.QUADRICEPS,
            "glutes": MuscleGroup.GLUTES,
            "calves": MuscleGroup.CALVES,
            "arms": MuscleGroup.BICEPS,
            "biceps": MuscleGroup.BICEPS,
            "triceps": MuscleGroup.TRICEPS,
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
            WorkoutGoal.SPORT_SPECIFIC: {"sets": 4, "reps": "6-10", "rest": 90},
        }
        config = goal_config.get(goal, goal_config[WorkoutGoal.GENERAL_FITNESS])

        selected = []
        exercises_per_muscle = max(1, exercises_per_workout // len(target_muscles))

        for muscle_name in target_muscles:
            muscle_group = muscle_mapping.get(muscle_name)
            if not muscle_group:
                continue

            # Find exercises for this muscle group
            muscle_exercises = [
                ex for ex in available_exercises
                if ex.muscle_group == muscle_group
            ]

            # Select exercises (randomize in production, for now take first N)
            import random
            if muscle_exercises:
                random.shuffle(muscle_exercises)
                for ex in muscle_exercises[:exercises_per_muscle]:
                    selected.append({
                        "exercise_id": ex.id,
                        "name": ex.name,
                        "muscle_group": ex.muscle_group,
                        "sets": config["sets"],
                        "reps": config["reps"],
                        "rest_seconds": config["rest"],
                        "order": len(selected),
                        "reason": f"Exercício para {muscle_name}",
                    })

        return selected

    async def create_program(
        self,
        created_by_id: uuid.UUID,
        name: str,
        goal: WorkoutGoal = WorkoutGoal.HYPERTROPHY,
        difficulty: Difficulty = Difficulty.INTERMEDIATE,
        split_type: SplitType = SplitType.ABC,
        description: str | None = None,
        duration_weeks: int | None = None,
        is_template: bool = False,
        is_public: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> WorkoutProgram:
        """Create a new workout program."""
        program = WorkoutProgram(
            name=name,
            description=description,
            goal=goal,
            difficulty=difficulty,
            split_type=split_type,
            duration_weeks=duration_weeks,
            is_template=is_template,
            is_public=is_public,
            created_by_id=created_by_id,
            organization_id=organization_id,
        )
        self.db.add(program)
        await self.db.commit()
        await self.db.refresh(program)
        return program

    async def update_program(
        self,
        program: WorkoutProgram,
        name: str | None = None,
        description: str | None = None,
        goal: WorkoutGoal | None = None,
        difficulty: Difficulty | None = None,
        split_type: SplitType | None = None,
        duration_weeks: int | None = None,
        is_template: bool | None = None,
        is_public: bool | None = None,
    ) -> WorkoutProgram:
        """Update a program."""
        if name is not None:
            program.name = name
        if description is not None:
            program.description = description
        if goal is not None:
            program.goal = goal
        if difficulty is not None:
            program.difficulty = difficulty
        if split_type is not None:
            program.split_type = split_type
        if duration_weeks is not None:
            program.duration_weeks = duration_weeks
        if is_template is not None:
            program.is_template = is_template
        if is_public is not None:
            program.is_public = is_public

        await self.db.commit()
        await self.db.refresh(program)
        return program

    async def delete_program(self, program: WorkoutProgram) -> None:
        """Delete a program."""
        await self.db.delete(program)
        await self.db.commit()

    async def add_workout_to_program(
        self,
        program_id: uuid.UUID,
        workout_id: uuid.UUID,
        label: str = "A",
        order: int = 0,
        day_of_week: int | None = None,
    ) -> ProgramWorkout:
        """Add a workout to a program."""
        program_workout = ProgramWorkout(
            program_id=program_id,
            workout_id=workout_id,
            label=label,
            order=order,
            day_of_week=day_of_week,
        )
        self.db.add(program_workout)
        await self.db.commit()
        await self.db.refresh(program_workout)
        return program_workout

    async def remove_workout_from_program(
        self,
        program_workout_id: uuid.UUID,
    ) -> None:
        """Remove a workout from a program."""
        result = await self.db.execute(
            select(ProgramWorkout).where(ProgramWorkout.id == program_workout_id)
        )
        program_workout = result.scalar_one_or_none()
        if program_workout:
            await self.db.delete(program_workout)
            await self.db.commit()

    async def duplicate_program(
        self,
        program: WorkoutProgram,
        new_owner_id: uuid.UUID,
        new_name: str | None = None,
        duplicate_workouts: bool = True,
    ) -> WorkoutProgram:
        """Duplicate a program for another user."""
        new_program = WorkoutProgram(
            name=new_name or f"Copy of {program.name}",
            description=program.description,
            goal=program.goal,
            difficulty=program.difficulty,
            split_type=program.split_type,
            duration_weeks=program.duration_weeks,
            is_template=False,
            is_public=False,
            created_by_id=new_owner_id,
        )
        self.db.add(new_program)
        await self.db.flush()

        # Copy program workouts (and optionally duplicate workouts)
        for pw in program.program_workouts:
            if duplicate_workouts:
                # Duplicate the workout itself
                new_workout = await self.duplicate_workout(
                    pw.workout,
                    new_owner_id,
                    new_name=None,
                )
                workout_id = new_workout.id
            else:
                # Reference the same workout
                workout_id = pw.workout_id

            new_pw = ProgramWorkout(
                program_id=new_program.id,
                workout_id=workout_id,
                label=pw.label,
                order=pw.order,
                day_of_week=pw.day_of_week,
            )
            self.db.add(new_pw)

        await self.db.commit()
        await self.db.refresh(new_program)
        return new_program

    # Program assignment operations

    async def get_program_assignment_by_id(
        self,
        assignment_id: uuid.UUID,
    ) -> ProgramAssignment | None:
        """Get a program assignment by ID."""
        result = await self.db.execute(
            select(ProgramAssignment)
            .where(ProgramAssignment.id == assignment_id)
            .options(selectinload(ProgramAssignment.program))
        )
        return result.scalar_one_or_none()

    async def list_student_program_assignments(
        self,
        student_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[ProgramAssignment]:
        """List program assignments for a student."""
        query = select(ProgramAssignment).where(
            ProgramAssignment.student_id == student_id
        ).options(
            selectinload(ProgramAssignment.program)
            .selectinload(WorkoutProgram.program_workouts)
        )

        if active_only:
            query = query.where(ProgramAssignment.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_trainer_program_assignments(
        self,
        trainer_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[ProgramAssignment]:
        """List program assignments created by a trainer."""
        query = select(ProgramAssignment).where(
            ProgramAssignment.trainer_id == trainer_id
        ).options(selectinload(ProgramAssignment.program))

        if active_only:
            query = query.where(ProgramAssignment.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_program_assignment(
        self,
        program_id: uuid.UUID,
        student_id: uuid.UUID,
        trainer_id: uuid.UUID,
        start_date: date,
        end_date: date | None = None,
        notes: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> ProgramAssignment:
        """Create a program assignment."""
        assignment = ProgramAssignment(
            program_id=program_id,
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

    async def update_program_assignment(
        self,
        assignment: ProgramAssignment,
        start_date: date | None = None,
        end_date: date | None = None,
        is_active: bool | None = None,
        notes: str | None = None,
    ) -> ProgramAssignment:
        """Update a program assignment."""
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
