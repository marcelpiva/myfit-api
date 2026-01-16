"""Marketplace router with template, purchase, review, and creator endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.marketplace.models import (
    PaymentProvider,
    PurchaseStatus,
    TemplateCategory,
    TemplateDifficulty,
    TemplateType,
)
from src.domains.marketplace.schemas import (
    CategoryResponse,
    CheckoutRequest,
    CheckoutResponse,
    CreatorDashboardResponse,
    CreatorInfo,
    EarningsResponse,
    OrganizationTemplateAccessCreate,
    OrganizationTemplateAccessResponse,
    PayoutRequest,
    PayoutResponse,
    PurchaseListResponse,
    PurchaseStatusResponse,
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
    TemplateCreate,
    TemplateListResponse,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateStatsResponse,
    TemplateUpdate,
)
from src.domains.marketplace.service import MarketplaceService

router = APIRouter()


# ==================== Template Endpoints ====================


@router.get("/templates", response_model=list[TemplateListResponse])
async def list_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    template_type: Annotated[TemplateType | None, Query()] = None,
    category: Annotated[TemplateCategory | None, Query()] = None,
    difficulty: Annotated[TemplateDifficulty | None, Query()] = None,
    min_price: Annotated[int | None, Query(ge=0)] = None,
    max_price: Annotated[int | None, Query(ge=0)] = None,
    free_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    sort_by: Annotated[str, Query()] = "created_at",
    sort_desc: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TemplateListResponse]:
    """List marketplace templates with filters."""
    service = MarketplaceService(db)
    templates = await service.list_templates(
        template_type=template_type,
        category=category,
        difficulty=difficulty,
        min_price=min_price,
        max_price=max_price,
        free_only=free_only,
        search=search,
        sort_by=sort_by,
        sort_desc=sort_desc,
        limit=limit,
        offset=offset,
    )

    return [
        TemplateListResponse(
            id=t.id,
            template_type=t.template_type,
            title=t.title,
            short_description=t.short_description,
            cover_image_url=t.cover_image_url,
            price_cents=t.price_cents,
            price_display=t.price_display,
            is_free=t.is_free,
            category=t.category,
            difficulty=t.difficulty,
            purchase_count=t.purchase_count,
            rating_average=t.rating_average,
            rating_count=t.rating_count,
            is_featured=t.is_featured,
            creator=CreatorInfo(
                id=t.creator.id,
                name=t.creator.name,
                avatar_url=t.creator.avatar_url if hasattr(t.creator, 'avatar_url') else None,
            ),
        )
        for t in templates
    ]


@router.get("/templates/featured", response_model=list[TemplateListResponse])
async def list_featured_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[TemplateListResponse]:
    """List featured templates."""
    service = MarketplaceService(db)
    templates = await service.list_featured_templates(limit=limit)

    return [
        TemplateListResponse(
            id=t.id,
            template_type=t.template_type,
            title=t.title,
            short_description=t.short_description,
            cover_image_url=t.cover_image_url,
            price_cents=t.price_cents,
            price_display=t.price_display,
            is_free=t.is_free,
            category=t.category,
            difficulty=t.difficulty,
            purchase_count=t.purchase_count,
            rating_average=t.rating_average,
            rating_count=t.rating_count,
            is_featured=t.is_featured,
            creator=CreatorInfo(
                id=t.creator.id,
                name=t.creator.name,
                avatar_url=t.creator.avatar_url if hasattr(t.creator, 'avatar_url') else None,
            ),
        )
        for t in templates
    ]


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateResponse:
    """Get template details."""
    service = MarketplaceService(db)
    template = await service.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return TemplateResponse(
        id=template.id,
        template_type=template.template_type,
        workout_id=template.workout_id,
        diet_plan_id=template.diet_plan_id,
        creator_id=template.creator_id,
        organization_id=template.organization_id,
        price_cents=template.price_cents,
        price_display=template.price_display,
        is_free=template.is_free,
        currency=template.currency,
        title=template.title,
        short_description=template.short_description,
        full_description=template.full_description,
        cover_image_url=template.cover_image_url,
        preview_images=template.preview_images,
        category=template.category,
        difficulty=template.difficulty,
        tags=template.tags,
        purchase_count=template.purchase_count,
        rating_average=template.rating_average,
        rating_count=template.rating_count,
        is_active=template.is_active,
        is_featured=template.is_featured,
        approved_at=template.approved_at,
        created_at=template.created_at,
        creator=CreatorInfo(
            id=template.creator.id,
            name=template.creator.name,
            avatar_url=template.creator.avatar_url if hasattr(template.creator, 'avatar_url') else None,
        ),
    )


@router.get("/templates/{template_id}/preview", response_model=TemplatePreviewResponse)
async def get_template_preview(
    template_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplatePreviewResponse:
    """Get template preview (limited info for non-buyers)."""
    service = MarketplaceService(db)
    template = await service.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Get limited content info
    exercise_count = None
    estimated_duration_min = None
    meal_count = None
    target_calories = None

    if template.workout and template.template_type == TemplateType.WORKOUT:
        exercise_count = len(template.workout.exercises) if template.workout.exercises else 0
        estimated_duration_min = template.workout.estimated_duration_min

    if template.diet_plan and template.template_type == TemplateType.DIET_PLAN:
        meal_count = len(template.diet_plan.meals) if template.diet_plan.meals else 0
        target_calories = template.diet_plan.target_calories

    return TemplatePreviewResponse(
        id=template.id,
        template_type=template.template_type,
        title=template.title,
        short_description=template.short_description,
        full_description=template.full_description,
        cover_image_url=template.cover_image_url,
        preview_images=template.preview_images,
        price_cents=template.price_cents,
        price_display=template.price_display,
        is_free=template.is_free,
        category=template.category,
        difficulty=template.difficulty,
        tags=template.tags,
        purchase_count=template.purchase_count,
        rating_average=template.rating_average,
        rating_count=template.rating_count,
        creator=CreatorInfo(
            id=template.creator.id,
            name=template.creator.name,
            avatar_url=template.creator.avatar_url if hasattr(template.creator, 'avatar_url') else None,
        ),
        exercise_count=exercise_count,
        estimated_duration_min=estimated_duration_min,
        meal_count=meal_count,
        target_calories=target_calories,
    )


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: TemplateCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateResponse:
    """Create a new template listing."""
    service = MarketplaceService(db)

    # Validate that the referenced content exists and belongs to user
    if request.template_type == TemplateType.WORKOUT:
        if not request.workout_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workout_id is required for workout templates",
            )
    elif request.template_type == TemplateType.DIET_PLAN:
        if not request.diet_plan_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="diet_plan_id is required for diet plan templates",
            )

    template = await service.create_template(
        creator_id=current_user.id,
        template_type=request.template_type,
        title=request.title,
        price_cents=request.price_cents,
        workout_id=request.workout_id,
        diet_plan_id=request.diet_plan_id,
        organization_id=request.organization_id,
        short_description=request.short_description,
        full_description=request.full_description,
        cover_image_url=request.cover_image_url,
        preview_images=request.preview_images,
        category=request.category,
        difficulty=request.difficulty,
        tags=request.tags,
        currency=request.currency,
    )

    # Reload with relationships
    template = await service.get_template_by_id(template.id)

    return TemplateResponse(
        id=template.id,
        template_type=template.template_type,
        workout_id=template.workout_id,
        diet_plan_id=template.diet_plan_id,
        creator_id=template.creator_id,
        organization_id=template.organization_id,
        price_cents=template.price_cents,
        price_display=template.price_display,
        is_free=template.is_free,
        currency=template.currency,
        title=template.title,
        short_description=template.short_description,
        full_description=template.full_description,
        cover_image_url=template.cover_image_url,
        preview_images=template.preview_images,
        category=template.category,
        difficulty=template.difficulty,
        tags=template.tags,
        purchase_count=template.purchase_count,
        rating_average=template.rating_average,
        rating_count=template.rating_count,
        is_active=template.is_active,
        is_featured=template.is_featured,
        approved_at=template.approved_at,
        created_at=template.created_at,
        creator=CreatorInfo(
            id=template.creator.id,
            name=template.creator.name,
            avatar_url=template.creator.avatar_url if hasattr(template.creator, 'avatar_url') else None,
        ),
    )


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: UUID,
    request: TemplateUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateResponse:
    """Update a template (owner only)."""
    service = MarketplaceService(db)
    template = await service.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own templates",
        )

    template = await service.update_template(
        template=template,
        price_cents=request.price_cents,
        title=request.title,
        short_description=request.short_description,
        full_description=request.full_description,
        cover_image_url=request.cover_image_url,
        preview_images=request.preview_images,
        category=request.category,
        difficulty=request.difficulty,
        tags=request.tags,
        is_active=request.is_active,
    )

    return TemplateResponse(
        id=template.id,
        template_type=template.template_type,
        workout_id=template.workout_id,
        diet_plan_id=template.diet_plan_id,
        creator_id=template.creator_id,
        organization_id=template.organization_id,
        price_cents=template.price_cents,
        price_display=template.price_display,
        is_free=template.is_free,
        currency=template.currency,
        title=template.title,
        short_description=template.short_description,
        full_description=template.full_description,
        cover_image_url=template.cover_image_url,
        preview_images=template.preview_images,
        category=template.category,
        difficulty=template.difficulty,
        tags=template.tags,
        purchase_count=template.purchase_count,
        rating_average=template.rating_average,
        rating_count=template.rating_count,
        is_active=template.is_active,
        is_featured=template.is_featured,
        approved_at=template.approved_at,
        created_at=template.created_at,
        creator=CreatorInfo(
            id=template.creator.id,
            name=template.creator.name,
            avatar_url=template.creator.avatar_url if hasattr(template.creator, 'avatar_url') else None,
        ),
    )


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Deactivate a template (owner only)."""
    service = MarketplaceService(db)
    template = await service.get_template_by_id(template_id)

    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    if template.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own templates",
        )

    await service.deactivate_template(template)


@router.get("/my-templates", response_model=list[TemplateStatsResponse])
async def list_my_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_inactive: Annotated[bool, Query()] = False,
) -> list[TemplateStatsResponse]:
    """List templates created by current user with stats."""
    service = MarketplaceService(db)
    templates = await service.list_creator_templates(
        creator_id=current_user.id,
        include_inactive=include_inactive,
    )

    return [
        TemplateStatsResponse(
            id=t.id,
            title=t.title,
            template_type=t.template_type,
            price_cents=t.price_cents,
            purchase_count=t.purchase_count,
            total_earnings_cents=t.purchase_count * int(t.price_cents * 0.8),  # 80% creator share
            rating_average=t.rating_average,
            rating_count=t.rating_count,
            is_active=t.is_active,
        )
        for t in templates
    ]


# ==================== Purchase Endpoints ====================


@router.post("/templates/{template_id}/checkout", response_model=CheckoutResponse)
async def checkout_template(
    template_id: UUID,
    request: CheckoutRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckoutResponse:
    """Start checkout process for a template."""
    service = MarketplaceService(db)

    template = await service.get_template_by_id(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    # Check if already purchased
    if await service.check_user_purchased(current_user.id, template_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already own this template",
        )

    # Create purchase record
    purchase = await service.create_purchase(
        buyer_id=current_user.id,
        template_id=template_id,
        payment_provider=request.payment_provider,
    )

    # Handle free templates immediately
    if template.is_free:
        purchase = await service.complete_purchase(purchase)
        return CheckoutResponse(
            purchase_id=purchase.id,
            template_id=template_id,
            price_cents=purchase.price_cents,
            price_display=template.price_display,
            payment_provider=request.payment_provider,
            status=purchase.status,
        )

    # For paid templates, generate payment info
    # TODO: Integrate with actual payment provider (Stripe/Mercado Pago)
    pix_qr_code = None
    pix_copy_paste = None

    if request.payment_provider == PaymentProvider.PIX:
        # Generate PIX QR code (placeholder)
        pix_copy_paste = f"00020126580014br.gov.bcb.pix0136{purchase.id}5204000053039865802BR"
        pix_qr_code = pix_copy_paste  # In real impl, this would be base64 QR image

    return CheckoutResponse(
        purchase_id=purchase.id,
        template_id=template_id,
        price_cents=purchase.price_cents,
        price_display=template.price_display,
        payment_provider=request.payment_provider,
        status=purchase.status,
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
    )


@router.get("/purchases/{purchase_id}/status", response_model=PurchaseStatusResponse)
async def get_purchase_status(
    purchase_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PurchaseStatusResponse:
    """Get purchase status."""
    service = MarketplaceService(db)
    purchase = await service.get_purchase_by_id(purchase_id)

    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found",
        )

    if purchase.buyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return PurchaseStatusResponse(
        id=purchase.id,
        status=purchase.status,
        template_id=purchase.marketplace_template_id,
        template_title=purchase.template.title if purchase.template else "",
        price_cents=purchase.price_cents,
        duplicated_workout_id=purchase.duplicated_workout_id,
        duplicated_diet_plan_id=purchase.duplicated_diet_plan_id,
        completed_at=purchase.completed_at,
    )


@router.get("/my-purchases", response_model=list[PurchaseListResponse])
async def list_my_purchases(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[PurchaseStatus | None, Query(alias="status")] = None,
) -> list[PurchaseListResponse]:
    """List purchases by current user."""
    service = MarketplaceService(db)
    purchases = await service.list_user_purchases(
        user_id=current_user.id,
        status=status_filter,
    )

    return [
        PurchaseListResponse(
            id=p.id,
            template_id=p.marketplace_template_id,
            template_title=p.template.title if p.template else "",
            template_type=p.template.template_type if p.template else TemplateType.WORKOUT,
            price_cents=p.price_cents,
            status=p.status,
            duplicated_workout_id=p.duplicated_workout_id,
            duplicated_diet_plan_id=p.duplicated_diet_plan_id,
            completed_at=p.completed_at,
            created_at=p.created_at,
        )
        for p in purchases
    ]


# ==================== Review Endpoints ====================


@router.post("/purchases/{purchase_id}/review", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    purchase_id: UUID,
    request: ReviewCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReviewResponse:
    """Review a purchased template."""
    service = MarketplaceService(db)

    purchase = await service.get_purchase_by_id(purchase_id)
    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Purchase not found",
        )

    if purchase.buyer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only review your own purchases",
        )

    if purchase.status != PurchaseStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only review completed purchases",
        )

    review = await service.create_review(
        purchase_id=purchase_id,
        reviewer_id=current_user.id,
        template_id=purchase.marketplace_template_id,
        rating=request.rating,
        title=request.title,
        comment=request.comment,
    )

    return ReviewResponse(
        id=review.id,
        rating=review.rating,
        title=review.title,
        comment=review.comment,
        is_verified_purchase=review.is_verified_purchase,
        created_at=review.created_at,
        reviewer_name=current_user.name,
        reviewer_avatar_url=current_user.avatar_url if hasattr(current_user, 'avatar_url') else None,
    )


@router.get("/templates/{template_id}/reviews", response_model=ReviewListResponse)
async def list_template_reviews(
    template_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewListResponse:
    """List reviews for a template."""
    service = MarketplaceService(db)

    template = await service.get_template_by_id(template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    reviews = await service.list_template_reviews(
        template_id=template_id,
        limit=limit,
        offset=offset,
    )
    distribution = await service.get_review_distribution(template_id)

    return ReviewListResponse(
        reviews=[
            ReviewResponse(
                id=r.id,
                rating=r.rating,
                title=r.title,
                comment=r.comment,
                is_verified_purchase=r.is_verified_purchase,
                created_at=r.created_at,
                reviewer_name=r.reviewer.name if r.reviewer else "",
                reviewer_avatar_url=r.reviewer.avatar_url if r.reviewer and hasattr(r.reviewer, 'avatar_url') else None,
            )
            for r in reviews
        ],
        total_count=template.rating_count,
        rating_average=template.rating_average,
        rating_distribution=distribution,
    )


# ==================== Creator Dashboard Endpoints ====================


@router.get("/creator/dashboard", response_model=CreatorDashboardResponse)
async def get_creator_dashboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreatorDashboardResponse:
    """Get creator dashboard stats."""
    service = MarketplaceService(db)
    stats = await service.get_creator_dashboard_stats(current_user.id)

    return CreatorDashboardResponse(
        total_templates=stats["total_templates"],
        total_sales=stats["total_sales"],
        total_earnings_cents=stats["total_earnings_cents"],
        total_earnings_display=f"R$ {stats['total_earnings_cents'] / 100:.2f}",
        balance_cents=stats["balance_cents"],
        balance_display=f"R$ {stats['balance_cents'] / 100:.2f}",
        this_month_sales=0,  # TODO: Calculate from actual data
        this_month_earnings_cents=0,  # TODO: Calculate from actual data
        average_rating=stats["average_rating"],
    )


@router.get("/creator/earnings", response_model=EarningsResponse)
async def get_creator_earnings(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> EarningsResponse:
    """Get creator earnings details."""
    service = MarketplaceService(db)
    earnings = await service.get_creator_earnings(creator_id=current_user.id)

    if not earnings:
        return EarningsResponse(
            balance_cents=0,
            balance_display="R$ 0,00",
            total_earned_cents=0,
            total_withdrawn_cents=0,
            pending_payouts_cents=0,
            history=[],
        )

    # Calculate pending payouts
    payouts = await service.list_creator_payouts(current_user.id)
    pending_payouts = sum(
        p.amount_cents for p in payouts
        if p.status in [PayoutStatus.PENDING, PayoutStatus.PROCESSING]
    )

    return EarningsResponse(
        balance_cents=earnings.balance_cents,
        balance_display=earnings.balance_display,
        total_earned_cents=earnings.total_earned_cents,
        total_withdrawn_cents=earnings.total_withdrawn_cents,
        pending_payouts_cents=pending_payouts,
        history=[],  # TODO: Implement earnings history
    )


@router.get("/creator/payouts", response_model=list[PayoutResponse])
async def list_creator_payouts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PayoutResponse]:
    """List creator payout requests."""
    service = MarketplaceService(db)
    payouts = await service.list_creator_payouts(current_user.id)

    return [
        PayoutResponse(
            id=p.id,
            amount_cents=p.amount_cents,
            payout_method=p.payout_method,
            status=p.status,
            created_at=p.created_at,
            processed_at=p.processed_at,
        )
        for p in payouts
    ]


@router.post("/creator/payouts", response_model=PayoutResponse, status_code=status.HTTP_201_CREATED)
async def request_payout(
    request: PayoutRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PayoutResponse:
    """Request a payout."""
    service = MarketplaceService(db)

    payout_details = {}
    if request.payout_method == PayoutMethod.PIX and request.pix_key:
        payout_details["pix_key"] = request.pix_key
    elif request.payout_method == PayoutMethod.BANK_TRANSFER and request.bank_account:
        payout_details = request.bank_account

    try:
        payout = await service.request_payout(
            creator_id=current_user.id,
            amount_cents=request.amount_cents,
            payout_method=request.payout_method,
            payout_details=payout_details,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return PayoutResponse(
        id=payout.id,
        amount_cents=payout.amount_cents,
        payout_method=payout.payout_method,
        status=payout.status,
        created_at=payout.created_at,
        processed_at=payout.processed_at,
    )


# ==================== Category Endpoints ====================


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CategoryResponse]:
    """List categories with template counts."""
    service = MarketplaceService(db)
    counts = await service.get_category_counts()

    category_names = {
        TemplateCategory.STRENGTH: "Força",
        TemplateCategory.WEIGHT_LOSS: "Emagrecimento",
        TemplateCategory.MUSCLE_GAIN: "Hipertrofia",
        TemplateCategory.ENDURANCE: "Resistência",
        TemplateCategory.FLEXIBILITY: "Flexibilidade",
        TemplateCategory.GENERAL_FITNESS: "Fitness Geral",
        TemplateCategory.SPORTS: "Esportes",
        TemplateCategory.REHABILITATION: "Reabilitação",
    }

    return [
        CategoryResponse(
            category=cat,
            name=category_names.get(cat, cat.value),
            template_count=count,
        )
        for cat, count in counts.items()
    ]


# ==================== Organization Endpoints ====================


@router.post("/organization/{org_id}/templates", response_model=OrganizationTemplateAccessResponse, status_code=status.HTTP_201_CREATED)
async def grant_organization_template_access(
    org_id: UUID,
    request: OrganizationTemplateAccessCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationTemplateAccessResponse:
    """Grant organization members access to a template."""
    service = MarketplaceService(db)

    # TODO: Verify user has admin rights for the organization

    template = await service.get_template_by_id(request.marketplace_template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    access = await service.grant_organization_access(
        organization_id=org_id,
        template_id=request.marketplace_template_id,
        is_free_for_members=request.is_free_for_members,
        member_discount_percent=request.member_discount_percent,
    )

    # Calculate member price
    if request.is_free_for_members:
        member_price = 0
    else:
        member_price = int(template.price_cents * (100 - request.member_discount_percent) / 100)

    return OrganizationTemplateAccessResponse(
        id=access.id,
        template_id=access.marketplace_template_id,
        template_title=template.title,
        template_type=template.template_type,
        original_price_cents=template.price_cents,
        is_free_for_members=access.is_free_for_members,
        member_discount_percent=access.member_discount_percent,
        member_price_cents=member_price,
        created_at=access.created_at,
    )


@router.get("/organization/{org_id}/templates", response_model=list[OrganizationTemplateAccessResponse])
async def list_organization_templates(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationTemplateAccessResponse]:
    """List templates available to organization members."""
    service = MarketplaceService(db)
    access_list = await service.list_organization_templates(org_id)

    result = []
    for access in access_list:
        template = access.template
        if not template:
            continue

        if access.is_free_for_members:
            member_price = 0
        else:
            member_price = int(template.price_cents * (100 - access.member_discount_percent) / 100)

        result.append(
            OrganizationTemplateAccessResponse(
                id=access.id,
                template_id=access.marketplace_template_id,
                template_title=template.title,
                template_type=template.template_type,
                original_price_cents=template.price_cents,
                is_free_for_members=access.is_free_for_members,
                member_discount_percent=access.member_discount_percent,
                member_price_cents=member_price,
                created_at=access.created_at,
            )
        )

    return result
