"""
Co-Training Scenario Setup.

Sets up a complete environment for testing co-training flows:
- 1 Organization
- 1 Trainer with known credentials
- 1 Student with known credentials (linked to organization)
- 1 Training Plan with 3 workouts (ABC split)
- Plan assigned to student (accepted status)

This allows Playwright tests to:
1. Login as Trainer
2. Login as Student (different browser context)
3. Student starts workout in co-training mode
4. Trainer joins session
5. Real-time adjustments/messaging
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security.jwt import hash_password, create_access_token
from src.domains.users.models import User
from src.domains.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.workouts.models import (
    TrainingPlan,
    Workout,
    PlanWorkout,
    Exercise,
    WorkoutExercise,
    PlanAssignment,
    WorkoutGoal,
    Difficulty,
    SplitType,
    MuscleGroup,
    AssignmentStatus,
    TrainingMode,
)


# Known credentials for E2E tests
TRAINER_EMAIL = "trainer@e2e.test"
TRAINER_PASSWORD = "Trainer123!"
TRAINER_NAME = "E2E Trainer"

STUDENT_EMAIL = "student@e2e.test"
STUDENT_PASSWORD = "Student123!"
STUDENT_NAME = "E2E Student"

ORGANIZATION_NAME = "E2E Test Organization"


async def setup_cotraining_scenario(db_session: AsyncSession) -> dict:
    """
    Create complete co-training test scenario.

    Returns:
        dict with credentials and IDs for external test clients:
        {
            "trainer": {"email": str, "password": str, "id": str, "token": str},
            "student": {"email": str, "password": str, "id": str, "token": str},
            "organization_id": str,
            "plan_id": str,
            "assignment_id": str,
            "workouts": [{"id": str, "name": str, "label": str}, ...]
        }
    """
    # Create organization
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name=ORGANIZATION_NAME,
        type=OrganizationType.PERSONAL,
        description="Organization for E2E tests",
        is_active=True,
    )
    db_session.add(org)

    # Create trainer with known credentials
    trainer_id = uuid.uuid4()
    trainer = User(
        id=trainer_id,
        email=TRAINER_EMAIL,
        name=TRAINER_NAME,
        password_hash=hash_password(TRAINER_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(trainer)

    # Create student with known credentials
    student_id = uuid.uuid4()
    student = User(
        id=student_id,
        email=STUDENT_EMAIL,
        name=STUDENT_NAME,
        password_hash=hash_password(STUDENT_PASSWORD),
        is_active=True,
        is_verified=True,
    )
    db_session.add(student)

    # Create memberships
    trainer_membership = OrganizationMembership(
        user_id=trainer_id,
        organization_id=org_id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(trainer_membership)

    student_membership = OrganizationMembership(
        user_id=student_id,
        organization_id=org_id,
        role=UserRole.STUDENT,
        is_active=True,
        invited_by_id=trainer_id,
    )
    db_session.add(student_membership)

    # Create system exercises
    exercises = await _create_exercises(db_session)

    # Create training plan with workouts
    plan_id, workouts = await _create_training_plan(
        db_session,
        trainer_id=trainer_id,
        org_id=org_id,
        exercises=exercises,
    )

    # Create plan assignment (accepted)
    assignment_id = uuid.uuid4()
    assignment = PlanAssignment(
        id=assignment_id,
        plan_id=plan_id,
        student_id=student_id,
        trainer_id=trainer_id,
        organization_id=org_id,
        start_date=datetime.now(timezone.utc).date(),
        end_date=(datetime.now(timezone.utc) + timedelta(weeks=4)).date(),
        status=AssignmentStatus.ACCEPTED,
        accepted_at=datetime.now(timezone.utc),
        training_mode=TrainingMode.PRESENCIAL,
        notes="E2E Test Assignment",
    )
    db_session.add(assignment)

    await db_session.commit()

    # Generate auth tokens
    trainer_token = create_access_token(user_id=str(trainer_id))
    student_token = create_access_token(user_id=str(student_id))

    return {
        "trainer": {
            "email": TRAINER_EMAIL,
            "password": TRAINER_PASSWORD,
            "id": str(trainer_id),
            "name": TRAINER_NAME,
            "token": trainer_token,
        },
        "student": {
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "id": str(student_id),
            "name": STUDENT_NAME,
            "token": student_token,
        },
        "organization_id": str(org_id),
        "plan_id": str(plan_id),
        "assignment_id": str(assignment_id),
        "workouts": workouts,
    }


async def _create_exercises(db_session: AsyncSession) -> list[Exercise]:
    """Create system exercises for workouts."""
    exercise_data = [
        # Chest & Triceps (Workout A)
        ("Supino Reto com Barra", MuscleGroup.CHEST),
        ("Crucifixo com Halteres", MuscleGroup.CHEST),
        ("Triceps Pulley", MuscleGroup.TRICEPS),
        # Back & Biceps (Workout B)
        ("Puxada Frontal", MuscleGroup.BACK),
        ("Remada Curvada", MuscleGroup.BACK),
        ("Rosca Direta", MuscleGroup.BICEPS),
        # Legs & Shoulders (Workout C)
        ("Agachamento Livre", MuscleGroup.QUADRICEPS),
        ("Leg Press 45", MuscleGroup.QUADRICEPS),
        ("Desenvolvimento com Halteres", MuscleGroup.SHOULDERS),
    ]

    exercises = []
    for name, muscle_group in exercise_data:
        exercise = Exercise(
            id=uuid.uuid4(),
            name=name,
            muscle_group=muscle_group,
            is_custom=False,
            is_public=True,
        )
        db_session.add(exercise)
        exercises.append(exercise)

    return exercises


async def _create_training_plan(
    db_session: AsyncSession,
    trainer_id: uuid.UUID,
    org_id: uuid.UUID,
    exercises: list[Exercise],
) -> tuple[uuid.UUID, list[dict]]:
    """Create training plan with ABC split workouts."""

    # Create plan
    plan_id = uuid.uuid4()
    plan = TrainingPlan(
        id=plan_id,
        name="E2E Test Plan - ABC Split",
        description="Training plan for E2E co-training tests",
        goal=WorkoutGoal.GENERAL_FITNESS,
        difficulty=Difficulty.BEGINNER,
        split_type=SplitType.ABC,
        duration_weeks=4,
        is_template=False,
        is_public=False,
        created_by_id=trainer_id,
        organization_id=org_id,
    )
    db_session.add(plan)

    # Define workouts
    workouts_config = [
        {
            "name": "Treino A - Peito e Triceps",
            "label": "A",
            "exercises": exercises[0:3],  # First 3 exercises
        },
        {
            "name": "Treino B - Costas e Biceps",
            "label": "B",
            "exercises": exercises[3:6],  # Next 3 exercises
        },
        {
            "name": "Treino C - Pernas e Ombros",
            "label": "C",
            "exercises": exercises[6:9],  # Last 3 exercises
        },
    ]

    workouts_result = []
    for i, config in enumerate(workouts_config):
        # Create workout
        workout_id = uuid.uuid4()
        workout = Workout(
            id=workout_id,
            name=config["name"],
            description=f"Treino {config['label']} do plano E2E",
            difficulty=Difficulty.BEGINNER,
            estimated_duration_min=60,
            created_by_id=trainer_id,
            organization_id=org_id,
        )
        db_session.add(workout)

        # Link to plan
        plan_workout = PlanWorkout(
            plan_id=plan_id,
            workout_id=workout_id,
            order=i,
            label=config["label"],
        )
        db_session.add(plan_workout)

        # Add exercises to workout
        exercise_list = []
        for j, exercise in enumerate(config["exercises"]):
            we = WorkoutExercise(
                workout_id=workout_id,
                exercise_id=exercise.id,
                order=j,
                sets=4,
                reps="10-12",
                rest_seconds=90,
            )
            db_session.add(we)
            exercise_list.append({
                "id": str(exercise.id),
                "name": exercise.name,
                "sets": 4,
                "reps": "10-12",
            })

        workouts_result.append({
            "id": str(workout_id),
            "name": config["name"],
            "label": config["label"],
            "exercises": exercise_list,
        })

    return plan_id, workouts_result
