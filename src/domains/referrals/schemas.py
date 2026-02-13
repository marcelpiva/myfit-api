"""Referral schemas for API validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import RewardStatus, RewardType


class ReferralCodeResponse(BaseModel):
    """Schema for referral code response."""

    id: UUID
    user_id: UUID
    code: str
    total_referrals: int
    successful_referrals: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralResponse(BaseModel):
    """Schema for a single referral."""

    id: UUID
    referrer_id: UUID
    referrer_name: str
    referred_id: UUID
    referred_name: str
    is_qualified: bool
    qualified_at: datetime | None
    referrer_rewarded: bool
    referred_rewarded: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReferralListResponse(BaseModel):
    """Schema for referral list."""

    referrals: list[ReferralResponse]
    total: int


class ReferralRewardResponse(BaseModel):
    """Schema for referral reward."""

    id: UUID
    referral_id: UUID
    user_id: UUID
    reward_type: RewardType
    reward_days: int | None
    reward_value_cents: int | None
    status: RewardStatus
    activated_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RedeemReferralRequest(BaseModel):
    """Schema for redeeming a referral code."""

    code: str = Field(..., min_length=3, max_length=20)


class ReferralDashboardResponse(BaseModel):
    """Schema for referral dashboard."""

    referral_code: ReferralCodeResponse
    total_referrals: int
    successful_referrals: int
    pending_referrals: int
    active_rewards: list[ReferralRewardResponse]
    recent_referrals: list[ReferralResponse]
