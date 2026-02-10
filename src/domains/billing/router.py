"""Billing router for payments and subscriptions."""
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.email import send_payment_reminder_email
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.models import User

from .models import (
    Payment,
    PaymentPlan,
    PaymentStatus,
)
from .schemas import (
    BillingSummaryResponse,
    MarkPaidRequest,
    MonthlyRevenueResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentPlanCreate,
    PaymentPlanResponse,
    PaymentResponse,
    PaymentUpdate,
    RevenueHistoryItem,
    RevenueHistoryResponse,
    SendReminderRequest,
)

router = APIRouter(tags=["billing"])


def _payment_to_response(payment: Payment) -> PaymentResponse:
    """Convert payment model to response schema."""
    return PaymentResponse(
        id=payment.id,
        payer_id=payment.payer_id,
        payer_name=payment.payer.name if payment.payer else "Unknown",
        payer_email=payment.payer.email if payment.payer else "",
        payer_avatar_url=payment.payer.avatar_url if payment.payer else None,
        payee_id=payment.payee_id,
        payee_name=payment.payee.name if payment.payee else "Unknown",
        organization_id=payment.organization_id,
        organization_name=payment.organization.name if payment.organization else None,
        payment_type=payment.payment_type,
        description=payment.description,
        amount_cents=payment.amount_cents,
        currency=payment.currency,
        status=payment.status,
        due_date=payment.due_date,
        paid_at=payment.paid_at,
        payment_method=payment.payment_method,
        payment_reference=payment.payment_reference,
        notes=payment.notes,
        is_recurring=payment.is_recurring,
        recurrence_type=payment.recurrence_type,
        reminder_sent=payment.reminder_sent,
        reminder_sent_at=payment.reminder_sent_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


def _payment_plan_to_response(plan: PaymentPlan) -> PaymentPlanResponse:
    """Convert payment plan model to response schema."""
    return PaymentPlanResponse(
        id=plan.id,
        student_id=plan.student_id,
        student_name=plan.student.name if plan.student else "Unknown",
        trainer_id=plan.trainer_id,
        trainer_name=plan.trainer.name if plan.trainer else "Unknown",
        organization_id=plan.organization_id,
        name=plan.name,
        description=plan.description,
        amount_cents=plan.amount_cents,
        currency=plan.currency,
        recurrence_type=plan.recurrence_type,
        billing_day=plan.billing_day,
        start_date=plan.start_date,
        end_date=plan.end_date,
        is_active=plan.is_active,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/payments", response_model=PaymentListResponse)
async def list_payments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    as_payee: Annotated[bool, Query()] = False,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentListResponse:
    """List payments for current user (as payer or payee)."""
    # Build filter
    if as_payee:
        base_filter = [Payment.payee_id == current_user.id]
    else:
        base_filter = [Payment.payer_id == current_user.id]

    if status_filter:
        base_filter.append(Payment.status == status_filter)

    if from_date:
        base_filter.append(Payment.due_date >= from_date)

    if to_date:
        base_filter.append(Payment.due_date <= to_date)

    # Get total count
    count_query = select(func.count(Payment.id)).where(and_(*base_filter))
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Get payments
    query = (
        select(Payment)
        .where(and_(*base_filter))
        .order_by(Payment.due_date.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    payments = list(result.scalars().all())

    return PaymentListResponse(
        payments=[_payment_to_response(p) for p in payments],
        total=total,
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    """Get a specific payment."""
    payment = await db.get(Payment, payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    # Check access
    if payment.payer_id != current_user.id and payment.payee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _payment_to_response(payment)


@router.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    request: PaymentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    """Create a new payment (as payee/trainer)."""
    # Verify payer exists
    payer = await db.get(User, request.payer_id)
    if not payer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payer not found",
        )

    payment = Payment(
        payer_id=request.payer_id,
        payee_id=current_user.id,
        organization_id=request.organization_id,
        payment_type=request.payment_type,
        description=request.description,
        amount_cents=request.amount_cents,
        currency=request.currency,
        due_date=request.due_date,
        notes=request.notes,
        is_recurring=request.is_recurring,
        recurrence_type=request.recurrence_type,
        status=PaymentStatus.PENDING,
    )

    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    # Reload with relationships
    payment_query = select(Payment).where(Payment.id == payment.id)
    result = await db.execute(payment_query)
    payment = result.scalar_one()

    return _payment_to_response(payment)


@router.put("/payments/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: UUID,
    request: PaymentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    """Update a payment (only payee can update)."""
    payment = await db.get(Payment, payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.payee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the payee can update this payment",
        )

    if payment.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update a paid payment",
        )

    # Update fields
    if request.description is not None:
        payment.description = request.description
    if request.amount_cents is not None:
        payment.amount_cents = request.amount_cents
    if request.due_date is not None:
        payment.due_date = request.due_date
    if request.notes is not None:
        payment.notes = request.notes
    if request.internal_notes is not None:
        payment.internal_notes = request.internal_notes

    await db.commit()
    await db.refresh(payment)

    return _payment_to_response(payment)


@router.post("/payments/{payment_id}/mark-paid", response_model=PaymentResponse)
async def mark_payment_paid(
    payment_id: UUID,
    request: MarkPaidRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentResponse:
    """Mark a payment as paid (only payee can mark)."""
    payment = await db.get(Payment, payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.payee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the payee can mark this payment as paid",
        )

    if payment.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment is already marked as paid",
        )

    payment.status = PaymentStatus.PAID
    payment.payment_method = request.payment_method
    payment.payment_reference = request.payment_reference
    payment.paid_at = request.paid_at or datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(payment)

    return _payment_to_response(payment)


@router.post("/payments/{payment_id}/reminder", status_code=status.HTTP_204_NO_CONTENT)
async def send_payment_reminder(
    payment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    request: SendReminderRequest | None = None,
) -> None:
    """Send a payment reminder to the payer."""
    payment = await db.get(Payment, payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.payee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the payee can send reminders",
        )

    if payment.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment is already paid",
        )

    # Send payment reminder email in background
    payer = await db.get(User, payment.payer_id)
    if payer:
        background_tasks.add_task(
            send_payment_reminder_email,
            to_email=payer.email,
            name=payer.name,
            amount=payment.amount_cents / 100,
            due_date=payment.due_date.strftime("%d/%m/%Y") if payment.due_date else "Não definido",
            trainer_name=current_user.name,
        )

    payment.reminder_sent = True
    payment.reminder_sent_at = datetime.now(timezone.utc)

    await db.commit()


@router.delete("/payments/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_payment(
    payment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Cancel a payment (only payee can cancel unpaid payments)."""
    payment = await db.get(Payment, payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )

    if payment.payee_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the payee can cancel this payment",
        )

    if payment.status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a paid payment",
        )

    payment.status = PaymentStatus.CANCELLED
    await db.commit()


@router.get("/summary", response_model=BillingSummaryResponse)
async def get_billing_summary(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_payee: Annotated[bool, Query()] = False,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> BillingSummaryResponse:
    """Get billing summary for current user."""
    # Build filter
    if as_payee:
        base_filter = [Payment.payee_id == current_user.id]
    else:
        base_filter = [Payment.payer_id == current_user.id]

    if from_date:
        base_filter.append(Payment.due_date >= from_date)

    if to_date:
        base_filter.append(Payment.due_date <= to_date)

    # Exclude cancelled payments from summary
    base_filter.append(Payment.status != PaymentStatus.CANCELLED)

    # Get summary stats
    query = select(Payment).where(and_(*base_filter))
    result = await db.execute(query)
    payments = list(result.scalars().all())

    total_amount = sum(p.amount_cents for p in payments)
    paid_amount = sum(p.amount_cents for p in payments if p.status == PaymentStatus.PAID)
    pending_amount = sum(p.amount_cents for p in payments if p.status == PaymentStatus.PENDING)
    overdue_amount = sum(p.amount_cents for p in payments if p.status == PaymentStatus.OVERDUE)

    paid_count = sum(1 for p in payments if p.status == PaymentStatus.PAID)
    pending_count = sum(1 for p in payments if p.status == PaymentStatus.PENDING)
    overdue_count = sum(1 for p in payments if p.status == PaymentStatus.OVERDUE)

    return BillingSummaryResponse(
        total_amount_cents=total_amount,
        paid_amount_cents=paid_amount,
        pending_amount_cents=pending_amount,
        overdue_amount_cents=overdue_amount,
        total_payments=len(payments),
        paid_count=paid_count,
        pending_count=pending_count,
        overdue_count=overdue_count,
    )


# --- Payment Plans ---


@router.get("/plans", response_model=list[PaymentPlanResponse])
async def list_payment_plans(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    active_only: Annotated[bool, Query()] = True,
) -> list[PaymentPlanResponse]:
    """List payment plans for current user (as student or trainer)."""
    if as_trainer:
        base_filter = [PaymentPlan.trainer_id == current_user.id]
    else:
        base_filter = [PaymentPlan.student_id == current_user.id]

    if active_only:
        base_filter.append(PaymentPlan.is_active == True)

    query = (
        select(PaymentPlan)
        .where(and_(*base_filter))
        .order_by(PaymentPlan.created_at.desc())
    )

    result = await db.execute(query)
    plans = list(result.scalars().all())

    return [_payment_plan_to_response(p) for p in plans]


@router.post("/plans", response_model=PaymentPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_plan(
    request: PaymentPlanCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentPlanResponse:
    """Create a new payment plan (as trainer)."""
    # Verify student exists
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    plan = PaymentPlan(
        student_id=request.student_id,
        trainer_id=current_user.id,
        organization_id=request.organization_id,
        name=request.name,
        description=request.description,
        amount_cents=request.amount_cents,
        currency=request.currency,
        recurrence_type=request.recurrence_type,
        billing_day=request.billing_day,
        start_date=request.start_date,
        end_date=request.end_date,
    )

    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # Reload with relationships
    plan_query = select(PaymentPlan).where(PaymentPlan.id == plan.id)
    result = await db.execute(plan_query)
    plan = result.scalar_one()

    return _payment_plan_to_response(plan)


@router.get("/plans/{plan_id}", response_model=PaymentPlanResponse)
async def get_payment_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentPlanResponse:
    """Get a specific payment plan."""
    plan = await db.get(PaymentPlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment plan not found",
        )

    # Check access
    if plan.student_id != current_user.id and plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _payment_plan_to_response(plan)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_payment_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Deactivate a payment plan (trainer only)."""
    plan = await db.get(PaymentPlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment plan not found",
        )

    if plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can deactivate this plan",
        )

    plan.is_active = False
    await db.commit()


# --- Student payments for trainer view ---


@router.get("/students/{student_id}/payments", response_model=PaymentListResponse)
async def list_student_payments(
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaymentListResponse:
    """List payments for a specific student (trainer view)."""
    # Build filter - trainer is payee, student is payer
    base_filter = [
        Payment.payee_id == current_user.id,
        Payment.payer_id == student_id,
    ]

    if status_filter:
        base_filter.append(Payment.status == status_filter)

    # Get total count
    count_query = select(func.count(Payment.id)).where(and_(*base_filter))
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Get payments
    query = (
        select(Payment)
        .where(and_(*base_filter))
        .order_by(Payment.due_date.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    payments = list(result.scalars().all())

    return PaymentListResponse(
        payments=[_payment_to_response(p) for p in payments],
        total=total,
    )


# --- Revenue endpoints for trainer dashboard ---


@router.get("/revenue/current-month", response_model=MonthlyRevenueResponse)
async def get_current_month_revenue(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MonthlyRevenueResponse:
    """Get current month's revenue for trainer dashboard."""
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month

    # Get all payments for this month where current user is payee
    base_filter = [
        Payment.payee_id == current_user.id,
        extract("year", Payment.due_date) == year,
        extract("month", Payment.due_date) == month,
        Payment.status != PaymentStatus.CANCELLED,
    ]

    query = select(Payment).where(and_(*base_filter))
    result = await db.execute(query)
    payments = list(result.scalars().all())

    received_amount = sum(p.amount_cents for p in payments if p.status == PaymentStatus.PAID)
    pending_amount = sum(
        p.amount_cents for p in payments if p.status in [PaymentStatus.PENDING, PaymentStatus.OVERDUE]
    )
    total_amount = received_amount + pending_amount
    paid_count = sum(1 for p in payments if p.status == PaymentStatus.PAID)
    pending_count = sum(1 for p in payments if p.status in [PaymentStatus.PENDING, PaymentStatus.OVERDUE])

    return MonthlyRevenueResponse(
        year=year,
        month=month,
        received_amount_cents=received_amount,
        pending_amount_cents=pending_amount,
        total_amount_cents=total_amount,
        payments_count=len(payments),
        paid_count=paid_count,
        pending_count=pending_count,
    )


@router.get("/revenue/month/{year}/{month}", response_model=MonthlyRevenueResponse)
async def get_month_revenue(
    year: int,
    month: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MonthlyRevenueResponse:
    """Get revenue for a specific month for trainer dashboard."""
    if month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be between 1 and 12",
        )

    # Get all payments for this month where current user is payee
    base_filter = [
        Payment.payee_id == current_user.id,
        extract("year", Payment.due_date) == year,
        extract("month", Payment.due_date) == month,
        Payment.status != PaymentStatus.CANCELLED,
    ]

    query = select(Payment).where(and_(*base_filter))
    result = await db.execute(query)
    payments = list(result.scalars().all())

    received_amount = sum(p.amount_cents for p in payments if p.status == PaymentStatus.PAID)
    pending_amount = sum(
        p.amount_cents for p in payments if p.status in [PaymentStatus.PENDING, PaymentStatus.OVERDUE]
    )
    total_amount = received_amount + pending_amount
    paid_count = sum(1 for p in payments if p.status == PaymentStatus.PAID)
    pending_count = sum(1 for p in payments if p.status in [PaymentStatus.PENDING, PaymentStatus.OVERDUE])

    return MonthlyRevenueResponse(
        year=year,
        month=month,
        received_amount_cents=received_amount,
        pending_amount_cents=pending_amount,
        total_amount_cents=total_amount,
        payments_count=len(payments),
        paid_count=paid_count,
        pending_count=pending_count,
    )


@router.get("/revenue/history", response_model=RevenueHistoryResponse)
async def get_revenue_history(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    months_count: Annotated[int, Query(ge=1, le=24)] = 12,
) -> RevenueHistoryResponse:
    """Get revenue history for the last N months."""
    now = datetime.now(timezone.utc)

    # Calculate the start date (N months ago)
    start_year = now.year
    start_month = now.month - months_count + 1
    while start_month <= 0:
        start_month += 12
        start_year -= 1

    # Get all paid payments in the period
    base_filter = [
        Payment.payee_id == current_user.id,
        Payment.status == PaymentStatus.PAID,
        Payment.paid_at.isnot(None),
    ]

    # Build date range filter
    start_date = date(start_year, start_month, 1)
    base_filter.append(Payment.paid_at >= datetime.combine(start_date, datetime.min.time()))

    query = select(Payment).where(and_(*base_filter))
    result = await db.execute(query)
    payments = list(result.scalars().all())

    # Group by month
    monthly_totals: dict[tuple[int, int], int] = {}
    for payment in payments:
        if payment.paid_at:
            key = (payment.paid_at.year, payment.paid_at.month)
            monthly_totals[key] = monthly_totals.get(key, 0) + payment.amount_cents

    # Build response
    months = []
    current = now
    for _ in range(months_count):
        key = (current.year, current.month)
        months.append(
            RevenueHistoryItem(
                year=current.year,
                month=current.month,
                amount_cents=monthly_totals.get(key, 0),
            )
        )
        # Go to previous month
        if current.month == 1:
            current = current.replace(year=current.year - 1, month=12)
        else:
            current = current.replace(month=current.month - 1)

    # Reverse to have oldest first
    months.reverse()

    total = sum(m.amount_cents for m in months)

    return RevenueHistoryResponse(
        months=months,
        total_cents=total,
    )
