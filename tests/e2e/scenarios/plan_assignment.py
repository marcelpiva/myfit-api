"""
Plan Assignment Scenario Setup.

Sets up environment for testing plan assignment flows:
- 1 Organization
- 1 Trainer with known credentials
- 3 Students with known credentials
- 1 Training Plan (not yet assigned)

This allows Playwright tests to:
1. Login as Trainer
2. Create/modify plans
3. Assign plans to students
4. Login as different students to test assignment notification/acceptance
"""

import uuid
from datetime import datetime, timezone

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
    WorkoutGoal,
    Difficulty,
    SplitType,
    MuscleGroup,
)


# Known credentials for E2E tests
# Using @example.com since .test TLD is rejected by email validator
TRAINER_EMAIL = "trainer@example.com"
TRAINER_PASSWORD = "Trainer123!"
TRAINER_NAME = "E2E Trainer"

STUDENTS = [
    {"email": "student1@example.com", "password": "Student1!", "name": "Ana Silva"},
    {"email": "student2@example.com", "password": "Student2!", "name": "Bruno Costa"},
    {"email": "student3@example.com", "password": "Student3!", "name": "Carla Dias"},
]

ORGANIZATION_NAME = "E2E Test Organization"


async def setup_plan_assignment_scenario(db_session: AsyncSession) -> dict:
    """
    Create plan assignment test scenario.

    Returns:
        dict with credentials and IDs for external test clients:
        {
            "trainer": {"email": str, "password": str, "id": str, "token": str},
            "students": [{"email": str, "password": str, "id": str, "token": str}, ...],
            "organization_id": str,
            "plan_id": str,
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

    # Create trainer
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

    trainer_membership = OrganizationMembership(
        user_id=trainer_id,
        organization_id=org_id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(trainer_membership)

    # Create students
    students_data = []
    for student_info in STUDENTS:
        student_id = uuid.uuid4()
        student = User(
            id=student_id,
            email=student_info["email"],
            name=student_info["name"],
            password_hash=hash_password(student_info["password"]),
            is_active=True,
            is_verified=True,
        )
        db_session.add(student)

        membership = OrganizationMembership(
            user_id=student_id,
            organization_id=org_id,
            role=UserRole.STUDENT,
            is_active=True,
            invited_by_id=trainer_id,
        )
        db_session.add(membership)

        token = create_access_token(user_id=str(student_id))
        students_data.append({
            "email": student_info["email"],
            "password": student_info["password"],
            "id": str(student_id),
            "name": student_info["name"],
            "token": token,
        })

    # Create exercises and training plan
    exercises = await _create_exercises(db_session)
    plan_id, workouts = await _create_training_plan(
        db_session,
        trainer_id=trainer_id,
        org_id=org_id,
        exercises=exercises,
    )

    await db_session.commit()

    trainer_token = create_access_token(user_id=str(trainer_id))

    return {
        "trainer": {
            "email": TRAINER_EMAIL,
            "password": TRAINER_PASSWORD,
            "id": str(trainer_id),
            "name": TRAINER_NAME,
            "token": trainer_token,
        },
        "students": students_data,
        "organization_id": str(org_id),
        "plan_id": str(plan_id),
        "workouts": workouts,
    }


async def _create_exercises(db_session: AsyncSession) -> list[Exercise]:
    """Create exercises for workouts."""
    exercise_data = [
        ("Supino Reto", MuscleGroup.CHEST),
        ("Crucifixo", MuscleGroup.CHEST),
        ("Triceps Corda", MuscleGroup.TRICEPS),
        ("Puxada Alta", MuscleGroup.BACK),
        ("Remada Baixa", MuscleGroup.BACK),
        ("Rosca Alternada", MuscleGroup.BICEPS),
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
    """Create training plan with 2 workouts."""

    plan_id = uuid.uuid4()
    plan = TrainingPlan(
        id=plan_id,
        name="E2E Test Plan",
        description="Plan for assignment flow tests",
        goal=WorkoutGoal.HYPERTROPHY,
        difficulty=Difficulty.INTERMEDIATE,
        split_type=SplitType.UPPER_LOWER,
        duration_weeks=8,
        is_template=False,
        is_public=False,
        created_by_id=trainer_id,
        organization_id=org_id,
    )
    db_session.add(plan)

    workouts_config = [
        {"name": "Upper Body", "label": "A", "exercises": exercises[0:3]},
        {"name": "Pull Day", "label": "B", "exercises": exercises[3:6]},
    ]

    workouts_result = []
    for i, config in enumerate(workouts_config):
        workout_id = uuid.uuid4()
        workout = Workout(
            id=workout_id,
            name=config["name"],
            difficulty=Difficulty.INTERMEDIATE,
            estimated_duration_min=45,
            created_by_id=trainer_id,
            organization_id=org_id,
        )
        db_session.add(workout)

        plan_workout = PlanWorkout(
            plan_id=plan_id,
            workout_id=workout_id,
            order=i,
            label=config["label"],
        )
        db_session.add(plan_workout)

        exercise_list = []
        for j, exercise in enumerate(config["exercises"]):
            we = WorkoutExercise(
                workout_id=workout_id,
                exercise_id=exercise.id,
                order=j,
                sets=3,
                reps="8-10",
                rest_seconds=60,
            )
            db_session.add(we)
            exercise_list.append({
                "id": str(exercise.id),
                "name": exercise.name,
            })

        workouts_result.append({
            "id": str(workout_id),
            "name": config["name"],
            "label": config["label"],
            "exercises": exercise_list,
        })

    return plan_id, workouts_result
