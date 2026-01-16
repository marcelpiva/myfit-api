"""Gamification schemas for request/response validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# User Points schemas

class UserPointsResponse(BaseModel):
    """User points response."""

    id: UUID
    user_id: UUID
    total_points: int
    level: int
    current_streak: int
    longest_streak: int
    last_activity_at: datetime | None = None
    updated_at: datetime

    class Config:
        from_attributes = True


class AwardPointsRequest(BaseModel):
    """Award points request."""

    points: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=255)
    description: str | None = Field(None, max_length=500)
    reference_type: str | None = Field(None, max_length=50)
    reference_id: UUID | None = None


class PointTransactionResponse(BaseModel):
    """Point transaction response."""

    id: UUID
    user_points_id: UUID
    points: int
    reason: str
    description: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# Achievement schemas

class AchievementCreate(BaseModel):
    """Create achievement request."""

    name: str = Field(min_length=2, max_length=255)
    description: str = Field(min_length=5, max_length=1000)
    icon: str = Field(min_length=1, max_length=100)
    points_reward: int = Field(default=0, ge=0)
    category: str = Field(default="general", max_length=50)
    condition: dict = Field(default_factory=dict)
    order: int = Field(default=0, ge=0)


class AchievementResponse(BaseModel):
    """Achievement response."""

    id: UUID
    name: str
    description: str
    icon: str
    points_reward: int
    category: str
    condition: dict
    is_active: bool
    order: int

    class Config:
        from_attributes = True


class UserAchievementResponse(BaseModel):
    """User achievement response."""

    id: UUID
    user_id: UUID
    achievement_id: UUID
    earned_at: datetime
    progress: dict | None = None
    achievement: AchievementResponse | None = None

    class Config:
        from_attributes = True


class AwardAchievementRequest(BaseModel):
    """Award achievement request."""

    achievement_id: UUID
    progress: dict | None = None


# Leaderboard schemas

class LeaderboardEntryResponse(BaseModel):
    """Leaderboard entry response."""

    id: UUID
    user_id: UUID
    organization_id: UUID | None = None
    period: str
    period_start: datetime
    points: int
    rank: int
    updated_at: datetime

    class Config:
        from_attributes = True


# Stats schema

class GamificationStatsResponse(BaseModel):
    """Gamification statistics response."""

    total_points: int
    level: int
    current_streak: int
    longest_streak: int
    points_to_next_level: int
    achievements_earned: int
    achievements_total: int
