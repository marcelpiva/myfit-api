"""Billing schemas for API validation."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .models import PaymentMethod, PaymentStatus, PaymentType, RecurrenceType


class PaymentCreate(BaseModel):
    """Schema for creating a payment."""

    payer_id: UUID
    payment_type: PaymentType
    description: str = Field(..., max_length=500)
    amount_cents: int = Field(..., gt=0)
    currency: str = Field(default="BRL", max_length=3)
    due_date: date
    notes: str | None = None
    is_recurring: bool = False
    recurrence_type: RecurrenceType | None = None
    organization_id: UUID | None = None


class PaymentUpdate(BaseModel):
    """Schema for updating a payment."""

    description: str | None = Field(default=None, max_length=500)
    amount_cents: int | None = Field(default=None, gt=0)
    due_date: date | None = None
    notes: str | None = None
    internal_notes: str | None = None


class PaymentResponse(BaseModel):
    """Schema for payment response."""

    id: UUID
    payer_id: UUID
    payer_name: str
    payer_email: str
    payer_avatar_url: str | None = None
    payee_id: UUID
    payee_name: str
    organization_id: UUID | None
    organization_name: str | None = None
    payment_type: PaymentType
    description: str
    amount_cents: int
    currency: str
    status: PaymentStatus
    due_date: date
    paid_at: datetime | None
    payment_method: PaymentMethod | None
    payment_reference: str | None
    notes: str | None
    is_recurring: bool
    recurrence_type: RecurrenceType | None
    reminder_sent: bool
    reminder_sent_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Schema for payment list response."""

    payments: list[PaymentResponse]
    total: int


class MarkPaidRequest(BaseModel):
    """Schema for marking payment as paid."""

    payment_method: PaymentMethod
    payment_reference: str | None = None
    paid_at: datetime | None = None  # Defaults to now


class SendReminderRequest(BaseModel):
    """Schema for sending payment reminder."""

    channel: str = Field(default="email", pattern="^(email|sms|push)$")
    message: str | None = None  # Custom message


class BillingSummaryResponse(BaseModel):
    """Schema for billing summary."""

    total_amount_cents: int
    paid_amount_cents: int
    pending_amount_cents: int
    overdue_amount_cents: int
    total_payments: int
    paid_count: int
    pending_count: int
    overdue_count: int
    currency: str = "BRL"


class MonthlyRevenueResponse(BaseModel):
    """Schema for monthly revenue summary for trainer dashboard."""

    year: int
    month: int
    received_amount_cents: int
    pending_amount_cents: int
    total_amount_cents: int
    payments_count: int
    paid_count: int
    pending_count: int
    currency: str = "BRL"


class RevenueHistoryItem(BaseModel):
    """Schema for a single month's revenue."""

    year: int
    month: int
    amount_cents: int


class RevenueHistoryResponse(BaseModel):
    """Schema for revenue history."""

    months: list[RevenueHistoryItem]
    total_cents: int
    currency: str = "BRL"


class PaymentPlanCreate(BaseModel):
    """Schema for creating a payment plan."""

    student_id: UUID
    name: str = Field(..., max_length=255)
    description: str | None = None
    amount_cents: int = Field(..., gt=0)
    currency: str = Field(default="BRL", max_length=3)
    recurrence_type: RecurrenceType = RecurrenceType.MONTHLY
    billing_day: int = Field(default=1, ge=1, le=28)
    start_date: date
    end_date: date | None = None
    organization_id: UUID | None = None


class PaymentPlanResponse(BaseModel):
    """Schema for payment plan response."""

    id: UUID
    student_id: UUID
    student_name: str
    trainer_id: UUID
    trainer_name: str
    organization_id: UUID | None
    name: str
    description: str | None
    amount_cents: int
    currency: str
    recurrence_type: RecurrenceType
    billing_day: int
    start_date: date
    end_date: date | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True
