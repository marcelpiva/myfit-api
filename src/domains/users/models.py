"""User models for the MyFit platform."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class AuthProvider(str, enum.Enum):
    """Authentication provider options."""

    EMAIL = "email"
    GOOGLE = "google"
    APPLE = "apple"


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

    # Social login fields
    auth_provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, name="auth_provider_enum", values_callable=lambda x: [e.value for e in x]),
        default=AuthProvider.EMAIL,
        nullable=False,
    )
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    apple_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    # Professional credentials (for trainers)
    cref: Mapped[str | None] = mapped_column(String(20), nullable=True)  # CREF registration number
    cref_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cref_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Trainer onboarding fields
    specialties: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON array as string
    years_of_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Student onboarding fields
    fitness_goal: Mapped[str | None] = mapped_column(String(50), nullable=True)  # loseWeight, gainMuscle, etc
    fitness_goal_other: Mapped[str | None] = mapped_column(String(200), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), nullable=True)  # beginner, intermediate, advanced
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_frequency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    injuries: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON array as string
    injuries_other: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Extended student onboarding fields
    preferred_duration: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "30", "45", "60", "90"
    training_location: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON array as string
    preferred_activities: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON array as string
    can_do_impact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Onboarding completion tracking
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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


class EmailVerification(Base, UUIDMixin, TimestampMixin):
    """Email verification codes for user registration and password reset."""

    __tablename__ = "email_verifications"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # "registration", "password_reset"
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<EmailVerification email={self.email} purpose={self.purpose}>"


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

    # Do Not Disturb settings
    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dnd_start_time: Mapped[str | None] = mapped_column(
        String(5), nullable=True
    )  # HH:MM format (e.g., "22:00")
    dnd_end_time: Mapped[str | None] = mapped_column(
        String(5), nullable=True
    )  # HH:MM format (e.g., "07:00")

    goal_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    target_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="settings")

    def __repr__(self) -> str:
        return f"<UserSettings user_id={self.user_id}>"


# Import for type hints - avoid circular imports
from src.domains.organizations.models import Organization, OrganizationMembership  # noqa: E402, F401
