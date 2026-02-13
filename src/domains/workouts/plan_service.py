"""Plan-related service operations (plans, assignments, versioning, notes, AI generation)."""
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
    ExerciseMode,
    MuscleGroup,
    NoteAuthorRole,
    NoteContextType,
    PlanAssignment,
    PlanVersion,
    PlanWorkout,
    PrescriptionNote,
    SplitType,
    TechniqueType,
    TrainingPlan,
    Workout,
    WorkoutAssignment,
    WorkoutExercise,
    WorkoutGoal,
    WorkoutSession,
)


class PlanServiceMixin:
    """Mixin providing plan-related operations for WorkoutService."""

    db: AsyncSession

    # These methods are defined on the main WorkoutService and needed here:
    # _strip_copy_prefixes, _get_next_copy_name, list_workouts, list_exercises, get_workout_by_id,
    # get_plan_by_id, get_session_by_id, list_plans, duplicate_workout

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
            # Show public templates + user's own templates scoped to org
            if organization_id:
                conditions = [
                    and_(TrainingPlan.is_template == True, TrainingPlan.is_public == True),  # noqa: E712
                    and_(
                        TrainingPlan.created_by_id == user_id,
                        TrainingPlan.is_template == True,  # noqa: E712
                        TrainingPlan.organization_id == organization_id,
                    ),
                ]
            else:
                conditions = [
                    and_(TrainingPlan.is_template == True, TrainingPlan.is_public == True),  # noqa: E712
                    and_(
                        TrainingPlan.created_by_id == user_id,
                        TrainingPlan.is_template == True,  # noqa: E712
                        TrainingPlan.organization_id.is_(None),
                    ),
                ]
            query = query.where(or_(*conditions))
        else:
            # Show only user's own plans scoped to org (strict isolation)
            if organization_id:
                query = query.where(
                    and_(
                        TrainingPlan.created_by_id == user_id,
                        TrainingPlan.organization_id == organization_id,
                    )
                )
            else:
                query = query.where(
                    and_(
                        TrainingPlan.created_by_id == user_id,
                        TrainingPlan.organization_id.is_(None),
                    )
                )

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
                TrainingPlan.is_template == True,  # noqa: E712
                TrainingPlan.is_public == True,  # noqa: E712
                or_(
                    TrainingPlan.created_by_id == None,  # System templates  # noqa: E711
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
            WorkoutGoal.STRENGTH: "Forca",
            WorkoutGoal.FAT_LOSS: "Emagrecimento",
            WorkoutGoal.ENDURANCE: "Resistencia",
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
            "message": "Plano gerado com base nas suas preferencias. Revise os treinos e faca ajustes conforme necessario.",
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
                {"label": "A", "name": "Treino Peito e Triceps", "muscles": ["chest", "triceps"]},
                {"label": "B", "name": "Treino Costas e Biceps", "muscles": ["back", "biceps"]},
                {"label": "C", "name": "Treino Pernas e Ombros", "muscles": ["legs", "shoulders"]},
            ],
            SplitType.ABCDE: [
                {"label": "A", "name": "Treino Peito", "muscles": ["chest"]},
                {"label": "B", "name": "Treino Costas", "muscles": ["back"]},
                {"label": "C", "name": "Treino Ombros", "muscles": ["shoulders"]},
                {"label": "D", "name": "Treino Pernas", "muscles": ["legs", "glutes"]},
                {"label": "E", "name": "Treino Bracos", "muscles": ["biceps", "triceps"]},
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
                    execution_instructions = "Reduza a carga em 20-30% a cada drop. Faca 2-3 drops."
                # 20% chance of bi-set (need 2+ exercises)
                elif technique_roll < 0.5 and len(muscle_exercises) >= 2:
                    technique_type = "superset"
                    group_id = str(uuid_module.uuid4())
                # 15% chance of isometric hold
                elif technique_roll < 0.65:
                    technique_type = "normal"
                    isometric_seconds = random.choice([3, 5, 7])
                    execution_instructions = f"Pause por {isometric_seconds}s na contracao maxima."
                # 10% chance of rest-pause
                elif technique_roll < 0.75:
                    technique_type = "rest_pause"
                    execution_instructions = "Faca ate a falha, descanse 10-15s, repita 2-3 vezes."

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
                        "execution_instructions": "Sem descanso entre exercicios do bi-set.",
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
                        "reason": f"Exercicio para {muscle_name}" + (f" com {technique_type}" if apply_technique else ""),
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
        organization_id: uuid.UUID | None = None,
    ) -> TrainingPlan:
        """Duplicate a plan for another user.

        Args:
            source_template_id: If provided, marks this as an import from catalog.
            organization_id: Organization to scope the new plan to.
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
            organization_id=organization_id,
            source_template_id=source_template_id,
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
                    organization_id=organization_id,
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
        """List plan assignments for a student."""
        query = select(PlanAssignment).where(
            PlanAssignment.student_id == student_id
        ).options(
            selectinload(PlanAssignment.plan)
            .selectinload(TrainingPlan.plan_workouts)
            .selectinload(PlanWorkout.workout)
            .selectinload(Workout.exercises)
        )

        if prescribed_only:
            query = query.where(PlanAssignment.trainer_id != student_id)

        if organization_id:
            query = query.where(PlanAssignment.organization_id == organization_id)

        if active_only:
            query = query.where(
                PlanAssignment.is_active == True,  # noqa: E712
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
        """List plan assignments created by a trainer."""
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
            query = query.where(PlanAssignment.is_active == True)  # noqa: E712

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _create_plan_snapshot(self, plan: TrainingPlan) -> dict:
        """Create a complete snapshot of a plan for independent prescription."""
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
                    "drop_count": we.drop_count,
                    "rest_between_drops": we.rest_between_drops,
                    "pause_duration": we.pause_duration,
                    "mini_set_count": we.mini_set_count,
                    "isometric_seconds": we.isometric_seconds,
                    # Exercise mode and aerobic fields
                    "exercise_mode": we.exercise_mode.value if we.exercise_mode else None,
                    "duration_minutes": we.duration_minutes,
                    "distance_km": we.distance_km,
                    "work_seconds": we.work_seconds,
                    "interval_rest_seconds": we.interval_rest_seconds,
                    "rounds": we.rounds,
                    "target_pace_min_per_km": we.target_pace_min_per_km,
                    "intensity": we.intensity,
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
        """Create a plan assignment with independent copy."""
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
            status=AssignmentStatus.ACCEPTED,
            accepted_at=datetime.now(timezone.utc),
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
        """List prescription notes for a given context."""
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
        """List notes relevant to a student (notes from trainers on their assignments)."""
        # Build subqueries to find context_ids the student has access to
        session_ids_subquery = (
            select(WorkoutSession.id)
            .where(WorkoutSession.user_id == student_id)
        ).scalar_subquery()

        workout_assignment_ids_subquery = (
            select(WorkoutAssignment.workout_id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

        plan_ids_subquery = (
            select(TrainingPlan.id)
            .join(WorkoutAssignment, WorkoutAssignment.plan_id == TrainingPlan.id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

        exercise_ids_subquery = (
            select(WorkoutExercise.id)
            .join(Workout, WorkoutExercise.workout_id == Workout.id)
            .join(WorkoutAssignment, WorkoutAssignment.workout_id == Workout.id)
            .where(WorkoutAssignment.student_id == student_id)
        ).scalar_subquery()

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
        """Count unread notes for a given context."""
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
        """Validate if a user has access to a given context."""
        if context_type == NoteContextType.EXERCISE:
            return True

        if context_type == NoteContextType.PLAN:
            plan = await self.get_plan_by_id(context_id)
            if plan and plan.created_by_id == user_id:
                return True

            query = select(PlanAssignment).where(
                and_(
                    PlanAssignment.plan_id == context_id,
                    or_(
                        PlanAssignment.student_id == user_id,
                        PlanAssignment.trainer_id == user_id,
                    ),
                    PlanAssignment.is_active == True,  # noqa: E712
                )
            )
            result = await self.db.execute(query)
            assignment = result.scalar_one_or_none()
            return assignment is not None

        if context_type == NoteContextType.WORKOUT:
            workout = await self.get_workout_by_id(context_id)
            if workout and workout.created_by_id == user_id:
                return True

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
            session = await self.get_session_by_id(context_id)
            if session:
                return session.user_id == user_id or session.trainer_id == user_id
            return False

        return False

    # Plan Versioning operations

    async def create_plan_version(
        self,
        assignment: PlanAssignment,
        changed_by_id: uuid.UUID,
        change_description: str | None = None,
    ) -> PlanVersion:
        """Create a new version record for a plan assignment."""
        if not assignment.plan_snapshot:
            return None

        version = PlanVersion(
            assignment_id=assignment.id,
            version=assignment.version,
            snapshot=assignment.plan_snapshot,
            changed_by_id=changed_by_id,
            change_description=change_description,
        )
        self.db.add(version)

        # Increment the version number on the assignment
        assignment.version += 1

        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def get_plan_versions(
        self,
        assignment_id: uuid.UUID,
    ) -> list[PlanVersion]:
        """Get all version history for a plan assignment."""
        result = await self.db.execute(
            select(PlanVersion)
            .where(PlanVersion.assignment_id == assignment_id)
            .options(selectinload(PlanVersion.changed_by))
            .order_by(PlanVersion.version.desc())
        )
        return list(result.scalars().all())

    async def get_plan_version(
        self,
        assignment_id: uuid.UUID,
        version: int,
    ) -> PlanVersion | None:
        """Get a specific version of a plan assignment."""
        result = await self.db.execute(
            select(PlanVersion)
            .where(
                PlanVersion.assignment_id == assignment_id,
                PlanVersion.version == version,
            )
            .options(selectinload(PlanVersion.changed_by))
        )
        return result.scalar_one_or_none()

    async def mark_version_viewed(
        self,
        assignment: PlanAssignment,
        version: int,
    ) -> PlanAssignment:
        """Mark that the student has viewed a specific version."""
        assignment.last_version_viewed = version
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def update_plan_snapshot(
        self,
        assignment: PlanAssignment,
        new_snapshot: dict,
        changed_by_id: uuid.UUID,
        change_description: str | None = None,
    ) -> PlanAssignment:
        """Update the plan snapshot and create a version record."""
        if assignment.plan_snapshot:
            await self.create_plan_version(
                assignment=assignment,
                changed_by_id=changed_by_id,
                change_description=change_description,
            )

        assignment.plan_snapshot = new_snapshot

        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    def compute_snapshot_diff(
        self,
        old_snapshot: dict,
        new_snapshot: dict,
    ) -> dict:
        """Compute the differences between two plan snapshots."""
        diff = {
            "plan_changes": [],
            "workout_changes": [],
            "exercise_changes": [],
        }

        if not old_snapshot or not new_snapshot:
            return diff

        # Compare plan-level fields
        plan_fields = ["name", "description", "goal", "difficulty", "split_type"]
        for field in plan_fields:
            old_val = old_snapshot.get(field)
            new_val = new_snapshot.get(field)
            if old_val != new_val:
                diff["plan_changes"].append({
                    "field": field,
                    "old": old_val,
                    "new": new_val,
                })

        # Compare workouts
        old_workouts = {w.get("id"): w for w in old_snapshot.get("workouts", [])}
        new_workouts = {w.get("id"): w for w in new_snapshot.get("workouts", [])}

        # Check for added workouts
        for workout_id, workout in new_workouts.items():
            if workout_id not in old_workouts:
                diff["workout_changes"].append({
                    "type": "added",
                    "workout_id": workout_id,
                    "label": workout.get("label"),
                    "name": workout.get("name"),
                })

        # Check for removed workouts
        for workout_id, workout in old_workouts.items():
            if workout_id not in new_workouts:
                diff["workout_changes"].append({
                    "type": "removed",
                    "workout_id": workout_id,
                    "label": workout.get("label"),
                    "name": workout.get("name"),
                })

        # Check for modified workouts
        for workout_id in set(old_workouts.keys()) & set(new_workouts.keys()):
            old_w = old_workouts[workout_id]
            new_w = new_workouts[workout_id]

            old_exercises = {e.get("id"): e for e in old_w.get("exercises", [])}
            new_exercises = {e.get("id"): e for e in new_w.get("exercises", [])}

            for ex_id, ex in new_exercises.items():
                if ex_id not in old_exercises:
                    diff["exercise_changes"].append({
                        "type": "added",
                        "workout_label": new_w.get("label"),
                        "exercise_name": ex.get("name"),
                    })

            for ex_id, ex in old_exercises.items():
                if ex_id not in new_exercises:
                    diff["exercise_changes"].append({
                        "type": "removed",
                        "workout_label": old_w.get("label"),
                        "exercise_name": ex.get("name"),
                    })

            # Check for modified exercises
            for ex_id in set(old_exercises.keys()) & set(new_exercises.keys()):
                old_ex = old_exercises[ex_id]
                new_ex = new_exercises[ex_id]

                changes = []
                for field in ["sets", "reps", "rest_seconds", "notes"]:
                    if old_ex.get(field) != new_ex.get(field):
                        changes.append({
                            "field": field,
                            "old": old_ex.get(field),
                            "new": new_ex.get(field),
                        })

                if changes:
                    diff["exercise_changes"].append({
                        "type": "modified",
                        "workout_label": new_w.get("label"),
                        "exercise_name": new_ex.get("name"),
                        "changes": changes,
                    })

        return diff
