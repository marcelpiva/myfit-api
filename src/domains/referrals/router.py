"""Referral system router."""
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser

from .models import (
    Referral,
    ReferralCode,
    ReferralReward,
    RewardStatus,
    RewardType,
    generate_referral_code,
)
from .schemas import (
    RedeemReferralRequest,
    ReferralCodeResponse,
    ReferralDashboardResponse,
    ReferralListResponse,
    ReferralResponse,
    ReferralRewardResponse,
)

router = APIRouter(tags=["referrals"])


# --- Helper functions ---


def _code_to_response(code: ReferralCode) -> ReferralCodeResponse:
    return ReferralCodeResponse(
        id=code.id,
        user_id=code.user_id,
        code=code.code,
        total_referrals=code.total_referrals,
        successful_referrals=code.successful_referrals,
        is_active=code.is_active,
        created_at=code.created_at,
    )


def _referral_to_response(ref: Referral) -> ReferralResponse:
    return ReferralResponse(
        id=ref.id,
        referrer_id=ref.referrer_id,
        referrer_name=ref.referrer.name if ref.referrer else "Unknown",
        referred_id=ref.referred_id,
        referred_name=ref.referred.name if ref.referred else "Unknown",
        is_qualified=ref.is_qualified,
        qualified_at=ref.qualified_at,
        referrer_rewarded=ref.referrer_rewarded,
        referred_rewarded=ref.referred_rewarded,
        created_at=ref.created_at,
    )


def _reward_to_response(reward: ReferralReward) -> ReferralRewardResponse:
    return ReferralRewardResponse(
        id=reward.id,
        referral_id=reward.referral_id,
        user_id=reward.user_id,
        reward_type=reward.reward_type,
        reward_days=reward.reward_days,
        reward_value_cents=reward.reward_value_cents,
        status=reward.status,
        activated_at=reward.activated_at,
        expires_at=reward.expires_at,
        created_at=reward.created_at,
    )


# --- Endpoints ---


@router.get("/code", response_model=ReferralCodeResponse)
async def get_my_referral_code(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReferralCodeResponse:
    """Get or create the current user's referral code."""
    query = select(ReferralCode).where(
        ReferralCode.user_id == current_user.id,
        ReferralCode.is_active == True,  # noqa: E712
    )
    result = await db.execute(query)
    code = result.scalar_one_or_none()

    if not code:
        # Auto-create a referral code
        code = ReferralCode(
            user_id=current_user.id,
            code=generate_referral_code(),
        )
        db.add(code)
        await db.commit()
        await db.refresh(code)

    return _code_to_response(code)


@router.post("/redeem", response_model=ReferralResponse, status_code=status.HTTP_201_CREATED)
async def redeem_referral_code(
    request: RedeemReferralRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReferralResponse:
    """Redeem a referral code (apply someone else's code to your account)."""
    # Find the referral code
    code_query = select(ReferralCode).where(
        ReferralCode.code == request.code.upper(),
        ReferralCode.is_active == True,  # noqa: E712
    )
    code_result = await db.execute(code_query)
    referral_code = code_result.scalar_one_or_none()

    if not referral_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid referral code",
        )

    # Can't refer yourself
    if referral_code.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot use your own referral code",
        )

    # Check if already referred by anyone
    existing_query = select(Referral).where(
        Referral.referred_id == current_user.id,
    )
    existing_result = await db.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already used a referral code",
        )

    # Create referral
    referral = Referral(
        referral_code_id=referral_code.id,
        referrer_id=referral_code.user_id,
        referred_id=current_user.id,
    )

    db.add(referral)

    # Update referral code stats
    referral_code.total_referrals += 1

    await db.commit()
    await db.refresh(referral)

    # Grant immediate rewards to both parties (1 week Pro trial)
    now = datetime.now(timezone.utc)
    reward_expiry = now + timedelta(days=7)

    # Reward for the referred user
    referred_reward = ReferralReward(
        referral_id=referral.id,
        user_id=current_user.id,
        reward_type=RewardType.PRO_TRIAL,
        reward_days=7,
        status=RewardStatus.ACTIVE,
        activated_at=now,
        expires_at=reward_expiry,
    )
    db.add(referred_reward)

    # Reward for the referrer
    referrer_reward = ReferralReward(
        referral_id=referral.id,
        user_id=referral_code.user_id,
        reward_type=RewardType.PRO_TRIAL,
        reward_days=7,
        status=RewardStatus.ACTIVE,
        activated_at=now,
        expires_at=reward_expiry,
    )
    db.add(referrer_reward)

    # Mark rewards as granted
    referral.referred_rewarded = True
    referral.referrer_rewarded = True

    # Update referral code stats
    referral_code.successful_referrals += 1

    # Grant Pro trials via subscription service
    from src.domains.subscriptions.service import SubscriptionService
    sub_service = SubscriptionService(db)
    await sub_service.grant_trial(current_user.id, days=7)
    await sub_service.grant_trial(referral_code.user_id, days=7)

    await db.commit()

    # Reload with relationships
    ref_query = select(Referral).where(Referral.id == referral.id)
    ref_result = await db.execute(ref_query)
    referral = ref_result.scalar_one()

    return _referral_to_response(referral)


@router.get("/dashboard", response_model=ReferralDashboardResponse)
async def get_referral_dashboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReferralDashboardResponse:
    """Get the referral dashboard with stats and recent activity."""
    # Get or create referral code
    code_query = select(ReferralCode).where(
        ReferralCode.user_id == current_user.id,
        ReferralCode.is_active == True,  # noqa: E712
    )
    code_result = await db.execute(code_query)
    code = code_result.scalar_one_or_none()

    if not code:
        code = ReferralCode(
            user_id=current_user.id,
            code=generate_referral_code(),
        )
        db.add(code)
        await db.commit()
        await db.refresh(code)

    # Get referrals
    referrals_query = (
        select(Referral)
        .where(Referral.referrer_id == current_user.id)
        .order_by(Referral.created_at.desc())
        .limit(10)
    )
    referrals_result = await db.execute(referrals_query)
    referrals = list(referrals_result.scalars().all())

    # Count totals
    total = code.total_referrals
    successful = code.successful_referrals
    pending = total - successful

    # Get active rewards
    rewards_query = select(ReferralReward).where(
        ReferralReward.user_id == current_user.id,
        ReferralReward.status == RewardStatus.ACTIVE,
    )
    rewards_result = await db.execute(rewards_query)
    active_rewards = list(rewards_result.scalars().all())

    return ReferralDashboardResponse(
        referral_code=_code_to_response(code),
        total_referrals=total,
        successful_referrals=successful,
        pending_referrals=pending,
        active_rewards=[_reward_to_response(r) for r in active_rewards],
        recent_referrals=[_referral_to_response(r) for r in referrals],
    )


@router.get("/rewards", response_model=list[ReferralRewardResponse])
async def list_my_rewards(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: Annotated[bool, Query()] = False,
) -> list[ReferralRewardResponse]:
    """List current user's referral rewards."""
    base_filter = [ReferralReward.user_id == current_user.id]

    if active_only:
        base_filter.append(ReferralReward.status == RewardStatus.ACTIVE)

    query = (
        select(ReferralReward)
        .where(and_(*base_filter))
        .order_by(ReferralReward.created_at.desc())
    )

    result = await db.execute(query)
    rewards = list(result.scalars().all())

    return [_reward_to_response(r) for r in rewards]
