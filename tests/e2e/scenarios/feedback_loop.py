"""
Feedback Loop Scenario Setup.

Sets up an environment for testing real-time feedback during co-training:
- All data from cotraining scenario (org, trainer, student, plan, assignment)
- Active workout session (in progress, shared with trainer)
- Some sets already completed
- Trainer adjustments ready to be sent

This allows Playwright tests to:
1. Immediately see active session (no login flow needed if using tokens)
2. Test trainer sending adjustments
3. Test student receiving adjustments
4. Test real-time messaging
5. Test set completion feedback
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
    WorkoutSession,
    WorkoutSessionSet,
    SessionMessage,
    SessionStatus,
)


# Known credentials for E2E tests
TRAINER_EMAIL = "trainer.feedback@e2e.test"
TRAINER_PASSWORD = "Trainer123!"
TRAINER_NAME = "Feedback Trainer"

STUDENT_EMAIL = "student.feedback@e2e.test"
STUDENT_PASSWORD = "Student123!"
STUDENT_NAME = "Feedback Student"

ORGANIZATION_NAME = "Feedback Loop Test Org"


async def setup_feedback_loop_scenario(db_session: AsyncSession) -> dict:
    """
    Create feedback loop test scenario with active session.

    Returns:
        dict with credentials, IDs, and session info:
        {
            "trainer": {"email": str, "password": str, "id": str, "token": str},
            "student": {"email": str, "password": str, "id": str, "token": str},
            "organization_id": str,
            "plan_id": str,
            "assignment_id": str,
            "workouts": [{"id": str, "name": str, "label": str}, ...],
            "active_session": {
                "id": str,
                "workout_id": str,
                "workout_name": str,
                "current_exercise": {"id": str, "name": str},
                "completed_sets": int,
                "total_sets": int,
            },
            "exercises": [{"id": str, "name": str}, ...]
        }
    """
    # Create organization
    org_id = uuid.uuid4()
    org = Organization(
        id=org_id,
        name=ORGANIZATION_NAME,
        type=OrganizationType.PERSONAL,
        description="Organization for feedback loop E2E tests",
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

    # Create exercises
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
        notes="Feedback Loop E2E Test Assignment",
    )
    db_session.add(assignment)

    # Create active workout session (the key part of this scenario)
    first_workout = workouts[0]
    session_id = uuid.uuid4()
    session = WorkoutSession(
        id=session_id,
        workout_id=uuid.UUID(first_workout["id"]),
        user_id=student_id,
        trainer_id=trainer_id,  # Trainer already joined
        is_shared=True,
        status=SessionStatus.ACTIVE,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=10),  # Started 10 min ago
        notes="Feedback loop test session",
    )
    db_session.add(session)

    # Create some completed sets (student is on exercise 1, set 3)
    first_exercise = first_workout["exercises"][0]
    completed_sets = []
    for set_num in range(1, 3):  # 2 sets completed
        session_set = WorkoutSessionSet(
            id=uuid.uuid4(),
            session_id=session_id,
            exercise_id=uuid.UUID(first_exercise["id"]),
            set_number=set_num,
            reps_completed=10,
            weight_kg=20.0 + (set_num * 2.5),  # Progressive weight
            performed_at=datetime.now(timezone.utc) - timedelta(minutes=10 - set_num * 2),
        )
        db_session.add(session_set)
        completed_sets.append({
            "set_number": set_num,
            "reps": 10,
            "weight_kg": 20.0 + (set_num * 2.5),
        })

    # Create a welcome message from trainer
    welcome_msg = SessionMessage(
        id=uuid.uuid4(),
        session_id=session_id,
        sender_id=trainer_id,
        message="Estou acompanhando seu treino! Vamos com tudo! 💪",
        sent_at=datetime.now(timezone.utc) - timedelta(minutes=9),
        is_read=True,
    )
    db_session.add(welcome_msg)

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
        "active_session": {
            "id": str(session_id),
            "workout_id": first_workout["id"],
            "workout_name": first_workout["name"],
            "current_exercise": {
                "id": first_exercise["id"],
                "name": first_exercise["name"],
                "current_set": 3,  # Next set to do
            },
            "completed_sets": completed_sets,
            "total_sets": first_exercise["sets"],
        },
        "exercises": [
            {"id": ex["id"], "name": ex["name"]}
            for workout in workouts
            for ex in workout["exercises"]
        ],
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
        name="Feedback Loop Test Plan",
        description="Training plan for feedback loop E2E tests",
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
            "exercises": exercises[0:3],
        },
        {
            "name": "Treino B - Costas e Biceps",
            "label": "B",
            "exercises": exercises[3:6],
        },
        {
            "name": "Treino C - Pernas e Ombros",
            "label": "C",
            "exercises": exercises[6:9],
        },
    ]

    workouts_result = []
    for i, config in enumerate(workouts_config):
        # Create workout
        workout_id = uuid.uuid4()
        workout = Workout(
            id=workout_id,
            name=config["name"],
            description=f"Treino {config['label']} do plano Feedback Loop",
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
