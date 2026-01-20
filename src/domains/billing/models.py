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
    func,
)
from sqlalchemy.dialects.postgresql import UUID
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

    # Relationships
    payer = relationship("User", foreign_keys=[payer_id], lazy="selectin")
    payee = relationship("User", foreign_keys=[payee_id], lazy="selectin")
    organization = relationship("Organization", lazy="selectin")
    parent_payment = relationship("Payment", remote_side="Payment.id", lazy="selectin")


class PaymentPlan(Base, UUIDMixin, TimestampMixin):
    """Payment plan / subscription for a student."""

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
