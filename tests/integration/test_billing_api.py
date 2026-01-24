"""Integration tests for billing API endpoints."""
import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.billing.models import (
    Payment,
    PaymentPlan,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    RecurrenceType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_payment(
    db_session: AsyncSession, sample_user: dict[str, Any], student_user: dict[str, Any]
) -> Payment:
    """Create a sample payment where sample_user (trainer) is payee and student is payer."""
    payment = Payment(
        payer_id=student_user["id"],
        payee_id=sample_user["id"],
        organization_id=sample_user["organization_id"],
        payment_type=PaymentType.MONTHLY_FEE,
        description="Monthly training fee - January",
        amount_cents=15000,  # R$ 150.00
        currency="BRL",
        status=PaymentStatus.PENDING,
        due_date=date.today() + timedelta(days=7),
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def sample_paid_payment(
    db_session: AsyncSession, sample_user: dict[str, Any], student_user: dict[str, Any]
) -> Payment:
    """Create a sample paid payment."""
    from datetime import datetime, timezone

    payment = Payment(
        payer_id=student_user["id"],
        payee_id=sample_user["id"],
        organization_id=sample_user["organization_id"],
        payment_type=PaymentType.SESSION,
        description="Personal training session",
        amount_cents=10000,  # R$ 100.00
        currency="BRL",
        status=PaymentStatus.PAID,
        due_date=date.today() - timedelta(days=3),
        paid_at=datetime.now(timezone.utc),
        payment_method=PaymentMethod.PIX,
        payment_reference="PIX123456",
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


@pytest.fixture
async def sample_payment_plan(
    db_session: AsyncSession, sample_user: dict[str, Any], student_user: dict[str, Any]
) -> PaymentPlan:
    """Create a sample payment plan."""
    plan = PaymentPlan(
        student_id=student_user["id"],
        trainer_id=sample_user["id"],
        organization_id=sample_user["organization_id"],
        name="Monthly Training Plan",
        description="Standard monthly training subscription",
        amount_cents=20000,  # R$ 200.00
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


@pytest.fixture
async def other_user_payment(
    db_session: AsyncSession, sample_organization_id: uuid.UUID
) -> Payment:
    """Create a payment belonging to a different user."""
    from src.domains.users.models import User
    from src.domains.organizations.models import OrganizationMembership, UserRole

    # Create two separate users for this payment
    payer_id = uuid.uuid4()
    payee_id = uuid.uuid4()

    payer = User(
        id=payer_id,
        email=f"other-payer-{payer_id}@example.com",
        name="Other Payer",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(payer)

    payee = User(
        id=payee_id,
        email=f"other-payee-{payee_id}@example.com",
        name="Other Payee",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(payee)

    # Create memberships
    payer_membership = OrganizationMembership(
        user_id=payer_id,
        organization_id=sample_organization_id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(payer_membership)

    payee_membership = OrganizationMembership(
        user_id=payee_id,
        organization_id=sample_organization_id,
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(payee_membership)

    await db_session.flush()

    payment = Payment(
        payer_id=payer_id,
        payee_id=payee_id,
        organization_id=sample_organization_id,
        payment_type=PaymentType.MONTHLY_FEE,
        description="Other user's payment",
        amount_cents=12000,
        currency="BRL",
        status=PaymentStatus.PENDING,
        due_date=date.today() + timedelta(days=10),
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(payment)
    return payment


# =============================================================================
# Payment Endpoint Tests
# =============================================================================


class TestListPayments:
    """Tests for GET /api/v1/billing/billing/payments."""

    async def test_list_payments_authenticated(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Authenticated user can list their payments."""
        response = await authenticated_client.get("/api/v1/billing/billing/payments")

        assert response.status_code == 200
        data = response.json()
        assert "payments" in data
        assert "total" in data
        assert isinstance(data["payments"], list)

    async def test_list_payments_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/billing/billing/payments")

        assert response.status_code == 401

    async def test_list_payments_as_payee(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Can list payments where user is the payee (trainer view)."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/payments", params={"as_payee": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        # Should contain the sample payment where authenticated user is payee
        payment_ids = [p["id"] for p in data["payments"]]
        assert str(sample_payment.id) in payment_ids

    async def test_list_payments_filter_by_status(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Can filter payments by status."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/payments",
            params={"as_payee": True, "status": "pending"},
        )

        assert response.status_code == 200
        data = response.json()
        # All returned payments should be pending
        for payment in data["payments"]:
            assert payment["status"] == "pending"

    async def test_list_payments_pagination(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/payments",
            params={"as_payee": True, "limit": 1, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["payments"]) <= 1


class TestGetPayment:
    """Tests for GET /api/v1/billing/billing/payments/{payment_id}."""

    async def test_get_own_payment_as_payee(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Payee can get their payment."""
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/payments/{sample_payment.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_payment.id)
        assert data["description"] == "Monthly training fee - January"
        assert data["amount_cents"] == 15000

    async def test_get_payment_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent payment."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/payments/{fake_id}"
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_get_payment_access_denied(
        self, authenticated_client: AsyncClient, other_user_payment: Payment
    ):
        """Returns 403 when accessing another user's payment."""
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/payments/{other_user_payment.id}"
        )

        assert response.status_code == 403
        assert "denied" in response.json()["detail"].lower()


class TestCreatePayment:
    """Tests for POST /api/v1/billing/billing/payments."""

    async def test_create_payment_success(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Trainer can create a new payment for a student."""
        payload = {
            "payer_id": str(student_user["id"]),
            "payment_type": "monthly_fee",
            "description": "February training fee",
            "amount_cents": 15000,
            "currency": "BRL",
            "due_date": str(date.today() + timedelta(days=30)),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/payments", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "February training fee"
        assert data["amount_cents"] == 15000
        assert data["status"] == "pending"
        assert "id" in data

    async def test_create_payment_with_all_fields(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
        sample_organization_id: uuid.UUID,
    ):
        """Can create payment with all optional fields."""
        payload = {
            "payer_id": str(student_user["id"]),
            "payment_type": "package",
            "description": "10-session package",
            "amount_cents": 80000,
            "currency": "BRL",
            "due_date": str(date.today() + timedelta(days=15)),
            "notes": "Package discount applied",
            "is_recurring": True,
            "recurrence_type": "monthly",
            "organization_id": str(sample_organization_id),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/payments", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["payment_type"] == "package"
        assert data["notes"] == "Package discount applied"
        assert data["is_recurring"] is True

    async def test_create_payment_validation_error_missing_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {
            "description": "Missing payer_id and other required fields",
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/payments", json=payload
        )

        assert response.status_code == 422

    async def test_create_payment_validation_error_invalid_amount(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Returns 422 for invalid amount (must be > 0)."""
        payload = {
            "payer_id": str(student_user["id"]),
            "payment_type": "monthly_fee",
            "description": "Test payment",
            "amount_cents": 0,  # Invalid: must be > 0
            "due_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/payments", json=payload
        )

        assert response.status_code == 422

    async def test_create_payment_payer_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when payer does not exist."""
        fake_payer_id = uuid.uuid4()
        payload = {
            "payer_id": str(fake_payer_id),
            "payment_type": "monthly_fee",
            "description": "Test payment",
            "amount_cents": 10000,
            "due_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/payments", json=payload
        )

        assert response.status_code == 404
        assert "payer" in response.json()["detail"].lower()


class TestUpdatePayment:
    """Tests for PUT /api/v1/billing/billing/payments/{payment_id}."""

    async def test_update_payment_success(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Payee can update their payment."""
        payload = {
            "description": "Updated payment description",
            "amount_cents": 18000,
        }

        response = await authenticated_client.put(
            f"/api/v1/billing/billing/payments/{sample_payment.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated payment description"
        assert data["amount_cents"] == 18000

    async def test_update_payment_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent payment."""
        fake_id = uuid.uuid4()
        payload = {"description": "New description"}

        response = await authenticated_client.put(
            f"/api/v1/billing/billing/payments/{fake_id}", json=payload
        )

        assert response.status_code == 404

    async def test_update_payment_access_denied(
        self, authenticated_client: AsyncClient, other_user_payment: Payment
    ):
        """Returns 403 when non-payee tries to update."""
        payload = {"description": "Attempted update"}

        response = await authenticated_client.put(
            f"/api/v1/billing/billing/payments/{other_user_payment.id}", json=payload
        )

        assert response.status_code == 403

    async def test_update_paid_payment_fails(
        self, authenticated_client: AsyncClient, sample_paid_payment: Payment
    ):
        """Cannot update a payment that is already paid."""
        payload = {"description": "Cannot change this"}

        response = await authenticated_client.put(
            f"/api/v1/billing/billing/payments/{sample_paid_payment.id}", json=payload
        )

        assert response.status_code == 400
        assert "paid" in response.json()["detail"].lower()


class TestMarkPaymentPaid:
    """Tests for POST /api/v1/billing/billing/payments/{payment_id}/mark-paid."""

    async def test_mark_payment_paid_success(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Payee can mark a payment as paid."""
        payload = {
            "payment_method": "pix",
            "payment_reference": "PIX789012",
        }

        response = await authenticated_client.post(
            f"/api/v1/billing/billing/payments/{sample_payment.id}/mark-paid", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paid"
        assert data["payment_method"] == "pix"
        assert data["payment_reference"] == "PIX789012"
        assert data["paid_at"] is not None

    async def test_mark_already_paid_payment_fails(
        self, authenticated_client: AsyncClient, sample_paid_payment: Payment
    ):
        """Cannot mark an already paid payment as paid again."""
        payload = {
            "payment_method": "cash",
        }

        response = await authenticated_client.post(
            f"/api/v1/billing/billing/payments/{sample_paid_payment.id}/mark-paid", json=payload
        )

        assert response.status_code == 400
        assert "already" in response.json()["detail"].lower()


class TestCancelPayment:
    """Tests for DELETE /api/v1/billing/billing/payments/{payment_id}."""

    async def test_cancel_payment_success(
        self, authenticated_client: AsyncClient, sample_payment: Payment
    ):
        """Payee can cancel an unpaid payment."""
        response = await authenticated_client.delete(
            f"/api/v1/billing/billing/payments/{sample_payment.id}"
        )

        assert response.status_code == 204

    async def test_cancel_paid_payment_fails(
        self, authenticated_client: AsyncClient, sample_paid_payment: Payment
    ):
        """Cannot cancel a paid payment."""
        response = await authenticated_client.delete(
            f"/api/v1/billing/billing/payments/{sample_paid_payment.id}"
        )

        assert response.status_code == 400
        assert "paid" in response.json()["detail"].lower()


# =============================================================================
# Payment Plan Endpoint Tests
# =============================================================================


class TestListPaymentPlans:
    """Tests for GET /api/v1/billing/billing/plans."""

    async def test_list_payment_plans_authenticated(
        self, authenticated_client: AsyncClient, sample_payment_plan: PaymentPlan
    ):
        """Authenticated user can list payment plans."""
        response = await authenticated_client.get("/api/v1/billing/billing/plans")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_payment_plans_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/billing/billing/plans")

        assert response.status_code == 401

    async def test_list_payment_plans_as_trainer(
        self, authenticated_client: AsyncClient, sample_payment_plan: PaymentPlan
    ):
        """Trainer can list payment plans they created."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/plans", params={"as_trainer": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        plan_ids = [p["id"] for p in data]
        assert str(sample_payment_plan.id) in plan_ids

    async def test_list_payment_plans_active_only(
        self, authenticated_client: AsyncClient, sample_payment_plan: PaymentPlan
    ):
        """By default, only active plans are returned."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/plans", params={"as_trainer": True, "active_only": True}
        )

        assert response.status_code == 200
        data = response.json()
        for plan in data:
            assert plan["is_active"] is True


class TestCreatePaymentPlan:
    """Tests for POST /api/v1/billing/billing/plans."""

    async def test_create_payment_plan_success(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Trainer can create a new payment plan."""
        payload = {
            "student_id": str(student_user["id"]),
            "name": "Premium Training Plan",
            "description": "Premium monthly training with nutrition",
            "amount_cents": 35000,
            "currency": "BRL",
            "recurrence_type": "monthly",
            "billing_day": 10,
            "start_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Premium Training Plan"
        assert data["amount_cents"] == 35000
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_payment_plan_with_end_date(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
        sample_organization_id: uuid.UUID,
    ):
        """Can create payment plan with end date."""
        payload = {
            "student_id": str(student_user["id"]),
            "name": "3-Month Plan",
            "amount_cents": 25000,
            "recurrence_type": "monthly",
            "billing_day": 1,
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=90)),
            "organization_id": str(sample_organization_id),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["end_date"] is not None

    async def test_create_payment_plan_validation_error(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {
            "name": "Missing student_id",
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/plans", json=payload
        )

        assert response.status_code == 422

    async def test_create_payment_plan_student_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when student does not exist."""
        fake_student_id = uuid.uuid4()
        payload = {
            "student_id": str(fake_student_id),
            "name": "Test Plan",
            "amount_cents": 10000,
            "recurrence_type": "monthly",
            "billing_day": 1,
            "start_date": str(date.today()),
        }

        response = await authenticated_client.post(
            "/api/v1/billing/billing/plans", json=payload
        )

        assert response.status_code == 404
        assert "student" in response.json()["detail"].lower()


class TestGetPaymentPlan:
    """Tests for GET /api/v1/billing/billing/plans/{plan_id}."""

    async def test_get_payment_plan_as_trainer(
        self, authenticated_client: AsyncClient, sample_payment_plan: PaymentPlan
    ):
        """Trainer can get their payment plan."""
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/plans/{sample_payment_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_payment_plan.id)
        assert data["name"] == "Monthly Training Plan"

    async def test_get_payment_plan_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent payment plan."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(f"/api/v1/billing/billing/plans/{fake_id}")

        assert response.status_code == 404


class TestDeactivatePaymentPlan:
    """Tests for DELETE /api/v1/billing/billing/plans/{plan_id}."""

    async def test_deactivate_payment_plan_success(
        self,
        authenticated_client: AsyncClient,
        sample_payment_plan: PaymentPlan,
        db_session: AsyncSession,
    ):
        """Trainer can deactivate their payment plan."""
        plan_id = sample_payment_plan.id

        response = await authenticated_client.delete(
            f"/api/v1/billing/billing/plans/{plan_id}"
        )

        assert response.status_code == 204

        # Verify it's deactivated by querying the database directly
        await db_session.refresh(sample_payment_plan)
        assert sample_payment_plan.is_active is False

    async def test_deactivate_payment_plan_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent payment plan."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.delete(
            f"/api/v1/billing/billing/plans/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Billing Summary Endpoint Tests
# =============================================================================


class TestBillingSummary:
    """Tests for GET /api/v1/billing/billing/summary."""

    async def test_get_billing_summary(
        self,
        authenticated_client: AsyncClient,
        sample_payment: Payment,
        sample_paid_payment: Payment,
    ):
        """Can get billing summary as payee."""
        response = await authenticated_client.get(
            "/api/v1/billing/billing/summary", params={"as_payee": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_amount_cents" in data
        assert "paid_amount_cents" in data
        assert "pending_amount_cents" in data
        assert "total_payments" in data
        assert data["total_payments"] >= 2  # At least our two fixtures

    async def test_get_billing_summary_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/billing/billing/summary")

        assert response.status_code == 401


# =============================================================================
# Student Payments Endpoint Tests (Trainer View)
# =============================================================================


class TestListStudentPayments:
    """Tests for GET /api/v1/billing/billing/students/{student_id}/payments."""

    async def test_list_student_payments(
        self,
        authenticated_client: AsyncClient,
        sample_payment: Payment,
        student_user: dict[str, Any],
    ):
        """Trainer can list payments for a specific student."""
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/students/{student_user['id']}/payments"
        )

        assert response.status_code == 200
        data = response.json()
        assert "payments" in data
        assert "total" in data
        assert data["total"] >= 1

    async def test_list_student_payments_filter_by_status(
        self,
        authenticated_client: AsyncClient,
        sample_payment: Payment,
        student_user: dict[str, Any],
    ):
        """Can filter student payments by status."""
        response = await authenticated_client.get(
            f"/api/v1/billing/billing/students/{student_user['id']}/payments",
            params={"status": "pending"},
        )

        assert response.status_code == 200
        data = response.json()
        for payment in data["payments"]:
            assert payment["status"] == "pending"
