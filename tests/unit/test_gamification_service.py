"""Tests for GamificationService - points, levels, streaks, and achievements."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.gamification.models import (
    Achievement,
    PointTransaction,
    UserAchievement,
    UserPoints,
)
from src.domains.gamification.service import GamificationService


class TestCalculateLevel:
    """Tests for level calculation based on cumulative thresholds.

    LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5200, 6500]
    """

    def test_level_1_at_zero_points(self, db_session: AsyncSession):
        """0 points should be level 1."""
        service = GamificationService(db_session)
        assert service.calculate_level(0) == 1

    def test_level_1_at_99_points(self, db_session: AsyncSession):
        """99 points should still be level 1."""
        service = GamificationService(db_session)
        assert service.calculate_level(99) == 1

    def test_level_2_at_100_points(self, db_session: AsyncSession):
        """100 points should be level 2."""
        service = GamificationService(db_session)
        assert service.calculate_level(100) == 2

    def test_level_2_at_299_points(self, db_session: AsyncSession):
        """299 points should still be level 2."""
        service = GamificationService(db_session)
        assert service.calculate_level(299) == 2

    def test_level_3_at_300_points(self, db_session: AsyncSession):
        """300 points should be level 3."""
        service = GamificationService(db_session)
        assert service.calculate_level(300) == 3

    def test_level_4_at_600_points(self, db_session: AsyncSession):
        """600 points should be level 4."""
        service = GamificationService(db_session)
        assert service.calculate_level(600) == 4

    def test_level_5_at_1000_points(self, db_session: AsyncSession):
        """1000 points should be level 5."""
        service = GamificationService(db_session)
        assert service.calculate_level(1000) == 5

    def test_level_6_at_1500_points(self, db_session: AsyncSession):
        """1500 points should be level 6."""
        service = GamificationService(db_session)
        assert service.calculate_level(1500) == 6

    def test_level_7_at_2200_points(self, db_session: AsyncSession):
        """2200 points should be level 7."""
        service = GamificationService(db_session)
        assert service.calculate_level(2200) == 7

    def test_level_8_at_3000_points(self, db_session: AsyncSession):
        """3000 points should be level 8."""
        service = GamificationService(db_session)
        assert service.calculate_level(3000) == 8

    def test_level_9_at_4000_points(self, db_session: AsyncSession):
        """4000 points should be level 9."""
        service = GamificationService(db_session)
        assert service.calculate_level(4000) == 9

    def test_level_10_at_5200_points(self, db_session: AsyncSession):
        """5200 points should be level 10."""
        service = GamificationService(db_session)
        assert service.calculate_level(5200) == 10

    def test_level_11_at_6500_points(self, db_session: AsyncSession):
        """6500 points should be level 11 (max level)."""
        service = GamificationService(db_session)
        assert service.calculate_level(6500) == 11

    def test_max_level_at_10000_points(self, db_session: AsyncSession):
        """Points beyond 6500 should still be max level (11)."""
        service = GamificationService(db_session)
        assert service.calculate_level(10000) == 11

    @pytest.mark.parametrize(
        "points,expected_level",
        [
            (0, 1),
            (50, 1),
            (100, 2),
            (250, 2),
            (300, 3),
            (500, 3),
            (600, 4),
            (800, 4),
            (1000, 5),
            (1200, 5),
            (1500, 6),
            (1800, 6),
            (2200, 7),
            (2500, 7),
            (3000, 8),
            (3500, 8),
            (4000, 9),
            (4500, 9),
            (5200, 10),
            (6000, 10),
            (6500, 11),
            (8000, 11),
        ],
    )
    def test_level_thresholds_parametrized(
        self, db_session: AsyncSession, points: int, expected_level: int
    ):
        """Parametrized test for all level thresholds."""
        service = GamificationService(db_session)
        assert service.calculate_level(points) == expected_level


class TestUpdateStreak:
    """Tests for streak tracking logic."""

    async def test_first_activity_starts_streak_at_1(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """First activity should set streak to 1."""
        service = GamificationService(db_session)

        user_points = await service.update_streak(sample_user["id"])

        assert user_points.current_streak == 1

    async def test_same_day_activity_no_streak_increment(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Multiple activities on same day should not increment streak."""
        service = GamificationService(db_session)

        # First activity
        await service.update_streak(sample_user["id"])

        # Second activity same day
        user_points = await service.update_streak(sample_user["id"])

        assert user_points.current_streak == 1

    async def test_consecutive_day_increments_streak(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Activity on consecutive day should increment streak."""
        service = GamificationService(db_session)

        # Create user points with yesterday's activity
        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=0,
            level=1,
            current_streak=5,
            longest_streak=5,
            last_activity_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(user_points)
        await db_session.commit()

        # Update streak today
        updated = await service.update_streak(sample_user["id"])

        assert updated.current_streak == 6

    async def test_missed_day_resets_streak_to_1(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Missing a day should reset streak to 1."""
        service = GamificationService(db_session)

        # Create user points with activity 2 days ago
        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=100,
            level=2,
            current_streak=10,
            longest_streak=10,
            last_activity_at=datetime.utcnow() - timedelta(days=2),
        )
        db_session.add(user_points)
        await db_session.commit()

        # Update streak today
        updated = await service.update_streak(sample_user["id"])

        assert updated.current_streak == 1

    async def test_longest_streak_preserved_on_reset(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Longest streak should not decrease when current streak resets."""
        service = GamificationService(db_session)

        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=100,
            level=2,
            current_streak=5,
            longest_streak=15,
            last_activity_at=datetime.utcnow() - timedelta(days=3),
        )
        db_session.add(user_points)
        await db_session.commit()

        updated = await service.update_streak(sample_user["id"])

        assert updated.current_streak == 1
        assert updated.longest_streak == 15

    async def test_longest_streak_updated_when_current_exceeds(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Longest streak should update when current streak exceeds it."""
        service = GamificationService(db_session)

        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=100,
            level=2,
            current_streak=10,
            longest_streak=10,
            last_activity_at=datetime.utcnow() - timedelta(days=1),
        )
        db_session.add(user_points)
        await db_session.commit()

        updated = await service.update_streak(sample_user["id"])

        assert updated.current_streak == 11
        assert updated.longest_streak == 11

    async def test_streak_updates_last_activity_timestamp(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Last activity timestamp should be updated."""
        service = GamificationService(db_session)

        before = datetime.utcnow()
        user_points = await service.update_streak(sample_user["id"])
        after = datetime.utcnow()

        assert user_points.last_activity_at is not None
        assert before <= user_points.last_activity_at <= after


class TestAwardPoints:
    """Tests for awarding points to users."""

    async def test_award_points_creates_user_points_if_not_exists(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create UserPoints record if user has none."""
        service = GamificationService(db_session)

        user_points, transaction = await service.award_points(
            user_id=sample_user["id"],
            points=50,
            reason="test_award",
            description="Test point award",
        )

        assert user_points.total_points == 50
        assert transaction.points == 50

    async def test_award_points_adds_to_existing(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Points should be added to existing total."""
        service = GamificationService(db_session)

        # Create initial points
        initial_points = UserPoints(
            user_id=sample_user["id"],
            total_points=100,
            level=2,
            current_streak=0,
            longest_streak=0,
        )
        db_session.add(initial_points)
        await db_session.commit()

        user_points, _ = await service.award_points(
            user_id=sample_user["id"],
            points=50,
            reason="additional",
        )

        assert user_points.total_points == 150

    async def test_award_points_creates_transaction(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Point transaction should be created with details."""
        service = GamificationService(db_session)

        _, transaction = await service.award_points(
            user_id=sample_user["id"],
            points=100,
            reason="workout_completed",
            description="Completed workout session",
            reference_type="workout_session",
            reference_id=uuid.uuid4(),
        )

        assert transaction.points == 100
        assert transaction.reason == "workout_completed"
        assert transaction.description == "Completed workout session"
        assert transaction.reference_type == "workout_session"

    async def test_award_points_updates_level(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Level should update when points cross threshold."""
        service = GamificationService(db_session)

        # Start with 90 points (level 1)
        initial_points = UserPoints(
            user_id=sample_user["id"],
            total_points=90,
            level=1,
            current_streak=0,
            longest_streak=0,
        )
        db_session.add(initial_points)
        await db_session.commit()

        # Award 20 points to cross 100 threshold
        user_points, _ = await service.award_points(
            user_id=sample_user["id"],
            points=20,
            reason="level_up_test",
        )

        assert user_points.total_points == 110
        assert user_points.level == 2

    async def test_award_points_updates_last_activity(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Last activity timestamp should be updated."""
        service = GamificationService(db_session)

        before = datetime.utcnow()
        user_points, _ = await service.award_points(
            user_id=sample_user["id"],
            points=10,
            reason="activity",
        )

        assert user_points.last_activity_at is not None
        assert user_points.last_activity_at >= before


class TestAchievements:
    """Tests for achievement system."""

    async def test_create_achievement(self, db_session: AsyncSession):
        """Should create a new achievement."""
        service = GamificationService(db_session)

        achievement = await service.create_achievement(
            name="First Workout",
            description="Complete your first workout",
            icon="trophy",
            points_reward=50,
            category="workout",
        )

        assert achievement.name == "First Workout"
        assert achievement.points_reward == 50
        assert achievement.category == "workout"

    async def test_has_achievement_false(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return False if user doesn't have achievement."""
        service = GamificationService(db_session)

        achievement = await service.create_achievement(
            name="Test Achievement",
            description="Test",
            icon="star",
        )

        has_it = await service.has_achievement(sample_user["id"], achievement.id)

        assert has_it is False

    async def test_award_achievement_success(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should award achievement to user."""
        service = GamificationService(db_session)

        achievement = await service.create_achievement(
            name="Awarded Achievement",
            description="Test",
            icon="medal",
            points_reward=100,
        )

        user_achievement, user_points = await service.award_achievement(
            user_id=sample_user["id"],
            achievement_id=achievement.id,
        )

        assert user_achievement.user_id == sample_user["id"]
        assert user_achievement.achievement_id == achievement.id
        assert user_points.total_points == 100

    async def test_award_achievement_prevents_duplicate(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should not award same achievement twice."""
        service = GamificationService(db_session)

        achievement = await service.create_achievement(
            name="Unique Achievement",
            description="Test",
            icon="star",
        )

        # Award first time
        await service.award_achievement(
            user_id=sample_user["id"],
            achievement_id=achievement.id,
        )

        # Try to award again
        with pytest.raises(ValueError, match="already has this achievement"):
            await service.award_achievement(
                user_id=sample_user["id"],
                achievement_id=achievement.id,
            )

    async def test_award_achievement_not_found(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should raise error for nonexistent achievement."""
        service = GamificationService(db_session)

        with pytest.raises(ValueError, match="Achievement not found"):
            await service.award_achievement(
                user_id=sample_user["id"],
                achievement_id=uuid.uuid4(),
            )

    async def test_get_user_achievements(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return list of user's achievements."""
        service = GamificationService(db_session)

        ach1 = await service.create_achievement(
            name="Achievement 1",
            description="First",
            icon="star",
        )
        ach2 = await service.create_achievement(
            name="Achievement 2",
            description="Second",
            icon="medal",
        )

        await service.award_achievement(sample_user["id"], ach1.id)
        await service.award_achievement(sample_user["id"], ach2.id)

        achievements = await service.get_user_achievements(sample_user["id"])

        assert len(achievements) == 2


class TestGetOrCreateUserPoints:
    """Tests for get_or_create_user_points."""

    async def test_creates_new_if_not_exists(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create new UserPoints if user has none."""
        service = GamificationService(db_session)

        user_points = await service.get_or_create_user_points(sample_user["id"])

        assert user_points.user_id == sample_user["id"]
        assert user_points.total_points == 0
        assert user_points.level == 1
        assert user_points.current_streak == 0
        assert user_points.longest_streak == 0

    async def test_returns_existing_if_exists(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return existing UserPoints if user has one."""
        service = GamificationService(db_session)

        # Create initial
        initial = UserPoints(
            user_id=sample_user["id"],
            total_points=500,
            level=3,
            current_streak=5,
            longest_streak=10,
        )
        db_session.add(initial)
        await db_session.commit()

        user_points = await service.get_or_create_user_points(sample_user["id"])

        assert user_points.total_points == 500
        assert user_points.level == 3


class TestGamificationStats:
    """Tests for gamification stats retrieval."""

    async def test_get_gamification_stats(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return complete gamification stats."""
        service = GamificationService(db_session)

        # Create user points
        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=250,
            level=2,
            current_streak=3,
            longest_streak=7,
        )
        db_session.add(user_points)
        await db_session.commit()

        stats = await service.get_gamification_stats(sample_user["id"])

        assert stats["total_points"] == 250
        assert stats["level"] == 2
        assert stats["current_streak"] == 3
        assert stats["longest_streak"] == 7
        assert stats["points_to_next_level"] == 50  # 300 - 250

    async def test_get_gamification_stats_at_max_level(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Points to next level should be 0 at max level."""
        service = GamificationService(db_session)

        user_points = UserPoints(
            user_id=sample_user["id"],
            total_points=7000,
            level=11,
            current_streak=0,
            longest_streak=0,
        )
        db_session.add(user_points)
        await db_session.commit()

        stats = await service.get_gamification_stats(sample_user["id"])

        assert stats["level"] == 11
        assert stats["points_to_next_level"] == 0
