"""Subscription router for platform tier management."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser

from .models import PlatformTier, SubscriptionSource
from .schemas import (
    FeatureCheckResponse,
    FeatureDefinitionResponse,
    SubscriptionCheckoutResponse,
    SubscriptionResponse,
    SubscriptionUpgradeRequest,
    TierInfoResponse,
)
from .service import SubscriptionService

router = APIRouter(tags=["subscriptions"])


@router.get("/me", response_model=TierInfoResponse)
async def get_my_tier(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TierInfoResponse:
    """Get current user's tier info, features, and limits."""
    service = SubscriptionService(db)
    return await service.get_tier_info(current_user.id)


@router.get("/features", response_model=list[FeatureDefinitionResponse])
async def list_features(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FeatureDefinitionResponse]:
    """List all feature definitions with tier requirements."""
    service = SubscriptionService(db)
    features = await service._get_all_features()
    return [
        FeatureDefinitionResponse(
            key=f.key,
            name=f.name,
            description=f.description,
            required_tier=f.required_tier,
            free_tier_limit=f.free_tier_limit,
            pro_tier_limit=f.pro_tier_limit,
            category=f.category,
        )
        for f in features
    ]


@router.get("/features/{feature_key}", response_model=FeatureCheckResponse)
async def check_feature(
    feature_key: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FeatureCheckResponse:
    """Check if the current user has access to a specific feature."""
    service = SubscriptionService(db)
    return await service.check_feature_access(current_user.id, feature_key)


@router.post("/upgrade", response_model=SubscriptionCheckoutResponse)
async def upgrade_to_pro(
    request: SubscriptionUpgradeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionCheckoutResponse:
    """Upgrade current user to Pro tier via PIX checkout."""
    service = SubscriptionService(db)

    # Check if already Pro
    if await service.is_pro(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already on Pro tier",
        )

    use_pix = request.payment_provider == "pix"

    sub = await service.upgrade_to_pro(
        user_id=current_user.id,
        source=request.source,
        external_subscription_id=request.external_payment_id,
        payment_provider=request.payment_provider,
        pending=use_pix,
    )

    pix_copy_paste = None
    pix_qr_code = None
    if use_pix:
        pix_copy_paste = (
            f"00020126580014br.gov.bcb.pix0136{sub.id}"
            f"5204000053039865802BR5913MyFit Pro6009SAO PAULO"
            f"62070503***6304"
        )
        pix_qr_code = pix_copy_paste

    return SubscriptionCheckoutResponse(
        subscription_id=sub.id,
        amount_cents=sub.amount_cents,
        price_display="R$ 19,90/mês",
        payment_provider=request.payment_provider or "direct",
        status=sub.status.value,
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
    )


@router.get("/{subscription_id}/status")
async def get_subscription_status(
    subscription_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get subscription payment status (for polling)."""
    service = SubscriptionService(db)
    sub = await service.get_subscription_by_id(subscription_id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )

    if sub.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subscription",
        )

    return {
        "status": sub.status.value,
        "subscription_id": str(sub.id),
    }


@router.post("/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionResponse:
    """Cancel current user's Pro subscription."""
    service = SubscriptionService(db)
    sub = await service.cancel_subscription(current_user.id)

    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active subscription found",
        )

    return SubscriptionResponse(
        id=sub.id,
        user_id=sub.user_id,
        tier=sub.tier,
        status=sub.status,
        source=sub.source,
        amount_cents=sub.amount_cents,
        currency=sub.currency,
        started_at=sub.started_at,
        expires_at=sub.expires_at,
        trial_ends_at=sub.trial_ends_at,
        is_founder=sub.is_founder,
        is_active=sub.is_active,
        is_pro=sub.is_pro,
        created_at=sub.created_at,
    )


@router.get("/can-add-student")
async def can_add_student(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Check if the current professional can add another student."""
    service = SubscriptionService(db)
    can_add, current_count, limit = await service.can_add_student(current_user.id)

    return {
        "can_add": can_add,
        "current_count": current_count,
        "limit": limit,
        "upgrade_required": not can_add,
    }
