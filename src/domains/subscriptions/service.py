"""Subscription service — tier checking and enforcement."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import OrganizationMembership, OrganizationType, UserRole
from src.domains.users.models import User

from .models import (
    DEFAULT_FEATURES,
    FeatureDefinition,
    PlatformSubscription,
    PlatformTier,
    SubscriptionSource,
    SubscriptionStatus,
)
from .schemas import FeatureCheckResponse, TierInfoResponse


class SubscriptionService:
    """Service for managing platform subscriptions and tier enforcement."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_subscription(self, user_id: uuid.UUID) -> PlatformSubscription | None:
        """Get active subscription for a user."""
        query = (
            select(PlatformSubscription)
            .where(
                PlatformSubscription.user_id == user_id,
                PlatformSubscription.status.in_([
                    SubscriptionStatus.ACTIVE,
                    SubscriptionStatus.TRIAL,
                ]),
            )
            .order_by(PlatformSubscription.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_user_tier(self, user_id: uuid.UUID) -> PlatformTier:
        """Get the current tier for a user."""
        sub = await self.get_user_subscription(user_id)
        if sub and sub.is_pro:
            return PlatformTier.PRO
        return PlatformTier.FREE

    async def is_pro(self, user_id: uuid.UUID) -> bool:
        """Check if user has Pro tier."""
        return await self.get_user_tier(user_id) == PlatformTier.PRO

    async def get_active_student_count(self, professional_id: uuid.UUID) -> int:
        """Count active students across all organizations owned by this professional."""
        # Find organizations where user is trainer/nutritionist
        org_query = select(OrganizationMembership.organization_id).where(
            OrganizationMembership.user_id == professional_id,
            OrganizationMembership.is_active == True,  # noqa: E712
            OrganizationMembership.role.in_([
                UserRole.TRAINER,
                UserRole.COACH,
                UserRole.NUTRITIONIST,
            ]),
        )
        org_result = await self.db.execute(org_query)
        org_ids = [row[0] for row in org_result.fetchall()]

        if not org_ids:
            return 0

        # Count active students in those organizations
        student_query = select(func.count(func.distinct(OrganizationMembership.user_id))).where(
            OrganizationMembership.organization_id.in_(org_ids),
            OrganizationMembership.role == UserRole.STUDENT,
            OrganizationMembership.is_active == True,  # noqa: E712
        )
        result = await self.db.execute(student_query)
        return result.scalar() or 0

    async def get_student_limit(self, user_id: uuid.UUID) -> int | None:
        """Get student limit for a professional. None = unlimited."""
        tier = await self.get_user_tier(user_id)
        if tier == PlatformTier.PRO:
            return None  # Unlimited

        # Check feature definition
        feature = await self._get_feature("max_active_students")
        if feature:
            return feature.free_tier_limit
        return 5  # Default fallback

    async def can_add_student(self, professional_id: uuid.UUID) -> tuple[bool, int, int | None]:
        """Check if a professional can add another student.

        Returns (can_add, current_count, limit).
        """
        current = await self.get_active_student_count(professional_id)
        limit = await self.get_student_limit(professional_id)

        if limit is None:
            return True, current, None

        return current < limit, current, limit

    async def check_feature_access(
        self, user_id: uuid.UUID, feature_key: str
    ) -> FeatureCheckResponse:
        """Check if a user has access to a specific feature."""
        tier = await self.get_user_tier(user_id)
        feature = await self._get_feature(feature_key)

        if not feature:
            # Feature not defined — allow by default
            return FeatureCheckResponse(
                feature_key=feature_key,
                has_access=True,
                current_tier=tier,
                required_tier=PlatformTier.FREE,
            )

        has_access = tier.value >= feature.required_tier.value if feature.required_tier == PlatformTier.FREE else tier == PlatformTier.PRO

        # Check limits for free tier
        current_usage = None
        limit = None
        if feature_key == "max_active_students":
            current_usage = await self.get_active_student_count(user_id)
            limit = feature.free_tier_limit if tier == PlatformTier.FREE else feature.pro_tier_limit
            if limit is not None:
                has_access = current_usage < limit

        return FeatureCheckResponse(
            feature_key=feature_key,
            has_access=has_access,
            current_tier=tier,
            required_tier=feature.required_tier,
            current_usage=current_usage,
            limit=limit,
            upgrade_required=not has_access,
        )

    async def get_tier_info(self, user_id: uuid.UUID) -> TierInfoResponse:
        """Get full tier info for a user."""
        sub = await self.get_user_subscription(user_id)
        tier = PlatformTier.PRO if (sub and sub.is_pro) else PlatformTier.FREE
        student_count = await self.get_active_student_count(user_id)
        student_limit = await self.get_student_limit(user_id)

        # Check all features
        features = await self._get_all_features()
        feature_checks = []
        for feature in features:
            check = await self.check_feature_access(user_id, feature.key)
            feature_checks.append(check)

        sub_response = None
        if sub:
            from .schemas import SubscriptionResponse
            sub_response = SubscriptionResponse(
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

        return TierInfoResponse(
            user_id=user_id,
            current_tier=tier,
            is_founder=sub.is_founder if sub else False,
            subscription=sub_response,
            features=feature_checks,
            active_students_count=student_count,
            max_students=student_limit,
        )

    async def upgrade_to_pro(
        self,
        user_id: uuid.UUID,
        source: SubscriptionSource = SubscriptionSource.DIRECT,
        amount_cents: int = 1990,
        expires_at: datetime | None = None,
        is_founder: bool = False,
        external_subscription_id: str | None = None,
        payment_provider: str | None = None,
    ) -> PlatformSubscription:
        """Upgrade a user to Pro tier."""
        # Deactivate existing subscription if any
        existing = await self.get_user_subscription(user_id)
        if existing:
            existing.status = SubscriptionStatus.CANCELLED
            existing.cancelled_at = datetime.now(timezone.utc)

        sub = PlatformSubscription(
            user_id=user_id,
            tier=PlatformTier.PRO,
            status=SubscriptionStatus.ACTIVE,
            source=source,
            amount_cents=amount_cents,
            started_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            is_founder=is_founder,
            external_subscription_id=external_subscription_id,
            payment_provider=payment_provider,
        )

        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def grant_trial(
        self, user_id: uuid.UUID, days: int = 7, source: SubscriptionSource = SubscriptionSource.REFERRAL
    ) -> PlatformSubscription:
        """Grant a Pro trial to a user."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        trial_end = now + timedelta(days=days)

        sub = PlatformSubscription(
            user_id=user_id,
            tier=PlatformTier.PRO,
            status=SubscriptionStatus.TRIAL,
            source=source,
            amount_cents=0,
            started_at=now,
            expires_at=trial_end,
            trial_ends_at=trial_end,
        )

        self.db.add(sub)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def cancel_subscription(self, user_id: uuid.UUID) -> PlatformSubscription | None:
        """Cancel a user's subscription."""
        sub = await self.get_user_subscription(user_id)
        if not sub:
            return None

        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def _get_feature(self, key: str) -> FeatureDefinition | None:
        """Get a feature definition by key."""
        query = select(FeatureDefinition).where(
            FeatureDefinition.key == key,
            FeatureDefinition.is_enabled == True,  # noqa: E712
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _get_all_features(self) -> list[FeatureDefinition]:
        """Get all enabled feature definitions."""
        query = select(FeatureDefinition).where(
            FeatureDefinition.is_enabled == True  # noqa: E712
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def seed_features(self) -> int:
        """Seed default feature definitions."""
        count = 0
        for feature_data in DEFAULT_FEATURES:
            existing = await self._get_feature(feature_data["key"])
            if not existing:
                feature = FeatureDefinition(**feature_data)
                self.db.add(feature)
                count += 1

        if count > 0:
            await self.db.commit()
        return count
