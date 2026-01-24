"""Schedule models for trainer appointments."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Text,
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

    # Relationships
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")


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
