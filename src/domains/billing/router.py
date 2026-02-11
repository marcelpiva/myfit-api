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
    ServicePlan,
    ServicePlanType,
)
from .schemas import (
    BillingSummaryResponse,
    ConsumeSessionRequest,
    ConsumeSessionResponse,
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
    ServicePlanCreate,
    ServicePlanListResponse,
    ServicePlanResponse,
    ServicePlanUpdate,
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

    # Received: filter by paid_at (when payment was actually received)
    received_query = select(Payment).where(and_(
        Payment.payee_id == current_user.id,
        Payment.status == PaymentStatus.PAID,
        Payment.paid_at.isnot(None),
        extract("year", Payment.paid_at) == year,
        extract("month", Payment.paid_at) == month,
    ))
    received_result = await db.execute(received_query)
    received_payments = list(received_result.scalars().all())

    # Pending: filter by due_date (when payment is due)
    pending_query = select(Payment).where(and_(
        Payment.payee_id == current_user.id,
        Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE]),
        extract("year", Payment.due_date) == year,
        extract("month", Payment.due_date) == month,
    ))
    pending_result = await db.execute(pending_query)
    pending_payments = list(pending_result.scalars().all())

    received_amount = sum(p.amount_cents for p in received_payments)
    pending_amount = sum(p.amount_cents for p in pending_payments)
    total_amount = received_amount + pending_amount

    return MonthlyRevenueResponse(
        year=year,
        month=month,
        received_amount_cents=received_amount,
        pending_amount_cents=pending_amount,
        total_amount_cents=total_amount,
        payments_count=len(received_payments) + len(pending_payments),
        paid_count=len(received_payments),
        pending_count=len(pending_payments),
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

    # Received: filter by paid_at (when payment was actually received)
    received_query = select(Payment).where(and_(
        Payment.payee_id == current_user.id,
        Payment.status == PaymentStatus.PAID,
        Payment.paid_at.isnot(None),
        extract("year", Payment.paid_at) == year,
        extract("month", Payment.paid_at) == month,
    ))
    received_result = await db.execute(received_query)
    received_payments = list(received_result.scalars().all())

    # Pending: filter by due_date (when payment is due)
    pending_query = select(Payment).where(and_(
        Payment.payee_id == current_user.id,
        Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE]),
        extract("year", Payment.due_date) == year,
        extract("month", Payment.due_date) == month,
    ))
    pending_result = await db.execute(pending_query)
    pending_payments = list(pending_result.scalars().all())

    received_amount = sum(p.amount_cents for p in received_payments)
    pending_amount = sum(p.amount_cents for p in pending_payments)
    total_amount = received_amount + pending_amount

    return MonthlyRevenueResponse(
        year=year,
        month=month,
        received_amount_cents=received_amount,
        pending_amount_cents=pending_amount,
        total_amount_cents=total_amount,
        payments_count=len(received_payments) + len(pending_payments),
        paid_count=len(received_payments),
        pending_count=len(pending_payments),
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


# --- Service Plans ---


def _service_plan_to_response(plan: ServicePlan) -> ServicePlanResponse:
    """Convert service plan model to response schema."""
    from .schemas import ScheduleSlotConfig

    schedule_config = None
    if plan.schedule_config:
        schedule_config = [
            ScheduleSlotConfig(**slot) for slot in plan.schedule_config
        ]

    return ServicePlanResponse(
        id=plan.id,
        student_id=plan.student_id,
        student_name=plan.student.name if plan.student else "Unknown",
        student_avatar_url=plan.student.avatar_url if plan.student else None,
        trainer_id=plan.trainer_id,
        trainer_name=plan.trainer.name if plan.trainer else "Unknown",
        organization_id=plan.organization_id,
        organization_name=plan.organization.name if plan.organization else None,
        name=plan.name,
        description=plan.description,
        plan_type=plan.plan_type,
        amount_cents=plan.amount_cents,
        currency=plan.currency,
        sessions_per_week=plan.sessions_per_week,
        recurrence_type=plan.recurrence_type,
        billing_day=plan.billing_day,
        schedule_config=schedule_config,
        total_sessions=plan.total_sessions,
        remaining_sessions=plan.remaining_sessions,
        package_expiry_date=plan.package_expiry_date,
        per_session_cents=plan.per_session_cents,
        start_date=plan.start_date,
        end_date=plan.end_date,
        is_active=plan.is_active,
        auto_renew=plan.auto_renew,
        notes=plan.notes,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.get("/service-plans", response_model=ServicePlanListResponse)
async def list_service_plans(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    student_id: Annotated[UUID | None, Query()] = None,
    active_only: Annotated[bool, Query()] = True,
    as_trainer: Annotated[bool, Query()] = True,
) -> ServicePlanListResponse:
    """List service plans for current user."""
    if as_trainer:
        base_filter = [ServicePlan.trainer_id == current_user.id]
    else:
        base_filter = [ServicePlan.student_id == current_user.id]

    if student_id:
        base_filter.append(ServicePlan.student_id == student_id)

    if active_only:
        base_filter.append(ServicePlan.is_active == True)  # noqa: E712

    # Count
    count_query = select(func.count(ServicePlan.id)).where(and_(*base_filter))
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Fetch
    query = (
        select(ServicePlan)
        .where(and_(*base_filter))
        .order_by(ServicePlan.created_at.desc())
    )

    result = await db.execute(query)
    plans = list(result.scalars().all())

    return ServicePlanListResponse(
        plans=[_service_plan_to_response(p) for p in plans],
        total=total,
    )


@router.post("/service-plans", response_model=ServicePlanResponse, status_code=status.HTTP_201_CREATED)
async def create_service_plan(
    request: ServicePlanCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServicePlanResponse:
    """Create a new service plan (trainer only)."""
    from datetime import timedelta

    # Verify student exists
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # Convert schedule_config to JSON-compatible format
    schedule_config_json = None
    if request.schedule_config:
        schedule_config_json = [
            slot.model_dump() for slot in request.schedule_config
        ]

    # Calculate package expiry date
    package_expiry_date = None
    if request.plan_type == ServicePlanType.PACKAGE and request.package_expiry_days:
        package_expiry_date = request.start_date + timedelta(days=request.package_expiry_days)

    plan = ServicePlan(
        student_id=request.student_id,
        trainer_id=current_user.id,
        organization_id=request.organization_id,
        name=request.name,
        description=request.description,
        plan_type=request.plan_type,
        amount_cents=request.amount_cents,
        currency=request.currency,
        # Recurring
        sessions_per_week=request.sessions_per_week,
        recurrence_type=request.recurrence_type,
        billing_day=request.billing_day,
        schedule_config=schedule_config_json,
        # Package
        total_sessions=request.total_sessions,
        remaining_sessions=request.total_sessions,  # Start with full balance
        package_expiry_date=package_expiry_date,
        # Drop-in
        per_session_cents=request.per_session_cents,
        # General
        start_date=request.start_date,
        end_date=request.end_date,
        auto_renew=request.auto_renew,
        notes=request.notes,
    )

    db.add(plan)
    await db.commit()
    await db.refresh(plan)

    # Reload with relationships
    plan_query = select(ServicePlan).where(ServicePlan.id == plan.id)
    result = await db.execute(plan_query)
    plan = result.scalar_one()

    return _service_plan_to_response(plan)


@router.get("/service-plans/{plan_id}", response_model=ServicePlanResponse)
async def get_service_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServicePlanResponse:
    """Get a specific service plan."""
    plan = await db.get(ServicePlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service plan not found",
        )

    if plan.student_id != current_user.id and plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _service_plan_to_response(plan)


@router.put("/service-plans/{plan_id}", response_model=ServicePlanResponse)
async def update_service_plan(
    plan_id: UUID,
    request: ServicePlanUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ServicePlanResponse:
    """Update a service plan (trainer only)."""
    plan = await db.get(ServicePlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service plan not found",
        )

    if plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can update this plan",
        )

    update_data = request.model_dump(exclude_unset=True)

    # Convert schedule_config if provided
    if "schedule_config" in update_data and update_data["schedule_config"] is not None:
        update_data["schedule_config"] = [
            slot.model_dump() if hasattr(slot, "model_dump") else slot
            for slot in update_data["schedule_config"]
        ]

    for field, value in update_data.items():
        setattr(plan, field, value)

    await db.commit()
    await db.refresh(plan)

    return _service_plan_to_response(plan)


@router.delete("/service-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_service_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Deactivate a service plan (trainer only)."""
    plan = await db.get(ServicePlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service plan not found",
        )

    if plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can deactivate this plan",
        )

    plan.is_active = False
    await db.commit()


@router.post("/service-plans/{plan_id}/consume-session", response_model=ConsumeSessionResponse)
async def consume_package_session(
    plan_id: UUID,
    request: ConsumeSessionRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsumeSessionResponse:
    """Consume one session credit from a package plan."""
    plan = await db.get(ServicePlan, plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service plan not found",
        )

    if plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can consume sessions",
        )

    if plan.plan_type != ServicePlanType.PACKAGE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only consume sessions from package plans",
        )

    if not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service plan is not active",
        )

    if plan.remaining_sessions is None or plan.remaining_sessions <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No remaining sessions in this package",
        )

    # Check expiry
    if plan.package_expiry_date and plan.package_expiry_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Package has expired",
        )

    plan.remaining_sessions -= 1

    # Auto-deactivate if no sessions left
    if plan.remaining_sessions == 0:
        plan.is_active = False

    await db.commit()
    await db.refresh(plan)

    return ConsumeSessionResponse(
        remaining_sessions=plan.remaining_sessions,
        total_sessions=plan.total_sessions or 0,
        plan_id=plan.id,
        plan_name=plan.name,
    )
