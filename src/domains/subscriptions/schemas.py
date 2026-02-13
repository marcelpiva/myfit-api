"""Subscription schemas for API validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import PlatformTier, SubscriptionSource, SubscriptionStatus


class SubscriptionResponse(BaseModel):
    """Schema for subscription response."""

    id: UUID
    user_id: UUID
    tier: PlatformTier
    status: SubscriptionStatus
    source: SubscriptionSource
    amount_cents: int
    currency: str
    started_at: datetime
    expires_at: datetime | None
    trial_ends_at: datetime | None
    is_founder: bool
    is_active: bool
    is_pro: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionUpgradeRequest(BaseModel):
    """Schema for upgrading to Pro."""

    payment_provider: str | None = None  # "stripe", "asaas", etc.
    external_payment_id: str | None = None
    source: SubscriptionSource = SubscriptionSource.DIRECT


class FeatureCheckResponse(BaseModel):
    """Response for checking feature access."""

    feature_key: str
    has_access: bool
    current_tier: PlatformTier
    required_tier: PlatformTier
    current_usage: int | None = None
    limit: int | None = None  # None = unlimited
    upgrade_required: bool = False


class TierInfoResponse(BaseModel):
    """Full tier info for a user."""

    user_id: UUID
    current_tier: PlatformTier
    is_founder: bool
    subscription: SubscriptionResponse | None
    features: list[FeatureCheckResponse]
    active_students_count: int
    max_students: int | None  # None = unlimited


class FeatureDefinitionResponse(BaseModel):
    """Schema for feature definition."""

    key: str
    name: str
    description: str | None
    required_tier: PlatformTier
    free_tier_limit: int | None
    pro_tier_limit: int | None
    category: str | None

    model_config = ConfigDict(from_attributes=True)
