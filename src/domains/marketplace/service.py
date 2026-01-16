"""Marketplace service with database operations."""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.marketplace.models import (
    CreatorEarnings,
    CreatorPayout,
    MarketplaceTemplate,
    OrganizationTemplateAccess,
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
from src.domains.nutrition.service import NutritionService
from src.domains.workouts.service import WorkoutService

# Platform fee percentage (20%)
PLATFORM_FEE_PERCENT = 20


class MarketplaceService:
    """Service for handling marketplace operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._workout_service = WorkoutService(db)
        self._nutrition_service = NutritionService(db)

    # ==================== Template Operations ====================

    async def get_template_by_id(
        self,
        template_id: uuid.UUID,
    ) -> MarketplaceTemplate | None:
        """Get a template by ID."""
        result = await self.db.execute(
            select(MarketplaceTemplate)
            .where(MarketplaceTemplate.id == template_id)
            .options(
                selectinload(MarketplaceTemplate.creator),
                selectinload(MarketplaceTemplate.workout),
                selectinload(MarketplaceTemplate.diet_plan),
            )
        )
        return result.scalar_one_or_none()

    async def list_templates(
        self,
        template_type: TemplateType | None = None,
        category: TemplateCategory | None = None,
        difficulty: TemplateDifficulty | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        free_only: bool = False,
        featured_only: bool = False,
        search: str | None = None,
        sort_by: str = "created_at",
        sort_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MarketplaceTemplate]:
        """List templates with filters."""
        query = select(MarketplaceTemplate).where(
            MarketplaceTemplate.is_active == True,
            MarketplaceTemplate.approved_at.isnot(None),
        ).options(
            selectinload(MarketplaceTemplate.creator),
        )

        if template_type:
            query = query.where(MarketplaceTemplate.template_type == template_type)

        if category:
            query = query.where(MarketplaceTemplate.category == category)

        if difficulty:
            query = query.where(MarketplaceTemplate.difficulty == difficulty)

        if free_only:
            query = query.where(MarketplaceTemplate.price_cents == 0)
        else:
            if min_price is not None:
                query = query.where(MarketplaceTemplate.price_cents >= min_price)
            if max_price is not None:
                query = query.where(MarketplaceTemplate.price_cents <= max_price)

        if featured_only:
            query = query.where(MarketplaceTemplate.is_featured == True)

        if search:
            query = query.where(
                or_(
                    MarketplaceTemplate.title.ilike(f"%{search}%"),
                    MarketplaceTemplate.short_description.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(MarketplaceTemplate, sort_by, MarketplaceTemplate.created_at)
        if sort_desc:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_featured_templates(
        self,
        limit: int = 10,
    ) -> list[MarketplaceTemplate]:
        """Get featured templates."""
        return await self.list_templates(
            featured_only=True,
            limit=limit,
        )

    async def create_template(
        self,
        creator_id: uuid.UUID,
        template_type: TemplateType,
        title: str,
        price_cents: int = 0,
        workout_id: uuid.UUID | None = None,
        diet_plan_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        short_description: str | None = None,
        full_description: str | None = None,
        cover_image_url: str | None = None,
        preview_images: list[str] | None = None,
        category: TemplateCategory | None = None,
        difficulty: TemplateDifficulty = TemplateDifficulty.INTERMEDIATE,
        tags: list[str] | None = None,
        currency: str = "BRL",
    ) -> MarketplaceTemplate:
        """Create a new template listing."""
        template = MarketplaceTemplate(
            template_type=template_type,
            workout_id=workout_id,
            diet_plan_id=diet_plan_id,
            creator_id=creator_id,
            organization_id=organization_id,
            price_cents=price_cents,
            currency=currency,
            title=title,
            short_description=short_description,
            full_description=full_description,
            cover_image_url=cover_image_url,
            preview_images=preview_images,
            category=category,
            difficulty=difficulty,
            tags=tags,
            approved_at=datetime.now(timezone.utc),  # Auto-approve for now
        )
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_template(
        self,
        template: MarketplaceTemplate,
        **kwargs,
    ) -> MarketplaceTemplate:
        """Update a template."""
        for key, value in kwargs.items():
            if value is not None and hasattr(template, key):
                setattr(template, key, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def deactivate_template(
        self,
        template: MarketplaceTemplate,
    ) -> MarketplaceTemplate:
        """Deactivate a template (soft delete)."""
        template.is_active = False
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def list_creator_templates(
        self,
        creator_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> list[MarketplaceTemplate]:
        """List templates created by a user."""
        query = select(MarketplaceTemplate).where(
            MarketplaceTemplate.creator_id == creator_id
        ).options(
            selectinload(MarketplaceTemplate.creator),
        )

        if not include_inactive:
            query = query.where(MarketplaceTemplate.is_active == True)

        query = query.order_by(MarketplaceTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Purchase Operations ====================

    async def get_purchase_by_id(
        self,
        purchase_id: uuid.UUID,
    ) -> TemplatePurchase | None:
        """Get a purchase by ID."""
        result = await self.db.execute(
            select(TemplatePurchase)
            .where(TemplatePurchase.id == purchase_id)
            .options(
                selectinload(TemplatePurchase.template),
                selectinload(TemplatePurchase.buyer),
            )
        )
        return result.scalar_one_or_none()

    async def check_user_purchased(
        self,
        user_id: uuid.UUID,
        template_id: uuid.UUID,
    ) -> bool:
        """Check if user has purchased a template."""
        result = await self.db.execute(
            select(TemplatePurchase).where(
                TemplatePurchase.buyer_id == user_id,
                TemplatePurchase.marketplace_template_id == template_id,
                TemplatePurchase.status == PurchaseStatus.COMPLETED,
            )
        )
        return result.scalar_one_or_none() is not None

    async def create_purchase(
        self,
        buyer_id: uuid.UUID,
        template_id: uuid.UUID,
        payment_provider: PaymentProvider,
    ) -> TemplatePurchase:
        """Create a purchase record."""
        template = await self.get_template_by_id(template_id)
        if not template:
            raise ValueError("Template not found")

        # Calculate revenue split
        creator_earnings = int(template.price_cents * (100 - PLATFORM_FEE_PERCENT) / 100)
        platform_fee = template.price_cents - creator_earnings

        purchase = TemplatePurchase(
            marketplace_template_id=template_id,
            buyer_id=buyer_id,
            price_cents=template.price_cents,
            currency=template.currency,
            payment_provider=payment_provider,
            status=PurchaseStatus.PENDING,
            creator_earnings_cents=creator_earnings,
            platform_fee_cents=platform_fee,
        )
        self.db.add(purchase)
        await self.db.commit()
        await self.db.refresh(purchase)
        return purchase

    async def complete_purchase(
        self,
        purchase: TemplatePurchase,
        payment_provider_id: str | None = None,
    ) -> TemplatePurchase:
        """Complete a purchase after payment confirmation."""
        template = await self.get_template_by_id(purchase.marketplace_template_id)
        if not template:
            raise ValueError("Template not found")

        # Duplicate the content for the buyer
        if template.template_type == TemplateType.WORKOUT and template.workout_id:
            workout = await self._workout_service.get_workout_by_id(template.workout_id)
            if workout:
                new_workout = await self._workout_service.duplicate_workout(
                    workout=workout,
                    new_owner_id=purchase.buyer_id,
                    new_name=template.title,
                )
                purchase.duplicated_workout_id = new_workout.id

        elif template.template_type == TemplateType.DIET_PLAN and template.diet_plan_id:
            diet_plan = await self._nutrition_service.get_diet_plan_by_id(template.diet_plan_id)
            if diet_plan:
                new_plan = await self.duplicate_diet_plan(
                    plan=diet_plan,
                    new_owner_id=purchase.buyer_id,
                    new_name=template.title,
                )
                purchase.duplicated_diet_plan_id = new_plan.id

        # Update purchase status
        purchase.status = PurchaseStatus.COMPLETED
        purchase.payment_provider_id = payment_provider_id
        purchase.completed_at = datetime.now(timezone.utc)

        # Update template stats
        template.purchase_count += 1

        # Update creator earnings
        await self._add_to_creator_earnings(
            creator_id=template.creator_id,
            organization_id=template.organization_id,
            amount_cents=purchase.creator_earnings_cents or 0,
        )

        await self.db.commit()
        await self.db.refresh(purchase)
        return purchase

    async def fail_purchase(
        self,
        purchase: TemplatePurchase,
    ) -> TemplatePurchase:
        """Mark a purchase as failed."""
        purchase.status = PurchaseStatus.FAILED
        await self.db.commit()
        await self.db.refresh(purchase)
        return purchase

    async def list_user_purchases(
        self,
        user_id: uuid.UUID,
        status: PurchaseStatus | None = None,
    ) -> list[TemplatePurchase]:
        """List purchases by a user."""
        query = select(TemplatePurchase).where(
            TemplatePurchase.buyer_id == user_id
        ).options(
            selectinload(TemplatePurchase.template),
        )

        if status:
            query = query.where(TemplatePurchase.status == status)

        query = query.order_by(TemplatePurchase.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ==================== Review Operations ====================

    async def create_review(
        self,
        purchase_id: uuid.UUID,
        reviewer_id: uuid.UUID,
        template_id: uuid.UUID,
        rating: int,
        title: str | None = None,
        comment: str | None = None,
    ) -> TemplateReview:
        """Create a review for a purchased template."""
        review = TemplateReview(
            marketplace_template_id=template_id,
            purchase_id=purchase_id,
            reviewer_id=reviewer_id,
            rating=rating,
            title=title,
            comment=comment,
            is_verified_purchase=True,
        )
        self.db.add(review)

        # Update template rating
        template = await self.get_template_by_id(template_id)
        if template:
            template.rating_count += 1
            # Calculate new average
            if template.rating_average:
                total = float(template.rating_average) * (template.rating_count - 1) + rating
                template.rating_average = Decimal(str(round(total / template.rating_count, 2)))
            else:
                template.rating_average = Decimal(str(rating))

        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def list_template_reviews(
        self,
        template_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[TemplateReview]:
        """List reviews for a template."""
        result = await self.db.execute(
            select(TemplateReview)
            .where(TemplateReview.marketplace_template_id == template_id)
            .options(selectinload(TemplateReview.reviewer))
            .order_by(TemplateReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_review_distribution(
        self,
        template_id: uuid.UUID,
    ) -> dict[int, int]:
        """Get rating distribution for a template."""
        result = await self.db.execute(
            select(TemplateReview.rating, func.count(TemplateReview.id))
            .where(TemplateReview.marketplace_template_id == template_id)
            .group_by(TemplateReview.rating)
        )
        distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for rating, count in result.all():
            distribution[rating] = count
        return distribution

    # ==================== Creator Dashboard ====================

    async def get_creator_earnings(
        self,
        creator_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> CreatorEarnings | None:
        """Get creator earnings record."""
        query = select(CreatorEarnings)
        if creator_id:
            query = query.where(CreatorEarnings.creator_id == creator_id)
        if organization_id:
            query = query.where(CreatorEarnings.organization_id == organization_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _add_to_creator_earnings(
        self,
        creator_id: uuid.UUID,
        organization_id: uuid.UUID | None,
        amount_cents: int,
    ) -> CreatorEarnings:
        """Add earnings to creator balance."""
        earnings = await self.get_creator_earnings(
            creator_id=creator_id,
            organization_id=organization_id,
        )

        if not earnings:
            earnings = CreatorEarnings(
                creator_id=creator_id,
                organization_id=organization_id,
                balance_cents=0,
                total_earned_cents=0,
                total_withdrawn_cents=0,
            )
            self.db.add(earnings)

        earnings.balance_cents += amount_cents
        earnings.total_earned_cents += amount_cents

        await self.db.commit()
        await self.db.refresh(earnings)
        return earnings

    async def get_creator_dashboard_stats(
        self,
        creator_id: uuid.UUID,
    ) -> dict:
        """Get dashboard stats for a creator."""
        templates = await self.list_creator_templates(creator_id, include_inactive=True)
        earnings = await self.get_creator_earnings(creator_id=creator_id)

        total_sales = sum(t.purchase_count for t in templates)
        avg_rating = None
        ratings_count = 0
        rating_sum = Decimal(0)

        for t in templates:
            if t.rating_average and t.rating_count > 0:
                rating_sum += t.rating_average * t.rating_count
                ratings_count += t.rating_count

        if ratings_count > 0:
            avg_rating = rating_sum / ratings_count

        return {
            "total_templates": len(templates),
            "active_templates": len([t for t in templates if t.is_active]),
            "total_sales": total_sales,
            "total_earnings_cents": earnings.total_earned_cents if earnings else 0,
            "balance_cents": earnings.balance_cents if earnings else 0,
            "average_rating": avg_rating,
        }

    # ==================== Payout Operations ====================

    async def request_payout(
        self,
        creator_id: uuid.UUID,
        amount_cents: int,
        payout_method: PayoutMethod,
        payout_details: dict | None = None,
    ) -> CreatorPayout:
        """Request a payout."""
        earnings = await self.get_creator_earnings(creator_id=creator_id)
        if not earnings:
            raise ValueError("No earnings found")

        if earnings.balance_cents < amount_cents:
            raise ValueError("Insufficient balance")

        payout = CreatorPayout(
            earnings_id=earnings.id,
            amount_cents=amount_cents,
            payout_method=payout_method,
            payout_details=payout_details,
            status=PayoutStatus.PENDING,
        )
        self.db.add(payout)

        # Deduct from balance
        earnings.balance_cents -= amount_cents

        await self.db.commit()
        await self.db.refresh(payout)
        return payout

    async def list_creator_payouts(
        self,
        creator_id: uuid.UUID,
    ) -> list[CreatorPayout]:
        """List payouts for a creator."""
        earnings = await self.get_creator_earnings(creator_id=creator_id)
        if not earnings:
            return []

        result = await self.db.execute(
            select(CreatorPayout)
            .where(CreatorPayout.earnings_id == earnings.id)
            .order_by(CreatorPayout.created_at.desc())
        )
        return list(result.scalars().all())

    # ==================== Organization Access ====================

    async def grant_organization_access(
        self,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
        is_free_for_members: bool = False,
        member_discount_percent: int = 0,
    ) -> OrganizationTemplateAccess:
        """Grant organization members access to a template."""
        access = OrganizationTemplateAccess(
            organization_id=organization_id,
            marketplace_template_id=template_id,
            is_free_for_members=is_free_for_members,
            member_discount_percent=member_discount_percent,
        )
        self.db.add(access)
        await self.db.commit()
        await self.db.refresh(access)
        return access

    async def list_organization_templates(
        self,
        organization_id: uuid.UUID,
    ) -> list[OrganizationTemplateAccess]:
        """List templates available to organization members."""
        result = await self.db.execute(
            select(OrganizationTemplateAccess)
            .where(OrganizationTemplateAccess.organization_id == organization_id)
            .options(selectinload(OrganizationTemplateAccess.template))
        )
        return list(result.scalars().all())

    async def get_member_price(
        self,
        organization_id: uuid.UUID,
        template_id: uuid.UUID,
    ) -> int | None:
        """Get the price for an organization member."""
        result = await self.db.execute(
            select(OrganizationTemplateAccess).where(
                OrganizationTemplateAccess.organization_id == organization_id,
                OrganizationTemplateAccess.marketplace_template_id == template_id,
            )
        )
        access = result.scalar_one_or_none()
        if not access:
            return None

        template = await self.get_template_by_id(template_id)
        if not template:
            return None

        if access.is_free_for_members:
            return 0

        discount = access.member_discount_percent
        return int(template.price_cents * (100 - discount) / 100)

    # ==================== Category Stats ====================

    async def get_category_counts(self) -> dict[TemplateCategory, int]:
        """Get template counts by category."""
        result = await self.db.execute(
            select(MarketplaceTemplate.category, func.count(MarketplaceTemplate.id))
            .where(
                MarketplaceTemplate.is_active == True,
                MarketplaceTemplate.approved_at.isnot(None),
            )
            .group_by(MarketplaceTemplate.category)
        )
        return {cat: count for cat, count in result.all() if cat}

    # ==================== Diet Plan Duplication ====================

    async def duplicate_diet_plan(
        self,
        plan,  # DietPlan
        new_owner_id: uuid.UUID,
        new_name: str | None = None,
    ):
        """Duplicate a diet plan for another user."""
        from src.domains.nutrition.models import DietPlan, DietPlanMeal, DietPlanMealFood

        new_plan = DietPlan(
            name=new_name or f"Copy of {plan.name}",
            description=plan.description,
            target_calories=plan.target_calories,
            target_protein=plan.target_protein,
            target_carbs=plan.target_carbs,
            target_fat=plan.target_fat,
            tags=plan.tags,
            is_template=False,
            is_public=False,
            created_by_id=new_owner_id,
        )
        self.db.add(new_plan)
        await self.db.flush()

        # Copy meals
        for meal in plan.meals:
            new_meal = DietPlanMeal(
                plan_id=new_plan.id,
                name=meal.name,
                meal_time=meal.meal_time,
                order=meal.order,
                notes=meal.notes,
            )
            self.db.add(new_meal)
            await self.db.flush()

            # Copy meal foods
            for mf in meal.foods:
                new_mf = DietPlanMealFood(
                    meal_id=new_meal.id,
                    food_id=mf.food_id,
                    servings=mf.servings,
                    portion_description=mf.portion_description,
                    notes=mf.notes,
                )
                self.db.add(new_mf)

        await self.db.commit()
        await self.db.refresh(new_plan)
        return new_plan
