"""Referral system models.

Handles referral codes, tracking who invited whom,
and distributing rewards (e.g., 1 week of Pro features).
"""
import enum
import secrets
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class RewardType(str, enum.Enum):
    """Type of reward granted for a referral."""

    PRO_TRIAL = "pro_trial"  # X days of Pro features
    CONSULTANCY_DISCOUNT = "consultancy_discount"  # Discount on marketplace
    FREE_CONSULTANCY = "free_consultancy"  # Free trial consultancy


class RewardStatus(str, enum.Enum):
    """Status of a referral reward."""

    PENDING = "pending"  # Waiting to be activated
    ACTIVE = "active"  # Currently active
    USED = "used"  # Consumed
    EXPIRED = "expired"


def generate_referral_code() -> str:
    """Generate a unique referral code (MF-XXXXXX)."""
    return f"MF-{secrets.token_hex(3).upper()}"


class ReferralCode(Base, UUIDMixin, TimestampMixin):
    """A referral code owned by a user.

    Each user gets one primary referral code.
    They can share it to invite others.
    """

    __tablename__ = "referral_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        default=generate_referral_code,
    )

    # Stats
    total_referrals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    successful_referrals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    referrals = relationship("Referral", back_populates="referral_code", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ReferralCode {self.code} user={self.user_id}>"


class Referral(Base, UUIDMixin, TimestampMixin):
    """Tracks a single referral event (who invited whom)."""

    __tablename__ = "referrals"

    referral_code_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referral_codes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referrer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    referred_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Whether the referred user completed a qualifying action
    # (e.g., first workout completed, first consultancy purchased)
    is_qualified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Whether rewards have been granted to both parties
    referrer_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    referred_rewarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    referral_code = relationship("ReferralCode", back_populates="referrals")
    referrer = relationship("User", foreign_keys=[referrer_id])
    referred = relationship("User", foreign_keys=[referred_id])
    rewards = relationship("ReferralReward", back_populates="referral", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Referral referrer={self.referrer_id} referred={self.referred_id}>"


class ReferralReward(Base, UUIDMixin, TimestampMixin):
    """A reward granted as part of a referral."""

    __tablename__ = "referral_rewards"

    referral_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("referrals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reward_type: Mapped[RewardType] = mapped_column(
        Enum(RewardType, name="reward_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # Reward details
    reward_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Days of Pro trial
    reward_value_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Discount amount

    status: Mapped[RewardStatus] = mapped_column(
        Enum(RewardStatus, name="reward_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=RewardStatus.PENDING,
        nullable=False,
    )

    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    referral = relationship("Referral", back_populates="rewards")
    user = relationship("User", foreign_keys=[user_id])

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        from datetime import timezone
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now > expires

    def __repr__(self) -> str:
        return f"<ReferralReward {self.reward_type} user={self.user_id} status={self.status}>"


# Import for type hints
from src.domains.users.models import User  # noqa: E402, F401
