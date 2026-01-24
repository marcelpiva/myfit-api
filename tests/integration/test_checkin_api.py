"""Integration tests for check-in API endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.checkin.models import (
    CheckIn,
    CheckInCode,
    CheckInMethod,
    CheckInRequest,
    CheckInStatus,
    Gym,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_gym(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Gym:
    """Create a sample gym."""
    gym = Gym(
        organization_id=sample_user["organization_id"],
        name="Test Gym",
        address="123 Test Street, Test City",
        latitude=-23.5505,
        longitude=-46.6333,
        phone="+55 11 99999-9999",
        radius_meters=100,
        is_active=True,
    )
    db_session.add(gym)
    await db_session.commit()
    await db_session.refresh(gym)
    return gym


@pytest.fixture
async def sample_gym_2(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Gym:
    """Create a second sample gym."""
    gym = Gym(
        organization_id=sample_user["organization_id"],
        name="Second Gym",
        address="456 Another Street, Test City",
        latitude=-23.5600,
        longitude=-46.6400,
        phone="+55 11 88888-8888",
        radius_meters=150,
        is_active=True,
    )
    db_session.add(gym)
    await db_session.commit()
    await db_session.refresh(gym)
    return gym


@pytest.fixture
async def inactive_gym(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Gym:
    """Create an inactive gym."""
    gym = Gym(
        organization_id=sample_user["organization_id"],
        name="Inactive Gym",
        address="789 Closed Street, Test City",
        latitude=-23.5700,
        longitude=-46.6500,
        radius_meters=100,
        is_active=False,
    )
    db_session.add(gym)
    await db_session.commit()
    await db_session.refresh(gym)
    return gym


@pytest.fixture
async def sample_checkin(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_gym: Gym
) -> CheckIn:
    """Create a sample active check-in."""
    checkin = CheckIn(
        user_id=sample_user["id"],
        gym_id=sample_gym.id,
        method=CheckInMethod.MANUAL,
        status=CheckInStatus.CONFIRMED,
    )
    db_session.add(checkin)
    await db_session.commit()
    await db_session.refresh(checkin)
    return checkin


@pytest.fixture
async def completed_checkin(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_gym: Gym
) -> CheckIn:
    """Create a completed (checked out) check-in."""
    checkin = CheckIn(
        user_id=sample_user["id"],
        gym_id=sample_gym.id,
        method=CheckInMethod.MANUAL,
        status=CheckInStatus.CONFIRMED,
        checked_out_at=datetime.now(timezone.utc),
    )
    db_session.add(checkin)
    await db_session.commit()
    await db_session.refresh(checkin)
    return checkin


@pytest.fixture
async def sample_checkin_code(
    db_session: AsyncSession, sample_gym: Gym
) -> CheckInCode:
    """Create a sample check-in code."""
    code = CheckInCode(
        gym_id=sample_gym.id,
        code="TESTCODE",
        is_active=True,
        uses_count=0,
        max_uses=10,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add(code)
    await db_session.commit()
    await db_session.refresh(code)
    return code


@pytest.fixture
async def expired_checkin_code(
    db_session: AsyncSession, sample_gym: Gym
) -> CheckInCode:
    """Create an expired check-in code."""
    code = CheckInCode(
        gym_id=sample_gym.id,
        code="EXPIRED1",
        is_active=True,
        uses_count=0,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(code)
    await db_session.commit()
    await db_session.refresh(code)
    return code


@pytest.fixture
async def maxed_out_code(
    db_session: AsyncSession, sample_gym: Gym
) -> CheckInCode:
    """Create a check-in code that has reached max uses."""
    code = CheckInCode(
        gym_id=sample_gym.id,
        code="MAXEDOUT",
        is_active=True,
        uses_count=5,
        max_uses=5,
    )
    db_session.add(code)
    await db_session.commit()
    await db_session.refresh(code)
    return code


@pytest.fixture
async def sample_checkin_request(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_gym: Gym, student_user: dict[str, Any]
) -> CheckInRequest:
    """Create a sample check-in request."""
    request = CheckInRequest(
        user_id=student_user["id"],
        gym_id=sample_gym.id,
        approver_id=sample_user["id"],
        status=CheckInStatus.PENDING,
        reason="I forgot my card",
    )
    db_session.add(request)
    await db_session.commit()
    await db_session.refresh(request)
    return request


# =============================================================================
# List Gyms Tests
# =============================================================================


class TestListGyms:
    """Tests for GET /api/v1/checkins/gyms."""

    async def test_list_gyms_empty(
        self, authenticated_client: AsyncClient
    ):
        """Returns empty list when no gyms exist."""
        response = await authenticated_client.get("/api/v1/checkins/gyms")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_gyms_returns_active_gyms(
        self, authenticated_client: AsyncClient, sample_gym: Gym, sample_gym_2: Gym
    ):
        """Returns list of active gyms."""
        response = await authenticated_client.get("/api/v1/checkins/gyms")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        gym_names = [g["name"] for g in data]
        assert "Test Gym" in gym_names
        assert "Second Gym" in gym_names

    async def test_list_gyms_excludes_inactive(
        self, authenticated_client: AsyncClient, sample_gym: Gym, inactive_gym: Gym
    ):
        """Inactive gyms are excluded by default."""
        response = await authenticated_client.get("/api/v1/checkins/gyms")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Gym"

    async def test_list_gyms_filter_by_organization(
        self, authenticated_client: AsyncClient, sample_gym: Gym, sample_user: dict[str, Any]
    ):
        """Can filter gyms by organization."""
        response = await authenticated_client.get(
            f"/api/v1/checkins/gyms?organization_id={sample_user['organization_id']}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["organization_id"] == str(sample_user["organization_id"])

    async def test_list_gyms_pagination(
        self, authenticated_client: AsyncClient, sample_gym: Gym, sample_gym_2: Gym
    ):
        """Pagination works correctly."""
        response = await authenticated_client.get("/api/v1/checkins/gyms?limit=1&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    async def test_list_gyms_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/checkins/gyms")

        assert response.status_code == 401


# =============================================================================
# Create Gym Tests
# =============================================================================


class TestCreateGym:
    """Tests for POST /api/v1/checkins/gyms."""

    async def test_create_gym_success(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can create a new gym."""
        payload = {
            "organization_id": str(sample_user["organization_id"]),
            "name": "New Fitness Center",
            "address": "100 New Street, Test City",
            "latitude": -23.5550,
            "longitude": -46.6350,
            "phone": "+55 11 77777-7777",
            "radius_meters": 200,
        }

        response = await authenticated_client.post("/api/v1/checkins/gyms", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Fitness Center"
        assert data["address"] == "100 New Street, Test City"
        assert data["latitude"] == -23.5550
        assert data["longitude"] == -46.6350
        assert data["radius_meters"] == 200
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_gym_minimal_fields(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can create gym with only required fields."""
        payload = {
            "organization_id": str(sample_user["organization_id"]),
            "name": "Minimal Gym",
            "address": "50 Minimal Street",
            "latitude": -23.5600,
            "longitude": -46.6400,
        }

        response = await authenticated_client.post("/api/v1/checkins/gyms", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Gym"
        assert data["phone"] is None
        assert data["radius_meters"] == 100  # default value

    async def test_create_gym_invalid_latitude(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Invalid latitude returns validation error."""
        payload = {
            "organization_id": str(sample_user["organization_id"]),
            "name": "Invalid Gym",
            "address": "Invalid Street",
            "latitude": 100.0,  # Invalid: must be between -90 and 90
            "longitude": -46.6333,
        }

        response = await authenticated_client.post("/api/v1/checkins/gyms", json=payload)

        assert response.status_code == 422

    async def test_create_gym_invalid_longitude(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Invalid longitude returns validation error."""
        payload = {
            "organization_id": str(sample_user["organization_id"]),
            "name": "Invalid Gym",
            "address": "Invalid Street",
            "latitude": -23.5505,
            "longitude": 200.0,  # Invalid: must be between -180 and 180
        }

        response = await authenticated_client.post("/api/v1/checkins/gyms", json=payload)

        assert response.status_code == 422

    async def test_create_gym_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {
            "organization_id": str(uuid.uuid4()),
            "name": "Test Gym",
            "address": "Test Street",
            "latitude": -23.5505,
            "longitude": -46.6333,
        }

        response = await client.post("/api/v1/checkins/gyms", json=payload)

        assert response.status_code == 401


# =============================================================================
# Get Gym Tests
# =============================================================================


class TestGetGym:
    """Tests for GET /api/v1/checkins/gyms/{gym_id}."""

    async def test_get_gym_success(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can get gym by ID."""
        response = await authenticated_client.get(f"/api/v1/checkins/gyms/{sample_gym.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_gym.id)
        assert data["name"] == "Test Gym"
        assert data["address"] == "123 Test Street, Test City"

    async def test_get_gym_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for non-existent gym."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(f"/api/v1/checkins/gyms/{fake_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Gym not found"

    async def test_get_gym_unauthenticated(self, client: AsyncClient, sample_gym: Gym):
        """Unauthenticated request returns 401."""
        response = await client.get(f"/api/v1/checkins/gyms/{sample_gym.id}")

        assert response.status_code == 401


# =============================================================================
# Check-in by Location Tests
# =============================================================================


class TestCheckinByLocation:
    """Tests for POST /api/v1/checkins/location."""

    async def test_checkin_by_location_success(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can check in when within gym radius."""
        # Location very close to gym coordinates
        payload = {
            "latitude": -23.5505,
            "longitude": -46.6333,
        }

        response = await authenticated_client.post("/api/v1/checkins/location", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["checkin"] is not None
        assert data["checkin"]["method"] == "location"
        assert data["nearest_gym"]["id"] == str(sample_gym.id)
        assert data["message"] == f"Checked in at {sample_gym.name}"

    async def test_checkin_by_location_too_far(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Returns failure when too far from gym."""
        # Location far from gym (approximately 1km away)
        payload = {
            "latitude": -23.5605,
            "longitude": -46.6433,
        }

        response = await authenticated_client.post("/api/v1/checkins/location", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["checkin"] is None
        assert "Too far from nearest gym" in data["message"]

    async def test_checkin_by_location_no_gyms(
        self, authenticated_client: AsyncClient
    ):
        """Returns appropriate message when no gyms exist."""
        payload = {
            "latitude": -23.5505,
            "longitude": -46.6333,
        }

        response = await authenticated_client.post("/api/v1/checkins/location", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["message"] == "No gyms found"

    async def test_checkin_by_location_already_checked_in(
        self, authenticated_client: AsyncClient, sample_gym: Gym, sample_checkin: CheckIn
    ):
        """Returns 400 when already checked in."""
        payload = {
            "latitude": -23.5505,
            "longitude": -46.6333,
        }

        response = await authenticated_client.post("/api/v1/checkins/location", json=payload)

        assert response.status_code == 400
        assert "Already checked in" in response.json()["detail"]

    async def test_checkin_by_location_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {
            "latitude": -23.5505,
            "longitude": -46.6333,
        }

        response = await client.post("/api/v1/checkins/location", json=payload)

        assert response.status_code == 401


# =============================================================================
# Check-in by Code Tests
# =============================================================================


class TestCheckinByCode:
    """Tests for POST /api/v1/checkins/code."""

    async def test_checkin_by_code_success(
        self, authenticated_client: AsyncClient, sample_checkin_code: CheckInCode
    ):
        """Can check in using valid code."""
        payload = {"code": sample_checkin_code.code}

        response = await authenticated_client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["method"] == "code"
        assert data["gym_id"] == str(sample_checkin_code.gym_id)

    async def test_checkin_by_code_invalid_code(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for invalid code."""
        payload = {"code": "INVALIDCODE"}

        response = await authenticated_client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 404
        assert response.json()["detail"] == "Invalid check-in code"

    async def test_checkin_by_code_expired(
        self, authenticated_client: AsyncClient, expired_checkin_code: CheckInCode
    ):
        """Returns 400 for expired code."""
        payload = {"code": expired_checkin_code.code}

        response = await authenticated_client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    async def test_checkin_by_code_max_uses_reached(
        self, authenticated_client: AsyncClient, maxed_out_code: CheckInCode
    ):
        """Returns 400 when code has reached max uses."""
        payload = {"code": maxed_out_code.code}

        response = await authenticated_client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower() or "maximum uses" in response.json()["detail"].lower()

    async def test_checkin_by_code_already_checked_in(
        self, authenticated_client: AsyncClient, sample_checkin_code: CheckInCode, sample_checkin: CheckIn
    ):
        """Returns 400 when already checked in."""
        payload = {"code": sample_checkin_code.code}

        response = await authenticated_client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 400
        assert "Already checked in" in response.json()["detail"]

    async def test_checkin_by_code_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {"code": "TESTCODE"}

        response = await client.post("/api/v1/checkins/code", json=payload)

        assert response.status_code == 401


# =============================================================================
# Get Active Check-in Tests
# =============================================================================


class TestGetActiveCheckin:
    """Tests for GET /api/v1/checkins/active."""

    async def test_get_active_checkin_exists(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn
    ):
        """Returns active check-in when exists."""
        response = await authenticated_client.get("/api/v1/checkins/active")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_checkin.id)
        assert data["is_active"] is True
        assert data["checked_out_at"] is None

    async def test_get_active_checkin_none(
        self, authenticated_client: AsyncClient
    ):
        """Returns null when no active check-in."""
        response = await authenticated_client.get("/api/v1/checkins/active")

        assert response.status_code == 200
        assert response.json() is None

    async def test_get_active_checkin_after_checkout(
        self, authenticated_client: AsyncClient, completed_checkin: CheckIn
    ):
        """Returns null when check-in is completed."""
        response = await authenticated_client.get("/api/v1/checkins/active")

        assert response.status_code == 200
        assert response.json() is None

    async def test_get_active_checkin_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/checkins/active")

        assert response.status_code == 401


# =============================================================================
# Checkout Tests
# =============================================================================


class TestCheckout:
    """Tests for POST /api/v1/checkins/checkout."""

    async def test_checkout_success(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn
    ):
        """Can checkout from active check-in."""
        response = await authenticated_client.post("/api/v1/checkins/checkout")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_checkin.id)
        assert data["is_active"] is False
        assert data["checked_out_at"] is not None

    async def test_checkout_with_notes(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn
    ):
        """Can checkout with notes."""
        payload = {"notes": "Great workout session!"}

        response = await authenticated_client.post("/api/v1/checkins/checkout", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Great workout session!"

    async def test_checkout_not_checked_in(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 when not checked in."""
        response = await authenticated_client.post("/api/v1/checkins/checkout")

        assert response.status_code == 400
        assert response.json()["detail"] == "Not currently checked in"

    async def test_checkout_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.post("/api/v1/checkins/checkout")

        assert response.status_code == 401


# =============================================================================
# Check-in History Tests
# =============================================================================


class TestCheckinHistory:
    """Tests for GET /api/v1/checkins/."""

    async def test_list_checkins_empty(
        self, authenticated_client: AsyncClient
    ):
        """Returns empty list when no check-ins exist."""
        response = await authenticated_client.get("/api/v1/checkins/")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_checkins_returns_user_checkins(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn, completed_checkin: CheckIn
    ):
        """Returns user's check-in history."""
        response = await authenticated_client.get("/api/v1/checkins/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_list_checkins_filter_by_gym(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn, sample_gym: Gym
    ):
        """Can filter check-ins by gym."""
        response = await authenticated_client.get(f"/api/v1/checkins/?gym_id={sample_gym.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert all(c["gym_id"] == str(sample_gym.id) for c in data)

    async def test_list_checkins_pagination(
        self, authenticated_client: AsyncClient, sample_checkin: CheckIn, completed_checkin: CheckIn
    ):
        """Pagination works correctly."""
        response = await authenticated_client.get("/api/v1/checkins/?limit=1&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

    async def test_list_checkins_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/checkins/")

        assert response.status_code == 401


# =============================================================================
# Create Check-in Code Tests
# =============================================================================


class TestCreateCheckinCode:
    """Tests for POST /api/v1/checkins/codes."""

    async def test_create_code_success(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can create a check-in code."""
        payload = {
            "gym_id": str(sample_gym.id),
            "max_uses": 10,
        }

        response = await authenticated_client.post("/api/v1/checkins/codes", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["gym_id"] == str(sample_gym.id)
        assert data["max_uses"] == 10
        assert data["uses_count"] == 0
        assert data["is_active"] is True
        assert "code" in data

    async def test_create_code_with_expiration(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can create a code with expiration date."""
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        payload = {
            "gym_id": str(sample_gym.id),
            "expires_at": expires_at,
        }

        response = await authenticated_client.post("/api/v1/checkins/codes", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None

    async def test_create_code_gym_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for non-existent gym."""
        payload = {
            "gym_id": str(uuid.uuid4()),
        }

        response = await authenticated_client.post("/api/v1/checkins/codes", json=payload)

        assert response.status_code == 404
        assert response.json()["detail"] == "Gym not found"

    async def test_create_code_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {"gym_id": str(uuid.uuid4())}

        response = await client.post("/api/v1/checkins/codes", json=payload)

        assert response.status_code == 401


# =============================================================================
# Update Gym Tests
# =============================================================================


class TestUpdateGym:
    """Tests for PUT /api/v1/checkins/gyms/{gym_id}."""

    async def test_update_gym_name(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can update gym name."""
        payload = {"name": "Updated Gym Name"}

        response = await authenticated_client.put(
            f"/api/v1/checkins/gyms/{sample_gym.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Gym Name"

    async def test_update_gym_multiple_fields(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can update multiple gym fields."""
        payload = {
            "name": "New Name",
            "address": "New Address",
            "radius_meters": 250,
        }

        response = await authenticated_client.put(
            f"/api/v1/checkins/gyms/{sample_gym.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["address"] == "New Address"
        assert data["radius_meters"] == 250

    async def test_update_gym_deactivate(
        self, authenticated_client: AsyncClient, sample_gym: Gym
    ):
        """Can deactivate a gym."""
        payload = {"is_active": False}

        response = await authenticated_client.put(
            f"/api/v1/checkins/gyms/{sample_gym.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    async def test_update_gym_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for non-existent gym."""
        fake_id = uuid.uuid4()
        payload = {"name": "Updated Name"}

        response = await authenticated_client.put(
            f"/api/v1/checkins/gyms/{fake_id}", json=payload
        )

        assert response.status_code == 404

    async def test_update_gym_unauthenticated(self, client: AsyncClient, sample_gym: Gym):
        """Unauthenticated request returns 401."""
        payload = {"name": "Updated Name"}

        response = await client.put(
            f"/api/v1/checkins/gyms/{sample_gym.id}", json=payload
        )

        assert response.status_code == 401


# =============================================================================
# Check-in Stats Tests
# =============================================================================


class TestCheckinStats:
    """Tests for GET /api/v1/checkins/stats."""

    async def test_get_stats_empty(
        self, authenticated_client: AsyncClient
    ):
        """Returns zero stats when no check-ins exist."""
        response = await authenticated_client.get("/api/v1/checkins/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_checkins"] == 0
        assert data["total_duration_minutes"] == 0
        assert data["avg_duration_minutes"] == 0

    async def test_get_stats_with_checkins(
        self, authenticated_client: AsyncClient, completed_checkin: CheckIn
    ):
        """Returns stats for user's check-ins."""
        response = await authenticated_client.get("/api/v1/checkins/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_checkins"] >= 1
        assert data["period_days"] == 30  # default

    async def test_get_stats_custom_period(
        self, authenticated_client: AsyncClient, completed_checkin: CheckIn
    ):
        """Can specify custom period for stats."""
        response = await authenticated_client.get("/api/v1/checkins/stats?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    async def test_get_stats_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/checkins/stats")

        assert response.status_code == 401


# =============================================================================
# Deactivate Code Tests
# =============================================================================


class TestDeactivateCode:
    """Tests for DELETE /api/v1/checkins/codes/{code}."""

    async def test_deactivate_code_success(
        self, authenticated_client: AsyncClient, sample_checkin_code: CheckInCode
    ):
        """Can deactivate a check-in code."""
        response = await authenticated_client.delete(
            f"/api/v1/checkins/codes/{sample_checkin_code.code}"
        )

        assert response.status_code == 204

    async def test_deactivate_code_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for non-existent code."""
        response = await authenticated_client.delete("/api/v1/checkins/codes/NONEXISTENT")

        assert response.status_code == 404
        assert response.json()["detail"] == "Code not found"

    async def test_deactivate_code_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.delete("/api/v1/checkins/codes/TESTCODE")

        assert response.status_code == 401


# =============================================================================
# Check-in Requests Tests
# =============================================================================


class TestCheckinRequests:
    """Tests for check-in request endpoints."""

    async def test_list_pending_requests_empty(
        self, authenticated_client: AsyncClient
    ):
        """Returns empty list when no pending requests."""
        response = await authenticated_client.get("/api/v1/checkins/requests")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_pending_requests(
        self, authenticated_client: AsyncClient, sample_checkin_request: CheckInRequest
    ):
        """Returns pending requests for approver."""
        response = await authenticated_client.get("/api/v1/checkins/requests")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "pending"

    async def test_create_request_success(
        self, authenticated_client: AsyncClient, sample_gym: Gym, sample_user: dict[str, Any]
    ):
        """Can create a check-in request."""
        payload = {
            "gym_id": str(sample_gym.id),
            "approver_id": str(sample_user["id"]),
            "reason": "Forgot my card",
        }

        response = await authenticated_client.post("/api/v1/checkins/requests", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["gym_id"] == str(sample_gym.id)
        assert data["status"] == "pending"
        assert data["reason"] == "Forgot my card"

    async def test_create_request_gym_not_found(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns 404 for non-existent gym."""
        payload = {
            "gym_id": str(uuid.uuid4()),
            "approver_id": str(sample_user["id"]),
        }

        response = await authenticated_client.post("/api/v1/checkins/requests", json=payload)

        assert response.status_code == 404
        assert response.json()["detail"] == "Gym not found"

    async def test_respond_to_request_approve(
        self, authenticated_client: AsyncClient, sample_checkin_request: CheckInRequest
    ):
        """Can approve a check-in request."""
        payload = {
            "approved": True,
            "response_note": "Approved",
        }

        response = await authenticated_client.post(
            f"/api/v1/checkins/requests/{sample_checkin_request.id}/respond",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["response_note"] == "Approved"

    async def test_respond_to_request_deny(
        self, authenticated_client: AsyncClient, sample_checkin_request: CheckInRequest
    ):
        """Can deny a check-in request."""
        payload = {
            "approved": False,
            "response_note": "Not authorized",
        }

        response = await authenticated_client.post(
            f"/api/v1/checkins/requests/{sample_checkin_request.id}/respond",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

    async def test_respond_to_request_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for non-existent request."""
        fake_id = uuid.uuid4()
        payload = {"approved": True}

        response = await authenticated_client.post(
            f"/api/v1/checkins/requests/{fake_id}/respond",
            json=payload,
        )

        assert response.status_code == 404

    async def test_create_request_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {
            "gym_id": str(uuid.uuid4()),
            "approver_id": str(uuid.uuid4()),
        }

        response = await client.post("/api/v1/checkins/requests", json=payload)

        assert response.status_code == 401
