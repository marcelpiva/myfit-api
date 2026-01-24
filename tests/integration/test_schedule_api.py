"""Integration tests for schedule API endpoints."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.schedule.models import Appointment, AppointmentStatus, AppointmentType


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_appointment(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a sample appointment where sample_user is the trainer."""
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    appointment = Appointment(
        trainer_id=sample_user["id"],
        student_id=student_user["id"],
        organization_id=sample_user["organization_id"],
        date_time=tomorrow.replace(hour=10, minute=0, second=0, microsecond=0),
        duration_minutes=60,
        workout_type=AppointmentType.STRENGTH,
        status=AppointmentStatus.PENDING,
        notes="Initial training session",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
async def confirmed_appointment(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a confirmed appointment."""
    tomorrow = datetime.now(timezone.utc) + timedelta(days=2)
    appointment = Appointment(
        trainer_id=sample_user["id"],
        student_id=student_user["id"],
        organization_id=sample_user["organization_id"],
        date_time=tomorrow.replace(hour=14, minute=0, second=0, microsecond=0),
        duration_minutes=45,
        workout_type=AppointmentType.CARDIO,
        status=AppointmentStatus.CONFIRMED,
        notes="Cardio session",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
async def past_appointment(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a past completed appointment."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    appointment = Appointment(
        trainer_id=sample_user["id"],
        student_id=student_user["id"],
        organization_id=sample_user["organization_id"],
        date_time=yesterday.replace(hour=10, minute=0, second=0, microsecond=0),
        duration_minutes=60,
        workout_type=AppointmentType.HIIT,
        status=AppointmentStatus.COMPLETED,
        notes="Completed session",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
async def other_trainer_appointment(
    db_session: AsyncSession,
    student_user: dict[str, Any],
    sample_organization_id: uuid.UUID,
) -> Appointment:
    """Create an appointment with a different trainer."""
    from src.domains.users.models import User

    # Create another trainer
    other_trainer_id = uuid.uuid4()
    other_trainer = User(
        id=other_trainer_id,
        email=f"other-trainer-{other_trainer_id}@example.com",
        name="Other Trainer",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(other_trainer)
    await db_session.flush()

    tomorrow = datetime.now(timezone.utc) + timedelta(days=3)
    appointment = Appointment(
        trainer_id=other_trainer_id,
        student_id=student_user["id"],
        organization_id=sample_organization_id,
        date_time=tomorrow.replace(hour=16, minute=0, second=0, microsecond=0),
        duration_minutes=60,
        workout_type=AppointmentType.FUNCTIONAL,
        status=AppointmentStatus.PENDING,
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


# =============================================================================
# List Appointments Tests
# =============================================================================


class TestListAppointments:
    """Tests for GET /api/v1/schedule/appointments."""

    async def test_list_appointments_as_trainer(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can list their appointments."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments",
            params={"as_trainer": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(a["id"] == str(sample_appointment.id) for a in data)

    async def test_list_appointments_as_student(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Student can list appointments where they are the student."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments",
            params={"as_trainer": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_appointments_filter_by_from_date(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
        past_appointment: Appointment,
    ):
        """Can filter appointments by from_date."""
        today = datetime.now(timezone.utc).date()
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments",
            params={
                "as_trainer": True,
                "from_date": today.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should include sample_appointment (tomorrow) but not past_appointment (yesterday)
        appointment_ids = [a["id"] for a in data]
        assert str(sample_appointment.id) in appointment_ids

    async def test_list_appointments_filter_by_to_date(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
        confirmed_appointment: Appointment,
    ):
        """Can filter appointments by to_date."""
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).date()
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments",
            params={
                "as_trainer": True,
                "to_date": tomorrow.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        # Should include sample_appointment but not confirmed_appointment (day after tomorrow)
        appointment_ids = [a["id"] for a in data]
        assert str(sample_appointment.id) in appointment_ids

    async def test_list_appointments_filter_by_student_id(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
        student_user: dict[str, Any],
    ):
        """Can filter appointments by student_id."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments",
            params={
                "as_trainer": True,
                "student_id": str(student_user["id"]),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert all(a["student_id"] == str(student_user["id"]) for a in data)

    async def test_list_appointments_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/schedule/appointments")

        assert response.status_code == 401


# =============================================================================
# Create Appointment Tests
# =============================================================================


class TestCreateAppointment:
    """Tests for POST /api/v1/schedule/appointments."""

    async def test_create_appointment_success(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
        sample_user: dict[str, Any],
    ):
        """Can create a new appointment."""
        future_date = datetime.now(timezone.utc) + timedelta(days=5)
        payload = {
            "student_id": str(student_user["id"]),
            "date_time": future_date.isoformat(),
            "duration_minutes": 60,
            "workout_type": "strength",
            "notes": "First session",
            "organization_id": str(sample_user["organization_id"]),
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["student_id"] == str(student_user["id"])
        assert data["duration_minutes"] == 60
        assert data["workout_type"] == "strength"
        assert data["status"] == "pending"
        assert "id" in data

    async def test_create_appointment_minimal(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
    ):
        """Can create appointment with minimal fields."""
        future_date = datetime.now(timezone.utc) + timedelta(days=6)
        payload = {
            "student_id": str(student_user["id"]),
            "date_time": future_date.isoformat(),
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["duration_minutes"] == 60  # default value

    async def test_create_appointment_invalid_duration(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
    ):
        """Returns 422 for invalid duration."""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        payload = {
            "student_id": str(student_user["id"]),
            "date_time": future_date.isoformat(),
            "duration_minutes": 10,  # Less than minimum 15
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments",
            json=payload,
        )

        assert response.status_code == 422

    async def test_create_appointment_nonexistent_student(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent student."""
        future_date = datetime.now(timezone.utc) + timedelta(days=8)
        fake_student_id = uuid.uuid4()
        payload = {
            "student_id": str(fake_student_id),
            "date_time": future_date.isoformat(),
            "duration_minutes": 60,
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments",
            json=payload,
        )

        assert response.status_code == 404
        assert "Student not found" in response.json()["detail"]

    async def test_create_appointment_missing_required_fields(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 422 for missing required fields."""
        payload = {
            "duration_minutes": 60,
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments",
            json=payload,
        )

        assert response.status_code == 422


# =============================================================================
# Get Appointment Tests
# =============================================================================


class TestGetAppointment:
    """Tests for GET /api/v1/schedule/appointments/{appointment_id}."""

    async def test_get_own_appointment_as_trainer(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can get their appointment."""
        response = await authenticated_client.get(
            f"/api/v1/schedule/appointments/{sample_appointment.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_appointment.id)
        assert data["notes"] == "Initial training session"

    async def test_get_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/schedule/appointments/{fake_id}"
        )

        assert response.status_code == 404
        assert "Appointment not found" in response.json()["detail"]

    async def test_get_appointment_access_denied(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when trying to access another trainer's appointment."""
        response = await authenticated_client.get(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}"
        )

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]


# =============================================================================
# Update Appointment Tests
# =============================================================================


class TestUpdateAppointment:
    """Tests for PUT /api/v1/schedule/appointments/{appointment_id}."""

    async def test_update_appointment_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can update their appointment."""
        new_date = datetime.now(timezone.utc) + timedelta(days=10)
        payload = {
            "date_time": new_date.isoformat(),
            "duration_minutes": 90,
            "notes": "Updated notes",
        }

        response = await authenticated_client.put(
            f"/api/v1/schedule/appointments/{sample_appointment.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["duration_minutes"] == 90
        assert data["notes"] == "Updated notes"

    async def test_update_appointment_partial(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Can partially update appointment."""
        payload = {
            "workout_type": "cardio",
        }

        response = await authenticated_client.put(
            f"/api/v1/schedule/appointments/{sample_appointment.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["workout_type"] == "cardio"
        # Original values preserved
        assert data["duration_minutes"] == sample_appointment.duration_minutes

    async def test_update_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        payload = {"notes": "New notes"}

        response = await authenticated_client.put(
            f"/api/v1/schedule/appointments/{fake_id}",
            json=payload,
        )

        assert response.status_code == 404

    async def test_update_appointment_not_trainer(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when non-trainer tries to update."""
        payload = {"notes": "Trying to update"}

        response = await authenticated_client.put(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}",
            json=payload,
        )

        assert response.status_code == 403
        assert "Only the trainer can update" in response.json()["detail"]


# =============================================================================
# Cancel Appointment Tests
# =============================================================================


class TestCancelAppointment:
    """Tests for POST /api/v1/schedule/appointments/{appointment_id}/cancel."""

    async def test_cancel_appointment_with_reason(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Can cancel appointment with a reason."""
        payload = {"reason": "Schedule conflict"}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{sample_appointment.id}/cancel",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["cancellation_reason"] == "Schedule conflict"

    async def test_cancel_appointment_without_reason(
        self,
        authenticated_client: AsyncClient,
        confirmed_appointment: Appointment,
    ):
        """Can cancel appointment without a reason."""
        payload = {}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{confirmed_appointment.id}/cancel",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    async def test_cancel_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        payload = {"reason": "Test"}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{fake_id}/cancel",
            json=payload,
        )

        assert response.status_code == 404

    async def test_cancel_appointment_access_denied(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when unauthorized user tries to cancel."""
        payload = {"reason": "Trying to cancel"}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}/cancel",
            json=payload,
        )

        assert response.status_code == 403


# =============================================================================
# Delete Appointment Tests
# =============================================================================


class TestDeleteAppointment:
    """Tests for DELETE /api/v1/schedule/appointments/{appointment_id}."""

    async def test_delete_appointment_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can delete their appointment."""
        response = await authenticated_client.delete(
            f"/api/v1/schedule/appointments/{sample_appointment.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/schedule/appointments/{sample_appointment.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.delete(
            f"/api/v1/schedule/appointments/{fake_id}"
        )

        assert response.status_code == 404

    async def test_delete_appointment_not_trainer(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when non-trainer tries to delete."""
        response = await authenticated_client.delete(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}"
        )

        assert response.status_code == 403
        assert "Only the trainer can delete" in response.json()["detail"]


# =============================================================================
# Confirm Appointment Tests
# =============================================================================


class TestConfirmAppointment:
    """Tests for POST /api/v1/schedule/appointments/{appointment_id}/confirm."""

    async def test_confirm_appointment_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can confirm a pending appointment."""
        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{sample_appointment.id}/confirm"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"

    async def test_confirm_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{fake_id}/confirm"
        )

        assert response.status_code == 404

    async def test_confirm_appointment_access_denied(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when unauthorized user tries to confirm."""
        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}/confirm"
        )

        assert response.status_code == 403


# =============================================================================
# Get Appointments for Day Tests
# =============================================================================


class TestGetAppointmentsForDay:
    """Tests for GET /api/v1/schedule/day/{date_str}."""

    async def test_get_appointments_for_day_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Can get appointments for a specific day."""
        target_date = sample_appointment.date_time.strftime("%Y-%m-%d")
        response = await authenticated_client.get(
            f"/api/v1/schedule/day/{target_date}"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_appointments_for_day_invalid_format(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 400 for invalid date format."""
        response = await authenticated_client.get(
            "/api/v1/schedule/day/invalid-date"
        )

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    async def test_get_appointments_for_day_empty(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns empty list for day with no appointments."""
        far_future = (datetime.now(timezone.utc) + timedelta(days=100)).strftime("%Y-%m-%d")
        response = await authenticated_client.get(
            f"/api/v1/schedule/day/{far_future}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []


# =============================================================================
# Get Appointments for Week Tests
# =============================================================================


class TestGetAppointmentsForWeek:
    """Tests for GET /api/v1/schedule/week/{date_str}."""

    async def test_get_appointments_for_week_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Can get appointments for a week."""
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = await authenticated_client.get(
            f"/api/v1/schedule/week/{start_date}"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    async def test_get_appointments_for_week_invalid_format(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 400 for invalid date format."""
        response = await authenticated_client.get(
            "/api/v1/schedule/week/not-a-date"
        )

        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]

    async def test_get_appointments_for_week_groups_by_date(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
        confirmed_appointment: Appointment,
    ):
        """Week response groups appointments by date."""
        start_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = await authenticated_client.get(
            f"/api/v1/schedule/week/{start_date}"
        )

        assert response.status_code == 200
        data = response.json()
        # Each key should be a date string
        for date_key in data.keys():
            assert len(date_key) == 10  # YYYY-MM-DD format
            assert isinstance(data[date_key], list)


# =============================================================================
# Recurring Appointments Tests
# =============================================================================


class TestRecurringAppointments:
    """Tests for POST /api/v1/schedule/appointments/recurring."""

    async def test_create_recurring_appointments_weekly(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
        sample_user: dict[str, Any],
    ):
        """Can create weekly recurring appointments."""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        payload = {
            "student_id": str(student_user["id"]),
            "start_date": future_date.isoformat(),
            "duration_minutes": 60,
            "workout_type": "strength",
            "recurrence_pattern": "weekly",
            "occurrences": 4,
            "organization_id": str(sample_user["organization_id"]),
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments/recurring",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 4
        # Verify appointments are a week apart
        for i in range(1, len(data)):
            prev_date = datetime.fromisoformat(data[i - 1]["date_time"].replace("Z", "+00:00"))
            curr_date = datetime.fromisoformat(data[i]["date_time"].replace("Z", "+00:00"))
            assert (curr_date - prev_date).days == 7

    async def test_create_recurring_appointments_daily(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
    ):
        """Can create daily recurring appointments."""
        future_date = datetime.now(timezone.utc) + timedelta(days=10)
        payload = {
            "student_id": str(student_user["id"]),
            "start_date": future_date.isoformat(),
            "recurrence_pattern": "daily",
            "occurrences": 3,
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments/recurring",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 3

    async def test_create_recurring_appointments_biweekly(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
    ):
        """Can create biweekly recurring appointments."""
        future_date = datetime.now(timezone.utc) + timedelta(days=14)
        payload = {
            "student_id": str(student_user["id"]),
            "start_date": future_date.isoformat(),
            "recurrence_pattern": "biweekly",
            "occurrences": 2,
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments/recurring",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data) == 2

    async def test_create_recurring_appointments_nonexistent_student(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent student."""
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        fake_student_id = uuid.uuid4()
        payload = {
            "student_id": str(fake_student_id),
            "start_date": future_date.isoformat(),
            "recurrence_pattern": "weekly",
            "occurrences": 4,
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/appointments/recurring",
            json=payload,
        )

        assert response.status_code == 404
        assert "Student not found" in response.json()["detail"]


# =============================================================================
# Reschedule Appointment Tests
# =============================================================================


class TestRescheduleAppointment:
    """Tests for PATCH /api/v1/schedule/appointments/{appointment_id}/reschedule."""

    async def test_reschedule_appointment_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can reschedule their appointment."""
        new_date = datetime.now(timezone.utc) + timedelta(days=14)
        payload = {
            "new_date_time": new_date.isoformat(),
            "reason": "Client requested different time",
        }

        response = await authenticated_client.patch(
            f"/api/v1/schedule/appointments/{sample_appointment.id}/reschedule",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert "Rescheduled:" in data["notes"]

    async def test_reschedule_appointment_without_reason(
        self,
        authenticated_client: AsyncClient,
        confirmed_appointment: Appointment,
    ):
        """Can reschedule without providing a reason."""
        new_date = datetime.now(timezone.utc) + timedelta(days=15)
        payload = {
            "new_date_time": new_date.isoformat(),
        }

        response = await authenticated_client.patch(
            f"/api/v1/schedule/appointments/{confirmed_appointment.id}/reschedule",
            json=payload,
        )

        assert response.status_code == 200

    async def test_reschedule_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        new_date = datetime.now(timezone.utc) + timedelta(days=14)
        payload = {
            "new_date_time": new_date.isoformat(),
        }

        response = await authenticated_client.patch(
            f"/api/v1/schedule/appointments/{fake_id}/reschedule",
            json=payload,
        )

        assert response.status_code == 404

    async def test_reschedule_appointment_not_trainer(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when non-trainer tries to reschedule."""
        new_date = datetime.now(timezone.utc) + timedelta(days=14)
        payload = {
            "new_date_time": new_date.isoformat(),
        }

        response = await authenticated_client.patch(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}/reschedule",
            json=payload,
        )

        assert response.status_code == 403
        assert "Only the trainer can reschedule" in response.json()["detail"]

    async def test_reschedule_completed_appointment_fails(
        self,
        authenticated_client: AsyncClient,
        past_appointment: Appointment,
    ):
        """Cannot reschedule a completed appointment."""
        new_date = datetime.now(timezone.utc) + timedelta(days=14)
        payload = {
            "new_date_time": new_date.isoformat(),
        }

        response = await authenticated_client.patch(
            f"/api/v1/schedule/appointments/{past_appointment.id}/reschedule",
            json=payload,
        )

        assert response.status_code == 400
        assert "Cannot reschedule" in response.json()["detail"]


# =============================================================================
# Complete Appointment Tests
# =============================================================================


class TestCompleteAppointment:
    """Tests for POST /api/v1/schedule/appointments/{appointment_id}/complete."""

    async def test_complete_appointment_success(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can complete an appointment."""
        payload = {
            "notes": "Great session, client made good progress",
            "rating": 5,
        }

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{sample_appointment.id}/complete",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "Completion notes:" in data["notes"]

    async def test_complete_appointment_without_notes(
        self,
        authenticated_client: AsyncClient,
        confirmed_appointment: Appointment,
    ):
        """Can complete appointment without additional notes."""
        payload = {}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{confirmed_appointment.id}/complete",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    async def test_complete_appointment_not_found(
        self,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 for nonexistent appointment."""
        fake_id = uuid.uuid4()
        payload = {}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{fake_id}/complete",
            json=payload,
        )

        assert response.status_code == 404

    async def test_complete_appointment_not_trainer(
        self,
        authenticated_client: AsyncClient,
        other_trainer_appointment: Appointment,
    ):
        """Returns 403 when non-trainer tries to complete."""
        payload = {}

        response = await authenticated_client.post(
            f"/api/v1/schedule/appointments/{other_trainer_appointment.id}/complete",
            json=payload,
        )

        assert response.status_code == 403
        assert "Only the trainer can complete" in response.json()["detail"]


# =============================================================================
# Trainer Availability Tests
# =============================================================================


class TestTrainerAvailability:
    """Tests for GET/POST /api/v1/schedule/availability."""

    async def test_get_availability_empty(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
    ):
        """Get availability returns empty slots when none set."""
        response = await authenticated_client.get("/api/v1/schedule/availability")

        assert response.status_code == 200
        data = response.json()
        assert data["trainer_id"] == str(sample_user["id"])
        assert data["slots"] == []

    async def test_set_availability_success(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
    ):
        """Trainer can set their availability."""
        payload = {
            "slots": [
                {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
                {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"},
                {"day_of_week": 2, "start_time": "09:00", "end_time": "12:00"},
            ]
        }

        response = await authenticated_client.post(
            "/api/v1/schedule/availability",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["trainer_id"] == str(sample_user["id"])
        assert len(data["slots"]) == 3

    async def test_get_availability_after_setting(
        self,
        authenticated_client: AsyncClient,
        sample_user: dict[str, Any],
    ):
        """Can retrieve availability after setting it."""
        # First set availability
        payload = {
            "slots": [
                {"day_of_week": 4, "start_time": "10:00", "end_time": "18:00"},
            ]
        }
        await authenticated_client.post("/api/v1/schedule/availability", json=payload)

        # Then retrieve it
        response = await authenticated_client.get("/api/v1/schedule/availability")

        assert response.status_code == 200
        data = response.json()
        assert len(data["slots"]) == 1
        assert data["slots"][0]["day_of_week"] == 4
        assert data["slots"][0]["start_time"] == "10:00"

    async def test_set_availability_replaces_existing(
        self,
        authenticated_client: AsyncClient,
    ):
        """Setting availability replaces existing slots."""
        # First set some availability
        payload1 = {
            "slots": [
                {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"},
                {"day_of_week": 1, "start_time": "09:00", "end_time": "17:00"},
            ]
        }
        await authenticated_client.post("/api/v1/schedule/availability", json=payload1)

        # Then replace with new availability
        payload2 = {
            "slots": [
                {"day_of_week": 3, "start_time": "14:00", "end_time": "20:00"},
            ]
        }
        response = await authenticated_client.post(
            "/api/v1/schedule/availability",
            json=payload2,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["slots"]) == 1
        assert data["slots"][0]["day_of_week"] == 3


# =============================================================================
# Upcoming Appointments Tests
# =============================================================================


class TestUpcomingAppointments:
    """Tests for GET /api/v1/schedule/appointments/upcoming."""

    async def test_get_upcoming_appointments_as_trainer(
        self,
        authenticated_client: AsyncClient,
        sample_appointment: Appointment,
    ):
        """Trainer can get their upcoming appointments."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments/upcoming",
            params={"as_trainer": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert "appointments" in data
        assert "total_count" in data
        assert isinstance(data["appointments"], list)

    async def test_get_upcoming_appointments_as_student(
        self,
        authenticated_client: AsyncClient,
    ):
        """Student can get their upcoming appointments."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments/upcoming",
            params={"as_trainer": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert "appointments" in data
        assert "total_count" in data

    async def test_get_upcoming_appointments_with_limit(
        self,
        authenticated_client: AsyncClient,
        student_user: dict[str, Any],
    ):
        """Can limit the number of upcoming appointments returned."""
        # Create multiple future appointments
        for i in range(5):
            future_date = datetime.now(timezone.utc) + timedelta(days=20 + i)
            payload = {
                "student_id": str(student_user["id"]),
                "date_time": future_date.isoformat(),
            }
            await authenticated_client.post("/api/v1/schedule/appointments", json=payload)

        response = await authenticated_client.get(
            "/api/v1/schedule/appointments/upcoming",
            params={"as_trainer": True, "limit": 3},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["appointments"]) <= 3

    async def test_upcoming_appointments_excludes_past(
        self,
        authenticated_client: AsyncClient,
        past_appointment: Appointment,
        sample_appointment: Appointment,
    ):
        """Upcoming appointments excludes past appointments."""
        response = await authenticated_client.get(
            "/api/v1/schedule/appointments/upcoming",
            params={"as_trainer": True},
        )

        assert response.status_code == 200
        data = response.json()
        appointment_ids = [a["id"] for a in data["appointments"]]
        # Past appointment should not be in the list
        assert str(past_appointment.id) not in appointment_ids
