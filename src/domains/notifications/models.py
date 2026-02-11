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
    PLAN_UPDATED = "plan_updated"  # When a prescribed plan is modified

    # Nutrition related
    DIET_ASSIGNED = "diet_assigned"
    MEAL_REMINDER = "meal_reminder"

    # Progress related
    PROGRESS_MILESTONE = "progress_milestone"
    WEIGHT_GOAL_REACHED = "weight_goal_reached"

    # Check-in related
    CHECKIN_REMINDER = "checkin_reminder"
    CHECKIN_STREAK = "checkin_streak"
    CHECKIN_REQUEST_CREATED = "checkin_request_created"
    CHECKIN_REQUEST_APPROVED = "checkin_request_approved"
    CHECKIN_REQUEST_REJECTED = "checkin_request_rejected"

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

    # Self-service booking
    SESSION_BOOKED_BY_STUDENT = "session_booked_by_student"
    ATTENDANCE_MARKED = "attendance_marked"

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


class DevicePlatform(str, enum.Enum):
    """Mobile platform for push notifications."""

    IOS = "ios"
    ANDROID = "android"


class DeviceToken(Base, UUIDMixin, TimestampMixin):
    """FCM device token for push notifications."""

    __tablename__ = "device_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(500), nullable=False, unique=True, index=True)
    platform: Mapped[DevicePlatform] = mapped_column(
        Enum(DevicePlatform),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", lazy="selectin")


class NotificationCategory(str, enum.Enum):
    """Categories for grouping notification preferences."""

    WORKOUTS = "workouts"  # Workout reminders, plan assignments
    PROGRESS = "progress"  # Progress milestones, achievements
    MESSAGES = "messages"  # Chat messages, mentions
    ORGANIZATION = "organization"  # Invites, role changes
    PAYMENTS = "payments"  # Payment reminders, receipts
    APPOINTMENTS = "appointments"  # Appointment reminders
    SYSTEM = "system"  # System announcements


class NotificationPreference(Base, UUIDMixin, TimestampMixin):
    """User preferences for granular notification control.

    Each user can enable/disable notifications by type.
    Default is enabled for all notification types.
    """

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType),
        nullable=False,
    )
    # Individual type settings
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user = relationship("User", lazy="selectin")

    class Meta:
        unique_together = ["user_id", "notification_type"]


# Mapping of notification types to categories
NOTIFICATION_TYPE_CATEGORIES = {
    # Workouts
    NotificationType.WORKOUT_ASSIGNED: NotificationCategory.WORKOUTS,
    NotificationType.WORKOUT_REMINDER: NotificationCategory.WORKOUTS,
    NotificationType.WORKOUT_COMPLETED: NotificationCategory.WORKOUTS,
    NotificationType.PLAN_ASSIGNED: NotificationCategory.WORKOUTS,
    NotificationType.PLAN_UPDATED: NotificationCategory.WORKOUTS,
    NotificationType.DIET_ASSIGNED: NotificationCategory.WORKOUTS,
    NotificationType.MEAL_REMINDER: NotificationCategory.WORKOUTS,
    # Progress
    NotificationType.PROGRESS_MILESTONE: NotificationCategory.PROGRESS,
    NotificationType.WEIGHT_GOAL_REACHED: NotificationCategory.PROGRESS,
    NotificationType.CHECKIN_REMINDER: NotificationCategory.PROGRESS,
    NotificationType.CHECKIN_STREAK: NotificationCategory.PROGRESS,
    NotificationType.ACHIEVEMENT_UNLOCKED: NotificationCategory.PROGRESS,
    NotificationType.POINTS_EARNED: NotificationCategory.PROGRESS,
    NotificationType.LEADERBOARD_CHANGE: NotificationCategory.PROGRESS,
    # Messages
    NotificationType.NEW_MESSAGE: NotificationCategory.MESSAGES,
    NotificationType.NEW_FOLLOWER: NotificationCategory.MESSAGES,
    NotificationType.MENTION: NotificationCategory.MESSAGES,
    # Organization
    NotificationType.INVITE_RECEIVED: NotificationCategory.ORGANIZATION,
    NotificationType.MEMBER_JOINED: NotificationCategory.ORGANIZATION,
    NotificationType.ROLE_CHANGED: NotificationCategory.ORGANIZATION,
    NotificationType.STUDENT_INACTIVE: NotificationCategory.ORGANIZATION,
    NotificationType.STUDENT_PROGRESS: NotificationCategory.ORGANIZATION,
    # Payments
    NotificationType.PAYMENT_DUE: NotificationCategory.PAYMENTS,
    NotificationType.PAYMENT_RECEIVED: NotificationCategory.PAYMENTS,
    NotificationType.PAYMENT_OVERDUE: NotificationCategory.PAYMENTS,
    # Appointments
    NotificationType.APPOINTMENT_CREATED: NotificationCategory.APPOINTMENTS,
    NotificationType.APPOINTMENT_REMINDER: NotificationCategory.APPOINTMENTS,
    NotificationType.APPOINTMENT_CANCELLED: NotificationCategory.APPOINTMENTS,
    NotificationType.APPOINTMENT_CONFIRMED: NotificationCategory.APPOINTMENTS,
    NotificationType.SESSION_BOOKED_BY_STUDENT: NotificationCategory.APPOINTMENTS,
    NotificationType.ATTENDANCE_MARKED: NotificationCategory.APPOINTMENTS,
    # System
    NotificationType.SYSTEM_ANNOUNCEMENT: NotificationCategory.SYSTEM,
    NotificationType.SYSTEM_MAINTENANCE: NotificationCategory.SYSTEM,
}
