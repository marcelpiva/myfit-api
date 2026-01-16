"""Marketplace schemas for request/response validation."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.marketplace.models import (
    PaymentProvider,
    PayoutMethod,
    PayoutStatus,
    PurchaseStatus,
    TemplateCategory,
    TemplateDifficulty,
    TemplateType,
)


# ==================== Template Schemas ====================


class TemplateCreate(BaseModel):
    """Create template listing request."""

    template_type: TemplateType
    workout_id: UUID | None = None
    diet_plan_id: UUID | None = None
    organization_id: UUID | None = None

    price_cents: int = Field(default=0, ge=0)
    currency: str = Field(default="BRL", max_length=3)

    title: str = Field(min_length=3, max_length=200)
    short_description: str | None = Field(None, max_length=500)
    full_description: str | None = None
    cover_image_url: str | None = Field(None, max_length=500)
    preview_images: list[str] | None = None

    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty = TemplateDifficulty.INTERMEDIATE
    tags: list[str] | None = None


class TemplateUpdate(BaseModel):
    """Update template listing request."""

    price_cents: int | None = Field(None, ge=0)
    title: str | None = Field(None, min_length=3, max_length=200)
    short_description: str | None = Field(None, max_length=500)
    full_description: str | None = None
    cover_image_url: str | None = Field(None, max_length=500)
    preview_images: list[str] | None = None
    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class CreatorInfo(BaseModel):
    """Creator information for display."""

    id: UUID
    name: str
    avatar_url: str | None = None
    is_verified: bool = False

    class Config:
        from_attributes = True


class TemplateListResponse(BaseModel):
    """Template list item response."""

    id: UUID
    template_type: TemplateType
    title: str
    short_description: str | None = None
    cover_image_url: str | None = None
    price_cents: int
    price_display: str
    is_free: bool
    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty
    purchase_count: int
    rating_average: Decimal | None = None
    rating_count: int
    is_featured: bool
    creator: CreatorInfo

    class Config:
        from_attributes = True


class TemplateResponse(BaseModel):
    """Template detail response."""

    id: UUID
    template_type: TemplateType
    workout_id: UUID | None = None
    diet_plan_id: UUID | None = None
    creator_id: UUID
    organization_id: UUID | None = None

    price_cents: int
    price_display: str
    is_free: bool
    currency: str

    title: str
    short_description: str | None = None
    full_description: str | None = None
    cover_image_url: str | None = None
    preview_images: list[str] | None = None

    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty
    tags: list[str] | None = None

    purchase_count: int
    rating_average: Decimal | None = None
    rating_count: int

    is_active: bool
    is_featured: bool
    approved_at: datetime | None = None
    created_at: datetime

    creator: CreatorInfo

    class Config:
        from_attributes = True


class TemplatePreviewResponse(BaseModel):
    """Template preview response (limited info for non-buyers)."""

    id: UUID
    template_type: TemplateType
    title: str
    short_description: str | None = None
    full_description: str | None = None
    cover_image_url: str | None = None
    preview_images: list[str] | None = None
    price_cents: int
    price_display: str
    is_free: bool
    category: TemplateCategory | None = None
    difficulty: TemplateDifficulty
    tags: list[str] | None = None
    purchase_count: int
    rating_average: Decimal | None = None
    rating_count: int
    creator: CreatorInfo

    # Limited workout/diet info
    exercise_count: int | None = None
    estimated_duration_min: int | None = None
    meal_count: int | None = None
    target_calories: int | None = None

    class Config:
        from_attributes = True


# ==================== Purchase Schemas ====================


class CheckoutRequest(BaseModel):
    """Checkout request."""

    payment_provider: PaymentProvider = PaymentProvider.PIX


class CheckoutResponse(BaseModel):
    """Checkout response with payment info."""

    purchase_id: UUID
    template_id: UUID
    price_cents: int
    price_display: str
    payment_provider: PaymentProvider
    status: PurchaseStatus

    # PIX specific
    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None

    # Stripe specific
    stripe_payment_intent_id: str | None = None
    stripe_client_secret: str | None = None

    expires_at: datetime | None = None


class PurchaseStatusResponse(BaseModel):
    """Purchase status response."""

    id: UUID
    status: PurchaseStatus
    template_id: UUID
    template_title: str
    price_cents: int
    duplicated_workout_id: UUID | None = None
    duplicated_diet_plan_id: UUID | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class PurchaseListResponse(BaseModel):
    """Purchase list item response."""

    id: UUID
    template_id: UUID
    template_title: str
    template_type: TemplateType
    price_cents: int
    status: PurchaseStatus
    duplicated_workout_id: UUID | None = None
    duplicated_diet_plan_id: UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Review Schemas ====================


class ReviewCreate(BaseModel):
    """Create review request."""

    rating: int = Field(ge=1, le=5)
    title: str | None = Field(None, max_length=200)
    comment: str | None = None


class ReviewResponse(BaseModel):
    """Review response."""

    id: UUID
    rating: int
    title: str | None = None
    comment: str | None = None
    is_verified_purchase: bool
    created_at: datetime
    reviewer_name: str
    reviewer_avatar_url: str | None = None

    class Config:
        from_attributes = True


class ReviewListResponse(BaseModel):
    """Review list with summary."""

    reviews: list[ReviewResponse]
    total_count: int
    rating_average: Decimal | None = None
    rating_distribution: dict[int, int]  # {5: 10, 4: 5, ...}


# ==================== Creator Dashboard Schemas ====================


class CreatorDashboardResponse(BaseModel):
    """Creator dashboard summary."""

    total_templates: int
    total_sales: int
    total_earnings_cents: int
    total_earnings_display: str
    balance_cents: int
    balance_display: str
    this_month_sales: int
    this_month_earnings_cents: int
    average_rating: Decimal | None = None


class TemplateStatsResponse(BaseModel):
    """Stats for a single template."""

    id: UUID
    title: str
    template_type: TemplateType
    price_cents: int
    purchase_count: int
    total_earnings_cents: int
    rating_average: Decimal | None = None
    rating_count: int
    is_active: bool

    class Config:
        from_attributes = True


class EarningsHistoryItem(BaseModel):
    """Earnings history item."""

    purchase_id: UUID
    template_title: str
    buyer_name: str
    amount_cents: int
    completed_at: datetime


class EarningsResponse(BaseModel):
    """Creator earnings detail."""

    balance_cents: int
    balance_display: str
    total_earned_cents: int
    total_withdrawn_cents: int
    pending_payouts_cents: int
    history: list[EarningsHistoryItem]


class PayoutRequest(BaseModel):
    """Payout request."""

    amount_cents: int = Field(ge=5000)  # Minimum R$ 50
    payout_method: PayoutMethod
    pix_key: str | None = None
    bank_account: dict | None = None


class PayoutResponse(BaseModel):
    """Payout response."""

    id: UUID
    amount_cents: int
    payout_method: PayoutMethod
    status: PayoutStatus
    created_at: datetime
    processed_at: datetime | None = None

    class Config:
        from_attributes = True


# ==================== Organization Schemas ====================


class OrganizationTemplateAccessCreate(BaseModel):
    """Grant template access to organization members."""

    marketplace_template_id: UUID
    is_free_for_members: bool = False
    member_discount_percent: int = Field(default=0, ge=0, le=100)


class OrganizationTemplateAccessResponse(BaseModel):
    """Organization template access response."""

    id: UUID
    template_id: UUID
    template_title: str
    template_type: TemplateType
    original_price_cents: int
    is_free_for_members: bool
    member_discount_percent: int
    member_price_cents: int
    created_at: datetime

    class Config:
        from_attributes = True


# ==================== Category Schemas ====================


class CategoryResponse(BaseModel):
    """Category with template count."""

    category: TemplateCategory
    name: str
    template_count: int
    icon: str | None = None
