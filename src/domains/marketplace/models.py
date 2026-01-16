"""Marketplace models for templates marketplace."""
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
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class TemplateType(str, enum.Enum):
    """Type of template."""

    WORKOUT = "workout"
    DIET_PLAN = "diet_plan"


class TemplateCategory(str, enum.Enum):
    """Template categories."""

    STRENGTH = "strength"
    WEIGHT_LOSS = "weight_loss"
    MUSCLE_GAIN = "muscle_gain"
    ENDURANCE = "endurance"
    FLEXIBILITY = "flexibility"
    GENERAL_FITNESS = "general_fitness"
    SPORTS = "sports"
    REHABILITATION = "rehabilitation"


class TemplateDifficulty(str, enum.Enum):
    """Template difficulty levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class PurchaseStatus(str, enum.Enum):
    """Purchase status."""

    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"


class PayoutStatus(str, enum.Enum):
    """Payout request status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentProvider(str, enum.Enum):
    """Payment providers."""

    STRIPE = "stripe"
    PIX = "pix"
    MERCADOPAGO = "mercadopago"


class PayoutMethod(str, enum.Enum):
    """Payout methods."""

    PIX = "pix"
    BANK_TRANSFER = "bank_transfer"


class MarketplaceTemplate(Base, UUIDMixin, TimestampMixin):
    """Template listing in the marketplace."""

    __tablename__ = "marketplace_templates"

    template_type: Mapped[TemplateType] = mapped_column(
        Enum(TemplateType, name="template_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )

    # References to actual content
    workout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=True,
    )
    diet_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plans.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Creator (person or organization)
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Pricing
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Marketing
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    short_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_images: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Categorization
    category: Mapped[TemplateCategory | None] = mapped_column(
        Enum(TemplateCategory, name="template_category_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    difficulty: Mapped[TemplateDifficulty] = mapped_column(
        Enum(TemplateDifficulty, name="template_difficulty_enum", values_callable=lambda x: [e.value for e in x]),
        default=TemplateDifficulty.INTERMEDIATE,
        nullable=False,
    )
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Statistics
    purchase_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_average: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
    )
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    creator: Mapped["User"] = relationship("User", foreign_keys=[creator_id])
    organization: Mapped["Organization | None"] = relationship("Organization")
    workout: Mapped["Workout | None"] = relationship("Workout")
    diet_plan: Mapped["DietPlan | None"] = relationship("DietPlan")
    purchases: Mapped[list["TemplatePurchase"]] = relationship(
        "TemplatePurchase",
        back_populates="template",
        lazy="selectin",
    )
    reviews: Mapped[list["TemplateReview"]] = relationship(
        "TemplateReview",
        back_populates="template",
        lazy="selectin",
    )

    @property
    def price_display(self) -> str:
        """Format price for display."""
        if self.price_cents == 0:
            return "Grátis"
        price = self.price_cents / 100
        return f"R$ {price:.2f}"

    @property
    def is_free(self) -> bool:
        return self.price_cents == 0

    def __repr__(self) -> str:
        return f"<MarketplaceTemplate {self.title}>"


class TemplatePurchase(Base, UUIDMixin, TimestampMixin):
    """Purchase of a template."""

    __tablename__ = "template_purchases"

    marketplace_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Price at time of purchase
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Payment
    payment_provider: Mapped[PaymentProvider | None] = mapped_column(
        Enum(PaymentProvider, name="payment_provider_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    payment_provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[PurchaseStatus] = mapped_column(
        Enum(PurchaseStatus, name="purchase_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=PurchaseStatus.PENDING,
        nullable=False,
    )

    # Revenue split
    creator_earnings_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    platform_fee_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Result - duplicated content
    duplicated_workout_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="SET NULL"),
        nullable=True,
    )
    duplicated_diet_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plans.id", ondelete="SET NULL"),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    template: Mapped["MarketplaceTemplate"] = relationship(
        "MarketplaceTemplate",
        back_populates="purchases",
    )
    buyer: Mapped["User"] = relationship("User", foreign_keys=[buyer_id])
    duplicated_workout: Mapped["Workout | None"] = relationship(
        "Workout", foreign_keys=[duplicated_workout_id]
    )
    duplicated_diet_plan: Mapped["DietPlan | None"] = relationship(
        "DietPlan", foreign_keys=[duplicated_diet_plan_id]
    )
    review: Mapped["TemplateReview | None"] = relationship(
        "TemplateReview",
        back_populates="purchase",
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<TemplatePurchase {self.id} status={self.status}>"


class TemplateReview(Base, UUIDMixin, TimestampMixin):
    """Review of a purchased template."""

    __tablename__ = "template_reviews"

    marketplace_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    purchase_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("template_purchases.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_verified_purchase: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Relationships
    template: Mapped["MarketplaceTemplate"] = relationship(
        "MarketplaceTemplate",
        back_populates="reviews",
    )
    purchase: Mapped["TemplatePurchase"] = relationship(
        "TemplatePurchase",
        back_populates="review",
    )
    reviewer: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<TemplateReview {self.id} rating={self.rating}>"


class CreatorEarnings(Base, UUIDMixin):
    """Creator earnings balance."""

    __tablename__ = "creator_earnings"

    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )

    balance_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_earned_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_withdrawn_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    creator: Mapped["User | None"] = relationship("User")
    organization: Mapped["Organization | None"] = relationship("Organization")
    payouts: Mapped[list["CreatorPayout"]] = relationship(
        "CreatorPayout",
        back_populates="earnings",
        lazy="selectin",
    )

    @property
    def balance_display(self) -> str:
        return f"R$ {self.balance_cents / 100:.2f}"

    def __repr__(self) -> str:
        return f"<CreatorEarnings balance={self.balance_cents}>"


class CreatorPayout(Base, UUIDMixin, TimestampMixin):
    """Payout request from creator."""

    __tablename__ = "creator_payouts"

    earnings_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("creator_earnings.id", ondelete="CASCADE"),
        nullable=False,
    )

    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    payout_method: Mapped[PayoutMethod] = mapped_column(
        Enum(PayoutMethod, name="payout_method_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    payout_details: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # PIX key, bank account

    status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, name="payout_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=PayoutStatus.PENDING,
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payment_provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Relationships
    earnings: Mapped["CreatorEarnings"] = relationship(
        "CreatorEarnings",
        back_populates="payouts",
    )

    def __repr__(self) -> str:
        return f"<CreatorPayout {self.id} amount={self.amount_cents} status={self.status}>"


class OrganizationTemplateAccess(Base, UUIDMixin, TimestampMixin):
    """Templates made available by an organization to its members."""

    __tablename__ = "organization_template_access"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    marketplace_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("marketplace_templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Members can get this template free or with discount
    is_free_for_members: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    member_discount_percent: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization")
    template: Mapped["MarketplaceTemplate"] = relationship("MarketplaceTemplate")

    def __repr__(self) -> str:
        return f"<OrganizationTemplateAccess org={self.organization_id} template={self.marketplace_template_id}>"


# Import for type hints
from src.domains.nutrition.models import DietPlan  # noqa: E402, F401
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
from src.domains.workouts.models import Workout  # noqa: E402, F401
