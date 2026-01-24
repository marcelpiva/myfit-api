"""Integration tests for gamification API endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.gamification.models import (
    Achievement,
    LeaderboardEntry,
    PointTransaction,
    UserAchievement,
    UserPoints,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_achievement(db_session: AsyncSession) -> Achievement:
    """Create a sample achievement."""
    achievement = Achievement(
        name="First Workout",
        description="Complete your first workout session",
        icon="trophy",
        points_reward=100,
        category="workout",
        condition={"workouts_completed": 1},
        is_active=True,
        order=1,
    )
    db_session.add(achievement)
    await db_session.commit()
    await db_session.refresh(achievement)
    return achievement


@pytest.fixture
async def sample_achievement_streak(db_session: AsyncSession) -> Achievement:
    """Create a streak achievement."""
    achievement = Achievement(
        name="Week Warrior",
        description="Maintain a 7-day workout streak",
        icon="fire",
        points_reward=200,
        category="streak",
        condition={"streak_days": 7},
        is_active=True,
        order=2,
    )
    db_session.add(achievement)
    await db_session.commit()
    await db_session.refresh(achievement)
    return achievement


@pytest.fixture
async def sample_inactive_achievement(db_session: AsyncSession) -> Achievement:
    """Create an inactive achievement."""
    achievement = Achievement(
        name="Hidden Achievement",
        description="This achievement is not available",
        icon="lock",
        points_reward=50,
        category="general",
        condition={},
        is_active=False,
        order=99,
    )
    db_session.add(achievement)
    await db_session.commit()
    await db_session.refresh(achievement)
    return achievement


@pytest.fixture
async def sample_user_achievement(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_achievement: Achievement
) -> UserAchievement:
    """Create a user achievement (earned achievement)."""
    user_achievement = UserAchievement(
        user_id=sample_user["id"],
        achievement_id=sample_achievement.id,
        progress={"workouts_completed": 1},
    )
    db_session.add(user_achievement)
    await db_session.commit()
    await db_session.refresh(user_achievement)
    return user_achievement


@pytest.fixture
async def sample_point_transaction(
    db_session: AsyncSession, user_with_points: dict[str, Any]
) -> PointTransaction:
    """Create a sample point transaction."""
    # Get user_points record
    from sqlalchemy import select

    result = await db_session.execute(
        select(UserPoints).where(UserPoints.user_id == user_with_points["id"])
    )
    user_points = result.scalar_one()

    transaction = PointTransaction(
        user_points_id=user_points.id,
        points=50,
        reason="workout_completed",
        description="Completed morning workout",
        reference_type="workout_session",
        reference_id=uuid.uuid4(),
    )
    db_session.add(transaction)
    await db_session.commit()
    await db_session.refresh(transaction)
    return transaction


@pytest.fixture
async def sample_leaderboard_entry(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> LeaderboardEntry:
    """Create a sample leaderboard entry."""
    entry = LeaderboardEntry(
        user_id=sample_user["id"],
        organization_id=None,
        period="all_time",
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        points=500,
        rank=1,
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


@pytest.fixture
async def multiple_leaderboard_entries(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> list[LeaderboardEntry]:
    """Create multiple leaderboard entries for different users."""
    # Create additional users for the leaderboard
    from src.domains.users.models import User

    entries = []
    for i in range(3):
        # Create user
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            email=f"leaderboard-user-{i}@example.com",
            name=f"Leaderboard User {i}",
            password_hash="$2b$12$test.hash.password",
            is_active=True,
        )
        db_session.add(user)
        await db_session.flush()

        # Create leaderboard entry
        entry = LeaderboardEntry(
            user_id=user_id,
            organization_id=None,
            period="all_time",
            period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
            points=1000 - (i * 100),
            rank=i + 1,
        )
        db_session.add(entry)
        entries.append(entry)

    await db_session.commit()
    for entry in entries:
        await db_session.refresh(entry)
    return entries


# =============================================================================
# Points Endpoint Tests
# =============================================================================


class TestGetUserPoints:
    """Tests for GET /api/v1/gamification/points."""

    async def test_get_points_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can get their points."""
        response = await authenticated_client.get("/api/v1/gamification/points")

        assert response.status_code == 200
        data = response.json()
        assert "total_points" in data
        assert "level" in data
        assert "current_streak" in data
        assert "longest_streak" in data

    async def test_get_points_creates_record_if_not_exists(
        self, authenticated_client: AsyncClient
    ):
        """Points endpoint creates a record for new user."""
        response = await authenticated_client.get("/api/v1/gamification/points")

        assert response.status_code == 200
        data = response.json()
        assert data["total_points"] == 0
        assert data["level"] == 1
        assert data["current_streak"] == 0

    async def test_get_points_with_existing_points(
        self, authenticated_client: AsyncClient, user_with_points: dict[str, Any]
    ):
        """Returns existing points for user with points."""
        response = await authenticated_client.get("/api/v1/gamification/points")

        assert response.status_code == 200
        data = response.json()
        assert data["total_points"] == user_with_points["points"]
        assert data["level"] == user_with_points["level"]

    async def test_get_points_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/gamification/points")

        assert response.status_code == 401


class TestAwardPoints:
    """Tests for POST /api/v1/gamification/points."""

    async def test_award_points_success(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can award points to a user."""
        payload = {
            "points": 50,
            "reason": "workout_completed",
            "description": "Completed morning workout",
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/points", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_points"] >= 50

    async def test_award_points_with_reference(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can award points with reference type and ID."""
        reference_id = str(uuid.uuid4())
        payload = {
            "points": 100,
            "reason": "achievement_earned",
            "description": "Earned First Workout achievement",
            "reference_type": "achievement",
            "reference_id": reference_id,
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/points", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["total_points"] >= 100

    async def test_award_points_invalid_payload(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid payload."""
        payload = {
            "points": -10,  # Invalid: must be >= 1
            "reason": "test",
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/points", json=payload
        )

        assert response.status_code == 422


class TestGetPointsHistory:
    """Tests for GET /api/v1/gamification/points/history."""

    async def test_get_points_history(
        self,
        authenticated_client: AsyncClient,
        user_with_points: dict[str, Any],
        sample_point_transaction: PointTransaction,
    ):
        """Can get points transaction history."""
        response = await authenticated_client.get("/api/v1/gamification/points/history")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_points_history_empty(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns empty list for user with no transactions."""
        response = await authenticated_client.get("/api/v1/gamification/points/history")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_get_points_history_pagination(
        self,
        authenticated_client: AsyncClient,
        user_with_points: dict[str, Any],
        sample_point_transaction: PointTransaction,
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/gamification/points/history",
            params={"limit": 1, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1


class TestUpdateStreak:
    """Tests for POST /api/v1/gamification/points/streak."""

    async def test_update_streak_first_activity(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """First activity sets streak to 1."""
        response = await authenticated_client.post("/api/v1/gamification/points/streak")

        assert response.status_code == 200
        data = response.json()
        assert data["current_streak"] == 1

    async def test_update_streak_consecutive_days(
        self, authenticated_client: AsyncClient, user_with_points: dict[str, Any]
    ):
        """Streak update works correctly."""
        response = await authenticated_client.post("/api/v1/gamification/points/streak")

        assert response.status_code == 200
        data = response.json()
        assert "current_streak" in data
        assert "longest_streak" in data


# =============================================================================
# Achievement Endpoint Tests
# =============================================================================


class TestListAchievements:
    """Tests for GET /api/v1/gamification/achievements."""

    async def test_list_achievements_authenticated(
        self, authenticated_client: AsyncClient, sample_achievement: Achievement
    ):
        """Authenticated user can list achievements."""
        response = await authenticated_client.get("/api/v1/gamification/achievements")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_achievements_only_active(
        self,
        authenticated_client: AsyncClient,
        sample_achievement: Achievement,
        sample_inactive_achievement: Achievement,
    ):
        """Only active achievements are returned by default."""
        response = await authenticated_client.get("/api/v1/gamification/achievements")

        assert response.status_code == 200
        data = response.json()
        # All returned achievements should be active
        assert all(a["is_active"] for a in data)
        # Should not contain the inactive achievement
        assert not any(a["name"] == "Hidden Achievement" for a in data)

    async def test_list_achievements_filter_by_category(
        self,
        authenticated_client: AsyncClient,
        sample_achievement: Achievement,
        sample_achievement_streak: Achievement,
    ):
        """Can filter achievements by category."""
        response = await authenticated_client.get(
            "/api/v1/gamification/achievements", params={"category": "workout"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(a["category"] == "workout" for a in data)

    async def test_list_achievements_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/gamification/achievements")

        assert response.status_code == 401


class TestCreateAchievement:
    """Tests for POST /api/v1/gamification/achievements."""

    async def test_create_achievement_success(
        self, authenticated_client: AsyncClient
    ):
        """Can create a new achievement."""
        payload = {
            "name": "Century Club",
            "description": "Complete 100 workouts",
            "icon": "medal",
            "points_reward": 500,
            "category": "workout",
            "condition": {"workouts_completed": 100},
            "order": 10,
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/achievements", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Century Club"
        assert data["points_reward"] == 500
        assert "id" in data

    async def test_create_achievement_missing_required_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {"name": "Incomplete"}

        response = await authenticated_client.post(
            "/api/v1/gamification/achievements", json=payload
        )

        assert response.status_code == 422


class TestGetUserAchievements:
    """Tests for GET /api/v1/gamification/achievements/mine."""

    async def test_get_user_achievements(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
        sample_user_achievement: UserAchievement,
    ):
        """Can get user's earned achievements."""
        response = await authenticated_client.get("/api/v1/gamification/achievements/mine")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_user_achievements_empty(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns empty list for user with no achievements."""
        response = await authenticated_client.get("/api/v1/gamification/achievements/mine")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestAwardAchievement:
    """Tests for POST /api/v1/gamification/achievements/award."""

    async def test_award_achievement_success(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
        sample_achievement_streak: Achievement,
    ):
        """Can award an achievement to user."""
        payload = {
            "achievement_id": str(sample_achievement_streak.id),
            "progress": {"streak_days": 7},
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/achievements/award", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["achievement_id"] == str(sample_achievement_streak.id)

    async def test_award_achievement_already_earned(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
        sample_user_achievement: UserAchievement,
        sample_achievement: Achievement,
    ):
        """Returns 400 when achievement is already earned."""
        payload = {
            "achievement_id": str(sample_achievement.id),
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/achievements/award", json=payload
        )

        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()

    async def test_award_nonexistent_achievement(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 for nonexistent achievement."""
        fake_id = uuid.uuid4()
        payload = {
            "achievement_id": str(fake_id),
        }

        response = await authenticated_client.post(
            "/api/v1/gamification/achievements/award", json=payload
        )

        assert response.status_code == 400


# =============================================================================
# Leaderboard Endpoint Tests
# =============================================================================


class TestGetLeaderboard:
    """Tests for GET /api/v1/gamification/leaderboard."""

    async def test_get_leaderboard_authenticated(
        self,
        authenticated_client: AsyncClient,
        multiple_leaderboard_entries: list[LeaderboardEntry],
    ):
        """Authenticated user can get leaderboard."""
        response = await authenticated_client.get("/api/v1/gamification/leaderboard")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_leaderboard_sorted_by_rank(
        self,
        authenticated_client: AsyncClient,
        multiple_leaderboard_entries: list[LeaderboardEntry],
    ):
        """Leaderboard is sorted by rank."""
        response = await authenticated_client.get("/api/v1/gamification/leaderboard")

        assert response.status_code == 200
        data = response.json()
        ranks = [entry["rank"] for entry in data]
        assert ranks == sorted(ranks)

    async def test_get_leaderboard_by_period(
        self, authenticated_client: AsyncClient, sample_leaderboard_entry: LeaderboardEntry
    ):
        """Can filter leaderboard by period."""
        response = await authenticated_client.get(
            "/api/v1/gamification/leaderboard", params={"period": "all_time"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(entry["period"] == "all_time" for entry in data)

    async def test_get_leaderboard_invalid_period(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid period."""
        response = await authenticated_client.get(
            "/api/v1/gamification/leaderboard", params={"period": "invalid_period"}
        )

        assert response.status_code == 422

    async def test_get_leaderboard_pagination(
        self,
        authenticated_client: AsyncClient,
        multiple_leaderboard_entries: list[LeaderboardEntry],
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/gamification/leaderboard",
            params={"limit": 2, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2

    async def test_get_leaderboard_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/gamification/leaderboard")

        assert response.status_code == 401


class TestGetMyRank:
    """Tests for GET /api/v1/gamification/leaderboard/me."""

    async def test_get_my_rank_with_entry(
        self,
        authenticated_client: AsyncClient,
        sample_leaderboard_entry: LeaderboardEntry,
    ):
        """Can get user's leaderboard position."""
        response = await authenticated_client.get("/api/v1/gamification/leaderboard/me")

        assert response.status_code == 200
        data = response.json()
        assert "rank" in data
        assert "points" in data

    async def test_get_my_rank_no_entry(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns null when user has no leaderboard entry."""
        response = await authenticated_client.get("/api/v1/gamification/leaderboard/me")

        assert response.status_code == 200
        # Response can be null for users not on leaderboard
        data = response.json()
        assert data is None


class TestRefreshLeaderboard:
    """Tests for POST /api/v1/gamification/leaderboard/refresh."""

    async def test_refresh_leaderboard(
        self, authenticated_client: AsyncClient, user_with_points: dict[str, Any]
    ):
        """Can refresh leaderboard rankings."""
        response = await authenticated_client.post(
            "/api/v1/gamification/leaderboard/refresh",
            params={"period": "all_time"},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# Stats Endpoint Tests
# =============================================================================


class TestGetGamificationStats:
    """Tests for GET /api/v1/gamification/stats."""

    async def test_get_stats_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can get gamification stats."""
        response = await authenticated_client.get("/api/v1/gamification/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_points" in data
        assert "level" in data
        assert "current_streak" in data
        assert "longest_streak" in data
        assert "points_to_next_level" in data
        assert "achievements_earned" in data
        assert "achievements_total" in data

    async def test_get_stats_with_existing_data(
        self,
        authenticated_client: AsyncClient,
        user_with_points: dict[str, Any],
        sample_achievement: Achievement,
        sample_user_achievement: UserAchievement,
    ):
        """Stats reflect existing points and achievements."""
        response = await authenticated_client.get("/api/v1/gamification/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_points"] == user_with_points["points"]
        assert data["achievements_earned"] >= 1
        assert data["achievements_total"] >= 1

    async def test_get_stats_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/gamification/stats")

        assert response.status_code == 401
