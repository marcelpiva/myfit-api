"""Schedule models for trainer appointments."""
import enum
import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class AppointmentStatus(str, enum.Enum):
    """Appointment status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class AppointmentType(str, enum.Enum):
    """Type of training appointment."""

    STRENGTH = "strength"
    CARDIO = "cardio"
    FUNCTIONAL = "functional"
    HIIT = "hiit"
    ASSESSMENT = "assessment"
    OTHER = "other"


class SessionType(str, enum.Enum):
    """How this session relates to the service plan."""

    SCHEDULED = "scheduled"  # Regular scheduled session
    MAKEUP = "makeup"  # Make-up for a missed session
    EXTRA = "extra"  # Extra session beyond the plan
    TRIAL = "trial"  # Trial/experimental session


class AttendanceStatus(str, enum.Enum):
    """Attendance tracking for appointments."""

    SCHEDULED = "scheduled"  # Not yet happened
    ATTENDED = "attended"  # Student was present (check-in done)
    MISSED = "missed"  # Student didn't show up
    LATE_CANCELLED = "late_cancelled"  # Cancelled too close to session time


class Appointment(Base, UUIDMixin, TimestampMixin):
    """Trainer-student appointment/session."""

    __tablename__ = "appointments"

    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    date_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    duration_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
    )

    workout_type: Mapped[AppointmentType | None] = mapped_column(
        Enum(AppointmentType),
        nullable=True,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus),
        nullable=False,
        default=AppointmentStatus.PENDING,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Service plan & billing link
    service_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType),
        default=SessionType.SCHEDULED,
        nullable=False,
        server_default="scheduled",
    )
    attendance_status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus),
        default=AttendanceStatus.SCHEDULED,
        nullable=False,
        server_default="scheduled",
    )
    is_complimentary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )

    # Reminder tracking
    reminder_24h_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    reminder_1h_sent: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )

    # Relationships
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
    service_plan = relationship("ServicePlan", lazy="selectin")
    payment = relationship("Payment", lazy="selectin")


class TrainerAvailability(Base, UUIDMixin, TimestampMixin):
    """Trainer availability slots for scheduling."""

    __tablename__ = "trainer_availability"

    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )  # 0=Monday, 6=Sunday
    start_time: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # HH:MM format
    end_time: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )  # HH:MM format

    # Relationships
    trainer = relationship("User", lazy="selectin")


class TrainerBlockedSlot(Base, UUIDMixin, TimestampMixin):
    """Blocked time slots for a trainer (lunch, vacation, etc)."""

    __tablename__ = "trainer_blocked_slots"

    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )  # 0=Monday..6=Sunday (for recurring blocks)
    specific_date: Mapped[date | None] = mapped_column(
        Date, nullable=True,
    )  # For one-off blocks
    start_time: Mapped[time] = mapped_column(
        Time, nullable=False,
    )
    end_time: Mapped[time] = mapped_column(
        Time, nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_recurring: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )  # True = weekly on day_of_week, False = specific_date

    # Relationships
    trainer = relationship("User", lazy="selectin")


class TrainerSettings(Base, UUIDMixin, TimestampMixin):
    """Per-trainer scheduling settings."""

    __tablename__ = "trainer_settings"

    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    default_start_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(6, 0),
    )  # Default 06:00
    default_end_time: Mapped[time] = mapped_column(
        Time, nullable=False, default=time(21, 0),
    )  # Default 21:00
    session_duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60,
    )
    slot_interval_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30,
    )
    late_cancel_window_hours: Mapped[int] = mapped_column(
        Integer, default=24, nullable=False, server_default="24",
    )
    late_cancel_policy: Mapped[str] = mapped_column(
        String(10), default="warn", nullable=False, server_default="warn",
    )

    # Relationships
    trainer = relationship("User", lazy="selectin")
