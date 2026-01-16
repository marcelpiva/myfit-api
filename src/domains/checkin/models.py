"""Check-in models for the MyFit platform."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class CheckInMethod(str, enum.Enum):
    """Methods of checking in."""

    QR = "qr"
    CODE = "code"
    LOCATION = "location"
    REQUEST = "request"
    MANUAL = "manual"


class CheckInStatus(str, enum.Enum):
    """Check-in status."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class Gym(Base, UUIDMixin, TimestampMixin):
    """Gym/Location for check-ins."""

    __tablename__ = "gyms"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    radius_meters: Mapped[int] = mapped_column(
        Integer, default=100, nullable=False
    )  # Radius for location check-in

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    check_in_codes: Mapped[list["CheckInCode"]] = relationship(
        "CheckInCode",
        back_populates="gym",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Gym {self.name}>"


class CheckIn(Base, UUIDMixin):
    """User check-in record."""

    __tablename__ = "check_ins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gyms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[CheckInMethod] = mapped_column(
        Enum(CheckInMethod, name="checkin_method_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[CheckInStatus] = mapped_column(
        Enum(CheckInStatus, name="checkin_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=CheckInStatus.CONFIRMED,
        nullable=False,
    )
    checked_in_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    checked_out_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    gym: Mapped["Gym"] = relationship("Gym")
    approved_by: Mapped["User | None"] = relationship(
        "User", foreign_keys=[approved_by_id]
    )

    @property
    def is_active(self) -> bool:
        """Check if user is still checked in."""
        return self.checked_out_at is None

    @property
    def duration_minutes(self) -> int | None:
        """Calculate check-in duration."""
        if self.checked_out_at:
            delta = self.checked_out_at - self.checked_in_at
            return int(delta.total_seconds() / 60)
        return None

    def __repr__(self) -> str:
        return f"<CheckIn user={self.user_id} gym={self.gym_id}>"


class CheckInCode(Base, UUIDMixin, TimestampMixin):
    """Reusable check-in codes for gyms."""

    __tablename__ = "check_in_codes"

    gym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gyms.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    uses_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    gym: Mapped["Gym"] = relationship("Gym", back_populates="check_in_codes")

    @property
    def is_valid(self) -> bool:
        """Check if code is still valid."""
        if not self.is_active:
            return False
        if self.expires_at and datetime.now(self.expires_at.tzinfo) > self.expires_at:
            return False
        if self.max_uses and self.uses_count >= self.max_uses:
            return False
        return True

    def __repr__(self) -> str:
        return f"<CheckInCode {self.code}>"


class CheckInRequest(Base, UUIDMixin, TimestampMixin):
    """Request for check-in approval."""

    __tablename__ = "check_in_requests"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    gym_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gyms.id", ondelete="CASCADE"),
        nullable=False,
    )
    approver_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[CheckInStatus] = mapped_column(
        Enum(CheckInStatus, name="checkin_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=CheckInStatus.PENDING,
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    response_note: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    gym: Mapped["Gym"] = relationship("Gym")
    approver: Mapped["User"] = relationship("User", foreign_keys=[approver_id])

    def __repr__(self) -> str:
        return f"<CheckInRequest user={self.user_id} status={self.status}>"


# Import for type hints
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
