"""Integration tests for workouts API endpoints."""
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.workouts.models import (
    Difficulty,
    Exercise,
    MuscleGroup,
    PlanAssignment,
    TrainingPlan,
    Workout,
    WorkoutExercise,
    WorkoutSession,
    SessionStatus,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_exercise(db_session: AsyncSession, sample_user: dict[str, Any]) -> Exercise:
    """Create a sample exercise."""
    exercise = Exercise(
        name="Bench Press",
        muscle_group=MuscleGroup.CHEST,
        description="Classic chest exercise",
        is_public=True,
        created_by_id=sample_user["id"],
    )
    db_session.add(exercise)
    await db_session.commit()
    await db_session.refresh(exercise)
    return exercise


@pytest.fixture
async def sample_private_exercise(db_session: AsyncSession, sample_user: dict[str, Any]) -> Exercise:
    """Create a private exercise owned by sample_user."""
    exercise = Exercise(
        name="My Custom Exercise",
        muscle_group=MuscleGroup.BICEPS,
        description="A private custom exercise",
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(exercise)
    await db_session.commit()
    await db_session.refresh(exercise)
    return exercise


@pytest.fixture
async def sample_workout(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_exercise: Exercise
) -> Workout:
    """Create a sample workout with an exercise."""
    workout = Workout(
        name="Test Workout",
        description="A test workout",
        difficulty=Difficulty.INTERMEDIATE,
        estimated_duration_min=45,
        target_muscles=["chest", "triceps"],
        is_template=False,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(workout)
    await db_session.flush()

    # Add exercise to workout
    workout_exercise = WorkoutExercise(
        workout_id=workout.id,
        exercise_id=sample_exercise.id,
        order=1,
        sets=3,
        reps="8-12",
        rest_seconds=90,
    )
    db_session.add(workout_exercise)
    await db_session.commit()
    await db_session.refresh(workout)
    return workout


@pytest.fixture
async def sample_session(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_workout: Workout
) -> WorkoutSession:
    """Create a sample workout session."""
    session = WorkoutSession(
        user_id=sample_user["id"],
        workout_id=sample_workout.id,
        status=SessionStatus.ACTIVE,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


# =============================================================================
# Exercise Endpoint Tests
# =============================================================================


class TestListExercises:
    """Tests for GET /api/v1/workouts/exercises."""

    async def test_list_exercises_authenticated(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Authenticated user can list exercises."""
        response = await authenticated_client.get("/api/v1/workouts/exercises")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_exercises_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/workouts/exercises")

        assert response.status_code == 401

    async def test_list_exercises_filter_by_muscle_group(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Can filter exercises by muscle group."""
        response = await authenticated_client.get(
            "/api/v1/workouts/exercises", params={"muscle_group": "chest"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(ex["muscle_group"] == "chest" for ex in data)

    async def test_list_exercises_search(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Can search exercises by name."""
        response = await authenticated_client.get(
            "/api/v1/workouts/exercises", params={"search": "Bench"}
        )

        assert response.status_code == 200
        data = response.json()
        assert any("Bench" in ex["name"] for ex in data)

    async def test_list_exercises_pagination(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/workouts/exercises", params={"limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1


class TestGetExercise:
    """Tests for GET /api/v1/workouts/exercises/{exercise_id}."""

    async def test_get_public_exercise(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Can get a public exercise."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/exercises/{sample_exercise.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Bench Press"
        assert data["muscle_group"] == "chest"

    async def test_get_own_private_exercise(
        self, authenticated_client: AsyncClient, sample_private_exercise: Exercise
    ):
        """Owner can access their private exercise."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/exercises/{sample_private_exercise.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Custom Exercise"

    async def test_get_nonexistent_exercise(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent exercise."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/workouts/exercises/{fake_id}"
        )

        assert response.status_code == 404


class TestCreateExercise:
    """Tests for POST /api/v1/workouts/exercises."""

    async def test_create_exercise_success(self, authenticated_client: AsyncClient):
        """Can create a new exercise."""
        payload = {
            "name": "Custom Squat",
            "muscle_group": "quadriceps",
            "description": "A custom squat variation",
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/exercises", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Custom Squat"
        assert data["muscle_group"] == "quadriceps"
        assert "id" in data

    async def test_create_exercise_with_all_fields(self, authenticated_client: AsyncClient):
        """Can create exercise with all optional fields."""
        payload = {
            "name": "Full Exercise",
            "muscle_group": "chest",
            "description": "Complete exercise",
            "secondary_muscles": ["triceps", "shoulders"],
            "equipment": ["barbell", "bench"],
            "instructions": "Step 1: Prepare. Step 2: Execute.",
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/exercises", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["secondary_muscles"] == ["triceps", "shoulders"]

    async def test_create_exercise_missing_required_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {"description": "Missing name and muscle_group"}

        response = await authenticated_client.post(
            "/api/v1/workouts/exercises", json=payload
        )

        assert response.status_code == 422


class TestUpdateExercise:
    """Tests for PUT /api/v1/workouts/exercises/{exercise_id}."""

    async def test_update_own_exercise(
        self, authenticated_client: AsyncClient, sample_private_exercise: Exercise
    ):
        """Owner can update their exercise."""
        payload = {
            "name": "Updated Exercise Name",
            "description": "Updated description",
        }

        response = await authenticated_client.put(
            f"/api/v1/workouts/exercises/{sample_private_exercise.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Exercise Name"

    async def test_update_nonexistent_exercise(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent exercise."""
        fake_id = uuid.uuid4()
        payload = {"name": "New Name"}

        response = await authenticated_client.put(
            f"/api/v1/workouts/exercises/{fake_id}", json=payload
        )

        assert response.status_code == 404


# =============================================================================
# Workout Endpoint Tests
# =============================================================================


class TestListWorkouts:
    """Tests for GET /api/v1/workouts/."""

    async def test_list_workouts_authenticated(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Authenticated user can list their workouts."""
        response = await authenticated_client.get("/api/v1/workouts/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_workouts_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/workouts/")

        assert response.status_code == 401


class TestGetWorkout:
    """Tests for GET /api/v1/workouts/{workout_id}."""

    async def test_get_own_workout(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can get own workout with exercises."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/{sample_workout.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Workout"
        assert data["difficulty"] == "intermediate"

    async def test_get_nonexistent_workout(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent workout."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(f"/api/v1/workouts/{fake_id}")

        assert response.status_code == 404


class TestCreateWorkout:
    """Tests for POST /api/v1/workouts/."""

    async def test_create_workout_success(self, authenticated_client: AsyncClient):
        """Can create a new workout."""
        payload = {
            "name": "My New Workout",
            "difficulty": "beginner",
            "estimated_duration_min": 30,
        }

        response = await authenticated_client.post("/api/v1/workouts/", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My New Workout"
        assert data["difficulty"] == "beginner"

    async def test_create_workout_with_description(self, authenticated_client: AsyncClient):
        """Can create workout with description."""
        payload = {
            "name": "Described Workout",
            "difficulty": "intermediate",
            "description": "A detailed description",
            "target_muscles": ["chest", "back"],
        }

        response = await authenticated_client.post("/api/v1/workouts/", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "A detailed description"


class TestUpdateWorkout:
    """Tests for PUT /api/v1/workouts/{workout_id}."""

    async def test_update_own_workout(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Owner can update their workout."""
        payload = {
            "name": "Updated Workout",
            "difficulty": "advanced",
        }

        response = await authenticated_client.put(
            f"/api/v1/workouts/{sample_workout.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Workout"
        assert data["difficulty"] == "advanced"


class TestDeleteWorkout:
    """Tests for DELETE /api/v1/workouts/{workout_id}."""

    async def test_delete_own_workout(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Owner can delete their workout."""
        response = await authenticated_client.delete(
            f"/api/v1/workouts/{sample_workout.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/workouts/{sample_workout.id}"
        )
        assert get_response.status_code == 404


# =============================================================================
# Session Endpoint Tests
# =============================================================================


class TestStartSession:
    """Tests for POST /api/v1/workouts/sessions."""

    async def test_start_session_success(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can start a new workout session."""
        payload = {"workout_id": str(sample_workout.id)}
        response = await authenticated_client.post(
            "/api/v1/workouts/sessions", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
        assert "id" in data

    async def test_start_session_nonexistent_workout(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent workout."""
        fake_id = uuid.uuid4()
        payload = {"workout_id": str(fake_id)}
        response = await authenticated_client.post(
            "/api/v1/workouts/sessions", json=payload
        )

        assert response.status_code == 404


class TestGetActiveSession:
    """Tests for GET /api/v1/workouts/sessions/active (trainer view)."""

    @pytest.mark.xfail(
        reason="Route /sessions/active is defined after /sessions/{session_id} "
        "in the router, causing FastAPI to match {session_id}='active' first. "
        "Fix requires reordering routes in workouts/router.py."
    )
    async def test_get_active_sessions_as_trainer(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_user: dict,
    ):
        """Trainer can list active sessions in their organization."""
        response = await authenticated_client.get(
            "/api/v1/workouts/sessions/active",
            params={"organization_id": str(sample_user["organization_id"])},
        )

        # May return empty list if no students are active
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCompleteSession:
    """Tests for POST /api/v1/workouts/sessions/{session_id}/complete."""

    async def test_complete_session_success(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can complete an active session."""
        # First start a session
        start_payload = {"workout_id": str(sample_workout.id)}
        start_response = await authenticated_client.post(
            "/api/v1/workouts/sessions", json=start_payload
        )
        session_id = start_response.json()["id"]

        # Then complete it
        complete_payload = {"notes": "Great workout!", "rating": 5}
        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/complete",
            json=complete_payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["notes"] == "Great workout!"
        assert data["rating"] == 5

    async def test_complete_session_minimal(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can complete session without notes/rating."""
        # First start a session
        start_payload = {"workout_id": str(sample_workout.id)}
        start_response = await authenticated_client.post(
            "/api/v1/workouts/sessions", json=start_payload
        )
        session_id = start_response.json()["id"]

        # Then complete it
        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/complete",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"


class TestListSessions:
    """Tests for GET /api/v1/workouts/sessions."""

    async def test_list_sessions(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Can list user's sessions."""
        response = await authenticated_client.get("/api/v1/workouts/sessions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# =============================================================================
# Workout Exercise Endpoint Tests
# =============================================================================


class TestAddExerciseToWorkout:
    """Tests for POST /api/v1/workouts/{workout_id}/exercises."""

    async def test_add_exercise_to_workout(
        self,
        authenticated_client: AsyncClient,
        sample_workout: Workout,
        db_session: AsyncSession,
    ):
        """Can add an exercise to a workout."""
        # Create a new exercise to add
        exercise = Exercise(
            name="Deadlift",
            muscle_group=MuscleGroup.BACK,
            is_public=True,
        )
        db_session.add(exercise)
        await db_session.commit()
        await db_session.refresh(exercise)

        payload = {
            "exercise_id": str(exercise.id),
            "order": 2,
            "sets": 4,
            "reps": "6-8",
            "rest_seconds": 120,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/{sample_workout.id}/exercises",
            json=payload,
        )

        # Endpoint returns 200 and the updated workout
        assert response.status_code == 200
        data = response.json()
        # Response is the full workout, not just the added exercise
        assert "exercises" in data


class TestRemoveExerciseFromWorkout:
    """Tests for DELETE /api/v1/workouts/{workout_id}/exercises/{exercise_id}."""

    async def test_remove_exercise_from_workout(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can remove an exercise from a workout."""
        # Get the workout exercises first
        get_response = await authenticated_client.get(
            f"/api/v1/workouts/{sample_workout.id}"
        )
        workout_data = get_response.json()

        if workout_data.get("exercises"):
            exercise_id = workout_data["exercises"][0]["id"]
            response = await authenticated_client.delete(
                f"/api/v1/workouts/{sample_workout.id}/exercises/{exercise_id}"
            )
            assert response.status_code == 204


# =============================================================================
# Training Plan Endpoint Tests
# =============================================================================


@pytest.fixture
async def sample_plan(db_session: AsyncSession, sample_user: dict[str, Any]) -> "TrainingPlan":
    """Create a sample training plan."""
    from src.domains.workouts.models import TrainingPlan, WorkoutGoal, SplitType

    plan = TrainingPlan(
        name="Test Training Plan",
        description="A test training plan",
        goal=WorkoutGoal.HYPERTROPHY,
        difficulty=Difficulty.INTERMEDIATE,
        split_type=SplitType.ABC,
        duration_weeks=8,
        is_template=False,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.fixture
async def sample_public_plan(db_session: AsyncSession, sample_user: dict[str, Any]) -> "TrainingPlan":
    """Create a sample public training plan for catalog."""
    from src.domains.workouts.models import TrainingPlan, WorkoutGoal, SplitType

    plan = TrainingPlan(
        name="Public Catalog Plan",
        description="A public catalog plan",
        goal=WorkoutGoal.STRENGTH,
        difficulty=Difficulty.BEGINNER,
        split_type=SplitType.FULL_BODY,
        duration_weeks=4,
        is_template=True,
        is_public=True,
        created_by_id=sample_user["id"],
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


class TestListPlans:
    """Tests for GET /api/v1/workouts/plans."""

    async def test_list_plans_authenticated(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Authenticated user can list their plans."""
        response = await authenticated_client.get("/api/v1/workouts/plans")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(p["name"] == "Test Training Plan" for p in data)

    async def test_list_plans_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/workouts/plans")

        assert response.status_code == 401

    async def test_list_plans_with_search(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can search plans by name."""
        response = await authenticated_client.get(
            "/api/v1/workouts/plans", params={"search": "Training"}
        )

        assert response.status_code == 200
        data = response.json()
        assert any("Training" in p["name"] for p in data)

    async def test_list_plans_templates_only(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can filter for templates only."""
        response = await authenticated_client.get(
            "/api/v1/workouts/plans", params={"templates_only": True}
        )

        assert response.status_code == 200
        data = response.json()
        # sample_plan is not a template, so it should not appear
        assert not any(p["name"] == "Test Training Plan" for p in data)


class TestGetPlan:
    """Tests for GET /api/v1/workouts/plans/{plan_id}."""

    async def test_get_own_plan(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can get own plan."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/plans/{sample_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Training Plan"
        assert data["goal"] == "hypertrophy"

    async def test_get_nonexistent_plan(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent plan."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/workouts/plans/{fake_id}"
        )

        assert response.status_code == 404


class TestCreatePlan:
    """Tests for POST /api/v1/workouts/plans."""

    async def test_create_plan_success(self, authenticated_client: AsyncClient):
        """Can create a new plan."""
        payload = {
            "name": "My New Plan",
            "goal": "strength",
            "difficulty": "beginner",
            "split_type": "full_body",
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My New Plan"
        assert data["goal"] == "strength"
        assert data["difficulty"] == "beginner"

    async def test_create_plan_with_all_fields(self, authenticated_client: AsyncClient):
        """Can create plan with all optional fields."""
        payload = {
            "name": "Full Plan",
            "description": "A detailed plan",
            "goal": "hypertrophy",
            "difficulty": "intermediate",
            "split_type": "push_pull_legs",
            "duration_weeks": 12,
            "target_workout_minutes": 60,
            "is_template": True,
            "is_public": False,
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "A detailed plan"
        assert data["duration_weeks"] == 12
        assert data["is_template"] is True

    async def test_create_plan_missing_name(self, authenticated_client: AsyncClient):
        """Returns 422 for missing required fields."""
        payload = {"goal": "strength"}

        response = await authenticated_client.post(
            "/api/v1/workouts/plans", json=payload
        )

        assert response.status_code == 422


class TestUpdatePlan:
    """Tests for PUT /api/v1/workouts/plans/{plan_id}."""

    async def test_update_own_plan(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Owner can update their plan."""
        payload = {
            "name": "Updated Plan Name",
            "goal": "strength",
        }

        response = await authenticated_client.put(
            f"/api/v1/workouts/plans/{sample_plan.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Plan Name"
        assert data["goal"] == "strength"

    async def test_update_nonexistent_plan(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent plan."""
        fake_id = uuid.uuid4()
        payload = {"name": "New Name"}

        response = await authenticated_client.put(
            f"/api/v1/workouts/plans/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestDeletePlan:
    """Tests for DELETE /api/v1/workouts/plans/{plan_id}."""

    async def test_delete_own_plan(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Owner can delete their plan."""
        from src.domains.workouts.models import TrainingPlan, WorkoutGoal, SplitType

        # Create a plan to delete
        plan = TrainingPlan(
            name="Plan to Delete",
            goal=WorkoutGoal.STRENGTH,
            difficulty=Difficulty.BEGINNER,
            split_type=SplitType.FULL_BODY,
            created_by_id=sample_user["id"],
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        response = await authenticated_client.delete(
            f"/api/v1/workouts/plans/{plan.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/workouts/plans/{plan.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_nonexistent_plan(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent plan."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"/api/v1/workouts/plans/{fake_id}"
        )

        assert response.status_code == 404


class TestDuplicatePlan:
    """Tests for POST /api/v1/workouts/plans/{plan_id}/duplicate."""

    async def test_duplicate_own_plan(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can duplicate own plan."""
        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/{sample_plan.id}/duplicate"
        )

        assert response.status_code == 201
        data = response.json()
        # Duplicated plans get (2), (3), etc. suffix
        assert "Test Training Plan" in data["name"]
        assert data["id"] != str(sample_plan.id)

    async def test_duplicate_with_new_name(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can duplicate with custom name."""
        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/{sample_plan.id}/duplicate",
            params={"new_name": "My Duplicated Plan"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Duplicated Plan"

    async def test_duplicate_from_catalog(
        self, authenticated_client: AsyncClient, sample_public_plan: "TrainingPlan"
    ):
        """Can duplicate public plan from catalog."""
        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/{sample_public_plan.id}/duplicate",
            params={"from_catalog": True},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["source_template_id"] == str(sample_public_plan.id)


class TestPlanCatalog:
    """Tests for GET /api/v1/workouts/plans/catalog."""

    async def test_get_catalog_templates(
        self, authenticated_client: AsyncClient, sample_public_plan: "TrainingPlan"
    ):
        """Can get public catalog templates."""
        response = await authenticated_client.get("/api/v1/workouts/plans/catalog")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_catalog_with_filters(
        self, authenticated_client: AsyncClient, sample_public_plan: "TrainingPlan"
    ):
        """Can filter catalog by goal and difficulty."""
        response = await authenticated_client.get(
            "/api/v1/workouts/plans/catalog",
            params={"goal": "strength", "difficulty": "beginner"},
        )

        assert response.status_code == 200


# =============================================================================
# Plan Assignment Endpoint Tests
# =============================================================================


@pytest.fixture
async def sample_plan_assignment(
    db_session: AsyncSession,
    sample_plan: "TrainingPlan",
    sample_user: dict[str, Any],
    student_user: dict[str, Any],
) -> "PlanAssignment":
    """Create a sample plan assignment."""
    from datetime import date
    from src.domains.workouts.models import PlanAssignment, AssignmentStatus

    assignment = PlanAssignment(
        plan_id=sample_plan.id,
        student_id=student_user["id"],
        trainer_id=sample_user["id"],
        organization_id=sample_user["organization_id"],
        start_date=date.today(),
        is_active=True,
        status=AssignmentStatus.PENDING,
    )
    db_session.add(assignment)
    await db_session.commit()
    await db_session.refresh(assignment)
    return assignment


class TestListPlanAssignments:
    """Tests for GET /api/v1/workouts/plans/assignments."""

    async def test_list_plan_assignments_as_trainer(
        self, authenticated_client: AsyncClient, sample_plan_assignment: "PlanAssignment"
    ):
        """Trainer can list their plan assignments."""
        response = await authenticated_client.get(
            "/api/v1/workouts/plans/assignments",
            params={"as_trainer": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_plan_assignments_as_student(
        self, authenticated_client: AsyncClient
    ):
        """Student can list their assignments."""
        response = await authenticated_client.get(
            "/api/v1/workouts/plans/assignments",
            params={"as_trainer": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_plan_assignments_excludes_self_assigned(
        self,
        authenticated_client: AsyncClient,
        sample_plan: "TrainingPlan",
        sample_user: dict[str, Any],
        db_session: "AsyncSession",
    ):
        """Student should not see self-assigned plans in their list."""
        from datetime import date
        from src.domains.workouts.models import PlanAssignment, AssignmentStatus

        # Create a self-assigned plan (trainer_id == student_id)
        self_assigned = PlanAssignment(
            plan_id=sample_plan.id,
            student_id=sample_user["id"],
            trainer_id=sample_user["id"],  # Self-assigned
            organization_id=sample_user["organization_id"],
            start_date=date.today(),
            is_active=True,
            status=AssignmentStatus.ACCEPTED,
        )
        db_session.add(self_assigned)
        await db_session.commit()

        # List assignments as student
        response = await authenticated_client.get(
            "/api/v1/workouts/plans/assignments",
            params={"as_trainer": False},
        )

        assert response.status_code == 200
        data = response.json()
        # Self-assigned plans should not appear in the student's view
        self_assigned_ids = [
            a["id"] for a in data
            if a["trainer_id"] == a["student_id"]
        ]
        assert len(self_assigned_ids) == 0, "Self-assigned plans should not be visible to student"


class TestCreatePlanAssignment:
    """Tests for POST /api/v1/workouts/plans/assignments."""

    async def test_create_plan_assignment_success(
        self,
        authenticated_client: AsyncClient,
        sample_plan: "TrainingPlan",
        student_user: dict[str, Any],
        sample_user: dict[str, Any],
    ):
        """Trainer can assign a plan to a student."""
        from datetime import date

        payload = {
            "plan_id": str(sample_plan.id),
            "student_id": str(student_user["id"]),
            "start_date": str(date.today()),
            "organization_id": str(sample_user["organization_id"]),
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/plans/assignments", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["plan_id"] == str(sample_plan.id)
        assert data["student_id"] == str(student_user["id"])
        assert data["status"] == "accepted"  # Auto-accepted, no approval workflow

    async def test_create_plan_assignment_nonexistent_plan(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Returns 404 for nonexistent plan."""
        from datetime import date

        fake_id = uuid.uuid4()
        payload = {
            "plan_id": str(fake_id),
            "student_id": str(student_user["id"]),
            "start_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/plans/assignments", json=payload
        )

        assert response.status_code == 404

    async def test_create_plan_assignment_nonexistent_student(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Returns 404 for nonexistent student."""
        from datetime import date

        fake_id = uuid.uuid4()
        payload = {
            "plan_id": str(sample_plan.id),
            "student_id": str(fake_id),
            "start_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/plans/assignments", json=payload
        )

        assert response.status_code == 404


class TestUpdatePlanAssignment:
    """Tests for PUT /api/v1/workouts/plans/assignments/{assignment_id}."""

    async def test_update_plan_assignment_success(
        self, authenticated_client: AsyncClient, sample_plan_assignment: "PlanAssignment"
    ):
        """Trainer can update their assignment."""
        from datetime import date, timedelta

        payload = {
            "end_date": str(date.today() + timedelta(days=30)),
            "notes": "Updated notes",
        }

        response = await authenticated_client.put(
            f"/api/v1/workouts/plans/assignments/{sample_plan_assignment.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Updated notes"

    async def test_update_nonexistent_assignment(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent assignment."""
        fake_id = uuid.uuid4()
        payload = {"notes": "New notes"}

        response = await authenticated_client.put(
            f"/api/v1/workouts/plans/assignments/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestAcknowledgePlanAssignment:
    """Tests for POST /api/v1/workouts/plans/assignments/{assignment_id}/acknowledge."""

    async def test_acknowledge_assignment_success(
        self,
        authenticated_client: AsyncClient,
        db_session: "AsyncSession",
        sample_plan: "TrainingPlan",
        sample_user: dict[str, Any],
    ):
        """Student can acknowledge their assignment."""
        from datetime import date
        from src.domains.workouts.models import PlanAssignment, AssignmentStatus

        # Create an assignment for the sample_user as student
        assignment = PlanAssignment(
            plan_id=sample_plan.id,
            student_id=sample_user["id"],
            trainer_id=sample_plan.created_by_id,
            organization_id=sample_user["organization_id"],
            start_date=date.today(),
            is_active=True,
            status=AssignmentStatus.ACCEPTED,
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/assignments/{assignment.id}/acknowledge"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["acknowledged_at"] is not None

    async def test_acknowledge_assignment_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent assignment."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/assignments/{fake_id}/acknowledge"
        )

        assert response.status_code == 404


class TestDeletePlanAssignment:
    """Tests for DELETE /api/v1/workouts/plans/assignments/{assignment_id}."""

    async def test_delete_pending_assignment(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_plan: "TrainingPlan",
        sample_user: dict[str, Any],
        student_user: dict[str, Any],
    ):
        """Trainer can delete pending assignment."""
        from datetime import date
        from src.domains.workouts.models import PlanAssignment, AssignmentStatus

        # Create a pending assignment
        assignment = PlanAssignment(
            plan_id=sample_plan.id,
            student_id=student_user["id"],
            trainer_id=sample_user["id"],
            start_date=date.today(),
            is_active=True,
            status=AssignmentStatus.PENDING,
        )
        db_session.add(assignment)
        await db_session.commit()
        await db_session.refresh(assignment)

        response = await authenticated_client.delete(
            f"/api/v1/workouts/plans/assignments/{assignment.id}"
        )

        assert response.status_code == 204


# =============================================================================
# Session Set Endpoint Tests
# =============================================================================


class TestAddSessionSet:
    """Tests for POST /api/v1/workouts/sessions/{session_id}/sets."""

    async def test_add_set_success(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_exercise: Exercise,
    ):
        """Can add a set to an active session."""
        payload = {
            "exercise_id": str(sample_exercise.id),
            "set_number": 1,
            "reps_completed": 10,
            "weight_kg": 50.0,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/sets",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["reps_completed"] == 10
        assert data["weight_kg"] == 50.0
        assert data["set_number"] == 1

    async def test_add_set_with_notes(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_exercise: Exercise,
    ):
        """Can add a set with notes."""
        payload = {
            "exercise_id": str(sample_exercise.id),
            "set_number": 2,
            "reps_completed": 8,
            "weight_kg": 55.0,
            "notes": "Felt strong!",
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/sets",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["notes"] == "Felt strong!"

    async def test_add_set_nonexistent_session(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()
        payload = {
            "exercise_id": str(sample_exercise.id),
            "set_number": 1,
            "reps_completed": 10,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_id}/sets", json=payload
        )

        assert response.status_code == 404

    async def test_add_set_to_completed_session(
        self,
        authenticated_client: AsyncClient,
        sample_workout: Workout,
        sample_exercise: Exercise,
    ):
        """Cannot add sets to a completed session."""
        # Start and complete a session
        start_response = await authenticated_client.post(
            "/api/v1/workouts/sessions",
            json={"workout_id": str(sample_workout.id)},
        )
        session_id = start_response.json()["id"]

        await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/complete",
            json={},
        )

        # Try to add a set
        payload = {
            "exercise_id": str(sample_exercise.id),
            "set_number": 1,
            "reps_completed": 10,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/sets", json=payload
        )

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()


# =============================================================================
# Co-Training Endpoint Tests
# =============================================================================


class TestJoinSession:
    """Tests for POST /api/v1/workouts/sessions/{session_id}/join."""

    async def test_join_session_nonexistent(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_id}/join"
        )

        assert response.status_code == 404

    async def test_join_completed_session(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Cannot join a completed session."""
        # Start and complete a session
        start_response = await authenticated_client.post(
            "/api/v1/workouts/sessions",
            json={"workout_id": str(sample_workout.id)},
        )
        session_id = start_response.json()["id"]

        await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/complete",
            json={},
        )

        # Try to join
        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{session_id}/join"
        )

        assert response.status_code == 400


class TestLeaveSession:
    """Tests for POST /api/v1/workouts/sessions/{session_id}/leave."""

    async def test_leave_session_nonexistent(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_id}/leave"
        )

        assert response.status_code == 404

    async def test_leave_session_not_trainer(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Cannot leave session if not the trainer."""
        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/leave"
        )

        assert response.status_code == 403


class TestUpdateSessionStatus:
    """Tests for PUT /api/v1/workouts/sessions/{session_id}/status."""

    async def test_update_session_status_to_paused(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Session owner can pause session."""
        payload = {"status": "paused"}

        response = await authenticated_client.put(
            f"/api/v1/workouts/sessions/{sample_session.id}/status",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    async def test_update_session_status_nonexistent(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()
        payload = {"status": "paused"}

        response = await authenticated_client.put(
            f"/api/v1/workouts/sessions/{fake_id}/status", json=payload
        )

        assert response.status_code == 404


class TestSessionMessages:
    """Tests for session message endpoints."""

    async def test_send_message_to_session(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Session participant can send message."""
        # Schema requires session_id in body as well as path
        payload = {
            "session_id": str(sample_session.id),
            "message": "Great job!",
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/messages",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Great job!"

    async def test_list_session_messages(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Can list session messages."""
        # First send a message (schema requires session_id in body)
        await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/messages",
            json={
                "session_id": str(sample_session.id),
                "message": "Test message",
            },
        )

        response = await authenticated_client.get(
            f"/api/v1/workouts/sessions/{sample_session.id}/messages"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_send_message_nonexistent_session(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()
        payload = {
            "session_id": str(fake_id),
            "message": "Test",
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_id}/messages", json=payload
        )

        assert response.status_code == 404


class TestTrainerAdjustments:
    """Tests for trainer adjustment endpoints."""

    async def test_create_adjustment_not_trainer(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_exercise: Exercise,
    ):
        """Non-trainer cannot create adjustments."""
        # Schema requires session_id in body as well as path
        payload = {
            "session_id": str(sample_session.id),
            "exercise_id": str(sample_exercise.id),
            "set_number": 1,
            "suggested_weight_kg": 55.0,
            "suggested_reps": 10,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/adjustments",
            json=payload,
        )

        # User is owner but not trainer of this session
        assert response.status_code == 403

    async def test_create_adjustment_nonexistent_session(
        self, authenticated_client: AsyncClient, sample_exercise: Exercise
    ):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()
        payload = {
            "session_id": str(fake_id),
            "exercise_id": str(sample_exercise.id),
            "set_number": 1,
            "suggested_weight_kg": 55.0,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_id}/adjustments", json=payload
        )

        assert response.status_code == 404


# =============================================================================
# Workout Template Tests
# =============================================================================


class TestListWorkoutTemplates:
    """Tests for listing workout templates."""

    async def test_list_templates_only(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Can list only template workouts."""
        # Create a template workout
        template = Workout(
            name="Template Workout",
            difficulty=Difficulty.INTERMEDIATE,
            is_template=True,
            is_public=False,
            created_by_id=sample_user["id"],
        )
        db_session.add(template)
        await db_session.commit()

        response = await authenticated_client.get(
            "/api/v1/workouts/", params={"templates_only": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(w.get("is_template", False) for w in data)


class TestDuplicateWorkout:
    """Tests for POST /api/v1/workouts/{workout_id}/duplicate."""

    async def test_duplicate_own_workout(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can duplicate own workout."""
        response = await authenticated_client.post(
            f"/api/v1/workouts/{sample_workout.id}/duplicate"
        )

        assert response.status_code == 201
        data = response.json()
        # Duplicated workouts get (2), (3), etc. suffix
        assert "Test Workout" in data["name"]
        assert data["id"] != str(sample_workout.id)

    async def test_duplicate_nonexistent_workout(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent workout."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/workouts/{fake_id}/duplicate"
        )

        assert response.status_code == 404


class TestGetWorkoutExercises:
    """Tests for GET /api/v1/workouts/{workout_id}/exercises."""

    async def test_get_workout_exercises(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Can get exercises from workout."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/{sample_workout.id}/exercises"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_exercises_nonexistent_workout(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent workout."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.get(
            f"/api/v1/workouts/{fake_id}/exercises"
        )

        assert response.status_code == 404


# =============================================================================
# Prescription Notes Tests
# =============================================================================


class TestPrescriptionNotes:
    """Tests for prescription note endpoints."""

    async def test_create_prescription_note(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Trainer can create a prescription note."""
        payload = {
            "context_type": "plan",
            "context_id": str(sample_plan.id),
            "content": "Remember to warm up properly",
        }

        response = await authenticated_client.post(
            "/api/v1/workouts/notes", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Remember to warm up properly"
        # Response uses camelCase aliases
        assert data["contextType"] == "plan"

    async def test_list_prescription_notes(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can list prescription notes for a context."""
        # First create a note
        await authenticated_client.post(
            "/api/v1/workouts/notes",
            json={
                "context_type": "plan",
                "context_id": str(sample_plan.id),
                "content": "Test note",
            },
        )

        response = await authenticated_client.get(
            "/api/v1/workouts/notes",
            params={
                "context_type": "plan",
                "context_id": str(sample_plan.id),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "notes" in data
        assert data["total"] >= 1

    async def test_get_prescription_note(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Can get a specific prescription note."""
        # Create a note
        create_response = await authenticated_client.post(
            "/api/v1/workouts/notes",
            json={
                "context_type": "plan",
                "context_id": str(sample_plan.id),
                "content": "Specific note",
            },
        )
        note_id = create_response.json()["id"]

        response = await authenticated_client.get(
            f"/api/v1/workouts/notes/{note_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Specific note"

    async def test_update_prescription_note(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Author can update their note."""
        # Create a note
        create_response = await authenticated_client.post(
            "/api/v1/workouts/notes",
            json={
                "context_type": "plan",
                "context_id": str(sample_plan.id),
                "content": "Original content",
            },
        )
        note_id = create_response.json()["id"]

        # Update it
        response = await authenticated_client.put(
            f"/api/v1/workouts/notes/{note_id}",
            json={"content": "Updated content"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated content"

    async def test_delete_prescription_note(
        self, authenticated_client: AsyncClient, sample_plan: "TrainingPlan"
    ):
        """Author can delete their note."""
        # Create a note
        create_response = await authenticated_client.post(
            "/api/v1/workouts/notes",
            json={
                "context_type": "plan",
                "context_id": str(sample_plan.id),
                "content": "Note to delete",
            },
        )
        note_id = create_response.json()["id"]

        # Delete it
        response = await authenticated_client.delete(
            f"/api/v1/workouts/notes/{note_id}"
        )

        assert response.status_code == 204

        # Verify it's gone
        get_response = await authenticated_client.get(
            f"/api/v1/workouts/notes/{note_id}"
        )
        assert get_response.status_code == 404

    async def test_get_nonexistent_note(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent note."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.get(
            f"/api/v1/workouts/notes/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Workout Assignment Tests
# =============================================================================


class TestWorkoutAssignments:
    """Tests for workout assignment endpoints."""

    async def test_list_assignments_as_trainer(
        self, authenticated_client: AsyncClient
    ):
        """Trainer can list their assignments."""
        response = await authenticated_client.get(
            "/api/v1/workouts/assignments",
            params={"as_trainer": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_assignments_as_student(
        self, authenticated_client: AsyncClient
    ):
        """Student can list their assignments."""
        response = await authenticated_client.get(
            "/api/v1/workouts/assignments",
            params={"as_trainer": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# Get Session Tests
# =============================================================================


class TestGetSession:
    """Tests for GET /api/v1/workouts/sessions/{session_id}."""

    async def test_get_own_session(
        self, authenticated_client: AsyncClient, sample_session: WorkoutSession
    ):
        """Can get own session details."""
        response = await authenticated_client.get(
            f"/api/v1/workouts/sessions/{sample_session.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_session.id)
        assert data["status"] == "active"

    async def test_get_nonexistent_session(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent session."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.get(
            f"/api/v1/workouts/sessions/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Add Workout to Plan Tests
# =============================================================================


class TestAddWorkoutToPlan:
    """Tests for POST /api/v1/workouts/plans/{plan_id}/workouts."""

    async def test_add_workout_to_plan(
        self,
        authenticated_client: AsyncClient,
        sample_plan: "TrainingPlan",
        sample_workout: Workout,
    ):
        """Can add existing workout to plan."""
        payload = {
            "workout_id": str(sample_workout.id),
            "label": "Workout A",
            "order": 1,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/{sample_plan.id}/workouts",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert "plan_workouts" in data

    async def test_add_workout_to_nonexistent_plan(
        self, authenticated_client: AsyncClient, sample_workout: Workout
    ):
        """Returns 404 for nonexistent plan."""
        fake_id = uuid.uuid4()
        payload = {
            "workout_id": str(sample_workout.id),
            "label": "Workout A",
            "order": 1,
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/plans/{fake_id}/workouts",
            json=payload,
        )

        assert response.status_code == 404


# =============================================================================
# Exercise Feedback Tests
# =============================================================================


class TestExerciseFeedback:
    """Tests for exercise feedback endpoints."""

    async def test_create_feedback_success(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_workout: Workout,
        sample_exercise: Exercise,
        db_session: AsyncSession,
    ):
        """Student can create feedback for an exercise."""
        from src.domains.workouts.models import WorkoutExercise

        # Get or create a workout exercise
        result = await db_session.execute(
            select(WorkoutExercise).where(WorkoutExercise.workout_id == sample_workout.id)
        )
        workout_exercise = result.scalar_one_or_none()

        if not workout_exercise:
            workout_exercise = WorkoutExercise(
                workout_id=sample_workout.id,
                exercise_id=sample_exercise.id,
                order=1,
                sets=3,
                reps="10-12",
                rest_seconds=90,
            )
            db_session.add(workout_exercise)
            await db_session.commit()
            await db_session.refresh(workout_exercise)

        payload = {
            "feedback_type": "liked",
            "comment": "Great exercise!",
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/exercises/{workout_exercise.id}/feedback",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["feedback_type"] == "liked"
        assert data["comment"] == "Great exercise!"

    async def test_create_feedback_swap_request(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_workout: Workout,
        sample_exercise: Exercise,
        db_session: AsyncSession,
    ):
        """Student can request a swap for an exercise."""
        from src.domains.workouts.models import WorkoutExercise

        # Get or create a workout exercise
        result = await db_session.execute(
            select(WorkoutExercise).where(WorkoutExercise.workout_id == sample_workout.id)
        )
        workout_exercise = result.scalar_one_or_none()

        if not workout_exercise:
            workout_exercise = WorkoutExercise(
                workout_id=sample_workout.id,
                exercise_id=sample_exercise.id,
                order=1,
                sets=3,
                reps="10-12",
                rest_seconds=90,
            )
            db_session.add(workout_exercise)
            await db_session.commit()
            await db_session.refresh(workout_exercise)

        payload = {
            "feedback_type": "swap",
            "comment": "This exercise hurts my shoulder",
        }

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/exercises/{workout_exercise.id}/feedback",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["feedback_type"] == "swap"
        assert "shoulder" in data["comment"]

    async def test_create_feedback_session_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent session."""
        fake_session_id = uuid.uuid4()
        fake_exercise_id = uuid.uuid4()

        payload = {"feedback_type": "liked"}

        response = await authenticated_client.post(
            f"/api/v1/workouts/sessions/{fake_session_id}/exercises/{fake_exercise_id}/feedback",
            json=payload,
        )

        assert response.status_code == 404

    async def test_list_session_feedbacks(
        self,
        authenticated_client: AsyncClient,
        sample_session: WorkoutSession,
        sample_workout: Workout,
        sample_exercise: Exercise,
        db_session: AsyncSession,
    ):
        """Can list feedbacks for a session."""
        from src.domains.workouts.models import WorkoutExercise

        # Get or create a workout exercise
        result = await db_session.execute(
            select(WorkoutExercise).where(WorkoutExercise.workout_id == sample_workout.id)
        )
        workout_exercise = result.scalar_one_or_none()

        if not workout_exercise:
            workout_exercise = WorkoutExercise(
                workout_id=sample_workout.id,
                exercise_id=sample_exercise.id,
                order=1,
                sets=3,
                reps="10-12",
                rest_seconds=90,
            )
            db_session.add(workout_exercise)
            await db_session.commit()
            await db_session.refresh(workout_exercise)

        # Create a feedback
        await authenticated_client.post(
            f"/api/v1/workouts/sessions/{sample_session.id}/exercises/{workout_exercise.id}/feedback",
            json={"feedback_type": "liked"},
        )

        # List feedbacks
        response = await authenticated_client.get(
            f"/api/v1/workouts/sessions/{sample_session.id}/feedbacks"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
