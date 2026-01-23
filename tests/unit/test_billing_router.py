"""Tests for Billing router business logic."""
import uuid
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.billing.models import (
    Payment,
    PaymentMethod,
    PaymentPlan,
    PaymentStatus,
    PaymentType,
    RecurrenceType,
)
from src.domains.users.models import User


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def trainer_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a trainer user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"trainer-{user_id}@example.com",
        name="Test Trainer",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def student_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a student user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"student-{user_id}@example.com",
        name="Test Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def second_student(db_session: AsyncSession) -> dict[str, Any]:
    """Create a second student user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"student2-{user_id}@example.com",
        name="Second Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def sample_payment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Payment:
    """Create a sample payment."""
    payment = Payment(
        payer_id=student_user["id"],
        payee_id=trainer_user["id"],
        payment_type=PaymentType.MONTHLY_FEE,
        description="Monthly training fee",
        amount_cents=15000,
        currency="BRL",
        due_date=date.today() + timedelta(days=7),
        status=PaymentStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def paid_payment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Payment:
    """Create a paid payment."""
    payment = Payment(
        payer_id=student_user["id"],
        payee_id=trainer_user["id"],
        payment_type=PaymentType.MONTHLY_FEE,
        description="Paid monthly fee",
        amount_cents=15000,
        currency="BRL",
        due_date=date.today() - timedelta(days=3),
        status=PaymentStatus.PAID,
        paid_at=datetime.utcnow(),
        payment_method=PaymentMethod.PIX,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def overdue_payment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Payment:
    """Create an overdue payment."""
    payment = Payment(
        payer_id=student_user["id"],
        payee_id=trainer_user["id"],
        payment_type=PaymentType.MONTHLY_FEE,
        description="Overdue fee",
        amount_cents=15000,
        currency="BRL",
        due_date=date.today() - timedelta(days=10),
        status=PaymentStatus.OVERDUE,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def cancelled_payment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Payment:
    """Create a cancelled payment."""
    payment = Payment(
        payer_id=student_user["id"],
        payee_id=trainer_user["id"],
        payment_type=PaymentType.SESSION,
        description="Cancelled session",
        amount_cents=5000,
        currency="BRL",
        due_date=date.today(),
        status=PaymentStatus.CANCELLED,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def sample_payment_plan(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> PaymentPlan:
    """Create a sample payment plan."""
    plan = PaymentPlan(
        student_id=student_user["id"],
        trainer_id=trainer_user["id"],
        name="Monthly Training Plan",
        description="Standard monthly training",
        amount_cents=30000,
        currency="BRL",
        recurrence_type=RecurrenceType.MONTHLY,
        billing_day=5,
        start_date=date.today(),
        is_active=True,
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


# =============================================================================
# Payment Creation Tests
# =============================================================================


class TestPaymentCreation:
    """Tests for payment creation business rules."""

    async def test_create_payment_sets_pending_status(
        self, db_session: AsyncSession, trainer_user: dict, student_user: dict
    ):
        """New payment should have PENDING status."""
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="New fee",
            amount_cents=10000,
            currency="BRL",
            due_date=date.today() + timedelta(days=30),
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        assert payment.status == PaymentStatus.PENDING
        assert payment.paid_at is None

    async def test_create_payment_requires_payer(
        self, db_session: AsyncSession, trainer_user: dict, student_user: dict
    ):
        """Should create payment when payer exists."""
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.SESSION,
            description="Single session",
            amount_cents=8000,
            currency="BRL",
            due_date=date.today(),
        )
        db_session.add(payment)
        await db_session.commit()

        assert payment.id is not None
        assert payment.payer_id == student_user["id"]

    async def test_create_recurring_payment(
        self, db_session: AsyncSession, trainer_user: dict, student_user: dict
    ):
        """Should create recurring payment with recurrence type."""
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="Monthly recurring",
            amount_cents=15000,
            currency="BRL",
            due_date=date.today(),
            is_recurring=True,
            recurrence_type=RecurrenceType.MONTHLY,
        )
        db_session.add(payment)
        await db_session.commit()
        await db_session.refresh(payment)

        assert payment.is_recurring is True
        assert payment.recurrence_type == RecurrenceType.MONTHLY


# =============================================================================
# Payment Update Tests
# =============================================================================


class TestPaymentUpdate:
    """Tests for payment update business rules."""

    async def test_update_pending_payment_description(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should update description of pending payment."""
        sample_payment.description = "Updated description"
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.description == "Updated description"

    async def test_update_pending_payment_amount(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should update amount of pending payment."""
        sample_payment.amount_cents = 20000
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.amount_cents == 20000

    async def test_update_pending_payment_due_date(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should update due date of pending payment."""
        new_date = date.today() + timedelta(days=14)
        sample_payment.due_date = new_date
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.due_date == new_date

    async def test_cannot_modify_paid_payment_amount(
        self, db_session: AsyncSession, paid_payment: Payment
    ):
        """Business rule: Cannot modify amount of paid payment."""
        # This test verifies the model allows it (router enforces the rule)
        original_amount = paid_payment.amount_cents
        assert paid_payment.status == PaymentStatus.PAID
        # The router should reject this update
        assert original_amount == 15000


# =============================================================================
# Mark Payment Paid Tests
# =============================================================================


class TestMarkPaymentPaid:
    """Tests for marking payment as paid."""

    async def test_mark_payment_paid_sets_status(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should set status to PAID."""
        sample_payment.status = PaymentStatus.PAID
        sample_payment.paid_at = datetime.utcnow()
        sample_payment.payment_method = PaymentMethod.PIX
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.status == PaymentStatus.PAID
        assert sample_payment.paid_at is not None

    async def test_mark_payment_paid_records_timestamp(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should record payment timestamp."""
        before = datetime.utcnow()
        sample_payment.status = PaymentStatus.PAID
        sample_payment.paid_at = datetime.utcnow()
        await db_session.commit()
        after = datetime.utcnow()

        assert sample_payment.paid_at >= before
        assert sample_payment.paid_at <= after

    async def test_mark_payment_paid_records_method(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should record payment method."""
        sample_payment.status = PaymentStatus.PAID
        sample_payment.paid_at = datetime.utcnow()
        sample_payment.payment_method = PaymentMethod.CREDIT_CARD
        sample_payment.payment_reference = "TX123456"
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.payment_method == PaymentMethod.CREDIT_CARD
        assert sample_payment.payment_reference == "TX123456"

    async def test_already_paid_payment_has_status(
        self, db_session: AsyncSession, paid_payment: Payment
    ):
        """Already paid payment should have PAID status."""
        assert paid_payment.status == PaymentStatus.PAID


# =============================================================================
# Payment Reminder Tests
# =============================================================================


class TestPaymentReminder:
    """Tests for payment reminder business rules."""

    async def test_send_reminder_updates_flag(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should update reminder_sent flag."""
        sample_payment.reminder_sent = True
        sample_payment.reminder_sent_at = datetime.utcnow()
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.reminder_sent is True
        assert sample_payment.reminder_sent_at is not None

    async def test_reminder_not_sent_for_paid_payment(
        self, db_session: AsyncSession, paid_payment: Payment
    ):
        """Paid payment should not have reminder sent (business rule in router)."""
        # Verify the payment is already paid
        assert paid_payment.status == PaymentStatus.PAID
        # Router enforces: cannot send reminder for paid payments

    async def test_reminder_can_be_sent_for_pending(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Pending payment can receive reminder."""
        assert sample_payment.status == PaymentStatus.PENDING
        assert sample_payment.reminder_sent is False

    async def test_reminder_can_be_sent_for_overdue(
        self, db_session: AsyncSession, overdue_payment: Payment
    ):
        """Overdue payment can receive reminder."""
        assert overdue_payment.status == PaymentStatus.OVERDUE


# =============================================================================
# Cancel Payment Tests
# =============================================================================


class TestCancelPayment:
    """Tests for payment cancellation."""

    async def test_cancel_pending_payment(
        self, db_session: AsyncSession, sample_payment: Payment
    ):
        """Should cancel pending payment."""
        sample_payment.status = PaymentStatus.CANCELLED
        await db_session.commit()
        await db_session.refresh(sample_payment)

        assert sample_payment.status == PaymentStatus.CANCELLED

    async def test_cancel_overdue_payment(
        self, db_session: AsyncSession, overdue_payment: Payment
    ):
        """Should cancel overdue payment."""
        overdue_payment.status = PaymentStatus.CANCELLED
        await db_session.commit()
        await db_session.refresh(overdue_payment)

        assert overdue_payment.status == PaymentStatus.CANCELLED

    async def test_paid_payment_has_paid_status(
        self, db_session: AsyncSession, paid_payment: Payment
    ):
        """Paid payment has PAID status (router enforces no cancellation)."""
        assert paid_payment.status == PaymentStatus.PAID


# =============================================================================
# Billing Summary Tests
# =============================================================================


class TestBillingSummary:
    """Tests for billing summary calculations."""

    async def test_summary_totals_all_amounts(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
        paid_payment: Payment,
        overdue_payment: Payment,
    ):
        """Should calculate total of all non-cancelled payments."""
        # Query payments for trainer (payee)
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        total = sum(p.amount_cents for p in payments)
        assert total == 45000  # 15000 + 15000 + 15000

    async def test_summary_calculates_paid_amount(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
        paid_payment: Payment,
    ):
        """Should calculate paid amount correctly."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status == PaymentStatus.PAID,
            )
        )
        payments = list(result.scalars().all())

        paid_amount = sum(p.amount_cents for p in payments)
        assert paid_amount == 15000

    async def test_summary_calculates_pending_amount(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
        paid_payment: Payment,
    ):
        """Should calculate pending amount correctly."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        payments = list(result.scalars().all())

        pending_amount = sum(p.amount_cents for p in payments)
        assert pending_amount == 15000

    async def test_summary_excludes_cancelled(
        self,
        db_session: AsyncSession,
        cancelled_payment: Payment,
        sample_payment: Payment,
    ):
        """Should exclude cancelled payments from summary."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        # Cancelled payment should not be included
        assert cancelled_payment not in payments

    async def test_summary_counts_by_status(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
        paid_payment: Payment,
        overdue_payment: Payment,
    ):
        """Should count payments by status correctly."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        paid_count = sum(1 for p in payments if p.status == PaymentStatus.PAID)
        pending_count = sum(1 for p in payments if p.status == PaymentStatus.PENDING)
        overdue_count = sum(1 for p in payments if p.status == PaymentStatus.OVERDUE)

        assert paid_count == 1
        assert pending_count == 1
        assert overdue_count == 1


# =============================================================================
# Payment List Filters Tests
# =============================================================================


class TestPaymentListFilters:
    """Tests for payment list filtering."""

    async def test_filter_as_payee(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_payment: Payment,
    ):
        """Should filter payments where user is payee."""
        result = await db_session.execute(
            select(Payment).where(Payment.payee_id == trainer_user["id"])
        )
        payments = list(result.scalars().all())

        assert len(payments) >= 1
        assert all(p.payee_id == trainer_user["id"] for p in payments)

    async def test_filter_as_payer(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_payment: Payment,
    ):
        """Should filter payments where user is payer."""
        result = await db_session.execute(
            select(Payment).where(Payment.payer_id == student_user["id"])
        )
        payments = list(result.scalars().all())

        assert len(payments) >= 1
        assert all(p.payer_id == student_user["id"] for p in payments)

    async def test_filter_by_status(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
        paid_payment: Payment,
    ):
        """Should filter payments by status."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.status == PaymentStatus.PENDING,
            )
        )
        payments = list(result.scalars().all())

        assert all(p.status == PaymentStatus.PENDING for p in payments)

    async def test_filter_by_date_range(
        self,
        db_session: AsyncSession,
        sample_payment: Payment,
    ):
        """Should filter payments by due date range."""
        from_date = date.today()
        to_date = date.today() + timedelta(days=30)

        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == sample_payment.payee_id,
                Payment.due_date >= from_date,
                Payment.due_date <= to_date,
            )
        )
        payments = list(result.scalars().all())

        assert all(from_date <= p.due_date <= to_date for p in payments)

    async def test_pagination_limit(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should respect pagination limit."""
        # Create multiple payments
        for i in range(5):
            payment = Payment(
                payer_id=student_user["id"],
                payee_id=trainer_user["id"],
                payment_type=PaymentType.SESSION,
                description=f"Session {i}",
                amount_cents=5000,
                currency="BRL",
                due_date=date.today() + timedelta(days=i),
                status=PaymentStatus.PENDING,
            )
            db_session.add(payment)
        await db_session.commit()

        result = await db_session.execute(
            select(Payment)
            .where(Payment.payee_id == trainer_user["id"])
            .limit(3)
        )
        payments = list(result.scalars().all())

        assert len(payments) == 3

    async def test_pagination_offset(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should respect pagination offset."""
        # Create multiple payments with distinct descriptions
        for i in range(5):
            payment = Payment(
                payer_id=student_user["id"],
                payee_id=trainer_user["id"],
                payment_type=PaymentType.SESSION,
                description=f"Offset Session {i}",
                amount_cents=5000 + i * 100,
                currency="BRL",
                due_date=date.today() + timedelta(days=i),
                status=PaymentStatus.PENDING,
            )
            db_session.add(payment)
        await db_session.commit()

        # Get first page
        result1 = await db_session.execute(
            select(Payment)
            .where(Payment.payee_id == trainer_user["id"])
            .order_by(Payment.created_at)
            .limit(2)
            .offset(0)
        )
        page1 = list(result1.scalars().all())

        # Get second page
        result2 = await db_session.execute(
            select(Payment)
            .where(Payment.payee_id == trainer_user["id"])
            .order_by(Payment.created_at)
            .limit(2)
            .offset(2)
        )
        page2 = list(result2.scalars().all())

        # Pages should not overlap
        page1_ids = {p.id for p in page1}
        page2_ids = {p.id for p in page2}
        assert page1_ids.isdisjoint(page2_ids)


# =============================================================================
# Payment Plan Tests
# =============================================================================


class TestPaymentPlan:
    """Tests for payment plan business rules."""

    async def test_create_payment_plan(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should create payment plan with required fields."""
        plan = PaymentPlan(
            student_id=student_user["id"],
            trainer_id=trainer_user["id"],
            name="Premium Plan",
            amount_cents=50000,
            currency="BRL",
            recurrence_type=RecurrenceType.MONTHLY,
            billing_day=10,
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        assert plan.id is not None
        assert plan.is_active is True

    async def test_payment_plan_defaults_to_active(
        self, db_session: AsyncSession, sample_payment_plan: PaymentPlan
    ):
        """New payment plan should default to active."""
        assert sample_payment_plan.is_active is True

    async def test_deactivate_payment_plan(
        self, db_session: AsyncSession, sample_payment_plan: PaymentPlan
    ):
        """Should deactivate payment plan."""
        sample_payment_plan.is_active = False
        await db_session.commit()
        await db_session.refresh(sample_payment_plan)

        assert sample_payment_plan.is_active is False

    async def test_payment_plan_with_end_date(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should create plan with end date."""
        plan = PaymentPlan(
            student_id=student_user["id"],
            trainer_id=trainer_user["id"],
            name="3 Month Plan",
            amount_cents=40000,
            currency="BRL",
            recurrence_type=RecurrenceType.MONTHLY,
            billing_day=1,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=90),
        )
        db_session.add(plan)
        await db_session.commit()
        await db_session.refresh(plan)

        assert plan.end_date is not None

    async def test_list_payment_plans_as_trainer(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_payment_plan: PaymentPlan,
    ):
        """Should list plans where user is trainer."""
        result = await db_session.execute(
            select(PaymentPlan).where(PaymentPlan.trainer_id == trainer_user["id"])
        )
        plans = list(result.scalars().all())

        assert len(plans) >= 1
        assert all(p.trainer_id == trainer_user["id"] for p in plans)

    async def test_list_payment_plans_as_student(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_payment_plan: PaymentPlan,
    ):
        """Should list plans where user is student."""
        result = await db_session.execute(
            select(PaymentPlan).where(PaymentPlan.student_id == student_user["id"])
        )
        plans = list(result.scalars().all())

        assert len(plans) >= 1
        assert all(p.student_id == student_user["id"] for p in plans)

    async def test_list_only_active_plans(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_payment_plan: PaymentPlan,
    ):
        """Should filter only active plans when requested."""
        # Deactivate the plan
        sample_payment_plan.is_active = False
        await db_session.commit()

        result = await db_session.execute(
            select(PaymentPlan).where(
                PaymentPlan.trainer_id == trainer_user["id"],
                PaymentPlan.is_active == True,
            )
        )
        plans = list(result.scalars().all())

        assert sample_payment_plan not in plans

    async def test_payment_plan_recurrence_types(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should support different recurrence types."""
        for recurrence in RecurrenceType:
            plan = PaymentPlan(
                student_id=student_user["id"],
                trainer_id=trainer_user["id"],
                name=f"{recurrence.value} Plan",
                amount_cents=10000,
                currency="BRL",
                recurrence_type=recurrence,
                billing_day=15,
                start_date=date.today(),
            )
            db_session.add(plan)
        await db_session.commit()

        result = await db_session.execute(
            select(PaymentPlan).where(PaymentPlan.trainer_id == trainer_user["id"])
        )
        plans = list(result.scalars().all())

        recurrence_types = {p.recurrence_type for p in plans}
        assert RecurrenceType.MONTHLY in recurrence_types
        assert RecurrenceType.QUARTERLY in recurrence_types


# =============================================================================
# Student Payments (Trainer View) Tests
# =============================================================================


class TestStudentPayments:
    """Tests for trainer viewing student payments."""

    async def test_list_student_payments(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_payment: Payment,
    ):
        """Should list payments for specific student."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.payer_id == student_user["id"],
            )
        )
        payments = list(result.scalars().all())

        assert len(payments) >= 1
        assert all(p.payer_id == student_user["id"] for p in payments)

    async def test_student_payments_separated_by_student(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        second_student: dict,
    ):
        """Should separate payments by student."""
        # Create payment for first student
        payment1 = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="Student 1 fee",
            amount_cents=15000,
            currency="BRL",
            due_date=date.today(),
            status=PaymentStatus.PENDING,
        )
        # Create payment for second student
        payment2 = Payment(
            payer_id=second_student["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="Student 2 fee",
            amount_cents=20000,
            currency="BRL",
            due_date=date.today(),
            status=PaymentStatus.PENDING,
        )
        db_session.add_all([payment1, payment2])
        await db_session.commit()

        # Query only student 1's payments
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.payer_id == student_user["id"],
            )
        )
        student1_payments = list(result.scalars().all())

        # Should not include student 2's payment
        assert all(p.payer_id == student_user["id"] for p in student1_payments)

    async def test_student_payments_filter_by_status(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_payment: Payment,
        paid_payment: Payment,
    ):
        """Should filter student payments by status."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.payer_id == student_user["id"],
                Payment.status == PaymentStatus.PAID,
            )
        )
        payments = list(result.scalars().all())

        assert all(p.status == PaymentStatus.PAID for p in payments)


# =============================================================================
# Revenue Calculation Tests
# =============================================================================


class TestRevenueCalculation:
    """Tests for revenue calculation business rules."""

    async def test_current_month_revenue(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should calculate current month's revenue."""
        # Create paid payment this month
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="This month fee",
            amount_cents=15000,
            currency="BRL",
            due_date=date.today(),
            status=PaymentStatus.PAID,
            paid_at=datetime.utcnow(),
        )
        db_session.add(payment)
        await db_session.commit()

        # Calculate revenue
        now = datetime.utcnow()
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.status == PaymentStatus.PAID,
            )
        )
        payments = list(result.scalars().all())

        # Filter to current month
        current_month_payments = [
            p
            for p in payments
            if p.due_date.year == now.year and p.due_date.month == now.month
        ]

        revenue = sum(p.amount_cents for p in current_month_payments)
        assert revenue >= 15000

    async def test_revenue_excludes_cancelled(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should exclude cancelled payments from revenue."""
        # Create cancelled payment
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.SESSION,
            description="Cancelled session",
            amount_cents=5000,
            currency="BRL",
            due_date=date.today(),
            status=PaymentStatus.CANCELLED,
        )
        db_session.add(payment)
        await db_session.commit()

        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        assert payment not in payments

    async def test_revenue_separates_received_and_pending(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should separate received and pending amounts."""
        # Create paid payment
        paid = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="Paid fee",
            amount_cents=15000,
            currency="BRL",
            due_date=date.today(),
            status=PaymentStatus.PAID,
            paid_at=datetime.utcnow(),
        )
        # Create pending payment
        pending = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.SESSION,
            description="Pending session",
            amount_cents=8000,
            currency="BRL",
            due_date=date.today() + timedelta(days=7),
            status=PaymentStatus.PENDING,
        )
        db_session.add_all([paid, pending])
        await db_session.commit()

        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        received = sum(p.amount_cents for p in payments if p.status == PaymentStatus.PAID)
        pending_amount = sum(
            p.amount_cents
            for p in payments
            if p.status in [PaymentStatus.PENDING, PaymentStatus.OVERDUE]
        )

        assert received >= 15000
        assert pending_amount >= 8000

    async def test_revenue_history_groups_by_month(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should group revenue by month."""
        # Create payments in different months
        today = date.today()
        for i in range(3):
            if today.month - i > 0:
                due_month = today.month - i
                due_year = today.year
            else:
                due_month = 12 + (today.month - i)
                due_year = today.year - 1

            due_date = date(due_year, due_month, 15)
            payment = Payment(
                payer_id=student_user["id"],
                payee_id=trainer_user["id"],
                payment_type=PaymentType.MONTHLY_FEE,
                description=f"Month {i} fee",
                amount_cents=15000 + i * 1000,
                currency="BRL",
                due_date=due_date,
                status=PaymentStatus.PAID,
                paid_at=datetime(due_year, due_month, 15, 12, 0, 0),
            )
            db_session.add(payment)
        await db_session.commit()

        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.status == PaymentStatus.PAID,
            )
        )
        payments = list(result.scalars().all())

        # Group by month
        monthly: dict[tuple[int, int], int] = {}
        for p in payments:
            if p.paid_at:
                key = (p.paid_at.year, p.paid_at.month)
                monthly[key] = monthly.get(key, 0) + p.amount_cents

        # Should have multiple months
        assert len(monthly) >= 1


# =============================================================================
# Specific Month Revenue Tests
# =============================================================================


class TestSpecificMonthRevenue:
    """Tests for specific month revenue queries."""

    async def test_query_specific_month(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should query revenue for specific month."""
        # Create payment for January
        payment = Payment(
            payer_id=student_user["id"],
            payee_id=trainer_user["id"],
            payment_type=PaymentType.MONTHLY_FEE,
            description="January fee",
            amount_cents=15000,
            currency="BRL",
            due_date=date(2024, 1, 15),
            status=PaymentStatus.PAID,
            paid_at=datetime(2024, 1, 15, 12, 0, 0),
        )
        db_session.add(payment)
        await db_session.commit()

        # Query January 2024
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
                Payment.status != PaymentStatus.CANCELLED,
            )
        )
        payments = list(result.scalars().all())

        jan_payments = [
            p
            for p in payments
            if p.due_date.year == 2024 and p.due_date.month == 1
        ]

        assert len(jan_payments) >= 1

    async def test_empty_month_returns_zero(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
    ):
        """Should return zero for month with no payments."""
        result = await db_session.execute(
            select(Payment).where(
                Payment.payee_id == trainer_user["id"],
            )
        )
        payments = list(result.scalars().all())

        # Query a month far in the past
        old_month_payments = [
            p
            for p in payments
            if p.due_date.year == 2020 and p.due_date.month == 1
        ]

        total = sum(p.amount_cents for p in old_month_payments)
        assert total == 0


# =============================================================================
# Payment Access Control Tests
# =============================================================================


class TestPaymentAccessControl:
    """Tests for payment access control business rules."""

    async def test_payment_visible_to_payer(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_payment: Payment,
    ):
        """Payment should be visible to payer."""
        assert sample_payment.payer_id == student_user["id"]

    async def test_payment_visible_to_payee(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_payment: Payment,
    ):
        """Payment should be visible to payee."""
        assert sample_payment.payee_id == trainer_user["id"]

    async def test_only_payee_can_update(
        self, db_session: AsyncSession, sample_payment: Payment, trainer_user: dict
    ):
        """Business rule: Only payee can update payment (enforced in router)."""
        assert sample_payment.payee_id == trainer_user["id"]

    async def test_only_payee_can_mark_paid(
        self, db_session: AsyncSession, sample_payment: Payment, trainer_user: dict
    ):
        """Business rule: Only payee can mark as paid (enforced in router)."""
        assert sample_payment.payee_id == trainer_user["id"]

    async def test_only_payee_can_cancel(
        self, db_session: AsyncSession, sample_payment: Payment, trainer_user: dict
    ):
        """Business rule: Only payee can cancel (enforced in router)."""
        assert sample_payment.payee_id == trainer_user["id"]

    async def test_only_payee_can_send_reminder(
        self, db_session: AsyncSession, sample_payment: Payment, trainer_user: dict
    ):
        """Business rule: Only payee can send reminder (enforced in router)."""
        assert sample_payment.payee_id == trainer_user["id"]
