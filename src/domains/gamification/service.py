"""Gamification service with database operations."""
import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.gamification.models import (
    Achievement,
    LeaderboardEntry,
    PointTransaction,
    UserAchievement,
    UserPoints,
)


class GamificationService:
    """Service for handling gamification operations."""

    # Points required per level (cumulative)
    LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5200, 6500]

    def __init__(self, db: AsyncSession):
        self.db = db

    # User Points operations

    async def get_user_points(self, user_id: uuid.UUID) -> UserPoints | None:
        """Get user's points record."""
        result = await self.db.execute(
            select(UserPoints)
            .where(UserPoints.user_id == user_id)
            .options(selectinload(UserPoints.transactions))
        )
        return result.scalar_one_or_none()

    async def get_or_create_user_points(self, user_id: uuid.UUID) -> UserPoints:
        """Get or create user's points record."""
        user_points = await self.get_user_points(user_id)
        if not user_points:
            user_points = UserPoints(
                user_id=user_id,
                total_points=0,
                level=1,
                current_streak=0,
                longest_streak=0,
            )
            self.db.add(user_points)
            await self.db.commit()
            await self.db.refresh(user_points)
        return user_points

    def calculate_level(self, total_points: int) -> int:
        """Calculate level based on total points."""
        level = 1
        for i, threshold in enumerate(self.LEVEL_THRESHOLDS):
            if total_points >= threshold:
                level = i + 1
            else:
                break
        return min(level, len(self.LEVEL_THRESHOLDS))

    async def award_points(
        self,
        user_id: uuid.UUID,
        points: int,
        reason: str,
        description: str | None = None,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
    ) -> tuple[UserPoints, PointTransaction]:
        """Award points to a user."""
        user_points = await self.get_or_create_user_points(user_id)

        # Create transaction
        transaction = PointTransaction(
            user_points_id=user_points.id,
            points=points,
            reason=reason,
            description=description,
            reference_type=reference_type,
            reference_id=reference_id,
        )
        self.db.add(transaction)

        # Update total points and level
        user_points.total_points += points
        user_points.level = self.calculate_level(user_points.total_points)
        user_points.last_activity_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(user_points)
        await self.db.refresh(transaction)

        return user_points, transaction

    async def update_streak(self, user_id: uuid.UUID) -> UserPoints:
        """Update user's activity streak."""
        user_points = await self.get_or_create_user_points(user_id)
        now = datetime.utcnow()

        if user_points.last_activity_at:
            days_since_last = (now - user_points.last_activity_at).days
            if days_since_last == 0:
                # Same day, no streak update
                pass
            elif days_since_last == 1:
                # Consecutive day, increment streak
                user_points.current_streak += 1
                if user_points.current_streak > user_points.longest_streak:
                    user_points.longest_streak = user_points.current_streak
            else:
                # Streak broken, reset
                user_points.current_streak = 1
        else:
            # First activity
            user_points.current_streak = 1

        user_points.last_activity_at = now
        await self.db.commit()
        await self.db.refresh(user_points)
        return user_points

    async def get_point_transactions(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PointTransaction]:
        """Get user's point transactions."""
        user_points = await self.get_user_points(user_id)
        if not user_points:
            return []

        result = await self.db.execute(
            select(PointTransaction)
            .where(PointTransaction.user_points_id == user_points.id)
            .order_by(PointTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    # Achievement operations

    async def get_achievement_by_id(self, achievement_id: uuid.UUID) -> Achievement | None:
        """Get an achievement by ID."""
        result = await self.db.execute(
            select(Achievement).where(Achievement.id == achievement_id)
        )
        return result.scalar_one_or_none()

    async def list_achievements(
        self,
        category: str | None = None,
        active_only: bool = True,
    ) -> list[Achievement]:
        """List all achievements."""
        query = select(Achievement)

        if category:
            query = query.where(Achievement.category == category)
        if active_only:
            query = query.where(Achievement.is_active == True)

        query = query.order_by(Achievement.order, Achievement.name)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_achievement(
        self,
        name: str,
        description: str,
        icon: str,
        points_reward: int = 0,
        category: str = "general",
        condition: dict | None = None,
        order: int = 0,
    ) -> Achievement:
        """Create a new achievement."""
        achievement = Achievement(
            name=name,
            description=description,
            icon=icon,
            points_reward=points_reward,
            category=category,
            condition=condition or {},
            order=order,
        )
        self.db.add(achievement)
        await self.db.commit()
        await self.db.refresh(achievement)
        return achievement

    async def get_user_achievements(
        self,
        user_id: uuid.UUID,
    ) -> list[UserAchievement]:
        """Get achievements earned by a user."""
        result = await self.db.execute(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .options(selectinload(UserAchievement.achievement))
            .order_by(UserAchievement.earned_at.desc())
        )
        return list(result.scalars().all())

    async def has_achievement(
        self,
        user_id: uuid.UUID,
        achievement_id: uuid.UUID,
    ) -> bool:
        """Check if user has earned an achievement."""
        result = await self.db.execute(
            select(UserAchievement).where(
                and_(
                    UserAchievement.user_id == user_id,
                    UserAchievement.achievement_id == achievement_id,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    async def award_achievement(
        self,
        user_id: uuid.UUID,
        achievement_id: uuid.UUID,
        progress: dict | None = None,
    ) -> tuple[UserAchievement, UserPoints | None]:
        """Award an achievement to a user."""
        # Check if already earned
        if await self.has_achievement(user_id, achievement_id):
            raise ValueError("User already has this achievement")

        achievement = await self.get_achievement_by_id(achievement_id)
        if not achievement:
            raise ValueError("Achievement not found")

        # Create user achievement
        user_achievement = UserAchievement(
            user_id=user_id,
            achievement_id=achievement_id,
            progress=progress,
        )
        self.db.add(user_achievement)

        # Award points if any
        user_points = None
        if achievement.points_reward > 0:
            user_points, _ = await self.award_points(
                user_id=user_id,
                points=achievement.points_reward,
                reason="achievement_earned",
                description=f"Earned achievement: {achievement.name}",
                reference_type="achievement",
                reference_id=achievement_id,
            )

        await self.db.commit()

        # Reload with achievement relationship
        result = await self.db.execute(
            select(UserAchievement)
            .where(UserAchievement.id == user_achievement.id)
            .options(selectinload(UserAchievement.achievement))
        )
        user_achievement = result.scalar_one()

        return user_achievement, user_points

    # Leaderboard operations

    async def get_leaderboard(
        self,
        period: str = "all_time",
        organization_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[LeaderboardEntry]:
        """Get leaderboard entries."""
        query = select(LeaderboardEntry).where(LeaderboardEntry.period == period)

        if organization_id:
            query = query.where(LeaderboardEntry.organization_id == organization_id)
        else:
            query = query.where(LeaderboardEntry.organization_id.is_(None))

        query = query.order_by(LeaderboardEntry.rank).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_user_rank(
        self,
        user_id: uuid.UUID,
        period: str = "all_time",
        organization_id: uuid.UUID | None = None,
    ) -> LeaderboardEntry | None:
        """Get user's leaderboard entry."""
        query = select(LeaderboardEntry).where(
            and_(
                LeaderboardEntry.user_id == user_id,
                LeaderboardEntry.period == period,
            )
        )

        if organization_id:
            query = query.where(LeaderboardEntry.organization_id == organization_id)
        else:
            query = query.where(LeaderboardEntry.organization_id.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_leaderboard(
        self,
        period: str = "all_time",
        organization_id: uuid.UUID | None = None,
    ) -> list[LeaderboardEntry]:
        """Update leaderboard rankings."""
        # Get all user points
        query = select(UserPoints).order_by(UserPoints.total_points.desc())
        result = await self.db.execute(query)
        all_points = list(result.scalars().all())

        # Calculate period start
        now = datetime.utcnow()
        if period == "weekly":
            period_start = now - timedelta(days=now.weekday())
        elif period == "monthly":
            period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            period_start = datetime(2020, 1, 1)  # All time

        # Update or create leaderboard entries
        entries = []
        for rank, user_points in enumerate(all_points, start=1):
            # Find existing entry
            existing = await self.db.execute(
                select(LeaderboardEntry).where(
                    and_(
                        LeaderboardEntry.user_id == user_points.user_id,
                        LeaderboardEntry.period == period,
                        LeaderboardEntry.organization_id == organization_id
                        if organization_id
                        else LeaderboardEntry.organization_id.is_(None),
                    )
                )
            )
            entry = existing.scalar_one_or_none()

            if entry:
                entry.points = user_points.total_points
                entry.rank = rank
            else:
                entry = LeaderboardEntry(
                    user_id=user_points.user_id,
                    organization_id=organization_id,
                    period=period,
                    period_start=period_start,
                    points=user_points.total_points,
                    rank=rank,
                )
                self.db.add(entry)

            entries.append(entry)

        await self.db.commit()
        return entries

    # Stats

    async def get_gamification_stats(
        self,
        user_id: uuid.UUID,
    ) -> dict:
        """Get gamification stats for a user."""
        user_points = await self.get_or_create_user_points(user_id)
        achievements = await self.get_user_achievements(user_id)
        all_achievements = await self.list_achievements()

        # Calculate points to next level
        current_level = user_points.level
        if current_level < len(self.LEVEL_THRESHOLDS):
            next_threshold = self.LEVEL_THRESHOLDS[current_level]
            points_to_next_level = next_threshold - user_points.total_points
        else:
            points_to_next_level = 0

        return {
            "total_points": user_points.total_points,
            "level": user_points.level,
            "current_streak": user_points.current_streak,
            "longest_streak": user_points.longest_streak,
            "points_to_next_level": max(0, points_to_next_level),
            "achievements_earned": len(achievements),
            "achievements_total": len(all_achievements),
        }
