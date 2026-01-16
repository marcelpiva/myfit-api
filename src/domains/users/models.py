"""User models for the MyFit platform."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class Gender(str, enum.Enum):
    """User gender options."""

    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class Theme(str, enum.Enum):
    """UI theme options."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class Units(str, enum.Enum):
    """Measurement units."""

    METRIC = "metric"
    IMPERIAL = "imperial"


class User(Base, UUIDMixin, TimestampMixin):
    """User model representing a platform user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[Gender | None] = mapped_column(
        Enum(Gender, name="gender_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    bio: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    settings: Mapped["UserSettings"] = relationship(
        "UserSettings",
        back_populates="user",
        uselist=False,
        lazy="joined",
    )
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="user",
        foreign_keys="OrganizationMembership.user_id",
        lazy="selectin",
    )
    owned_organizations: Mapped[list["Organization"]] = relationship(
        "Organization",
        back_populates="owner",
        foreign_keys="Organization.owner_id",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"


class UserSettings(Base, UUIDMixin):
    """User settings and preferences."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    theme: Mapped[Theme] = mapped_column(
        Enum(Theme, name="theme_enum", values_callable=lambda x: [e.value for e in x]),
        default=Theme.SYSTEM,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(5), default="pt", nullable=False)
    units: Mapped[Units] = mapped_column(
        Enum(Units, name="units_enum", values_callable=lambda x: [e.value for e in x]),
        default=Units.METRIC,
        nullable=False,
    )
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    goal_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="settings")

    def __repr__(self) -> str:
        return f"<UserSettings user_id={self.user_id}>"


# Import for type hints - avoid circular imports
from src.domains.organizations.models import Organization, OrganizationMembership  # noqa: E402, F401
