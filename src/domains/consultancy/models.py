"""Consultancy marketplace models.

This domain handles the B2C marketplace where professionals
(trainers, nutritionists) sell consultancy services to students.
Different from the existing marketplace which sells templates (workouts/diets).
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import SoftDeleteMixin, TimestampMixin, UUIDMixin


class ConsultancyFormat(str, enum.Enum):
    """Format of the consultancy service."""

    MONTHLY = "monthly"  # Assinatura mensal
    PACKAGE = "package"  # Pacote fechado (ex: 3 meses)
    SINGLE = "single"  # Sessão avulsa


class ConsultancyCategory(str, enum.Enum):
    """Categories for consultancy services."""

    PERSONAL_TRAINING = "personal_training"
    ONLINE_COACHING = "online_coaching"
    NUTRITION = "nutrition"
    SPORTS_NUTRITION = "sports_nutrition"
    PHYSICAL_ASSESSMENT = "physical_assessment"
    REHABILITATION = "rehabilitation"
    YOGA = "yoga"
    PILATES = "pilates"
    FUNCTIONAL = "functional"
    BODYBUILDING = "bodybuilding"
    CROSSFIT = "crossfit"
    OTHER = "other"


class TransactionStatus(str, enum.Enum):
    """Transaction status for consultancy purchases."""

    PENDING = "pending"
    CONFIRMED = "confirmed"  # Payment confirmed
    ACTIVE = "active"  # Service in progress
    COMPLETED = "completed"  # Service delivered
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


class ProfessionalProfile(Base, UUIDMixin, TimestampMixin):
    """Extended public profile for professionals on the marketplace.

    This enriches the base User model with marketplace-specific info.
    """

    __tablename__ = "professional_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Public profile info
    headline: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "Personal Trainer especializado em hipertrofia"
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialties: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["hipertrofia", "emagrecimento"]
    certifications: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["CREF 123456", "ISSN"]
    languages: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["pt", "en", "es"]
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Location (for in-person services)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(50), nullable=True)
    country: Mapped[str] = mapped_column(String(2), default="BR", nullable=False)

    # Social / portfolio
    instagram: Mapped[str | None] = mapped_column(String(100), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portfolio_images: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Marketplace stats (denormalized for performance)
    rating_average: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_students_served: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_consultancies_sold: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Availability
    is_accepting_students: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_concurrent_students: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    listings = relationship("ConsultancyListing", back_populates="professional", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ProfessionalProfile user={self.user_id}>"


class ConsultancyListing(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """A consultancy service listed on the marketplace.

    Professionals create listings describing their services with pricing.
    Students browse and purchase these listings.
    """

    __tablename__ = "consultancy_listings"

    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Listing details
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    gallery_images: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Categorization
    category: Mapped[ConsultancyCategory] = mapped_column(
        Enum(ConsultancyCategory, name="consultancy_category_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Pricing
    format: Mapped[ConsultancyFormat] = mapped_column(
        Enum(ConsultancyFormat, name="consultancy_format_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # For packages
    sessions_included: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Sessions per month/package

    # What's included
    includes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # ["Treino personalizado", "Acompanhamento semanal"]

    # Platform commission rate (percentage, e.g., 10 = 10%)
    commission_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Stats
    purchase_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_average: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    professional = relationship("ProfessionalProfile", back_populates="listings")
    transactions = relationship("ConsultancyTransaction", back_populates="listing", lazy="selectin")

    @property
    def price_display(self) -> str:
        if self.price_cents == 0:
            return "Gratis"
        price = self.price_cents / 100
        return f"R$ {price:.2f}"

    @property
    def commission_amount_cents(self) -> int:
        return int(self.price_cents * self.commission_rate / 100)

    @property
    def professional_earnings_cents(self) -> int:
        return self.price_cents - self.commission_amount_cents

    def __repr__(self) -> str:
        return f"<ConsultancyListing {self.title}>"


class ConsultancyTransaction(Base, UUIDMixin, TimestampMixin):
    """A purchase/subscription of a consultancy service.

    Tracks the lifecycle of a student purchasing a professional's service.
    """

    __tablename__ = "consultancy_transactions"

    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultancy_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seller_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Pricing at time of purchase
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    seller_earnings_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Status
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=TransactionStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Dates
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Payment provider
    payment_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # If this creates an organization membership
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Notes
    buyer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    seller_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    listing = relationship("ConsultancyListing", back_populates="transactions")
    buyer = relationship("User", foreign_keys=[buyer_id])
    seller = relationship("User", foreign_keys=[seller_id])

    def __repr__(self) -> str:
        return f"<ConsultancyTransaction {self.id} status={self.status}>"


class ConsultancyReview(Base, UUIDMixin, TimestampMixin):
    """Review of a consultancy service after completion."""

    __tablename__ = "consultancy_reviews"

    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultancy_transactions.id", ondelete="CASCADE"),
        unique=True,  # One review per transaction
        nullable=False,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("consultancy_listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    professional_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Review content
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Professional response
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_verified_purchase: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    transaction = relationship("ConsultancyTransaction", foreign_keys=[transaction_id])
    reviewer = relationship("User", foreign_keys=[reviewer_id])

    def __repr__(self) -> str:
        return f"<ConsultancyReview {self.id} rating={self.rating}>"


# Import for type hints
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
