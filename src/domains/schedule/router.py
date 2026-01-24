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
        trainer_name=trainer_name or (appointment.trainer.name if appointment.trainer else None),
        student_name=student_name or (appointment.student.name if appointment.student else None),
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
