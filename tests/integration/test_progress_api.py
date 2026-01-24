"""Integration tests for progress API endpoints."""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.progress.models import (
    MeasurementLog,
    PhotoAngle,
    ProgressPhoto,
    WeightGoal,
    WeightLog,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_weight_log(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> WeightLog:
    """Create a sample weight log."""
    log = WeightLog(
        user_id=sample_user["id"],
        weight_kg=75.5,
        logged_at=datetime.now(timezone.utc),
        notes="Morning weight",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log


@pytest.fixture
async def multiple_weight_logs(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> list[WeightLog]:
    """Create multiple weight logs for testing."""
    logs = []
    base_date = datetime.now(timezone.utc)
    for i in range(5):
        log = WeightLog(
            user_id=sample_user["id"],
            weight_kg=75.0 - (i * 0.5),
            logged_at=base_date - timedelta(days=i),
            notes=f"Day {i} weight",
        )
        db_session.add(log)
        logs.append(log)
    await db_session.commit()
    for log in logs:
        await db_session.refresh(log)
    return logs


@pytest.fixture
async def sample_measurement_log(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> MeasurementLog:
    """Create a sample measurement log."""
    log = MeasurementLog(
        user_id=sample_user["id"],
        logged_at=datetime.now(timezone.utc),
        chest_cm=100.0,
        waist_cm=80.0,
        hips_cm=95.0,
        biceps_cm=35.0,
        thigh_cm=55.0,
        calf_cm=38.0,
        neck_cm=40.0,
        forearm_cm=28.0,
        notes="Full measurement",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log


@pytest.fixture
async def sample_progress_photo(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> ProgressPhoto:
    """Create a sample progress photo."""
    photo = ProgressPhoto(
        user_id=sample_user["id"],
        photo_url="https://example.com/photo.jpg",
        thumbnail_url="https://example.com/photo_thumb.jpg",
        angle=PhotoAngle.FRONT,
        logged_at=datetime.now(timezone.utc),
        notes="Front view",
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)
    return photo


@pytest.fixture
async def sample_weight_goal(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> WeightGoal:
    """Create a sample weight goal."""
    goal = WeightGoal(
        user_id=sample_user["id"],
        target_weight_kg=70.0,
        start_weight_kg=80.0,
        target_date=datetime.now(timezone.utc) + timedelta(days=90),
        notes="Summer goal",
    )
    db_session.add(goal)
    await db_session.commit()
    await db_session.refresh(goal)
    return goal


@pytest.fixture
async def other_user_weight_log(
    db_session: AsyncSession, sample_organization_id: uuid.UUID
) -> WeightLog:
    """Create a weight log for another user."""
    from src.domains.users.models import User

    # Create another user
    other_user_id = uuid.uuid4()
    other_user = User(
        id=other_user_id,
        email=f"other-{other_user_id}@example.com",
        name="Other User",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.flush()

    # Create weight log for other user
    log = WeightLog(
        user_id=other_user_id,
        weight_kg=85.0,
        logged_at=datetime.now(timezone.utc),
        notes="Other user weight",
    )
    db_session.add(log)
    await db_session.commit()
    await db_session.refresh(log)
    return log


# =============================================================================
# Weight Log Endpoint Tests
# =============================================================================


class TestListWeightLogs:
    """Tests for GET /api/v1/progress/weight."""

    async def test_list_weight_logs_authenticated(
        self, authenticated_client: AsyncClient, sample_weight_log: WeightLog
    ):
        """Authenticated user can list their weight logs."""
        response = await authenticated_client.get("/api/v1/progress/weight")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["weight_kg"] == 75.5

    async def test_list_weight_logs_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/progress/weight")

        assert response.status_code == 401

    async def test_list_weight_logs_with_date_filter(
        self, authenticated_client: AsyncClient, multiple_weight_logs: list[WeightLog]
    ):
        """Can filter weight logs by date range."""
        today = date.today()
        yesterday = today - timedelta(days=1)
        response = await authenticated_client.get(
            "/api/v1/progress/weight",
            params={
                "from_date": yesterday.isoformat(),
                "to_date": today.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_weight_logs_pagination(
        self, authenticated_client: AsyncClient, multiple_weight_logs: list[WeightLog]
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/progress/weight", params={"limit": 2, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


class TestCreateWeightLog:
    """Tests for POST /api/v1/progress/weight."""

    async def test_create_weight_log_success(self, authenticated_client: AsyncClient):
        """Can create a new weight log."""
        payload = {
            "weight_kg": 72.5,
            "notes": "After workout",
        }

        response = await authenticated_client.post(
            "/api/v1/progress/weight", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["weight_kg"] == 72.5
        assert data["notes"] == "After workout"
        assert "id" in data

    async def test_create_weight_log_with_logged_at(
        self, authenticated_client: AsyncClient
    ):
        """Can create weight log with specific date."""
        logged_at = datetime.now(timezone.utc) - timedelta(days=1)
        payload = {
            "weight_kg": 73.0,
            "logged_at": logged_at.isoformat(),
        }

        response = await authenticated_client.post(
            "/api/v1/progress/weight", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["weight_kg"] == 73.0

    async def test_create_weight_log_invalid_weight(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid weight."""
        payload = {
            "weight_kg": -10.0,
        }

        response = await authenticated_client.post(
            "/api/v1/progress/weight", json=payload
        )

        assert response.status_code == 422


class TestGetWeightLog:
    """Tests for GET /api/v1/progress/weight/{log_id}."""

    async def test_get_weight_log_success(
        self, authenticated_client: AsyncClient, sample_weight_log: WeightLog
    ):
        """Can get a specific weight log."""
        response = await authenticated_client.get(
            f"/api/v1/progress/weight/{sample_weight_log.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["weight_kg"] == 75.5
        assert data["notes"] == "Morning weight"

    async def test_get_weight_log_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent weight log."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/progress/weight/{fake_id}"
        )

        assert response.status_code == 404

    async def test_get_weight_log_forbidden(
        self, authenticated_client: AsyncClient, other_user_weight_log: WeightLog
    ):
        """Returns 403 when accessing another user's weight log."""
        response = await authenticated_client.get(
            f"/api/v1/progress/weight/{other_user_weight_log.id}"
        )

        assert response.status_code == 403


class TestGetLatestWeight:
    """Tests for GET /api/v1/progress/weight/latest."""

    async def test_get_latest_weight_success(
        self, authenticated_client: AsyncClient, multiple_weight_logs: list[WeightLog]
    ):
        """Can get the most recent weight log."""
        response = await authenticated_client.get("/api/v1/progress/weight/latest")

        assert response.status_code == 200
        data = response.json()
        # The latest log (most recent) should have the highest weight in our fixture
        assert data["weight_kg"] == 75.0

    async def test_get_latest_weight_none(self, authenticated_client: AsyncClient):
        """Returns null when no weight logs exist."""
        response = await authenticated_client.get("/api/v1/progress/weight/latest")

        assert response.status_code == 200
        assert response.json() is None


class TestUpdateWeightLog:
    """Tests for PUT /api/v1/progress/weight/{log_id}."""

    async def test_update_weight_log_success(
        self, authenticated_client: AsyncClient, sample_weight_log: WeightLog
    ):
        """Can update a weight log."""
        payload = {
            "weight_kg": 74.0,
            "notes": "Updated notes",
        }

        response = await authenticated_client.put(
            f"/api/v1/progress/weight/{sample_weight_log.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["weight_kg"] == 74.0
        assert data["notes"] == "Updated notes"

    async def test_update_weight_log_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent weight log."""
        fake_id = uuid.uuid4()
        payload = {"weight_kg": 74.0}

        response = await authenticated_client.put(
            f"/api/v1/progress/weight/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestDeleteWeightLog:
    """Tests for DELETE /api/v1/progress/weight/{log_id}."""

    async def test_delete_weight_log_success(
        self, authenticated_client: AsyncClient, sample_weight_log: WeightLog
    ):
        """Can delete a weight log."""
        response = await authenticated_client.delete(
            f"/api/v1/progress/weight/{sample_weight_log.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/progress/weight/{sample_weight_log.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_weight_log_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent weight log."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"/api/v1/progress/weight/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Measurement Log Endpoint Tests
# =============================================================================


class TestListMeasurementLogs:
    """Tests for GET /api/v1/progress/measurements."""

    async def test_list_measurement_logs_authenticated(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Authenticated user can list their measurement logs."""
        response = await authenticated_client.get("/api/v1/progress/measurements")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["chest_cm"] == 100.0

    async def test_list_measurement_logs_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/progress/measurements")

        assert response.status_code == 401

    async def test_list_measurement_logs_pagination(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/progress/measurements", params={"limit": 10, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCreateMeasurementLog:
    """Tests for POST /api/v1/progress/measurements."""

    async def test_create_measurement_log_success(
        self, authenticated_client: AsyncClient
    ):
        """Can create a new measurement log."""
        payload = {
            "chest_cm": 95.0,
            "waist_cm": 78.0,
            "biceps_cm": 34.0,
            "notes": "Weekly measurement",
        }

        response = await authenticated_client.post(
            "/api/v1/progress/measurements", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["chest_cm"] == 95.0
        assert data["waist_cm"] == 78.0
        assert data["biceps_cm"] == 34.0
        assert "id" in data

    async def test_create_measurement_log_partial(
        self, authenticated_client: AsyncClient
    ):
        """Can create measurement log with partial measurements."""
        payload = {
            "waist_cm": 82.0,
        }

        response = await authenticated_client.post(
            "/api/v1/progress/measurements", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["waist_cm"] == 82.0
        assert data["chest_cm"] is None


class TestGetMeasurementLog:
    """Tests for GET /api/v1/progress/measurements/{log_id}."""

    async def test_get_measurement_log_success(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Can get a specific measurement log."""
        response = await authenticated_client.get(
            f"/api/v1/progress/measurements/{sample_measurement_log.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chest_cm"] == 100.0
        assert data["waist_cm"] == 80.0

    async def test_get_measurement_log_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent measurement log."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/progress/measurements/{fake_id}"
        )

        assert response.status_code == 404


class TestGetLatestMeasurements:
    """Tests for GET /api/v1/progress/measurements/latest."""

    async def test_get_latest_measurements_success(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Can get the most recent measurement log."""
        response = await authenticated_client.get(
            "/api/v1/progress/measurements/latest"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chest_cm"] == 100.0

    async def test_get_latest_measurements_none(
        self, authenticated_client: AsyncClient
    ):
        """Returns null when no measurement logs exist."""
        response = await authenticated_client.get(
            "/api/v1/progress/measurements/latest"
        )

        assert response.status_code == 200
        assert response.json() is None


class TestUpdateMeasurementLog:
    """Tests for PUT /api/v1/progress/measurements/{log_id}."""

    async def test_update_measurement_log_success(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Can update a measurement log."""
        payload = {
            "chest_cm": 102.0,
            "notes": "Updated measurement",
        }

        response = await authenticated_client.put(
            f"/api/v1/progress/measurements/{sample_measurement_log.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chest_cm"] == 102.0
        assert data["notes"] == "Updated measurement"

    async def test_update_measurement_log_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent measurement log."""
        fake_id = uuid.uuid4()
        payload = {"chest_cm": 100.0}

        response = await authenticated_client.put(
            f"/api/v1/progress/measurements/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestDeleteMeasurementLog:
    """Tests for DELETE /api/v1/progress/measurements/{log_id}."""

    async def test_delete_measurement_log_success(
        self, authenticated_client: AsyncClient, sample_measurement_log: MeasurementLog
    ):
        """Can delete a measurement log."""
        response = await authenticated_client.delete(
            f"/api/v1/progress/measurements/{sample_measurement_log.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/progress/measurements/{sample_measurement_log.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_measurement_log_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent measurement log."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"/api/v1/progress/measurements/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Progress Photo Endpoint Tests
# =============================================================================


class TestListPhotos:
    """Tests for GET /api/v1/progress/photos."""

    async def test_list_photos_authenticated(
        self, authenticated_client: AsyncClient, sample_progress_photo: ProgressPhoto
    ):
        """Authenticated user can list their progress photos."""
        response = await authenticated_client.get("/api/v1/progress/photos")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["angle"] == "front"

    async def test_list_photos_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/progress/photos")

        assert response.status_code == 401

    async def test_list_photos_filter_by_angle(
        self, authenticated_client: AsyncClient, sample_progress_photo: ProgressPhoto
    ):
        """Can filter photos by angle."""
        response = await authenticated_client.get(
            "/api/v1/progress/photos", params={"angle": "front"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["angle"] == "front" for p in data)


class TestCreatePhoto:
    """Tests for POST /api/v1/progress/photos."""

    async def test_create_photo_success(self, authenticated_client: AsyncClient):
        """Can create a new progress photo."""
        payload = {
            "photo_url": "https://example.com/new_photo.jpg",
            "thumbnail_url": "https://example.com/new_photo_thumb.jpg",
            "angle": "side",
            "notes": "Side progress",
        }

        response = await authenticated_client.post(
            "/api/v1/progress/photos", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["photo_url"] == "https://example.com/new_photo.jpg"
        assert data["angle"] == "side"
        assert "id" in data

    async def test_create_photo_with_linked_weight_log(
        self, authenticated_client: AsyncClient, sample_weight_log: WeightLog
    ):
        """Can create photo linked to weight log."""
        payload = {
            "photo_url": "https://example.com/photo_with_weight.jpg",
            "angle": "back",
            "weight_log_id": str(sample_weight_log.id),
        }

        response = await authenticated_client.post(
            "/api/v1/progress/photos", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["weight_log_id"] == str(sample_weight_log.id)


class TestDeletePhoto:
    """Tests for DELETE /api/v1/progress/photos/{photo_id}."""

    async def test_delete_photo_success(
        self, authenticated_client: AsyncClient, sample_progress_photo: ProgressPhoto
    ):
        """Can delete a progress photo."""
        response = await authenticated_client.delete(
            f"/api/v1/progress/photos/{sample_progress_photo.id}"
        )

        assert response.status_code == 204

    async def test_delete_photo_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent photo."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"/api/v1/progress/photos/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Weight Goal Endpoint Tests
# =============================================================================


class TestGetWeightGoal:
    """Tests for GET /api/v1/progress/goal."""

    async def test_get_weight_goal_success(
        self, authenticated_client: AsyncClient, sample_weight_goal: WeightGoal
    ):
        """Can get weight goal."""
        response = await authenticated_client.get("/api/v1/progress/goal")

        assert response.status_code == 200
        data = response.json()
        assert data["target_weight_kg"] == 70.0
        assert data["start_weight_kg"] == 80.0
        assert data["weight_to_lose"] == 10.0

    async def test_get_weight_goal_none(self, authenticated_client: AsyncClient):
        """Returns null when no weight goal exists."""
        response = await authenticated_client.get("/api/v1/progress/goal")

        assert response.status_code == 200
        assert response.json() is None


class TestCreateOrUpdateWeightGoal:
    """Tests for POST /api/v1/progress/goal."""

    async def test_create_weight_goal_success(
        self, authenticated_client: AsyncClient
    ):
        """Can create a new weight goal."""
        target_date = datetime.now(timezone.utc) + timedelta(days=60)
        payload = {
            "target_weight_kg": 65.0,
            "start_weight_kg": 75.0,
            "target_date": target_date.isoformat(),
            "notes": "New year goal",
        }

        response = await authenticated_client.post(
            "/api/v1/progress/goal", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["target_weight_kg"] == 65.0
        assert data["start_weight_kg"] == 75.0
        assert data["weight_to_lose"] == 10.0
        assert "id" in data

    async def test_update_existing_weight_goal(
        self, authenticated_client: AsyncClient, sample_weight_goal: WeightGoal
    ):
        """Can update existing weight goal."""
        payload = {
            "target_weight_kg": 68.0,
            "start_weight_kg": 80.0,
            "notes": "Updated goal",
        }

        response = await authenticated_client.post(
            "/api/v1/progress/goal", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["target_weight_kg"] == 68.0


class TestDeleteWeightGoal:
    """Tests for DELETE /api/v1/progress/goal."""

    async def test_delete_weight_goal_success(
        self, authenticated_client: AsyncClient, sample_weight_goal: WeightGoal
    ):
        """Can delete weight goal."""
        response = await authenticated_client.delete("/api/v1/progress/goal")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get("/api/v1/progress/goal")
        assert get_response.status_code == 200
        assert get_response.json() is None

    async def test_delete_weight_goal_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when no weight goal exists."""
        response = await authenticated_client.delete("/api/v1/progress/goal")

        assert response.status_code == 404


# =============================================================================
# Progress Stats Endpoint Tests
# =============================================================================


class TestGetProgressStats:
    """Tests for GET /api/v1/progress/stats."""

    async def test_get_progress_stats_success(
        self,
        authenticated_client: AsyncClient,
        multiple_weight_logs: list[WeightLog],
        sample_measurement_log: MeasurementLog,
    ):
        """Can get progress statistics."""
        response = await authenticated_client.get("/api/v1/progress/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 30
        assert data["weight_logs_count"] >= 1
        assert data["measurement_logs_count"] >= 1
        assert "latest_weight_kg" in data
        assert "weight_change_kg" in data

    async def test_get_progress_stats_custom_period(
        self, authenticated_client: AsyncClient, multiple_weight_logs: list[WeightLog]
    ):
        """Can get stats for custom period."""
        response = await authenticated_client.get(
            "/api/v1/progress/stats", params={"days": 7}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    async def test_get_progress_stats_with_goal(
        self,
        authenticated_client: AsyncClient,
        multiple_weight_logs: list[WeightLog],
        sample_weight_goal: WeightGoal,
    ):
        """Stats include goal progress when goal exists."""
        response = await authenticated_client.get("/api/v1/progress/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["goal_weight_kg"] == 70.0
        assert "goal_progress_percent" in data

    async def test_get_progress_stats_empty(self, authenticated_client: AsyncClient):
        """Stats work when no data exists."""
        response = await authenticated_client.get("/api/v1/progress/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["weight_logs_count"] == 0
        assert data["measurement_logs_count"] == 0
        assert data["weight_change_kg"] == 0.0
