"""Notification models for user notifications."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class NotificationType(str, enum.Enum):
    """Type of notification."""

    # Workout related
    WORKOUT_ASSIGNED = "workout_assigned"
    WORKOUT_REMINDER = "workout_reminder"
    WORKOUT_COMPLETED = "workout_completed"
    PLAN_ASSIGNED = "plan_assigned"

    # Nutrition related
    DIET_ASSIGNED = "diet_assigned"
    MEAL_REMINDER = "meal_reminder"

    # Progress related
    PROGRESS_MILESTONE = "progress_milestone"
    WEIGHT_GOAL_REACHED = "weight_goal_reached"

    # Check-in related
    CHECKIN_REMINDER = "checkin_reminder"
    CHECKIN_STREAK = "checkin_streak"

    # Gamification related
    ACHIEVEMENT_UNLOCKED = "achievement_unlocked"
    POINTS_EARNED = "points_earned"
    LEADERBOARD_CHANGE = "leaderboard_change"

    # Social/Communication
    NEW_MESSAGE = "new_message"
    NEW_FOLLOWER = "new_follower"
    MENTION = "mention"

    # Organization related
    INVITE_RECEIVED = "invite_received"
    MEMBER_JOINED = "member_joined"
    ROLE_CHANGED = "role_changed"

    # Payment related
    PAYMENT_DUE = "payment_due"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_OVERDUE = "payment_overdue"

    # Appointments
    APPOINTMENT_CREATED = "appointment_created"
    APPOINTMENT_REMINDER = "appointment_reminder"
    APPOINTMENT_CANCELLED = "appointment_cancelled"
    APPOINTMENT_CONFIRMED = "appointment_confirmed"

    # Trainer specific
    STUDENT_INACTIVE = "student_inactive"
    STUDENT_PROGRESS = "student_progress"

    # System
    SYSTEM_ANNOUNCEMENT = "system_announcement"
    SYSTEM_MAINTENANCE = "system_maintenance"


class NotificationPriority(str, enum.Enum):
    """Priority level of notification."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Notification(Base, UUIDMixin, TimestampMixin):
    """Notification for a user."""

    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType),
        nullable=False,
        index=True,
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        Enum(NotificationPriority),
        default=NotificationPriority.NORMAL,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Action data (for navigation)
    action_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "navigate", "open_url"
    action_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string with route/params

    # Reference to related entity
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "workout", "appointment"
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Organization context (optional)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Sender (for messages, invites, etc.)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Push notification tracking
    push_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    push_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    sender = relationship("User", foreign_keys=[sender_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
