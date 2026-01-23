"""Tests for schedule router."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.schedule.models import Appointment, AppointmentStatus, AppointmentType
from src.domains.users.models import User


@pytest.fixture
async def trainer_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a trainer user."""
    user = User(
        email="schedule_trainer@example.com",
        password_hash="hashed_password",
        name="Schedule Trainer",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@pytest.fixture
async def student_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a student user."""
    user = User(
        email="schedule_student@example.com",
        password_hash="hashed_password",
        name="Schedule Student",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@pytest.fixture
async def other_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create another user with no access."""
    user = User(
        email="other_user@example.com",
        password_hash="hashed_password",
        name="Other User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@pytest.fixture
async def sample_appointment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a sample appointment."""
    appointment = Appointment(
        trainer_id=trainer_user["id"],
        student_id=student_user["id"],
        date_time=datetime.now(timezone.utc) + timedelta(days=1),
        duration_minutes=60,
        workout_type=AppointmentType.STRENGTH,
        status=AppointmentStatus.PENDING,
        notes="Regular training session",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
async def confirmed_appointment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a confirmed appointment."""
    appointment = Appointment(
        trainer_id=trainer_user["id"],
        student_id=student_user["id"],
        date_time=datetime.now(timezone.utc) + timedelta(days=2),
        duration_minutes=90,
        workout_type=AppointmentType.HIIT,
        status=AppointmentStatus.CONFIRMED,
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


@pytest.fixture
async def cancelled_appointment(
    db_session: AsyncSession,
    trainer_user: dict[str, Any],
    student_user: dict[str, Any],
) -> Appointment:
    """Create a cancelled appointment."""
    appointment = Appointment(
        trainer_id=trainer_user["id"],
        student_id=student_user["id"],
        date_time=datetime.now(timezone.utc) - timedelta(days=1),
        duration_minutes=60,
        status=AppointmentStatus.CANCELLED,
        cancellation_reason="Student sick",
    )
    db_session.add(appointment)
    await db_session.commit()
    await db_session.refresh(appointment)
    return appointment


class TestListAppointments:
    """Tests for list_appointments endpoint."""

    @pytest.mark.asyncio
    async def test_list_appointments_as_trainer(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Should return appointments where user is trainer."""
        result = await db_session.execute(
            select(Appointment).where(Appointment.trainer_id == trainer_user["id"])
        )
        appointments = list(result.scalars().all())

        assert len(appointments) >= 1
        assert all(a.trainer_id == trainer_user["id"] for a in appointments)

    @pytest.mark.asyncio
    async def test_list_appointments_as_student(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Should return appointments where user is student."""
        result = await db_session.execute(
            select(Appointment).where(Appointment.student_id == student_user["id"])
        )
        appointments = list(result.scalars().all())

        assert len(appointments) >= 1
        assert all(a.student_id == student_user["id"] for a in appointments)

    @pytest.mark.asyncio
    async def test_list_appointments_filter_by_student(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Should filter appointments by student_id when as_trainer."""
        result = await db_session.execute(
            select(Appointment).where(
                Appointment.trainer_id == trainer_user["id"],
                Appointment.student_id == student_user["id"],
            )
        )
        appointments = list(result.scalars().all())

        assert all(a.student_id == student_user["id"] for a in appointments)

    @pytest.mark.asyncio
    async def test_list_appointments_filter_by_date_range(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should filter appointments by date range."""
        # Create appointments on different dates
        today = datetime.now(timezone.utc).date()
        for i in range(3):
            appt = Appointment(
                trainer_id=trainer_user["id"],
                student_id=student_user["id"],
                date_time=datetime.combine(
                    today + timedelta(days=i), datetime.min.time()
                ).replace(tzinfo=timezone.utc),
                duration_minutes=60,
            )
            db_session.add(appt)
        await db_session.commit()

        # Query with date filter
        from_date = today
        to_date = today + timedelta(days=1)

        result = await db_session.execute(
            select(Appointment).where(
                Appointment.trainer_id == trainer_user["id"],
                Appointment.date_time
                >= datetime.combine(from_date, datetime.min.time()),
                Appointment.date_time <= datetime.combine(to_date, datetime.max.time()),
            )
        )
        appointments = list(result.scalars().all())

        # Should only include appointments within range
        for a in appointments:
            appt_date = a.date_time.date()
            assert from_date <= appt_date <= to_date

    @pytest.mark.asyncio
    async def test_list_appointments_ordered_by_date_desc(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should order appointments by date descending."""
        # Create appointments
        for i in range(3):
            appt = Appointment(
                trainer_id=trainer_user["id"],
                student_id=student_user["id"],
                date_time=datetime.now(timezone.utc) + timedelta(days=i),
                duration_minutes=60,
            )
            db_session.add(appt)
        await db_session.commit()

        result = await db_session.execute(
            select(Appointment)
            .where(Appointment.trainer_id == trainer_user["id"])
            .order_by(Appointment.date_time.desc())
        )
        appointments = list(result.scalars().all())

        for i in range(len(appointments) - 1):
            # Normalize timezones for comparison
            t1 = appointments[i].date_time.replace(tzinfo=None) if appointments[i].date_time.tzinfo else appointments[i].date_time
            t2 = appointments[i + 1].date_time.replace(tzinfo=None) if appointments[i + 1].date_time.tzinfo else appointments[i + 1].date_time
            assert t1 >= t2


class TestGetAppointmentsForDay:
    """Tests for get_appointments_for_day endpoint."""

    @pytest.mark.asyncio
    async def test_get_appointments_for_specific_day(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should return appointments for a specific day."""
        target_date = datetime.now(timezone.utc).date() + timedelta(days=5)

        # Create appointment on target date
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.combine(
                target_date, datetime.min.time().replace(hour=10)
            ).replace(tzinfo=timezone.utc),
            duration_minutes=60,
        )
        db_session.add(appointment)
        await db_session.commit()

        # Query for that day
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        result = await db_session.execute(
            select(Appointment).where(
                Appointment.trainer_id == trainer_user["id"],
                Appointment.date_time >= start_of_day,
                Appointment.date_time <= end_of_day,
            )
        )
        appointments = list(result.scalars().all())

        assert len(appointments) == 1
        # Normalize timezones for comparison
        appt_date = appointments[0].date_time.replace(tzinfo=None).date()
        assert appt_date == target_date

    @pytest.mark.asyncio
    async def test_get_appointments_for_day_ordered_by_time(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should order appointments by time ascending."""
        target_date = datetime.now(timezone.utc).date() + timedelta(days=6)

        # Create appointments at different times
        for hour in [14, 9, 11]:
            appt = Appointment(
                trainer_id=trainer_user["id"],
                student_id=student_user["id"],
                date_time=datetime.combine(
                    target_date, datetime.min.time().replace(hour=hour)
                ).replace(tzinfo=timezone.utc),
                duration_minutes=60,
            )
            db_session.add(appt)
        await db_session.commit()

        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())

        result = await db_session.execute(
            select(Appointment)
            .where(
                Appointment.trainer_id == trainer_user["id"],
                Appointment.date_time >= start_of_day,
                Appointment.date_time <= end_of_day,
            )
            .order_by(Appointment.date_time)
        )
        appointments = list(result.scalars().all())

        for i in range(len(appointments) - 1):
            # Normalize timezones for comparison
            t1 = appointments[i].date_time.replace(tzinfo=None) if appointments[i].date_time.tzinfo else appointments[i].date_time
            t2 = appointments[i + 1].date_time.replace(tzinfo=None) if appointments[i + 1].date_time.tzinfo else appointments[i + 1].date_time
            assert t1 <= t2


class TestGetAppointmentsForWeek:
    """Tests for get_appointments_for_week endpoint."""

    @pytest.mark.asyncio
    async def test_get_appointments_for_week_7_days(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should return appointments for 7 days starting from date."""
        start_date = datetime.now(timezone.utc).date() + timedelta(days=10)

        # Create appointments on different days
        for i in range(3):
            appt = Appointment(
                trainer_id=trainer_user["id"],
                student_id=student_user["id"],
                date_time=datetime.combine(
                    start_date + timedelta(days=i), datetime.min.time().replace(hour=10)
                ).replace(tzinfo=timezone.utc),
                duration_minutes=60,
            )
            db_session.add(appt)

        # Create appointment outside the week (day 8)
        outside_appt = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.combine(
                start_date + timedelta(days=8), datetime.min.time().replace(hour=10)
            ).replace(tzinfo=timezone.utc),
            duration_minutes=60,
        )
        db_session.add(outside_appt)
        await db_session.commit()

        end_date = start_date + timedelta(days=7)

        result = await db_session.execute(
            select(Appointment).where(
                Appointment.trainer_id == trainer_user["id"],
                Appointment.date_time
                >= datetime.combine(start_date, datetime.min.time()),
                Appointment.date_time < datetime.combine(end_date, datetime.min.time()),
            )
        )
        appointments = list(result.scalars().all())

        # Should only include 3 appointments (not the day 8 one)
        assert len(appointments) == 3


class TestCreateAppointment:
    """Tests for create_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_create_appointment_success(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should create an appointment successfully."""
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.now(timezone.utc) + timedelta(days=3),
            duration_minutes=60,
            workout_type=AppointmentType.CARDIO,
            status=AppointmentStatus.PENDING,
            notes="Cardio session",
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        assert appointment.id is not None
        assert appointment.trainer_id == trainer_user["id"]
        assert appointment.student_id == student_user["id"]
        assert appointment.status == AppointmentStatus.PENDING
        assert appointment.workout_type == AppointmentType.CARDIO
        assert appointment.notes == "Cardio session"

    @pytest.mark.asyncio
    async def test_create_appointment_default_status_pending(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should set status to PENDING by default."""
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.now(timezone.utc) + timedelta(days=3),
            duration_minutes=60,
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        assert appointment.status == AppointmentStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_appointment_default_duration(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should default duration to 60 minutes."""
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.now(timezone.utc) + timedelta(days=3),
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        assert appointment.duration_minutes == 60


class TestGetAppointment:
    """Tests for get_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_get_appointment_as_trainer(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_appointment: Appointment,
    ):
        """Should return appointment if user is the trainer."""
        appointment = await db_session.get(Appointment, sample_appointment.id)

        assert appointment is not None
        assert appointment.trainer_id == trainer_user["id"]

    @pytest.mark.asyncio
    async def test_get_appointment_as_student(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Should return appointment if user is the student."""
        appointment = await db_session.get(Appointment, sample_appointment.id)

        assert appointment is not None
        assert appointment.student_id == student_user["id"]

    @pytest.mark.asyncio
    async def test_get_appointment_not_found(
        self,
        db_session: AsyncSession,
    ):
        """Should return None for non-existent appointment."""
        appointment = await db_session.get(Appointment, uuid.uuid4())

        assert appointment is None


class TestUpdateAppointment:
    """Tests for update_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_update_appointment_date_time(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should update appointment date_time."""
        new_date_time = datetime.now(timezone.utc) + timedelta(days=5)
        sample_appointment.date_time = new_date_time
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        # Normalize timezones for comparison
        stored_dt = sample_appointment.date_time.replace(tzinfo=None) if sample_appointment.date_time.tzinfo else sample_appointment.date_time
        expected_dt = new_date_time.replace(tzinfo=None)
        assert stored_dt == expected_dt

    @pytest.mark.asyncio
    async def test_update_appointment_duration(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should update appointment duration."""
        sample_appointment.duration_minutes = 90
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.duration_minutes == 90

    @pytest.mark.asyncio
    async def test_update_appointment_workout_type(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should update appointment workout type."""
        sample_appointment.workout_type = AppointmentType.FUNCTIONAL
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.workout_type == AppointmentType.FUNCTIONAL

    @pytest.mark.asyncio
    async def test_update_appointment_notes(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should update appointment notes."""
        sample_appointment.notes = "Updated notes"
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.notes == "Updated notes"

    @pytest.mark.asyncio
    async def test_update_appointment_only_trainer_can_update(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Trainer should be the owner of the appointment."""
        # Verify the appointment is owned by trainer
        assert sample_appointment.trainer_id == trainer_user["id"]
        assert sample_appointment.trainer_id != student_user["id"]


class TestCancelAppointment:
    """Tests for cancel_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_appointment_sets_status(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should set status to CANCELLED."""
        sample_appointment.status = AppointmentStatus.CANCELLED
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.status == AppointmentStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_appointment_sets_reason(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should set cancellation reason."""
        reason = "Schedule conflict"
        sample_appointment.status = AppointmentStatus.CANCELLED
        sample_appointment.cancellation_reason = reason
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.cancellation_reason == reason

    @pytest.mark.asyncio
    async def test_cancel_appointment_trainer_can_cancel(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_appointment: Appointment,
    ):
        """Trainer should be able to cancel their appointments."""
        # Trainer owns the appointment
        assert sample_appointment.trainer_id == trainer_user["id"]

        sample_appointment.status = AppointmentStatus.CANCELLED
        await db_session.commit()

        assert sample_appointment.status == AppointmentStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_appointment_student_can_cancel(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Student should be able to cancel their appointments."""
        # Student is part of the appointment
        assert sample_appointment.student_id == student_user["id"]

        sample_appointment.status = AppointmentStatus.CANCELLED
        await db_session.commit()

        assert sample_appointment.status == AppointmentStatus.CANCELLED


class TestConfirmAppointment:
    """Tests for confirm_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_confirm_appointment_sets_status(
        self,
        db_session: AsyncSession,
        sample_appointment: Appointment,
    ):
        """Should set status to CONFIRMED."""
        sample_appointment.status = AppointmentStatus.CONFIRMED
        await db_session.commit()
        await db_session.refresh(sample_appointment)

        assert sample_appointment.status == AppointmentStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_confirm_appointment_trainer_can_confirm(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_appointment: Appointment,
    ):
        """Trainer should be able to confirm appointment."""
        assert sample_appointment.trainer_id == trainer_user["id"]

        sample_appointment.status = AppointmentStatus.CONFIRMED
        await db_session.commit()

        assert sample_appointment.status == AppointmentStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_confirm_appointment_student_can_confirm(
        self,
        db_session: AsyncSession,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Student should be able to confirm appointment."""
        assert sample_appointment.student_id == student_user["id"]

        sample_appointment.status = AppointmentStatus.CONFIRMED
        await db_session.commit()

        assert sample_appointment.status == AppointmentStatus.CONFIRMED


class TestDeleteAppointment:
    """Tests for delete_appointment endpoint."""

    @pytest.mark.asyncio
    async def test_delete_appointment(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should delete an appointment."""
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.now(timezone.utc) + timedelta(days=3),
            duration_minutes=60,
        )
        db_session.add(appointment)
        await db_session.commit()

        appointment_id = appointment.id

        # Delete
        await db_session.delete(appointment)
        await db_session.commit()

        # Verify deleted
        deleted = await db_session.get(Appointment, appointment_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_delete_appointment_only_trainer_can_delete(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        sample_appointment: Appointment,
    ):
        """Only trainer should own the appointment for deletion."""
        assert sample_appointment.trainer_id == trainer_user["id"]
        assert sample_appointment.trainer_id != student_user["id"]


class TestAppointmentModel:
    """Tests for Appointment model behavior."""

    @pytest.mark.asyncio
    async def test_appointment_default_values(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
    ):
        """Should have correct default values."""
        appointment = Appointment(
            trainer_id=trainer_user["id"],
            student_id=student_user["id"],
            date_time=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db_session.add(appointment)
        await db_session.commit()
        await db_session.refresh(appointment)

        assert appointment.status == AppointmentStatus.PENDING
        assert appointment.duration_minutes == 60
        assert appointment.notes is None
        assert appointment.cancellation_reason is None
        assert appointment.workout_type is None

    @pytest.mark.asyncio
    async def test_appointment_status_enum(self):
        """Should have all required status values."""
        statuses = [s.value for s in AppointmentStatus]

        assert "pending" in statuses
        assert "confirmed" in statuses
        assert "cancelled" in statuses
        assert "completed" in statuses

    @pytest.mark.asyncio
    async def test_appointment_type_enum(self):
        """Should have all required workout types."""
        types = [t.value for t in AppointmentType]

        assert "strength" in types
        assert "cardio" in types
        assert "functional" in types
        assert "hiit" in types
        assert "assessment" in types
        assert "other" in types


class TestAccessControl:
    """Tests for access control on appointments."""

    @pytest.mark.asyncio
    async def test_only_related_users_can_access(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        student_user: dict,
        other_user: dict,
        sample_appointment: Appointment,
    ):
        """Only trainer or student should have access to appointment."""
        # Trainer has access
        assert sample_appointment.trainer_id == trainer_user["id"]

        # Student has access
        assert sample_appointment.student_id == student_user["id"]

        # Other user should NOT have access
        assert sample_appointment.trainer_id != other_user["id"]
        assert sample_appointment.student_id != other_user["id"]

    @pytest.mark.asyncio
    async def test_trainer_is_appointment_owner(
        self,
        db_session: AsyncSession,
        trainer_user: dict,
        sample_appointment: Appointment,
    ):
        """Trainer should be the owner with full control."""
        assert sample_appointment.trainer_id == trainer_user["id"]

        # Trainer can update all fields
        sample_appointment.date_time = datetime.now(timezone.utc) + timedelta(days=10)
        sample_appointment.duration_minutes = 120
        sample_appointment.workout_type = AppointmentType.ASSESSMENT
        sample_appointment.notes = "Full assessment"
        await db_session.commit()

        await db_session.refresh(sample_appointment)
        assert sample_appointment.duration_minutes == 120
        assert sample_appointment.workout_type == AppointmentType.ASSESSMENT
