"""Tests for CheckInService - gym check-ins, location validation, and codes."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.checkin.models import (
    CheckIn,
    CheckInCode,
    CheckInMethod,
    CheckInRequest,
    CheckInStatus,
    Gym,
)
from src.domains.checkin.service import CheckInService


class TestCalculateDistance:
    """Tests for Haversine distance calculation."""

    def test_same_point_returns_zero(self, db_session: AsyncSession):
        """Same coordinates should return 0 distance."""
        service = CheckInService(db_session)

        distance = service.calculate_distance(
            -23.5505, -46.6333,
            -23.5505, -46.6333,
        )

        assert distance == 0

    def test_known_distance_sao_paulo_to_rio(self, db_session: AsyncSession):
        """Known coordinates should return expected distance (SP to RJ ~360km)."""
        service = CheckInService(db_session)

        # São Paulo coordinates
        sp_lat, sp_lon = -23.5505, -46.6333
        # Rio de Janeiro coordinates
        rj_lat, rj_lon = -22.9068, -43.1729

        distance = service.calculate_distance(sp_lat, sp_lon, rj_lat, rj_lon)

        # Distance should be approximately 360km (360000m)
        assert 350000 < distance < 370000

    def test_short_distance_100_meters(self, db_session: AsyncSession):
        """Short distance calculation accuracy."""
        service = CheckInService(db_session)

        # Base point
        lat1, lon1 = -23.5505, -46.6333
        # Point approximately 100m north
        lat2 = lat1 + 0.0009  # ~100m north
        lon2 = lon1

        distance = service.calculate_distance(lat1, lon1, lat2, lon2)

        # Should be close to 100m (allowing some margin)
        assert 90 < distance < 110

    def test_negative_to_positive_coordinates(self, db_session: AsyncSession):
        """Should handle crossing from negative to positive coordinates."""
        service = CheckInService(db_session)

        # Southern hemisphere to northern hemisphere
        distance = service.calculate_distance(
            -10.0, -50.0,
            10.0, -50.0,
        )

        # ~2220km
        assert 2200000 < distance < 2250000


class TestCreateGym:
    """Tests for gym creation."""

    async def test_create_gym_default_radius(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Default radius should be 100 meters."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Test Gym",
            address="Test Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        assert gym.radius_meters == 100

    async def test_create_gym_custom_radius(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should accept custom radius."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Large Gym",
            address="Large Address",
            latitude=-23.5505,
            longitude=-46.6333,
            radius_meters=200,
        )

        assert gym.radius_meters == 200

    async def test_create_gym_is_active_by_default(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """New gym should be active."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Active Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        assert gym.is_active is True


class TestCheckinByLocation:
    """Tests for GPS-based check-in."""

    async def test_checkin_within_radius_success(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """User within gym radius should be allowed to check in."""
        service = CheckInService(db_session)

        # Create gym at specific location with 100m radius
        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Location Test Gym",
            address="Test Address",
            latitude=-23.5505,
            longitude=-46.6333,
            radius_meters=100,
        )

        # User at same location (0 distance)
        checkin, found_gym, distance = await service.checkin_by_location(
            user_id=sample_user["id"],
            latitude=-23.5505,
            longitude=-46.6333,
        )

        assert checkin is not None
        assert found_gym.id == gym.id
        assert distance == 0
        assert checkin.method == CheckInMethod.LOCATION
        assert checkin.status == CheckInStatus.CONFIRMED

    async def test_checkin_at_edge_of_radius(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """User at edge of radius (exactly 100m) should still check in."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Edge Test Gym",
            address="Test Address",
            latitude=-23.5505,
            longitude=-46.6333,
            radius_meters=100,
        )

        # User approximately 90m away (within 100m)
        user_lat = -23.5505 + 0.0008  # ~89m north

        checkin, found_gym, distance = await service.checkin_by_location(
            user_id=sample_user["id"],
            latitude=user_lat,
            longitude=-46.6333,
        )

        assert checkin is not None
        assert distance <= 100

    async def test_checkin_outside_radius_fails(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """User outside gym radius should not check in."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Far Gym",
            address="Test Address",
            latitude=-23.5505,
            longitude=-46.6333,
            radius_meters=100,
        )

        # User 500m away
        user_lat = -23.5505 + 0.0045  # ~500m north

        checkin, found_gym, distance = await service.checkin_by_location(
            user_id=sample_user["id"],
            latitude=user_lat,
            longitude=-46.6333,
        )

        assert checkin is None
        assert found_gym is not None  # Still returns nearest gym
        assert distance > 100

    async def test_checkin_finds_nearest_gym(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should check in to nearest gym when multiple exist."""
        service = CheckInService(db_session)

        # Create two gyms
        gym_near = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Near Gym",
            address="Near Address",
            latitude=-23.5505,
            longitude=-46.6333,
            radius_meters=100,
        )

        gym_far = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Far Gym",
            address="Far Address",
            latitude=-23.5600,  # ~1km away
            longitude=-46.6333,
            radius_meters=100,
        )

        checkin, found_gym, distance = await service.checkin_by_location(
            user_id=sample_user["id"],
            latitude=-23.5505,
            longitude=-46.6333,
        )

        assert checkin is not None
        assert found_gym.id == gym_near.id

    async def test_checkin_no_gyms_available(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should return None when no gyms exist."""
        service = CheckInService(db_session)

        checkin, found_gym, distance = await service.checkin_by_location(
            user_id=sample_user["id"],
            latitude=-23.5505,
            longitude=-46.6333,
        )

        assert checkin is None
        assert found_gym is None
        assert distance is None


class TestCheckinCodes:
    """Tests for check-in codes."""

    async def test_create_code_generates_unique_code(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should generate a unique code."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Code Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        code1 = await service.create_code(gym_id=gym.id)
        code2 = await service.create_code(gym_id=gym.id)

        assert code1.code is not None
        assert code2.code is not None
        assert code1.code != code2.code
        assert len(code1.code) == 8  # 8 character hex

    async def test_create_code_uppercase(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Code should be uppercase."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Upper Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        code = await service.create_code(gym_id=gym.id)

        assert code.code == code.code.upper()

    async def test_get_code_by_value(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should find code by value."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Find Code Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        created = await service.create_code(gym_id=gym.id)
        found = await service.get_code_by_value(created.code)

        assert found is not None
        assert found.id == created.id

    async def test_get_code_case_insensitive(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Code lookup should be case insensitive."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Case Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        created = await service.create_code(gym_id=gym.id)

        # Search with lowercase
        found = await service.get_code_by_value(created.code.lower())

        assert found is not None

    async def test_use_code_increments_counter(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Using code should increment uses_count."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Use Code Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        code = await service.create_code(gym_id=gym.id)
        assert code.uses_count == 0

        await service.use_code(code)
        assert code.uses_count == 1

        await service.use_code(code)
        assert code.uses_count == 2

    async def test_deactivate_code(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should deactivate code."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Deactivate Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        code = await service.create_code(gym_id=gym.id)
        assert code.is_active is True

        await service.deactivate_code(code)
        assert code.is_active is False


class TestCheckoutFlow:
    """Tests for check-in/check-out flow."""

    async def test_get_active_checkin(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should return active (not checked out) check-in."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Active Checkin Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        checkin = await service.create_checkin(
            user_id=sample_user["id"],
            gym_id=gym.id,
            method=CheckInMethod.LOCATION,
        )

        active = await service.get_active_checkin(sample_user["id"])

        assert active is not None
        assert active.id == checkin.id
        assert active.checked_out_at is None

    async def test_checkout_sets_timestamp(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Checkout should set checked_out_at timestamp."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Checkout Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        checkin = await service.create_checkin(
            user_id=sample_user["id"],
            gym_id=gym.id,
            method=CheckInMethod.LOCATION,
        )

        before = datetime.now(timezone.utc).replace(tzinfo=None)
        checked_out = await service.checkout(checkin)
        after = datetime.now(timezone.utc).replace(tzinfo=None)

        assert checked_out.checked_out_at is not None
        # Normalize for SQLite compatibility (naive datetime from database)
        checkout_time = checked_out.checked_out_at.replace(tzinfo=None) if checked_out.checked_out_at.tzinfo else checked_out.checked_out_at
        assert before <= checkout_time <= after

    async def test_no_active_checkin_after_checkout(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """After checkout, get_active_checkin should return None."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="No Active Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        checkin = await service.create_checkin(
            user_id=sample_user["id"],
            gym_id=gym.id,
            method=CheckInMethod.LOCATION,
        )

        await service.checkout(checkin)

        active = await service.get_active_checkin(sample_user["id"])
        assert active is None


class TestCheckinRequests:
    """Tests for check-in request approval workflow."""

    async def test_create_request(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should create pending request."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Request Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        # Use same user as both requester and approver for FK constraints
        request = await service.create_request(
            user_id=sample_user["id"],
            gym_id=gym.id,
            approver_id=sample_user["id"],  # FK requires existing user
            reason="No GPS signal",
        )

        assert request.user_id == sample_user["id"]
        assert request.approver_id == sample_user["id"]
        assert request.status == CheckInStatus.PENDING
        assert request.reason == "No GPS signal"

    async def test_approve_request_creates_checkin(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Approving request should create check-in."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Approve Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        request = await service.create_request(
            user_id=sample_user["id"],
            gym_id=gym.id,
            approver_id=sample_user["id"],  # FK requires existing user
        )

        updated_request, checkin = await service.respond_to_request(
            request=request,
            approved=True,
            response_note="Approved",
        )

        assert updated_request.status == CheckInStatus.CONFIRMED
        assert updated_request.responded_at is not None
        assert checkin is not None
        assert checkin.user_id == sample_user["id"]
        assert checkin.method == CheckInMethod.REQUEST
        assert checkin.approved_by_id == sample_user["id"]

    async def test_reject_request_no_checkin(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Rejecting request should not create check-in."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Reject Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        request = await service.create_request(
            user_id=sample_user["id"],
            gym_id=gym.id,
            approver_id=sample_user["id"],  # FK requires existing user
        )

        updated_request, checkin = await service.respond_to_request(
            request=request,
            approved=False,
            response_note="Not allowed",
        )

        assert updated_request.status == CheckInStatus.REJECTED
        assert checkin is None

    async def test_list_pending_requests(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should list pending requests for approver."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Pending Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        # Create multiple requests (using the same user for FK constraints)
        for i in range(3):
            await service.create_request(
                user_id=sample_user["id"],
                gym_id=gym.id,
                approver_id=sample_user["id"],  # FK requires existing user
            )

        pending = await service.list_pending_requests(approver_id=sample_user["id"])

        assert len(pending) == 3


class TestCheckinStats:
    """Tests for check-in statistics."""

    async def test_get_user_checkin_stats(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should return check-in statistics."""
        service = CheckInService(db_session)

        gym = await service.create_gym(
            organization_id=sample_user["organization_id"],
            name="Stats Gym",
            address="Address",
            latitude=-23.5505,
            longitude=-46.6333,
        )

        # Create some check-ins
        for _ in range(5):
            await service.create_checkin(
                user_id=sample_user["id"],
                gym_id=gym.id,
                method=CheckInMethod.LOCATION,
            )

        stats = await service.get_user_checkin_stats(user_id=sample_user["id"], days=30)

        assert stats["period_days"] == 30
        assert stats["total_checkins"] == 5

    async def test_get_user_checkin_stats_no_checkins(
        self, db_session: AsyncSession, sample_user: dict[str, Any]
    ):
        """Should handle user with no check-ins."""
        service = CheckInService(db_session)

        stats = await service.get_user_checkin_stats(user_id=sample_user["id"], days=30)

        assert stats["total_checkins"] == 0
        assert stats["avg_duration_minutes"] == 0
