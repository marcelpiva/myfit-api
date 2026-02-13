"""Consultancy schemas for API validation."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import ConsultancyCategory, ConsultancyFormat, TransactionStatus


# --- Professional Profile ---


class ProfessionalProfileCreate(BaseModel):
    """Schema for creating a professional profile."""

    headline: str | None = Field(default=None, max_length=200)
    bio: str | None = None
    specialties: list[str] | None = None
    certifications: list[str] | None = None
    languages: list[str] | None = None
    experience_years: int | None = Field(default=None, ge=0)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    instagram: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=255)
    is_accepting_students: bool = True
    max_concurrent_students: int | None = Field(default=None, ge=1)


class ProfessionalProfileUpdate(BaseModel):
    """Schema for updating a professional profile."""

    headline: str | None = Field(default=None, max_length=200)
    bio: str | None = None
    specialties: list[str] | None = None
    certifications: list[str] | None = None
    languages: list[str] | None = None
    experience_years: int | None = Field(default=None, ge=0)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    instagram: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=255)
    is_accepting_students: bool | None = None
    max_concurrent_students: int | None = Field(default=None, ge=1)


class ProfessionalProfileResponse(BaseModel):
    """Schema for professional profile response."""

    id: UUID
    user_id: UUID
    user_name: str
    user_avatar_url: str | None = None
    headline: str | None
    bio: str | None
    specialties: list[str] | None
    certifications: list[str] | None
    languages: list[str] | None
    experience_years: int | None
    city: str | None
    state: str | None
    country: str
    instagram: str | None
    website: str | None
    rating_average: Decimal | None
    rating_count: int
    total_students_served: int
    total_consultancies_sold: int
    is_public: bool
    is_verified: bool
    is_featured: bool
    is_accepting_students: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Consultancy Listings ---


class ConsultancyListingCreate(BaseModel):
    """Schema for creating a consultancy listing."""

    title: str = Field(..., max_length=200)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = None
    cover_image_url: str | None = None
    category: ConsultancyCategory
    tags: list[str] | None = None
    format: ConsultancyFormat
    price_cents: int = Field(..., ge=0)
    currency: str = Field(default="BRL", max_length=3)
    duration_days: int | None = Field(default=None, ge=1)
    sessions_included: int | None = Field(default=None, ge=1)
    includes: list[str] | None = None


class ConsultancyListingUpdate(BaseModel):
    """Schema for updating a consultancy listing."""

    title: str | None = Field(default=None, max_length=200)
    short_description: str | None = Field(default=None, max_length=500)
    full_description: str | None = None
    cover_image_url: str | None = None
    category: ConsultancyCategory | None = None
    tags: list[str] | None = None
    format: ConsultancyFormat | None = None
    price_cents: int | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=1)
    sessions_included: int | None = Field(default=None, ge=1)
    includes: list[str] | None = None
    is_active: bool | None = None


class ConsultancyListingResponse(BaseModel):
    """Schema for consultancy listing response."""

    id: UUID
    professional_id: UUID
    professional_name: str
    professional_avatar_url: str | None = None
    professional_headline: str | None = None
    professional_rating: Decimal | None = None
    title: str
    short_description: str | None
    full_description: str | None
    cover_image_url: str | None
    category: ConsultancyCategory
    tags: list[str] | None
    format: ConsultancyFormat
    price_cents: int
    currency: str
    duration_days: int | None
    sessions_included: int | None
    includes: list[str] | None
    commission_rate: int
    purchase_count: int
    rating_average: Decimal | None
    rating_count: int
    view_count: int
    is_active: bool
    is_featured: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultancyListingListResponse(BaseModel):
    """Schema for listing list response."""

    listings: list[ConsultancyListingResponse]
    total: int


# --- Transactions ---


class ConsultancyPurchaseRequest(BaseModel):
    """Schema for purchasing a consultancy."""

    listing_id: UUID
    payment_provider: str | None = None
    buyer_notes: str | None = None


class ConsultancyTransactionResponse(BaseModel):
    """Schema for transaction response."""

    id: UUID
    listing_id: UUID
    listing_title: str
    buyer_id: UUID
    buyer_name: str
    seller_id: UUID
    seller_name: str
    amount_cents: int
    commission_cents: int
    seller_earnings_cents: int
    currency: str
    status: TransactionStatus
    confirmed_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    expires_at: datetime | None
    buyer_notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConsultancyCheckoutResponse(ConsultancyTransactionResponse):
    """Schema for consultancy checkout with PIX payment data."""

    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None


class ConsultancyTransactionListResponse(BaseModel):
    """Schema for transaction list response."""

    transactions: list[ConsultancyTransactionResponse]
    total: int


# --- Reviews ---


class ConsultancyReviewCreate(BaseModel):
    """Schema for creating a review."""

    rating: int = Field(..., ge=1, le=5)
    title: str | None = Field(default=None, max_length=200)
    comment: str | None = None


class ConsultancyReviewResponse(BaseModel):
    """Schema for review response."""

    id: UUID
    transaction_id: UUID
    listing_id: UUID
    reviewer_id: UUID
    reviewer_name: str
    reviewer_avatar_url: str | None = None
    professional_id: UUID
    rating: int
    title: str | None
    comment: str | None
    response: str | None
    responded_at: datetime | None
    is_verified_purchase: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
