"""Tests for MarketplaceService - templates, purchases, earnings, and payouts."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.marketplace.models import (
    CreatorEarnings,
    CreatorPayout,
    MarketplaceTemplate,
    PaymentProvider,
    PayoutMethod,
    PayoutStatus,
    PurchaseStatus,
    TemplateCategory,
    TemplateDifficulty,
    TemplatePurchase,
    TemplateReview,
    TemplateType,
)
from src.domains.marketplace.service import PLATFORM_FEE_PERCENT, MarketplaceService


class TestPlatformFeeCalculation:
    """Tests for 20% platform fee calculation."""

    async def test_platform_fee_is_20_percent(self, db_session: AsyncSession):
        """Platform fee should be 20%."""
        assert PLATFORM_FEE_PERCENT == 20

    async def test_creator_gets_80_percent_of_sale(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Creator should receive 80% of sale price."""
        service = MarketplaceService(db_session)

        # Create a template
        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Test Template",
            price_cents=10000,  # R$100.00
        )

        # Create purchase
        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        assert purchase.price_cents == 10000
        assert purchase.creator_earnings_cents == 8000  # 80%
        assert purchase.platform_fee_cents == 2000  # 20%

    async def test_platform_fee_rounds_down_for_creator(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Fee calculation should handle odd amounts correctly."""
        service = MarketplaceService(db_session)

        # Create template with price that doesn't divide evenly
        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Odd Price Template",
            price_cents=9999,  # R$99.99
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        # 80% of 9999 = 7999.2, should round down to 7999
        assert purchase.creator_earnings_cents == 7999
        # Platform gets the rest
        assert purchase.platform_fee_cents == 2000
        # Total should equal original price
        assert (
            purchase.creator_earnings_cents + purchase.platform_fee_cents
            == purchase.price_cents
        )

    async def test_free_template_no_fees(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Free templates should have zero earnings and fees."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Free Template",
            price_cents=0,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        assert purchase.price_cents == 0
        assert purchase.creator_earnings_cents == 0
        assert purchase.platform_fee_cents == 0

    @pytest.mark.parametrize(
        "price_cents,expected_creator,expected_platform",
        [
            (1000, 800, 200),  # R$10.00
            (5000, 4000, 1000),  # R$50.00
            (10000, 8000, 2000),  # R$100.00
            (15000, 12000, 3000),  # R$150.00
            (25000, 20000, 5000),  # R$250.00
            (100, 80, 20),  # R$1.00
            (1, 0, 1),  # R$0.01 - edge case
        ],
    )
    async def test_fee_calculation_parametrized(
        self,
        db_session: AsyncSession,
        sample_user: dict,
        price_cents: int,
        expected_creator: int,
        expected_platform: int,
    ):
        """Parametrized test for various price points."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title=f"Template {price_cents}",
            price_cents=price_cents,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        assert purchase.creator_earnings_cents == expected_creator
        assert purchase.platform_fee_cents == expected_platform


class TestCreateTemplate:
    """Tests for template creation."""

    async def test_create_workout_template(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a workout template."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="My Workout Template",
            price_cents=5000,
            short_description="A great workout",
            category=TemplateCategory.STRENGTH,
            difficulty=TemplateDifficulty.ADVANCED,
        )

        assert template.title == "My Workout Template"
        assert template.template_type == TemplateType.WORKOUT
        assert template.price_cents == 5000
        assert template.category == TemplateCategory.STRENGTH
        assert template.difficulty == TemplateDifficulty.ADVANCED
        assert template.is_active is True

    async def test_create_diet_plan_template(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a diet plan template."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.DIET_PLAN,
            title="My Diet Plan",
            price_cents=3000,
        )

        assert template.template_type == TemplateType.DIET_PLAN

    async def test_create_template_auto_approved(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Templates should be auto-approved for now."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Auto Approved",
            price_cents=1000,
        )

        assert template.approved_at is not None

    async def test_create_template_with_tags(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create template with tags."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Tagged Template",
            price_cents=1000,
            tags=["strength", "beginner", "home"],
        )

        assert template.tags == ["strength", "beginner", "home"]


class TestPurchaseFlow:
    """Tests for purchase workflow."""

    async def test_create_purchase_pending_status(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """New purchase should have PENDING status."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Template",
            price_cents=5000,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        assert purchase.status == PurchaseStatus.PENDING

    async def test_create_purchase_template_not_found(
        self, db_session: AsyncSession
    ):
        """Should raise error for nonexistent template."""
        service = MarketplaceService(db_session)

        with pytest.raises(ValueError, match="Template not found"):
            await service.create_purchase(
                buyer_id=uuid.uuid4(),
                template_id=uuid.uuid4(),
                payment_provider=PaymentProvider.PIX,
            )

    async def test_complete_purchase_updates_status(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Completing purchase should update status to COMPLETED."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Complete Me",
            price_cents=5000,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        # Mock workout service
        with patch.object(service, "_workout_service") as mock_workout:
            mock_workout.get_workout_by_id = AsyncMock(return_value=None)

            completed = await service.complete_purchase(
                purchase=purchase,
                payment_provider_id="pix_123",
            )

        assert completed.status == PurchaseStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.payment_provider_id == "pix_123"

    async def test_complete_purchase_increments_count(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Completing purchase should increment template purchase_count."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Popular Template",
            price_cents=5000,
        )

        assert template.purchase_count == 0

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        with patch.object(service, "_workout_service") as mock_workout:
            mock_workout.get_workout_by_id = AsyncMock(return_value=None)
            await service.complete_purchase(purchase=purchase)

        # Refresh template
        await db_session.refresh(template)
        assert template.purchase_count == 1

    async def test_fail_purchase_updates_status(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Failing purchase should update status to FAILED."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Fail Me",
            price_cents=5000,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        failed = await service.fail_purchase(purchase=purchase)

        assert failed.status == PurchaseStatus.FAILED

    async def test_check_user_purchased(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should correctly check if user purchased a template."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Check Purchase",
            price_cents=5000,
        )

        buyer_id = uuid.uuid4()

        # Not purchased yet
        has_purchased = await service.check_user_purchased(buyer_id, template.id)
        assert has_purchased is False

        # Create and complete purchase
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        with patch.object(service, "_workout_service") as mock_workout:
            mock_workout.get_workout_by_id = AsyncMock(return_value=None)
            await service.complete_purchase(purchase=purchase)

        # Now purchased
        has_purchased = await service.check_user_purchased(buyer_id, template.id)
        assert has_purchased is True


class TestCreatorEarnings:
    """Tests for creator earnings tracking."""

    async def test_add_to_creator_earnings_creates_record(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create earnings record if not exists."""
        service = MarketplaceService(db_session)

        earnings = await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=5000,
        )

        assert earnings.creator_id == sample_user["id"]
        assert earnings.balance_cents == 5000
        assert earnings.total_earned_cents == 5000

    async def test_add_to_creator_earnings_accumulates(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Earnings should accumulate."""
        service = MarketplaceService(db_session)

        await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=5000,
        )

        earnings = await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=3000,
        )

        assert earnings.balance_cents == 8000
        assert earnings.total_earned_cents == 8000

    async def test_complete_purchase_adds_earnings(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Completing purchase should add to creator earnings."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Earnings Test",
            price_cents=10000,  # R$100.00 -> creator gets R$80.00
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        with patch.object(service, "_workout_service") as mock_workout:
            mock_workout.get_workout_by_id = AsyncMock(return_value=None)
            await service.complete_purchase(purchase=purchase)

        earnings = await service.get_creator_earnings(creator_id=sample_user["id"])

        assert earnings is not None
        assert earnings.balance_cents == 8000
        assert earnings.total_earned_cents == 8000


class TestPayoutRequests:
    """Tests for payout requests."""

    async def test_request_payout_success(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create payout request."""
        service = MarketplaceService(db_session)

        # Add earnings first
        await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=10000,
        )

        payout = await service.request_payout(
            creator_id=sample_user["id"],
            amount_cents=5000,
            payout_method=PayoutMethod.PIX,
            payout_details={"pix_key": "email@example.com"},
        )

        assert payout.amount_cents == 5000
        assert payout.status == PayoutStatus.PENDING
        assert payout.payout_method == PayoutMethod.PIX

    async def test_request_payout_deducts_from_balance(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Payout should deduct from available balance."""
        service = MarketplaceService(db_session)

        await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=10000,
        )

        await service.request_payout(
            creator_id=sample_user["id"],
            amount_cents=7000,
            payout_method=PayoutMethod.PIX,
        )

        earnings = await service.get_creator_earnings(creator_id=sample_user["id"])
        assert earnings.balance_cents == 3000

    async def test_request_payout_insufficient_balance(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should reject payout if balance is insufficient."""
        service = MarketplaceService(db_session)

        await service._add_to_creator_earnings(
            creator_id=sample_user["id"],
            organization_id=None,
            amount_cents=5000,
        )

        with pytest.raises(ValueError, match="Insufficient balance"):
            await service.request_payout(
                creator_id=sample_user["id"],
                amount_cents=10000,
                payout_method=PayoutMethod.PIX,
            )

    async def test_request_payout_no_earnings(self, db_session: AsyncSession):
        """Should reject payout if no earnings exist."""
        service = MarketplaceService(db_session)

        with pytest.raises(ValueError, match="No earnings found"):
            await service.request_payout(
                creator_id=uuid.uuid4(),
                amount_cents=1000,
                payout_method=PayoutMethod.PIX,
            )


class TestReviews:
    """Tests for template reviews."""

    async def test_create_review(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a review."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Review This",
            price_cents=5000,
        )

        buyer_id = uuid.uuid4()
        purchase = await service.create_purchase(
            buyer_id=buyer_id,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        review = await service.create_review(
            purchase_id=purchase.id,
            reviewer_id=buyer_id,
            template_id=template.id,
            rating=5,
            title="Great template!",
            comment="Really helped me get in shape.",
        )

        assert review.rating == 5
        assert review.title == "Great template!"
        assert review.is_verified_purchase is True

    async def test_create_review_updates_template_rating(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Creating review should update template rating average."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Rate This",
            price_cents=5000,
        )

        # First review: 5 stars
        buyer1 = uuid.uuid4()
        purchase1 = await service.create_purchase(
            buyer_id=buyer1,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        await service.create_review(
            purchase_id=purchase1.id,
            reviewer_id=buyer1,
            template_id=template.id,
            rating=5,
        )

        await db_session.refresh(template)
        assert template.rating_count == 1
        assert template.rating_average == Decimal("5")

        # Second review: 3 stars
        buyer2 = uuid.uuid4()
        purchase2 = await service.create_purchase(
            buyer_id=buyer2,
            template_id=template.id,
            payment_provider=PaymentProvider.PIX,
        )

        await service.create_review(
            purchase_id=purchase2.id,
            reviewer_id=buyer2,
            template_id=template.id,
            rating=3,
        )

        await db_session.refresh(template)
        assert template.rating_count == 2
        assert template.rating_average == Decimal("4")  # (5+3)/2 = 4

    async def test_get_review_distribution(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return rating distribution."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Distribution Test",
            price_cents=5000,
        )

        # Create reviews with different ratings
        for rating in [5, 5, 4, 4, 4, 3, 1]:
            buyer = uuid.uuid4()
            purchase = await service.create_purchase(
                buyer_id=buyer,
                template_id=template.id,
                payment_provider=PaymentProvider.PIX,
            )
            await service.create_review(
                purchase_id=purchase.id,
                reviewer_id=buyer,
                template_id=template.id,
                rating=rating,
            )

        distribution = await service.get_review_distribution(template.id)

        assert distribution[5] == 2
        assert distribution[4] == 3
        assert distribution[3] == 1
        assert distribution[2] == 0
        assert distribution[1] == 1


class TestTemplateFiltering:
    """Tests for template listing and filtering."""

    async def test_list_templates_by_type(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter templates by type."""
        service = MarketplaceService(db_session)

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Workout 1",
            price_cents=1000,
        )

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.DIET_PLAN,
            title="Diet 1",
            price_cents=1000,
        )

        workouts = await service.list_templates(template_type=TemplateType.WORKOUT)

        assert len(workouts) == 1
        assert workouts[0].title == "Workout 1"

    async def test_list_templates_free_only(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter free templates only."""
        service = MarketplaceService(db_session)

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Free",
            price_cents=0,
        )

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Paid",
            price_cents=5000,
        )

        free_templates = await service.list_templates(free_only=True)

        assert len(free_templates) == 1
        assert free_templates[0].title == "Free"

    async def test_list_templates_price_range(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter by price range."""
        service = MarketplaceService(db_session)

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Cheap",
            price_cents=1000,
        )

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Mid",
            price_cents=5000,
        )

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Expensive",
            price_cents=10000,
        )

        mid_range = await service.list_templates(min_price=2000, max_price=7000)

        assert len(mid_range) == 1
        assert mid_range[0].title == "Mid"

    async def test_list_featured_templates(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return only featured templates."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Featured",
            price_cents=1000,
        )

        # Make it featured
        template.is_featured = True
        await db_session.commit()

        await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Not Featured",
            price_cents=1000,
        )

        featured = await service.list_featured_templates()

        assert len(featured) == 1
        assert featured[0].title == "Featured"


class TestDeactivateTemplate:
    """Tests for template deactivation."""

    async def test_deactivate_template(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should soft delete template."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Deactivate Me",
            price_cents=1000,
        )

        assert template.is_active is True

        deactivated = await service.deactivate_template(template)

        assert deactivated.is_active is False

    async def test_deactivated_not_in_list(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Deactivated templates should not appear in listings."""
        service = MarketplaceService(db_session)

        template = await service.create_template(
            creator_id=sample_user["id"],
            template_type=TemplateType.WORKOUT,
            title="Hidden",
            price_cents=1000,
        )

        await service.deactivate_template(template)

        templates = await service.list_templates()

        assert len(templates) == 0
