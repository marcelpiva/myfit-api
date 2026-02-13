"""Availability management, conflict detection, booking, and trainer settings endpoints."""
import json
import logging
from datetime import datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.notifications.push_service import send_push_notification

from .models import (
    Appointment,
    AppointmentStatus,
    SessionType,
    TrainerAvailability,
    TrainerBlockedSlot,
)
from .schemas import (
    AppointmentResponse,
    AvailableSlotResponse,
    AvailableSlotsResponse,
    ConflictCheckResponse,
    ConflictDetail,
    StudentBookSessionRequest,
    TrainerAvailabilityCreate,
    TrainerAvailabilityResponse,
    TrainerAvailabilitySlot,
    TrainerBlockedSlotCreate,
    TrainerBlockedSlotResponse,
    TrainerFullAvailabilityResponse,
    TrainerSettingsResponse,
    TrainerSettingsUpdate,
)
from .shared import _appointment_to_response, _get_or_create_trainer_settings

schedule_logger = logging.getLogger(__name__)

availability_router = APIRouter()


# ==================== Availability CRUD ====================

@availability_router.get("/availability", response_model=TrainerAvailabilityResponse)
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


@availability_router.post("/availability", response_model=TrainerAvailabilityResponse)
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


# ==================== Conflict Detection ====================

@availability_router.get("/conflicts", response_model=ConflictCheckResponse)
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


# ==================== Available Slots ====================

@availability_router.get("/available-slots", response_model=AvailableSlotsResponse)
async def get_available_slots(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    trainer_id: Annotated[UUID, Query()],
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> AvailableSlotsResponse:
    """Get available time slots for a trainer on a given date."""
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


# ==================== Self-service Booking ====================

@availability_router.post("/book", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
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
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Push notification failed on booking: %s", e)

    return _appointment_to_response(appointment)


# ==================== Trainer Availability Management ====================

@availability_router.get("/trainer-availability", response_model=TrainerFullAvailabilityResponse)
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
            late_cancel_window_hours=settings.late_cancel_window_hours,
            late_cancel_policy=settings.late_cancel_policy,
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


@availability_router.post(
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


@availability_router.delete("/trainer-availability/block/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@availability_router.put("/trainer-availability/settings", response_model=TrainerSettingsResponse)
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
    if request.late_cancel_window_hours is not None:
        settings.late_cancel_window_hours = request.late_cancel_window_hours
    if request.late_cancel_policy is not None:
        if request.late_cancel_policy not in ("charge", "warn", "block"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="late_cancel_policy must be 'charge', 'warn', or 'block'",
            )
        settings.late_cancel_policy = request.late_cancel_policy

    await db.commit()
    await db.refresh(settings)

    return TrainerSettingsResponse(
        trainer_id=settings.trainer_id,
        default_start_time=settings.default_start_time,
        default_end_time=settings.default_end_time,
        session_duration_minutes=settings.session_duration_minutes,
        slot_interval_minutes=settings.slot_interval_minutes,
        late_cancel_window_hours=settings.late_cancel_window_hours,
        late_cancel_policy=settings.late_cancel_policy,
    )
