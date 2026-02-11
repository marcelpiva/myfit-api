"""Schedule router for appointment management."""
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.models import User

from .models import Appointment, AppointmentStatus, TrainerAvailability
from .schemas import (
    AppointmentCancel,
    AppointmentComplete,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentUpdate,
    AutoGenerateScheduleRequest,
    ConflictCheckResponse,
    ConflictDetail,
    RecurringAppointmentCreate,
    TrainerAvailabilityCreate,
    TrainerAvailabilityResponse,
    TrainerAvailabilitySlot,
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

    appointment = Appointment(
        trainer_id=current_user.id,
        student_id=request.student_id,
        organization_id=request.organization_id,
        date_time=request.date_time,
        duration_minutes=request.duration_minutes,
        workout_type=request.workout_type,
        notes=request.notes,
        status=AppointmentStatus.PENDING,
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
