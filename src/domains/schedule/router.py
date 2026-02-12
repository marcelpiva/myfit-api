"""Schedule router for appointment management."""
import json
from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.models import User

from .models import (
    Appointment,
    AppointmentStatus,
    AttendanceStatus,
    SessionType,
    TrainerAvailability,
    TrainerBlockedSlot,
    TrainerSettings,
)
from .schemas import (
    AppointmentCancel,
    AppointmentComplete,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentUpdate,
    AttendanceUpdate,
    AutoGenerateScheduleRequest,
    AvailableSlotResponse,
    AvailableSlotsResponse,
    ConflictCheckResponse,
    ConflictDetail,
    DuplicateWeekRequest,
    RecurringAppointmentCreate,
    StudentBookSessionRequest,
    TrainerAvailabilityCreate,
    TrainerAvailabilityResponse,
    TrainerAvailabilitySlot,
    TrainerBlockedSlotCreate,
    TrainerBlockedSlotResponse,
    TrainerFullAvailabilityResponse,
    TrainerSettingsResponse,
    TrainerSettingsUpdate,
    UpcomingAppointmentsResponse,
)

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _appointment_to_response(
    appointment: Appointment,
    trainer_name: str | None = None,
    student_name: str | None = None,
) -> AppointmentResponse:
    """Convert appointment model to response."""
    return AppointmentResponse(
        id=appointment.id,
        trainer_id=appointment.trainer_id,
        student_id=appointment.student_id,
        organization_id=appointment.organization_id,
        date_time=appointment.date_time,
        duration_minutes=appointment.duration_minutes,
        workout_type=appointment.workout_type,
        status=appointment.status,
        notes=appointment.notes,
        cancellation_reason=appointment.cancellation_reason,
        created_at=appointment.created_at,
        updated_at=appointment.updated_at,
        service_plan_id=appointment.service_plan_id,
        payment_id=appointment.payment_id,
        session_type=appointment.session_type,
        attendance_status=appointment.attendance_status,
        is_complimentary=appointment.is_complimentary,
        trainer_name=trainer_name or (appointment.trainer.name if appointment.trainer else None),
        student_name=student_name or (appointment.student.name if appointment.student else None),
        service_plan_name=appointment.service_plan.name if hasattr(appointment, "service_plan") and appointment.service_plan else None,
    )


@router.get("/appointments", response_model=list[AppointmentResponse])
async def list_appointments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    student_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
) -> list[AppointmentResponse]:
    """List appointments for current user (as trainer or student)."""
    if as_trainer:
        query = select(Appointment).where(Appointment.trainer_id == current_user.id)
        if student_id:
            query = query.where(Appointment.student_id == student_id)
    else:
        query = select(Appointment).where(Appointment.student_id == current_user.id)

    if from_date:
        query = query.where(Appointment.date_time >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        query = query.where(Appointment.date_time <= datetime.combine(to_date, datetime.max.time()))

    query = query.order_by(Appointment.date_time.desc())

    result = await db.execute(query)
    appointments = list(result.scalars().all())

    return [_appointment_to_response(a) for a in appointments]


@router.get("/day/{date_str}", response_model=list[AppointmentResponse])
async def get_appointments_for_day(
    date_str: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AppointmentResponse]:
    """Get appointments for a specific day."""
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    query = select(Appointment).where(
        and_(
            Appointment.trainer_id == current_user.id,
            Appointment.date_time >= start_of_day,
            Appointment.date_time <= end_of_day,
        )
    ).order_by(Appointment.date_time)

    result = await db.execute(query)
    appointments = list(result.scalars().all())

    return [_appointment_to_response(a) for a in appointments]


@router.get("/week/{date_str}", response_model=dict[str, list[AppointmentResponse]])
async def get_appointments_for_week(
    date_str: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, list[AppointmentResponse]]:
    """Get appointments for a week starting from the given date."""
    try:
        start_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    end_date = start_date + timedelta(days=7)

    query = select(Appointment).where(
        and_(
            Appointment.trainer_id == current_user.id,
            Appointment.date_time >= datetime.combine(start_date, datetime.min.time()),
            Appointment.date_time < datetime.combine(end_date, datetime.min.time()),
        )
    ).order_by(Appointment.date_time)

    result = await db.execute(query)
    appointments = list(result.scalars().all())

    # Group by date
    by_date: dict[str, list[AppointmentResponse]] = {}
    for a in appointments:
        date_key = a.date_time.strftime("%Y-%m-%d")
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(_appointment_to_response(a))

    return by_date


@router.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    request: AppointmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Create a new appointment."""
    # Verify student exists
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # Validate service plan if provided
    if request.service_plan_id:
        from src.domains.billing.models import ServicePlan as BillingServicePlan

        plan = await db.get(BillingServicePlan, request.service_plan_id)
        if not plan or not plan.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service plan not found or inactive",
            )
        if plan.student_id != request.student_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service plan does not belong to this student",
            )

    appointment = Appointment(
        trainer_id=current_user.id,
        student_id=request.student_id,
        organization_id=request.organization_id,
        date_time=request.date_time,
        duration_minutes=request.duration_minutes,
        workout_type=request.workout_type,
        notes=request.notes,
        status=AppointmentStatus.PENDING,
        service_plan_id=request.service_plan_id,
        session_type=request.session_type,
        is_complimentary=request.is_complimentary,
    )

    db.add(appointment)
    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(
        appointment,
        trainer_name=current_user.name,
        student_name=student.name,
    )


@router.get("/appointments/upcoming", response_model=UpcomingAppointmentsResponse)
async def get_upcoming_appointments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> UpcomingAppointmentsResponse:
    """Get upcoming appointments (future appointments that are not cancelled/completed)."""
    from sqlalchemy import func

    now = datetime.now()

    if as_trainer:
        query = select(Appointment).where(
            and_(
                Appointment.trainer_id == current_user.id,
                Appointment.date_time > now,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            )
        )
    else:
        query = select(Appointment).where(
            and_(
                Appointment.student_id == current_user.id,
                Appointment.date_time > now,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            )
        )

    # Get total count first
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # Get paginated results
    query = query.order_by(Appointment.date_time).limit(limit)
    result = await db.execute(query)
    appointments = list(result.scalars().all())

    return UpcomingAppointmentsResponse(
        appointments=[_appointment_to_response(a) for a in appointments],
        total_count=total_count,
    )


@router.post("/appointments/recurring", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
async def create_recurring_appointments(
    request: RecurringAppointmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AppointmentResponse]:
    """Create recurring appointments based on a pattern."""
    # Verify student exists
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # Calculate interval based on recurrence pattern
    if request.recurrence_pattern.value == "daily":
        interval = timedelta(days=1)
    elif request.recurrence_pattern.value == "weekly":
        interval = timedelta(weeks=1)
    elif request.recurrence_pattern.value == "biweekly":
        interval = timedelta(weeks=2)
    else:  # monthly
        interval = timedelta(days=30)  # Approximation

    appointments = []
    current_date = request.start_date

    for _ in range(request.occurrences):
        appointment = Appointment(
            trainer_id=current_user.id,
            student_id=request.student_id,
            organization_id=request.organization_id,
            date_time=current_date,
            duration_minutes=request.duration_minutes,
            workout_type=request.workout_type,
            notes=request.notes,
            status=AppointmentStatus.PENDING,
        )
        db.add(appointment)
        appointments.append(appointment)
        current_date = current_date + interval

    await db.commit()

    # Refresh all appointments
    for appointment in appointments:
        await db.refresh(appointment)

    return [
        _appointment_to_response(a, trainer_name=current_user.name, student_name=student.name)
        for a in appointments
    ]


@router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Get a specific appointment."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Check access
    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return _appointment_to_response(appointment)


@router.put("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    request: AppointmentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Update an appointment (trainer only)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can update this appointment",
        )

    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit a cancelled or completed session",
        )

    if request.date_time is not None:
        appointment.date_time = request.date_time
    if request.duration_minutes is not None:
        appointment.duration_minutes = request.duration_minutes
    if request.workout_type is not None:
        appointment.workout_type = request.workout_type
    if request.notes is not None:
        appointment.notes = request.notes

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment)


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: UUID,
    request: AppointmentCancel,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Cancel an appointment."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Both trainer and student can cancel
    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel a session that is already cancelled or completed",
        )

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = request.reason

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment)


@router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Confirm an appointment (trainer or student)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if appointment.status != AppointmentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only confirm pending sessions",
        )

    appointment.status = AppointmentStatus.CONFIRMED

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment)


@router.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an appointment (trainer only)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can delete this appointment",
        )

    if appointment.status == AppointmentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a completed session with attendance records",
        )

    await db.delete(appointment)
    await db.commit()


@router.patch("/appointments/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: UUID,
    request: AppointmentReschedule,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Reschedule an appointment to a new date/time."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Only trainer can reschedule
    if appointment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can reschedule this appointment",
        )

    # Cannot reschedule completed or cancelled appointments
    if appointment.status in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reschedule {appointment.status.value} appointment",
        )

    appointment.date_time = request.new_date_time
    if request.reason:
        appointment.notes = f"{appointment.notes or ''}\nRescheduled: {request.reason}".strip()

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment)


@router.post("/appointments/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: UUID,
    request: AppointmentComplete,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Mark an appointment as completed."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    # Only trainer can complete
    if appointment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the trainer can complete this appointment",
        )

    # Cannot complete already cancelled appointment
    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot complete a cancelled appointment",
        )

    appointment.status = AppointmentStatus.COMPLETED
    if request.notes:
        appointment.notes = f"{appointment.notes or ''}\nCompletion notes: {request.notes}".strip()

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment)


@router.get("/availability", response_model=TrainerAvailabilityResponse)
async def get_trainer_availability(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    trainer_id: Annotated[UUID | None, Query()] = None,
) -> TrainerAvailabilityResponse:
    """Get trainer availability slots."""
    target_trainer_id = trainer_id or current_user.id

    query = select(TrainerAvailability).where(
        TrainerAvailability.trainer_id == target_trainer_id
    ).order_by(TrainerAvailability.day_of_week, TrainerAvailability.start_time)

    result = await db.execute(query)
    availability_slots = list(result.scalars().all())

    return TrainerAvailabilityResponse(
        trainer_id=target_trainer_id,
        slots=[
            TrainerAvailabilitySlot(
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
            for slot in availability_slots
        ],
    )


@router.post("/availability", response_model=TrainerAvailabilityResponse)
async def set_trainer_availability(
    request: TrainerAvailabilityCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrainerAvailabilityResponse:
    """Set trainer availability slots (replaces existing)."""
    # Delete existing availability
    query = select(TrainerAvailability).where(
        TrainerAvailability.trainer_id == current_user.id
    )
    result = await db.execute(query)
    existing_slots = list(result.scalars().all())
    for slot in existing_slots:
        await db.delete(slot)

    # Create new availability slots
    new_slots = []
    for slot_data in request.slots:
        slot = TrainerAvailability(
            trainer_id=current_user.id,
            day_of_week=slot_data.day_of_week,
            start_time=slot_data.start_time,
            end_time=slot_data.end_time,
        )
        db.add(slot)
        new_slots.append(slot)

    await db.commit()

    return TrainerAvailabilityResponse(
        trainer_id=current_user.id,
        slots=[
            TrainerAvailabilitySlot(
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
            )
            for slot in new_slots
        ],
    )


# --- Conflict Detection ---


@router.get("/conflicts", response_model=ConflictCheckResponse)
async def check_conflicts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    date_time: Annotated[datetime, Query()],
    duration: Annotated[int, Query(ge=15, le=240)] = 60,
    student_id: Annotated[UUID | None, Query()] = None,
) -> ConflictCheckResponse:
    """Check for scheduling conflicts before creating an appointment."""
    conflicts: list[ConflictDetail] = []
    warnings: list[ConflictDetail] = []

    end_time = date_time + timedelta(minutes=duration)
    buffer_minutes = 15

    # 1. Check trainer's existing appointments for overlap
    trainer_query = (
        select(Appointment)
        .where(
            and_(
                Appointment.trainer_id == current_user.id,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.date_time < end_time,
                (Appointment.date_time + timedelta(minutes=1) * Appointment.duration_minutes) > date_time,
            )
        )
    )
    # Use raw SQL for interval calculation since SQLAlchemy timedelta * column is tricky
    trainer_appointments_query = (
        select(Appointment)
        .where(
            and_(
                Appointment.trainer_id == current_user.id,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.date_time.between(
                    date_time - timedelta(minutes=240),  # Max session is 240min
                    end_time,
                ),
            )
        )
    )
    result = await db.execute(trainer_appointments_query)
    trainer_appointments = list(result.scalars().all())

    for apt in trainer_appointments:
        apt_end = apt.date_time + timedelta(minutes=apt.duration_minutes)
        # Check overlap
        if apt.date_time < end_time and apt_end > date_time:
            conflicts.append(ConflictDetail(
                type="trainer_overlap",
                message=f"Você já tem sessão com {apt.student.name if apt.student else 'aluno'} das {apt.date_time.strftime('%H:%M')} às {apt_end.strftime('%H:%M')}",
                conflicting_appointment_id=apt.id,
                conflicting_student_name=apt.student.name if apt.student else None,
                conflicting_time=apt.date_time,
            ))
        # Check buffer
        elif (apt.date_time - end_time).total_seconds() < buffer_minutes * 60 and apt.date_time > date_time:
            warnings.append(ConflictDetail(
                type="buffer_too_short",
                message=f"Menos de {buffer_minutes}min entre esta sessão e a próxima ({apt.student.name if apt.student else 'aluno'} às {apt.date_time.strftime('%H:%M')})",
                conflicting_appointment_id=apt.id,
                conflicting_time=apt.date_time,
            ))
        elif (date_time - apt_end).total_seconds() < buffer_minutes * 60 and apt_end < end_time:
            warnings.append(ConflictDetail(
                type="buffer_too_short",
                message=f"Menos de {buffer_minutes}min entre a sessão anterior ({apt.student.name if apt.student else 'aluno'}) e esta",
                conflicting_appointment_id=apt.id,
                conflicting_time=apt.date_time,
            ))

    # 2. Check student's existing appointments for overlap
    if student_id:
        student_appointments_query = (
            select(Appointment)
            .where(
                and_(
                    Appointment.student_id == student_id,
                    Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                    Appointment.date_time.between(
                        date_time - timedelta(minutes=240),
                        end_time,
                    ),
                )
            )
        )
        result = await db.execute(student_appointments_query)
        student_appointments = list(result.scalars().all())

        for apt in student_appointments:
            apt_end = apt.date_time + timedelta(minutes=apt.duration_minutes)
            if apt.date_time < end_time and apt_end > date_time:
                conflicts.append(ConflictDetail(
                    type="student_overlap",
                    message=f"O aluno já tem sessão das {apt.date_time.strftime('%H:%M')} às {apt_end.strftime('%H:%M')}",
                    conflicting_appointment_id=apt.id,
                    conflicting_time=apt.date_time,
                ))

    # 3. Check trainer availability
    target_day = date_time.weekday()  # 0=Monday
    availability_query = (
        select(TrainerAvailability)
        .where(
            and_(
                TrainerAvailability.trainer_id == current_user.id,
                TrainerAvailability.day_of_week == target_day,
            )
        )
    )
    result = await db.execute(availability_query)
    availability_slots = list(result.scalars().all())

    if availability_slots:
        # Check if the appointment falls within any availability slot
        appointment_start = date_time.strftime("%H:%M")
        appointment_end = end_time.strftime("%H:%M")
        in_availability = any(
            slot.start_time <= appointment_start and slot.end_time >= appointment_end
            for slot in availability_slots
        )
        if not in_availability:
            warnings.append(ConflictDetail(
                type="outside_availability",
                message="Este horário está fora da sua disponibilidade configurada",
            ))

    return ConflictCheckResponse(
        has_conflicts=len(conflicts) > 0,
        conflicts=conflicts,
        warnings=warnings,
    )


# --- Auto-generate schedule from service plan ---


@router.post("/auto-generate", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
async def auto_generate_schedule(
    request: AutoGenerateScheduleRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AppointmentResponse]:
    """Auto-generate appointments from a service plan's schedule config."""
    from src.domains.billing.models import ServicePlan

    plan = await db.get(ServicePlan, request.service_plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service plan not found",
        )

    if plan.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the plan's trainer can generate schedule",
        )

    if not plan.schedule_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service plan has no schedule configuration",
        )

    # Generate appointments for the next N weeks
    today = date.today()
    appointments_created = []

    for week_offset in range(request.weeks_ahead):
        week_start = today + timedelta(weeks=week_offset)
        # Adjust to Monday of that week
        monday = week_start - timedelta(days=week_start.weekday())

        for slot in plan.schedule_config:
            slot_day = slot.get("day_of_week", 0)
            slot_time = slot.get("time", "09:00")
            slot_duration = slot.get("duration_minutes", 60)

            # Calculate the actual date for this slot
            appointment_date = monday + timedelta(days=slot_day)

            # Skip dates in the past
            if appointment_date < today:
                continue

            # Parse time
            hour, minute = map(int, slot_time.split(":"))
            appointment_datetime = datetime.combine(
                appointment_date,
                datetime.min.time().replace(hour=hour, minute=minute),
            )

            # Check if appointment already exists for this slot
            existing_query = (
                select(Appointment)
                .where(
                    and_(
                        Appointment.trainer_id == current_user.id,
                        Appointment.student_id == plan.student_id,
                        Appointment.date_time == appointment_datetime,
                        Appointment.status != AppointmentStatus.CANCELLED,
                    )
                )
            )
            result = await db.execute(existing_query)
            if result.scalar():
                continue  # Skip — already exists

            apt = Appointment(
                trainer_id=current_user.id,
                student_id=plan.student_id,
                organization_id=plan.organization_id,
                date_time=appointment_datetime,
                duration_minutes=slot_duration,
                status=AppointmentStatus.CONFIRMED if request.auto_confirm else AppointmentStatus.PENDING,
                service_plan_id=plan.id,
                is_complimentary=plan.plan_type.value == "free_trial",
            )
            db.add(apt)
            appointments_created.append(apt)

    await db.commit()

    # Reload all with relationships
    created_ids = [a.id for a in appointments_created]
    if created_ids:
        reload_query = select(Appointment).where(Appointment.id.in_(created_ids)).order_by(Appointment.date_time)
        result = await db.execute(reload_query)
        appointments_created = list(result.scalars().all())

    return [_appointment_to_response(a) for a in appointments_created]


# --- Duplicate week ---


@router.post("/duplicate-week")
async def duplicate_week(
    request: DuplicateWeekRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Duplicate all non-cancelled appointments from one week to another."""
    source_start = datetime.combine(request.source_week_start, datetime.min.time())
    source_end = datetime.combine(request.source_week_start + timedelta(days=6), datetime.max.time())

    # Fetch all non-cancelled appointments in the source week for this trainer
    source_query = (
        select(Appointment)
        .where(
            and_(
                Appointment.trainer_id == current_user.id,
                Appointment.status != AppointmentStatus.CANCELLED,
                Appointment.date_time >= source_start,
                Appointment.date_time <= source_end,
            )
        )
        .order_by(Appointment.date_time)
    )
    result = await db.execute(source_query)
    source_appointments = list(result.scalars().all())

    total_source = len(source_appointments)
    day_offset = (request.target_week_start - request.source_week_start).days

    created = 0
    skipped = 0

    for apt in source_appointments:
        target_datetime = apt.date_time + timedelta(days=day_offset)

        # Conflict check (unless skip_conflicts is True)
        if not request.skip_conflicts:
            target_end = target_datetime + timedelta(minutes=apt.duration_minutes)
            # Check trainer overlap in target slot
            conflict_query = (
                select(Appointment)
                .where(
                    and_(
                        Appointment.trainer_id == current_user.id,
                        Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                        Appointment.date_time.between(
                            target_datetime - timedelta(minutes=240),
                            target_end,
                        ),
                    )
                )
            )
            conflict_result = await db.execute(conflict_query)
            existing = list(conflict_result.scalars().all())

            has_conflict = False
            for ex in existing:
                ex_end = ex.date_time + timedelta(minutes=ex.duration_minutes)
                if ex.date_time < target_end and ex_end > target_datetime:
                    has_conflict = True
                    break

            if has_conflict:
                skipped += 1
                continue

        new_apt = Appointment(
            trainer_id=current_user.id,
            student_id=apt.student_id,
            organization_id=apt.organization_id,
            date_time=target_datetime,
            duration_minutes=apt.duration_minutes,
            workout_type=apt.workout_type,
            notes=apt.notes,
            status=AppointmentStatus.PENDING,
            session_type=SessionType.SCHEDULED,
            service_plan_id=apt.service_plan_id,
            is_complimentary=apt.is_complimentary,
        )
        db.add(new_apt)
        created += 1

    await db.commit()

    return {
        "created": created,
        "skipped": skipped,
        "total_source": total_source,
    }


# --- Self-service booking endpoints ---


async def _get_or_create_trainer_settings(
    db: AsyncSession, trainer_id: UUID,
) -> TrainerSettings:
    """Get trainer settings, creating defaults if they don't exist."""
    result = await db.execute(
        select(TrainerSettings).where(TrainerSettings.trainer_id == trainer_id)
    )
    settings = result.scalar_one_or_none()
    if not settings:
        settings = TrainerSettings(
            trainer_id=trainer_id,
            default_start_time=time(6, 0),
            default_end_time=time(21, 0),
            session_duration_minutes=60,
            slot_interval_minutes=30,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


@router.get("/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    trainer_id: Annotated[UUID, Query()],
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> AvailableSlotsResponse:
    """Get available time slots for a trainer on a given date."""
    from datetime import date as date_type

    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    # 1. Get trainer settings
    settings = await _get_or_create_trainer_settings(db, trainer_id)

    # 2. Generate all possible slots
    interval = timedelta(minutes=settings.slot_interval_minutes)
    slot_start = datetime.combine(target_date, settings.default_start_time)
    day_end = datetime.combine(target_date, settings.default_end_time)

    all_slots: list[datetime] = []
    current = slot_start
    while current + timedelta(minutes=settings.session_duration_minutes) <= day_end:
        all_slots.append(current)
        current += interval

    # 3. Get blocked slots (recurring for this day_of_week + specific date)
    day_of_week = target_date.weekday()
    blocked_query = select(TrainerBlockedSlot).where(
        and_(
            TrainerBlockedSlot.trainer_id == trainer_id,
        )
    ).where(
        (
            (TrainerBlockedSlot.is_recurring == True) & (TrainerBlockedSlot.day_of_week == day_of_week)  # noqa: E712
        ) | (
            (TrainerBlockedSlot.is_recurring == False) & (TrainerBlockedSlot.specific_date == target_date)  # noqa: E712
        )
    )
    result = await db.execute(blocked_query)
    blocked_slots = list(result.scalars().all())

    # 4. Get existing appointments for that day
    start_of_day = datetime.combine(target_date, time(0, 0))
    end_of_day = datetime.combine(target_date, time(23, 59, 59))
    apt_query = select(Appointment).where(
        and_(
            Appointment.trainer_id == trainer_id,
            Appointment.date_time >= start_of_day,
            Appointment.date_time <= end_of_day,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
        )
    )
    result = await db.execute(apt_query)
    existing_appointments = list(result.scalars().all())

    # 5. Build response
    now = datetime.now()
    response_slots: list[AvailableSlotResponse] = []

    for slot_dt in all_slots:
        slot_time = slot_dt.time()
        slot_end_dt = slot_dt + timedelta(minutes=settings.session_duration_minutes)
        available = True

        # Skip past slots
        if slot_dt <= now:
            available = False

        # Check blocked slots
        if available:
            for blocked in blocked_slots:
                if slot_time < blocked.end_time and slot_end_dt.time() > blocked.start_time:
                    available = False
                    break

        # Check existing appointments
        if available:
            for apt in existing_appointments:
                apt_end = apt.date_time + timedelta(minutes=apt.duration_minutes)
                if slot_dt < apt_end and slot_end_dt > apt.date_time:
                    available = False
                    break

        response_slots.append(AvailableSlotResponse(
            time=slot_time.strftime("%H:%M"),
            available=available,
        ))

    return AvailableSlotsResponse(
        date=target_date,
        trainer_id=trainer_id,
        slots=response_slots,
    )


@router.post("/book", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def student_book_session(
    request: StudentBookSessionRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Student books a session with their trainer (self-service)."""
    from src.domains.billing.models import ServicePlan, ServicePlanType
    from src.domains.notifications.models import NotificationPriority, NotificationType
    from src.domains.notifications.router import create_notification
    from src.domains.notifications.schemas import NotificationCreate

    # Validate service plan exists and belongs to this student
    plan = await db.get(ServicePlan, request.service_plan_id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service plan not found")
    if plan.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This plan does not belong to you")
    if not plan.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service plan is not active")
    if plan.trainer_id != request.trainer_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Trainer does not match service plan")

    # For packages, check remaining sessions
    if plan.plan_type == ServicePlanType.PACKAGE:
        if plan.remaining_sessions is not None and plan.remaining_sessions <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No remaining sessions in package")
        if plan.package_expiry_date and plan.package_expiry_date < datetime.now().date():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Package has expired")

    # Check slot is available (no conflicts)
    slot_end = request.date_time + timedelta(minutes=request.duration_minutes)
    conflict_query = select(Appointment).where(
        and_(
            Appointment.trainer_id == request.trainer_id,
            Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
            Appointment.date_time < slot_end,
        )
    )
    result = await db.execute(conflict_query)
    conflicts = [
        a for a in result.scalars().all()
        if a.date_time + timedelta(minutes=a.duration_minutes) > request.date_time
    ]
    if conflicts:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Time slot is not available")

    # Determine session type and complimentary flag
    session_type = SessionType.SCHEDULED
    is_complimentary = False
    if plan.plan_type == ServicePlanType.FREE_TRIAL:
        session_type = SessionType.TRIAL
        is_complimentary = True

    # Create appointment
    appointment = Appointment(
        trainer_id=request.trainer_id,
        student_id=current_user.id,
        organization_id=plan.organization_id,
        date_time=request.date_time,
        duration_minutes=request.duration_minutes,
        workout_type=request.workout_type,
        status=AppointmentStatus.CONFIRMED,
        service_plan_id=plan.id,
        session_type=session_type,
        is_complimentary=is_complimentary,
    )
    db.add(appointment)

    # Note: remaining_sessions is NOT decremented at booking time.
    # Credits are consumed when attendance is marked as ATTENDED.

    await db.commit()
    await db.refresh(appointment)

    # Send notification to trainer
    formatted_time = request.date_time.strftime("%a %d/%m %H:%M")
    try:
        await create_notification(
            db,
            NotificationCreate(
                user_id=request.trainer_id,
                notification_type=NotificationType.SESSION_BOOKED_BY_STUDENT,
                priority=NotificationPriority.HIGH,
                title="Nova sessão agendada",
                body=f"{current_user.name} agendou {formatted_time}",
                icon="calendar-plus",
                action_type="navigate",
                action_data=json.dumps({"route": f"/schedule/day/{request.date_time.strftime('%Y-%m-%d')}"}),
                reference_type="appointment",
                reference_id=appointment.id,
                sender_id=current_user.id,
            ),
        )
    except Exception:
        pass  # Don't fail booking if notification fails

    return _appointment_to_response(appointment)


# --- Trainer availability management ---


@router.get("/trainer-availability", response_model=TrainerFullAvailabilityResponse)
async def get_trainer_full_availability(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrainerFullAvailabilityResponse:
    """Get trainer's settings and blocked slots."""
    settings = await _get_or_create_trainer_settings(db, current_user.id)

    blocked_query = select(TrainerBlockedSlot).where(
        TrainerBlockedSlot.trainer_id == current_user.id
    ).order_by(TrainerBlockedSlot.is_recurring.desc(), TrainerBlockedSlot.day_of_week, TrainerBlockedSlot.start_time)
    result = await db.execute(blocked_query)
    blocked_slots = list(result.scalars().all())

    return TrainerFullAvailabilityResponse(
        settings=TrainerSettingsResponse(
            trainer_id=settings.trainer_id,
            default_start_time=settings.default_start_time,
            default_end_time=settings.default_end_time,
            session_duration_minutes=settings.session_duration_minutes,
            slot_interval_minutes=settings.slot_interval_minutes,
        ),
        blocked_slots=[
            TrainerBlockedSlotResponse(
                id=s.id,
                trainer_id=s.trainer_id,
                day_of_week=s.day_of_week,
                specific_date=s.specific_date,
                start_time=s.start_time,
                end_time=s.end_time,
                reason=s.reason,
                is_recurring=s.is_recurring,
                created_at=s.created_at,
            )
            for s in blocked_slots
        ],
    )


@router.post(
    "/trainer-availability/block",
    response_model=TrainerBlockedSlotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_blocked_slot(
    request: TrainerBlockedSlotCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrainerBlockedSlotResponse:
    """Create a blocked time slot for the trainer."""
    if request.is_recurring and request.day_of_week is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="day_of_week is required for recurring blocks",
        )
    if not request.is_recurring and request.specific_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="specific_date is required for non-recurring blocks",
        )

    blocked = TrainerBlockedSlot(
        trainer_id=current_user.id,
        day_of_week=request.day_of_week,
        specific_date=request.specific_date,
        start_time=request.start_time,
        end_time=request.end_time,
        reason=request.reason,
        is_recurring=request.is_recurring,
    )
    db.add(blocked)
    await db.commit()
    await db.refresh(blocked)

    return TrainerBlockedSlotResponse(
        id=blocked.id,
        trainer_id=blocked.trainer_id,
        day_of_week=blocked.day_of_week,
        specific_date=blocked.specific_date,
        start_time=blocked.start_time,
        end_time=blocked.end_time,
        reason=blocked.reason,
        is_recurring=blocked.is_recurring,
        created_at=blocked.created_at,
    )


@router.delete("/trainer-availability/block/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blocked_slot(
    block_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a blocked time slot."""
    blocked = await db.get(TrainerBlockedSlot, block_id)
    if not blocked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Blocked slot not found")
    if blocked.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await db.delete(blocked)
    await db.commit()


@router.put("/trainer-availability/settings", response_model=TrainerSettingsResponse)
async def update_trainer_settings(
    request: TrainerSettingsUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrainerSettingsResponse:
    """Update trainer scheduling settings."""
    settings = await _get_or_create_trainer_settings(db, current_user.id)

    if request.default_start_time is not None:
        settings.default_start_time = request.default_start_time
    if request.default_end_time is not None:
        settings.default_end_time = request.default_end_time
    if request.session_duration_minutes is not None:
        settings.session_duration_minutes = request.session_duration_minutes
    if request.slot_interval_minutes is not None:
        settings.slot_interval_minutes = request.slot_interval_minutes

    await db.commit()
    await db.refresh(settings)

    return TrainerSettingsResponse(
        trainer_id=settings.trainer_id,
        default_start_time=settings.default_start_time,
        default_end_time=settings.default_end_time,
        session_duration_minutes=settings.session_duration_minutes,
        slot_interval_minutes=settings.slot_interval_minutes,
    )


# --- Attendance tracking ---


@router.patch("/appointments/{appointment_id}/attendance", response_model=AppointmentResponse)
async def update_attendance(
    appointment_id: UUID,
    request: AttendanceUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Trainer marks attendance for a session."""
    from src.domains.notifications.models import NotificationPriority, NotificationType
    from src.domains.notifications.router import create_notification
    from src.domains.notifications.schemas import NotificationCreate

    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")
    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the trainer can mark attendance")

    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot mark attendance on a cancelled session",
        )

    appointment.attendance_status = request.attendance_status
    if request.notes:
        appointment.notes = f"{appointment.notes or ''}\nAttendance: {request.notes}".strip()

    # If attended, mark as completed and handle billing
    if request.attendance_status == AttendanceStatus.ATTENDED:
        appointment.status = AppointmentStatus.COMPLETED

        # Billing integration: consume session credit or create payment
        if appointment.service_plan_id and not appointment.is_complimentary:
            from src.domains.billing.models import Payment, PaymentStatus, PaymentType, ServicePlan, ServicePlanType

            plan = await db.get(ServicePlan, appointment.service_plan_id)
            if plan:
                if plan.plan_type == ServicePlanType.PACKAGE and plan.remaining_sessions is not None:
                    plan.remaining_sessions = max(0, plan.remaining_sessions - 1)
                elif plan.plan_type == ServicePlanType.DROP_IN and plan.per_session_cents:
                    payment = Payment(
                        payer_id=appointment.student_id,
                        payee_id=appointment.trainer_id,
                        organization_id=appointment.organization_id,
                        payment_type=PaymentType.SESSION,
                        description=f"Sessão avulsa - {appointment.date_time.strftime('%d/%m/%Y %H:%M')}",
                        amount_cents=plan.per_session_cents,
                        status=PaymentStatus.PENDING,
                        due_date=appointment.date_time.date(),
                        service_plan_id=plan.id,
                    )
                    db.add(payment)
                    appointment.payment_id = payment.id

    # Package depletion alerts (after credit consumption)
    if (
        request.attendance_status == AttendanceStatus.ATTENDED
        and appointment.service_plan_id
        and not appointment.is_complimentary
    ):
        try:
            from src.domains.billing.models import ServicePlan, ServicePlanType
            _plan = await db.get(ServicePlan, appointment.service_plan_id)
            if _plan and _plan.plan_type == ServicePlanType.PACKAGE and _plan.remaining_sessions is not None:
                student_name = appointment.student.name if appointment.student else "Aluno"
                if _plan.remaining_sessions == 0:
                    # Package depleted
                    await create_notification(
                        db,
                        NotificationCreate(
                            user_id=appointment.trainer_id,
                            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                            priority=NotificationPriority.HIGH,
                            title="Pacote esgotado",
                            body=f"O pacote de {student_name} ({_plan.name}) não tem mais sessões restantes",
                            icon="package-x",
                            action_type="navigate",
                            action_data=json.dumps({"route": "/billing/plans"}),
                            reference_type="service_plan",
                            reference_id=_plan.id,
                        ),
                    )
                elif _plan.remaining_sessions <= 2:
                    # Package running low
                    await create_notification(
                        db,
                        NotificationCreate(
                            user_id=appointment.trainer_id,
                            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                            priority=NotificationPriority.NORMAL,
                            title="Pacote quase acabando",
                            body=f"{student_name} tem apenas {_plan.remaining_sessions} sessão(ões) restante(s) no pacote {_plan.name}",
                            icon="package-minus",
                            action_type="navigate",
                            action_data=json.dumps({"route": "/billing/plans"}),
                            reference_type="service_plan",
                            reference_id=_plan.id,
                        ),
                    )
        except Exception:
            pass  # Non-critical

    # If missed + grant_makeup, create a makeup appointment placeholder
    makeup_appointment = None
    if request.attendance_status == AttendanceStatus.MISSED and request.grant_makeup:
        makeup_appointment = Appointment(
            trainer_id=appointment.trainer_id,
            student_id=appointment.student_id,
            organization_id=appointment.organization_id,
            date_time=datetime.now() + timedelta(days=7),  # placeholder, trainer will reschedule
            duration_minutes=appointment.duration_minutes,
            workout_type=appointment.workout_type,
            status=AppointmentStatus.PENDING,
            service_plan_id=appointment.service_plan_id,
            session_type=SessionType.MAKEUP,
            notes="Reposição de falta",
        )
        db.add(makeup_appointment)

    await db.commit()
    await db.refresh(appointment)

    # Notify student
    status_labels = {
        AttendanceStatus.ATTENDED: "Presença confirmada",
        AttendanceStatus.MISSED: "Falta registrada",
        AttendanceStatus.LATE_CANCELLED: "Cancelamento tardio registrado",
    }
    label = status_labels.get(request.attendance_status, "Presença atualizada")
    makeup_note = " (reposição concedida)" if request.grant_makeup and request.attendance_status == AttendanceStatus.MISSED else ""

    try:
        await create_notification(
            db,
            NotificationCreate(
                user_id=appointment.student_id,
                notification_type=NotificationType.ATTENDANCE_MARKED,
                priority=NotificationPriority.NORMAL,
                title=label,
                body=f"{label}{makeup_note} para sessão de {appointment.date_time.strftime('%d/%m %H:%M')}",
                icon="clipboard-check",
                action_type="navigate",
                action_data=json.dumps({"route": "/schedule"}),
                reference_type="appointment",
                reference_id=appointment.id,
                sender_id=current_user.id,
            ),
        )
    except Exception:
        pass

    return _appointment_to_response(appointment)
