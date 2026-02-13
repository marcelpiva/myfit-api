"""Platform subscription models for tier management (Free/Pro)."""
import enum
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
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class PlatformTier(str, enum.Enum):
    """Platform subscription tiers."""

    FREE = "free"
    PRO = "pro"


class SubscriptionStatus(str, enum.Enum):
    """Subscription status."""

    PENDING = "pending"
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"


class SubscriptionSource(str, enum.Enum):
    """How the subscription was acquired."""

    DIRECT = "direct"  # User purchased directly
    REFERRAL = "referral"  # Earned via referral
    FOUNDER = "founder"  # Founders Club (early adopter)
    PROMOTION = "promotion"  # Marketing promotion
    TRIAL = "trial"  # Free trial


class PlatformSubscription(Base, UUIDMixin, TimestampMixin):
    """Platform subscription for a user (controls Free vs Pro tier).

    Each professional user has at most one active subscription.
    Students are always free — this only applies to professionals.
    """

    __tablename__ = "platform_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tier: Mapped[PlatformTier] = mapped_column(
        Enum(PlatformTier, name="platform_tier_enum", values_callable=lambda x: [e.value for e in x]),
        default=PlatformTier.FREE,
        nullable=False,
    )

    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionStatus.ACTIVE,
        nullable=False,
    )

    source: Mapped[SubscriptionSource] = mapped_column(
        Enum(SubscriptionSource, name="subscription_source_enum", values_callable=lambda x: [e.value for e in x]),
        default=SubscriptionSource.DIRECT,
        nullable=False,
    )

    # Pricing
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Dates
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Payment provider reference (Stripe/Asaas)
    external_subscription_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Founder badge
    is_founder: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    @property
    def is_active(self) -> bool:
        """Check if subscription is currently active."""
        if self.status in (SubscriptionStatus.PENDING, SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED):
            return False
        if self.expires_at and datetime.now(self.expires_at.tzinfo or None) > self.expires_at:
            return False
        return True

    @property
    def is_pro(self) -> bool:
        """Check if this is an active Pro subscription."""
        return self.tier == PlatformTier.PRO and self.is_active

    def __repr__(self) -> str:
        return f"<PlatformSubscription user={self.user_id} tier={self.tier} status={self.status}>"


class FeatureDefinition(Base, UUIDMixin):
    """Feature definitions controlled by tier.

    This is a configuration table — defines which features exist
    and which tier is required to access them.
    """

    __tablename__ = "feature_definitions"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which tier is required (free = available to all, pro = Pro only)
    required_tier: Mapped[PlatformTier] = mapped_column(
        Enum(PlatformTier, name="platform_tier_enum", values_callable=lambda x: [e.value for e in x]),
        default=PlatformTier.FREE,
        nullable=False,
    )

    # Feature limits for free tier (null = unlimited)
    free_tier_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pro_tier_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # null = unlimited

    # Whether feature is enabled globally
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Metadata
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)  # e.g., "students", "analytics", "marketplace"

    def __repr__(self) -> str:
        return f"<FeatureDefinition {self.key} tier={self.required_tier}>"


# Default feature definitions to seed
DEFAULT_FEATURES = [
    {
        "key": "max_active_students",
        "name": "Active Students",
        "description": "Maximum number of active students a professional can manage",
        "required_tier": PlatformTier.FREE,
        "free_tier_limit": 5,
        "pro_tier_limit": None,  # Unlimited
        "category": "students",
    },
    {
        "key": "advanced_analytics",
        "name": "Advanced Analytics",
        "description": "Detailed student analytics and progress reports",
        "required_tier": PlatformTier.PRO,
        "category": "analytics",
    },
    {
        "key": "marketplace_highlight",
        "name": "Marketplace Highlight",
        "description": "Priority placement in marketplace search results",
        "required_tier": PlatformTier.PRO,
        "category": "marketplace",
    },
    {
        "key": "ai_workout_generation",
        "name": "AI Workout Generation",
        "description": "AI-powered workout plan generation",
        "required_tier": PlatformTier.PRO,
        "category": "ai",
    },
    {
        "key": "custom_branding",
        "name": "Custom Branding",
        "description": "Personalized branding on shared content",
        "required_tier": PlatformTier.PRO,
        "category": "branding",
    },
    {
        "key": "professional_reports",
        "name": "Professional Reports",
        "description": "Generate PDF reports for students",
        "required_tier": PlatformTier.PRO,
        "category": "reports",
    },
    {
        "key": "marketplace_sell",
        "name": "Sell on Marketplace",
        "description": "List and sell consultancies on the marketplace",
        "required_tier": PlatformTier.FREE,
        "category": "marketplace",
    },
]


# Import for type hints
from src.domains.users.models import User  # noqa: E402, F401
