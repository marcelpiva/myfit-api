"""Gamification models for the MyFit platform."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class UserPoints(Base, UUIDMixin):
    """User's total points and level."""

    __tablename__ = "user_points"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    total_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    transactions: Mapped[list["PointTransaction"]] = relationship(
        "PointTransaction",
        back_populates="user_points",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserPoints user={self.user_id} points={self.total_points}>"


class PointTransaction(Base, UUIDMixin):
    """Individual point transaction."""

    __tablename__ = "point_transactions"

    user_points_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_points.id", ondelete="CASCADE"),
        nullable=False,
    )
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # Can be negative
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g., "workout_session", "checkin"
    reference_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user_points: Mapped["UserPoints"] = relationship(
        "UserPoints",
        back_populates="transactions",
    )

    def __repr__(self) -> str:
        return f"<PointTransaction {self.points} points: {self.reason}>"


class Achievement(Base, UUIDMixin, TimestampMixin):
    """Achievement/Badge definition."""

    __tablename__ = "achievements"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str] = mapped_column(String(100), nullable=False)
    points_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), default="general", nullable=False
    )  # workout, nutrition, streak, social
    condition: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )  # JSON condition for earning
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    user_achievements: Mapped[list["UserAchievement"]] = relationship(
        "UserAchievement",
        back_populates="achievement",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Achievement {self.name}>"


class UserAchievement(Base, UUIDMixin):
    """Achievement earned by a user."""

    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    progress: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # Current progress towards achievement

    # Relationships
    user: Mapped["User"] = relationship("User")
    achievement: Mapped["Achievement"] = relationship(
        "Achievement",
        back_populates="user_achievements",
    )

    def __repr__(self) -> str:
        return f"<UserAchievement user={self.user_id} achievement={self.achievement_id}>"


class LeaderboardEntry(Base, UUIDMixin):
    """Cached leaderboard entry for performance."""

    __tablename__ = "leaderboard_entries"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )
    period: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "weekly", "monthly", "all_time"
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    organization: Mapped["Organization | None"] = relationship("Organization")

    def __repr__(self) -> str:
        return f"<LeaderboardEntry rank={self.rank} points={self.points}>"


# Import for type hints
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
