"""Organization models for the MyFit platform."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class OrganizationType(str, enum.Enum):
    """Types of organizations in the platform."""

    GYM = "gym"
    PERSONAL = "personal"
    NUTRITIONIST = "nutritionist"
    CLINIC = "clinic"


class UserRole(str, enum.Enum):
    """User roles within an organization."""

    STUDENT = "student"
    TRAINER = "trainer"
    COACH = "coach"
    NUTRITIONIST = "nutritionist"
    GYM_ADMIN = "gym_admin"
    GYM_OWNER = "gym_owner"


class Organization(Base, UUIDMixin, TimestampMixin):
    """Organization model (gym, personal trainer, clinic, etc.)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(
        Enum(OrganizationType, name="organization_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Owner
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="owned_organizations",
        foreign_keys=[owner_id],
    )
    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="organization",
        lazy="selectin",
    )

    @property
    def member_count(self) -> int:
        """Get total number of members."""
        return len([m for m in self.memberships if m.is_active])

    @property
    def trainer_count(self) -> int:
        """Get number of trainers/professionals."""
        return len(
            [
                m
                for m in self.memberships
                if m.is_active and m.role in [UserRole.TRAINER, UserRole.COACH]
            ]
        )

    def __repr__(self) -> str:
        return f"<Organization {self.name}>"


class OrganizationMembership(Base, UUIDMixin):
    """Membership linking users to organizations with specific roles."""

    __tablename__ = "organization_memberships"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="memberships",
    )
    user: Mapped["User"] = relationship(
        "User",
        back_populates="memberships",
        foreign_keys=[user_id],
    )
    invited_by: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[invited_by_id],
    )

    def __repr__(self) -> str:
        return f"<OrganizationMembership org={self.organization_id} user={self.user_id} role={self.role}>"


class OrganizationInvite(Base, UUIDMixin, TimestampMixin):
    """Pending invitations to join an organization."""

    __tablename__ = "organization_invites"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    invited_by: Mapped["User"] = relationship("User")

    @property
    def is_expired(self) -> bool:
        """Check if invite has expired."""
        now = datetime.utcnow()
        return now > self.expires_at

    @property
    def is_accepted(self) -> bool:
        """Check if invite was accepted."""
        return self.accepted_at is not None

    def __repr__(self) -> str:
        return f"<OrganizationInvite {self.email} -> {self.organization_id}>"


# Import for type hints
from src.domains.users.models import User  # noqa: E402, F401
