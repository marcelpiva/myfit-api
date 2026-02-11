"""Billing models for payments and subscriptions."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class PaymentStatus(str, enum.Enum):
    """Payment status."""

    PENDING = "pending"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    """Payment method."""

    PIX = "pix"
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    BANK_TRANSFER = "bank_transfer"
    CASH = "cash"
    OTHER = "other"


class PaymentType(str, enum.Enum):
    """Type of payment."""

    MONTHLY_FEE = "monthly_fee"  # Mensalidade
    SESSION = "session"  # Sessão avulsa
    PACKAGE = "package"  # Pacote de sessões
    ENROLLMENT = "enrollment"  # Matrícula
    OTHER = "other"


class RecurrenceType(str, enum.Enum):
    """Recurrence type for subscriptions."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUAL = "semi_annual"
    ANNUAL = "annual"


class ServicePlanType(str, enum.Enum):
    """Type of service plan between trainer and student."""

    RECURRING = "recurring"  # Recorrente mensal (X sessões/semana)
    PACKAGE = "package"  # Pacote de sessões (X sessões, validade Y dias)
    DROP_IN = "drop_in"  # Avulso (paga por sessão)
    FREE_TRIAL = "free_trial"  # Experimental grátis


class Payment(Base, UUIDMixin, TimestampMixin):
    """Payment record."""

    __tablename__ = "payments"

    # Who owes
    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who receives (trainer/organization)
    payee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Payment details
    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(PaymentType),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Amount in cents
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Status
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Dates
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Payment method (when paid)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        Enum(PaymentMethod),
        nullable=True,
    )
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Transaction ID, etc.

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # Only visible to payee

    # Reminders
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Recurrence (for subscriptions)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_type: Mapped[RecurrenceType | None] = mapped_column(
        Enum(RecurrenceType),
        nullable=True,
    )
    parent_payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Service plan link
    service_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    payer = relationship("User", foreign_keys=[payer_id], lazy="selectin")
    payee = relationship("User", foreign_keys=[payee_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
    parent_payment = relationship("Payment", remote_side="Payment.id", lazy="selectin")
    service_plan = relationship("ServicePlan", lazy="selectin")


class PaymentPlan(Base, UUIDMixin, TimestampMixin):
    """Payment plan / subscription for a student. (Legacy — use ServicePlan instead)"""

    __tablename__ = "payment_plans"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    recurrence_type: Mapped[RecurrenceType] = mapped_column(
        Enum(RecurrenceType),
        default=RecurrenceType.MONTHLY,
        nullable=False,
    )
    billing_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Day of month

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")


class ServicePlan(Base, UUIDMixin, TimestampMixin):
    """Service plan: the agreement between trainer and student.

    Supports 4 strategies:
    - RECURRING: monthly fee for X sessions/week with auto-schedule
    - PACKAGE: X sessions for a fixed price with expiry
    - DROP_IN: pay per session
    - FREE_TRIAL: complimentary sessions
    """

    __tablename__ = "service_plans"

    # Parties
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Definition
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan_type: Mapped[ServicePlanType] = mapped_column(
        Enum(ServicePlanType),
        nullable=False,
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="BRL", nullable=False)

    # Recurring-specific fields
    sessions_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recurrence_type: Mapped[RecurrenceType | None] = mapped_column(
        Enum(RecurrenceType),
        nullable=True,
    )
    billing_day: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Day of month (1-28)
    schedule_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
    )  # [{"day_of_week": 1, "time": "14:00", "duration_minutes": 60}]

    # Package-specific fields
    total_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remaining_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    package_expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Drop-in specific
    per_session_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # General
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    student = relationship("User", foreign_keys=[student_id], lazy="selectin")
    trainer = relationship("User", foreign_keys=[trainer_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
