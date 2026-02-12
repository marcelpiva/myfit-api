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


class DifficultyLevel(str, enum.Enum):
    """Difficulty level for session feedback."""

    TOO_EASY = "too_easy"
    JUST_RIGHT = "just_right"
    TOO_HARD = "too_hard"


class EvaluatorRole(str, enum.Enum):
    """Role of the person evaluating a session."""

    TRAINER = "trainer"
    STUDENT = "student"


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

    # Group session fields
    is_group: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    max_participants: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )

    # Relationships
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
    service_plan = relationship("ServicePlan", lazy="selectin")
    payment = relationship("Payment", lazy="selectin")
    participants = relationship("AppointmentParticipant", lazy="selectin", cascade="all, delete-orphan")
    evaluations = relationship("SessionEvaluation", lazy="selectin", cascade="all, delete-orphan")


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


class AppointmentParticipant(Base, UUIDMixin, TimestampMixin):
    """Participant in a group session."""

    __tablename__ = "appointment_participants"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attendance_status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, create_constraint=False, native_enum=False),
        default=AttendanceStatus.SCHEDULED,
        nullable=False,
        server_default="scheduled",
    )
    service_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_plans.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_complimentary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    student = relationship("User", lazy="selectin")
    service_plan = relationship("ServicePlan", lazy="selectin")


class SessionEvaluation(Base, UUIDMixin, TimestampMixin):
    """Post-session feedback/evaluation."""

    __tablename__ = "session_evaluations"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    evaluator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    evaluator_role: Mapped[EvaluatorRole] = mapped_column(
        Enum(EvaluatorRole),
        nullable=False,
    )
    overall_rating: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    difficulty: Mapped[DifficultyLevel | None] = mapped_column(
        Enum(DifficultyLevel),
        nullable=True,
    )
    energy_level: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    appointment = relationship("Appointment", lazy="selectin", overlaps="evaluations")
    evaluator = relationship("User", lazy="selectin")


class WaitlistStatus(str, enum.Enum):
    """Status of a waitlist entry."""
    WAITING = "waiting"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    EXPIRED = "expired"


class WaitlistEntry(Base, UUIDMixin, TimestampMixin):
    """Student waiting for a slot with a trainer."""

    __tablename__ = "waitlist_entries"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    preferred_day_of_week: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    preferred_time_start: Mapped[time | None] = mapped_column(
        Time, nullable=True,
    )
    preferred_time_end: Mapped[time | None] = mapped_column(
        Time, nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[WaitlistStatus] = mapped_column(
        Enum(WaitlistStatus, create_constraint=False, native_enum=False),
        default=WaitlistStatus.WAITING,
        nullable=False,
        server_default="waiting",
    )
    offered_appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    offered_appointment = relationship("Appointment", lazy="selectin")
    organization = relationship("Organization", lazy="selectin")


class SessionTemplate(Base, UUIDMixin, TimestampMixin):
    """Reusable session template for quick scheduling."""

    __tablename__ = "session_templates"

    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60,
    )
    workout_type: Mapped[AppointmentType | None] = mapped_column(
        Enum(AppointmentType, create_constraint=False, native_enum=False),
        nullable=True,
    )
    is_group: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    max_participants: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true",
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    trainer = relationship("User", lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
