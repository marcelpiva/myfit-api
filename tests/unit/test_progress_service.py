"""Tests for Progress service business logic."""
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.progress.models import (
    MeasurementLog,
    PhotoAngle,
    ProgressPhoto,
    WeightGoal,
    WeightLog,
)
from src.domains.progress.service import ProgressService


class TestWeightLog:
    """Tests for weight log operations."""

    async def test_create_weight_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a weight log."""
        service = ProgressService(db_session)

        log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=75.5,
            notes="Morning weight",
        )

        assert log.id is not None
        assert log.weight_kg == 75.5
        assert log.notes == "Morning weight"
        assert log.logged_at is not None

    async def test_create_weight_log_with_timestamp(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create weight log with specific timestamp."""
        service = ProgressService(db_session)

        specific_time = datetime(2024, 1, 15, 8, 0)
        log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=76.0,
            logged_at=specific_time,
        )

        # Compare without microseconds
        assert log.logged_at.replace(microsecond=0) == specific_time

    async def test_get_weight_log_by_id(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get weight log by ID."""
        service = ProgressService(db_session)

        log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=74.0,
        )

        found = await service.get_weight_log_by_id(log.id)

        assert found is not None
        assert found.weight_kg == 74.0

    async def test_get_weight_log_not_found(self, db_session: AsyncSession):
        """Should return None for nonexistent log."""
        service = ProgressService(db_session)

        found = await service.get_weight_log_by_id(uuid.uuid4())

        assert found is None

    async def test_update_weight_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update weight log."""
        service = ProgressService(db_session)

        log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=80.0,
        )

        updated = await service.update_weight_log(
            log,
            weight_kg=79.5,
            notes="Corrected weight",
        )

        assert updated.weight_kg == 79.5
        assert updated.notes == "Corrected weight"

    async def test_delete_weight_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete weight log."""
        service = ProgressService(db_session)

        log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=77.0,
        )
        log_id = log.id

        await service.delete_weight_log(log)

        # Verify deleted
        result = await db_session.execute(
            select(WeightLog).where(WeightLog.id == log_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_list_weight_logs(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should list weight logs for user."""
        service = ProgressService(db_session)

        # Create multiple logs
        await service.create_weight_log(user_id=sample_user["id"], weight_kg=75.0)
        await service.create_weight_log(user_id=sample_user["id"], weight_kg=74.5)
        await service.create_weight_log(user_id=sample_user["id"], weight_kg=74.0)

        logs = await service.list_weight_logs(sample_user["id"])

        assert len(logs) >= 3

    async def test_list_weight_logs_date_filter(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter logs by date range."""
        service = ProgressService(db_session)

        # Create a log for today
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=73.0,
        )

        # Use UTC date to match the logged_at which is stored in UTC
        today = datetime.now(timezone.utc).date()
        logs = await service.list_weight_logs(
            sample_user["id"],
            from_date=today,
            to_date=today,
        )

        assert len(logs) >= 1

    async def test_get_latest_weight(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get most recent weight log."""
        service = ProgressService(db_session)

        # Create logs at different times
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=80.0,
            logged_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=79.0,
            logged_at=datetime.now(timezone.utc),
        )

        latest = await service.get_latest_weight(sample_user["id"])

        assert latest is not None
        assert latest.weight_kg == 79.0


class TestMeasurementLog:
    """Tests for measurement log operations."""

    async def test_create_measurement_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a measurement log."""
        service = ProgressService(db_session)

        log = await service.create_measurement_log(
            user_id=sample_user["id"],
            chest_cm=100.0,
            waist_cm=85.0,
            hips_cm=95.0,
            biceps_cm=35.0,
            notes="Initial measurements",
        )

        assert log.id is not None
        assert log.chest_cm == 100.0
        assert log.waist_cm == 85.0
        assert log.notes == "Initial measurements"

    async def test_get_measurement_log_by_id(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get measurement log by ID."""
        service = ProgressService(db_session)

        log = await service.create_measurement_log(
            user_id=sample_user["id"],
            waist_cm=80.0,
        )

        found = await service.get_measurement_log_by_id(log.id)

        assert found is not None
        assert found.waist_cm == 80.0

    async def test_update_measurement_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update measurement log."""
        service = ProgressService(db_session)

        log = await service.create_measurement_log(
            user_id=sample_user["id"],
            chest_cm=100.0,
            biceps_cm=34.0,
        )

        updated = await service.update_measurement_log(
            log,
            chest_cm=101.0,
            biceps_cm=35.5,
        )

        assert updated.chest_cm == 101.0
        assert updated.biceps_cm == 35.5

    async def test_delete_measurement_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete measurement log."""
        service = ProgressService(db_session)

        log = await service.create_measurement_log(
            user_id=sample_user["id"],
            waist_cm=90.0,
        )
        log_id = log.id

        await service.delete_measurement_log(log)

        result = await db_session.execute(
            select(MeasurementLog).where(MeasurementLog.id == log_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_get_latest_measurements(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get most recent measurement log."""
        service = ProgressService(db_session)

        # Create logs at different times
        await service.create_measurement_log(
            user_id=sample_user["id"],
            waist_cm=90.0,
            logged_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        await service.create_measurement_log(
            user_id=sample_user["id"],
            waist_cm=88.0,
            logged_at=datetime.now(timezone.utc),
        )

        latest = await service.get_latest_measurements(sample_user["id"])

        assert latest is not None
        assert latest.waist_cm == 88.0


class TestProgressPhoto:
    """Tests for progress photo operations."""

    async def test_create_photo(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a progress photo."""
        service = ProgressService(db_session)

        photo = await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/photo.jpg",
            angle=PhotoAngle.FRONT,
            thumbnail_url="https://example.com/thumb.jpg",
            notes="Week 1 front view",
        )

        assert photo.id is not None
        assert photo.photo_url == "https://example.com/photo.jpg"
        assert photo.angle == PhotoAngle.FRONT
        assert photo.thumbnail_url == "https://example.com/thumb.jpg"

    async def test_get_photo_by_id(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get photo by ID."""
        service = ProgressService(db_session)

        photo = await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/side.jpg",
            angle=PhotoAngle.SIDE,
        )

        found = await service.get_photo_by_id(photo.id)

        assert found is not None
        assert found.angle == PhotoAngle.SIDE

    async def test_list_photos_filter_by_angle(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter photos by angle."""
        service = ProgressService(db_session)

        # Create photos with different angles
        await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/front1.jpg",
            angle=PhotoAngle.FRONT,
        )
        await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/back1.jpg",
            angle=PhotoAngle.BACK,
        )

        front_photos = await service.list_photos(
            user_id=sample_user["id"],
            angle=PhotoAngle.FRONT,
        )

        assert all(p.angle == PhotoAngle.FRONT for p in front_photos)

    async def test_delete_photo(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete photo."""
        service = ProgressService(db_session)

        photo = await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/delete.jpg",
            angle=PhotoAngle.FRONT,
        )
        photo_id = photo.id

        await service.delete_photo(photo)

        result = await db_session.execute(
            select(ProgressPhoto).where(ProgressPhoto.id == photo_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_create_photo_with_linked_logs(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create photo linked to weight/measurement logs."""
        service = ProgressService(db_session)

        # Create weight log first
        weight_log = await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=75.0,
        )

        photo = await service.create_photo(
            user_id=sample_user["id"],
            photo_url="https://example.com/linked.jpg",
            angle=PhotoAngle.FRONT,
            weight_log_id=weight_log.id,
        )

        assert photo.weight_log_id == weight_log.id


class TestWeightGoal:
    """Tests for weight goal operations."""

    async def test_create_weight_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create weight goal."""
        service = ProgressService(db_session)

        goal = await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=70.0,
            start_weight_kg=80.0,
            notes="Lose 10kg by summer",
        )

        assert goal.id is not None
        assert goal.target_weight_kg == 70.0
        assert goal.start_weight_kg == 80.0
        assert goal.notes == "Lose 10kg by summer"

    async def test_update_existing_weight_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update existing weight goal."""
        service = ProgressService(db_session)

        # Create initial goal
        await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=70.0,
            start_weight_kg=80.0,
        )

        # Update goal
        updated = await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=68.0,
            start_weight_kg=80.0,
            notes="Updated target",
        )

        assert updated.target_weight_kg == 68.0
        assert updated.notes == "Updated target"

    async def test_get_weight_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get weight goal for user."""
        service = ProgressService(db_session)

        await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=65.0,
            start_weight_kg=75.0,
        )

        goal = await service.get_weight_goal(sample_user["id"])

        assert goal is not None
        assert goal.target_weight_kg == 65.0

    async def test_get_weight_goal_not_found(self, db_session: AsyncSession):
        """Should return None when no goal exists."""
        service = ProgressService(db_session)

        goal = await service.get_weight_goal(uuid.uuid4())

        assert goal is None

    async def test_delete_weight_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete weight goal."""
        service = ProgressService(db_session)

        goal = await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=72.0,
            start_weight_kg=82.0,
        )

        await service.delete_weight_goal(goal)

        # Verify deleted
        result = await service.get_weight_goal(sample_user["id"])
        assert result is None


class TestProgressStats:
    """Tests for progress statistics."""

    async def test_get_progress_stats_empty(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return zero stats when no data."""
        service = ProgressService(db_session)

        stats = await service.get_progress_stats(sample_user["id"], days=30)

        assert stats["weight_logs_count"] == 0
        assert stats["measurement_logs_count"] == 0
        assert stats["latest_weight_kg"] is None
        assert stats["weight_change_kg"] == 0.0

    async def test_get_progress_stats_with_data(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should calculate progress stats from data."""
        service = ProgressService(db_session)

        # Create weight logs
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=80.0,
            logged_at=datetime.now(timezone.utc) - timedelta(days=15),
        )
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=78.0,
            logged_at=datetime.now(timezone.utc),
        )

        # Create measurement log
        await service.create_measurement_log(
            user_id=sample_user["id"],
            waist_cm=90.0,
        )

        stats = await service.get_progress_stats(sample_user["id"], days=30)

        assert stats["weight_logs_count"] == 2
        assert stats["measurement_logs_count"] == 1
        assert stats["latest_weight_kg"] == 78.0
        assert stats["starting_weight_kg"] == 80.0
        assert stats["weight_change_kg"] == -2.0  # Lost 2 kg

    async def test_get_progress_stats_with_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should calculate goal progress percentage."""
        service = ProgressService(db_session)

        # Create goal (lose 10kg: 80 -> 70)
        await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=70.0,
            start_weight_kg=80.0,
        )

        # Current weight is 75 (lost 5 of 10 = 50%)
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=75.0,
        )

        stats = await service.get_progress_stats(sample_user["id"], days=30)

        assert stats["goal_weight_kg"] == 70.0
        assert stats["goal_progress_percent"] == 50.0  # 50% progress

    async def test_progress_stats_weight_gain_goal(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should handle weight gain goals (negative total_to_lose)."""
        service = ProgressService(db_session)

        # Create goal (gain 10kg: 60 -> 70)
        await service.create_or_update_weight_goal(
            user_id=sample_user["id"],
            target_weight_kg=70.0,
            start_weight_kg=60.0,
        )

        # Current weight is 65 (gained 5 of -10)
        await service.create_weight_log(
            user_id=sample_user["id"],
            weight_kg=65.0,
        )

        stats = await service.get_progress_stats(sample_user["id"], days=30)

        # Progress is 50% toward goal (but negative because it's a gain goal)
        assert stats["goal_progress_percent"] == 50.0
