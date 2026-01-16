"""Progress tracking models for the MyFit platform."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import UUIDMixin


class PhotoAngle(str, enum.Enum):
    """Photo angle options for progress photos."""

    FRONT = "front"
    SIDE = "side"
    BACK = "back"


class WeightLog(Base, UUIDMixin):
    """User weight tracking."""

    __tablename__ = "weight_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<WeightLog {self.weight_kg}kg at {self.logged_at}>"


class MeasurementLog(Base, UUIDMixin):
    """Body measurements tracking."""

    __tablename__ = "measurement_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Measurements in cm
    chest_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    waist_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    hips_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    biceps_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    thigh_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    calf_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    neck_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    forearm_cm: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<MeasurementLog at {self.logged_at}>"


class ProgressPhoto(Base, UUIDMixin):
    """Progress photos for visual tracking."""

    __tablename__ = "progress_photos"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    angle: Mapped[PhotoAngle] = mapped_column(
        Enum(PhotoAngle, name="photo_angle_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Optional: link to weight/measurement from same day
    weight_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("weight_logs.id", ondelete="SET NULL"),
        nullable=True,
    )
    measurement_log_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("measurement_logs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    weight_log: Mapped["WeightLog | None"] = relationship("WeightLog")
    measurement_log: Mapped["MeasurementLog | None"] = relationship("MeasurementLog")

    def __repr__(self) -> str:
        return f"<ProgressPhoto {self.angle} at {self.logged_at}>"


class WeightGoal(Base, UUIDMixin):
    """User's weight goal."""

    __tablename__ = "weight_goals"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    target_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    target_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    start_weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")

    @property
    def weight_to_lose(self) -> float:
        """Calculate weight difference to goal."""
        return self.start_weight_kg - self.target_weight_kg

    def __repr__(self) -> str:
        return f"<WeightGoal target={self.target_weight_kg}kg>"


# Import for type hints
from src.domains.users.models import User  # noqa: E402, F401
