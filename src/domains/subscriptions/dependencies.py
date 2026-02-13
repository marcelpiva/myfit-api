"""Subscription tier enforcement dependencies for FastAPI.

Use these as route dependencies to gate features by tier.

Example usage:
    @router.post("/some-pro-feature", dependencies=[Depends(require_pro)])
    async def pro_feature(...):
        ...

    @router.post("/invite-student", dependencies=[Depends(require_can_add_student)])
    async def invite_student(...):
        ...
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser

from .models import PlatformTier
from .service import SubscriptionService


async def require_pro(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Require the current user to have Pro tier."""
    service = SubscriptionService(db)
    if not await service.is_pro(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "pro_required",
                "message": "This feature requires a Pro subscription",
                "current_tier": PlatformTier.FREE.value,
                "required_tier": PlatformTier.PRO.value,
            },
        )


async def require_can_add_student(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Require the professional to be under their student limit."""
    service = SubscriptionService(db)
    can_add, current_count, limit = await service.can_add_student(current_user.id)

    if not can_add:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "student_limit_reached",
                "message": f"You have reached the maximum of {limit} students on the Free plan. Upgrade to Pro for unlimited students.",
                "current_count": current_count,
                "limit": limit,
                "current_tier": PlatformTier.FREE.value,
                "upgrade_required": True,
            },
        )


async def require_feature(feature_key: str):
    """Create a dependency that requires a specific feature.

    Usage:
        @router.post("/ai-workout", dependencies=[Depends(require_feature("ai_workout_generation"))])
    """
    async def _check(
        current_user: CurrentUser,
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> None:
        service = SubscriptionService(db)
        check = await service.check_feature_access(current_user.id, feature_key)

        if not check.has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "feature_locked",
                    "message": f"This feature requires {check.required_tier.value} tier",
                    "feature_key": feature_key,
                    "current_tier": check.current_tier.value,
                    "required_tier": check.required_tier.value,
                    "current_usage": check.current_usage,
                    "limit": check.limit,
                    "upgrade_required": True,
                },
            )

    return _check


# Pre-built dependencies for common feature checks
RequirePro = Depends(require_pro)
RequireCanAddStudent = Depends(require_can_add_student)
