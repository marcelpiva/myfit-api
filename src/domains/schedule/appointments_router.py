"""Appointment CRUD, analytics, attendance, group sessions, and calendar export endpoints."""
import json
import logging
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.notifications.push_service import send_push_notification
from src.domains.users.models import User

from .models import (
    Appointment,
    AppointmentParticipant,
    AppointmentStatus,
    AppointmentType,
    AttendanceStatus,
    DifficultyLevel,
    EvaluatorRole,
    SessionEvaluation,
    SessionType,
    TrainerAvailability,
)
from .schemas import (
    AddParticipantsRequest,
    AppointmentCancel,
    AppointmentComplete,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentUpdate,
    AttendanceUpdate,
    DayOfWeekAnalytics,
    GroupSessionCreate,
    HourAnalytics,
    ParticipantAttendanceUpdate,
    ParticipantResponse,
    RecurringAppointmentCreate,
    ScheduleAnalyticsResponse,
    SessionEvaluationCreate,
    SessionEvaluationResponse,
    StudentAnalytics,
    StudentReliability,
    StudentReliabilityResponse,
    UpcomingAppointmentsResponse,
)
from .shared import _appointment_to_response, _get_or_create_trainer_settings

schedule_logger = logging.getLogger(__name__)

appointments_router = APIRouter()


# ==================== Analytics ====================

@appointments_router.get("/analytics", response_model=ScheduleAnalyticsResponse)
async def get_schedule_analytics(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
    student_id: Annotated[UUID | None, Query()] = None,
) -> ScheduleAnalyticsResponse:
    """Get schedule analytics for a date range."""
    start_dt = datetime.combine(from_date, datetime.min.time())
    end_dt = datetime.combine(to_date, datetime.max.time())

    # Base filter: trainer's appointments in date range
    filters = [
        Appointment.trainer_id == current_user.id,
        Appointment.date_time >= start_dt,
        Appointment.date_time <= end_dt,
    ]
    if student_id:
        filters.append(Appointment.student_id == student_id)

    # Fetch all matching appointments with student info
    query = (
        select(Appointment)
        .where(and_(*filters))
        .order_by(Appointment.date_time)
    )
    result = await db.execute(query)
    appointments = list(result.scalars().all())

    # Aggregate totals
    total = len(appointments)
    attended = sum(1 for a in appointments if a.attendance_status == AttendanceStatus.ATTENDED)
    missed = sum(1 for a in appointments if a.attendance_status == AttendanceStatus.MISSED)
    late_cancelled = sum(1 for a in appointments if a.attendance_status == AttendanceStatus.LATE_CANCELLED)
    cancelled = sum(1 for a in appointments if a.status == AppointmentStatus.CANCELLED)
    pending = sum(1 for a in appointments if a.attendance_status == AttendanceStatus.SCHEDULED)

    denominator = attended + missed + late_cancelled
    attendance_rate = round((attended / denominator * 100), 1) if denominator > 0 else 0.0

    # By student
    student_map: dict[UUID, dict] = {}
    for a in appointments:
        sid = a.student_id
        if sid not in student_map:
            student_name = a.student.name if a.student else "Unknown"
            student_map[sid] = {
                "student_id": str(sid),
                "student_name": student_name,
                "total": 0,
                "attended": 0,
                "missed": 0,
            }
        student_map[sid]["total"] += 1
        if a.attendance_status == AttendanceStatus.ATTENDED:
            student_map[sid]["attended"] += 1
        elif a.attendance_status == AttendanceStatus.MISSED:
            student_map[sid]["missed"] += 1

    by_student = []
    for s in student_map.values():
        s_denom = s["attended"] + s["missed"]
        s["rate"] = round((s["attended"] / s_denom * 100), 1) if s_denom > 0 else 0.0
        by_student.append(StudentAnalytics(**s))

    # By day of week (0=Monday...6=Sunday)
    day_map: dict[int, dict] = {i: {"day": i, "total": 0, "attended": 0} for i in range(7)}
    for a in appointments:
        dow = a.date_time.weekday()
        day_map[dow]["total"] += 1
        if a.attendance_status == AttendanceStatus.ATTENDED:
            day_map[dow]["attended"] += 1
    by_day_of_week = [
        DayOfWeekAnalytics(**d) for d in day_map.values() if d["total"] > 0
    ]

    # By hour (0-23)
    hour_map: dict[int, dict] = {}
    for a in appointments:
        h = a.date_time.hour
        if h not in hour_map:
            hour_map[h] = {"hour": h, "total": 0, "attended": 0}
        hour_map[h]["total"] += 1
        if a.attendance_status == AttendanceStatus.ATTENDED:
            hour_map[h]["attended"] += 1
    by_hour = [
        HourAnalytics(**h) for h in sorted(hour_map.values(), key=lambda x: x["hour"])
    ]

    return ScheduleAnalyticsResponse(
        total=total,
        attended=attended,
        missed=missed,
        late_cancelled=late_cancelled,
        cancelled=cancelled,
        pending=pending,
        attendance_rate=attendance_rate,
        by_student=by_student,
        by_day_of_week=by_day_of_week,
        by_hour=by_hour,
    )


@appointments_router.get("/student-reliability", response_model=StudentReliabilityResponse)
async def get_student_reliability(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    student_id: Annotated[UUID | None, Query()] = None,
) -> StudentReliabilityResponse:
    """Get reliability scores for trainer's students."""
    now = datetime.now()
    window_90_start = now - timedelta(days=90)
    window_30_mid = now - timedelta(days=30)
    window_60_start = now - timedelta(days=60)

    filters = [
        Appointment.trainer_id == current_user.id,
        Appointment.date_time >= window_90_start,
        Appointment.date_time <= now,
    ]
    if student_id:
        filters.append(Appointment.student_id == student_id)

    query = select(Appointment).where(and_(*filters))
    result = await db.execute(query)
    appointments = list(result.scalars().all())

    student_data: dict[UUID, dict] = {}
    for a in appointments:
        sid = a.student_id
        if sid not in student_data:
            student_name = a.student.name if a.student else "Unknown"
            student_data[sid] = {
                "student_id": str(sid),
                "student_name": student_name,
                "total_sessions": 0,
                "attended": 0,
                "missed": 0,
                "late_cancelled": 0,
                "recent_attended": 0,
                "recent_total": 0,
                "prior_attended": 0,
                "prior_total": 0,
            }

        student_data[sid]["total_sessions"] += 1

        if a.attendance_status == AttendanceStatus.ATTENDED:
            student_data[sid]["attended"] += 1
        elif a.attendance_status == AttendanceStatus.MISSED:
            student_data[sid]["missed"] += 1
        elif a.attendance_status == AttendanceStatus.LATE_CANCELLED:
            student_data[sid]["late_cancelled"] += 1

        apt_dt = a.date_time if isinstance(a.date_time, datetime) else datetime.combine(a.date_time, datetime.min.time())
        if apt_dt >= window_30_mid:
            student_data[sid]["recent_total"] += 1
            if a.attendance_status == AttendanceStatus.ATTENDED:
                student_data[sid]["recent_attended"] += 1
        elif apt_dt >= window_60_start:
            student_data[sid]["prior_total"] += 1
            if a.attendance_status == AttendanceStatus.ATTENDED:
                student_data[sid]["prior_attended"] += 1

    students = []
    for s in student_data.values():
        denom = s["attended"] + s["missed"] + s["late_cancelled"]
        attendance_rate = round((s["attended"] / denom * 100), 1) if denom > 0 else 0.0

        if attendance_rate >= 90:
            reliability_score = "high"
        elif attendance_rate >= 70:
            reliability_score = "medium"
        else:
            reliability_score = "low"

        recent_rate = (s["recent_attended"] / s["recent_total"] * 100) if s["recent_total"] > 0 else 0.0
        prior_rate = (s["prior_attended"] / s["prior_total"] * 100) if s["prior_total"] > 0 else 0.0

        if s["recent_total"] == 0 or s["prior_total"] == 0:
            trend = "stable"
        elif recent_rate - prior_rate > 5:
            trend = "improving"
        elif prior_rate - recent_rate > 5:
            trend = "declining"
        else:
            trend = "stable"

        students.append(StudentReliability(
            student_id=s["student_id"],
            student_name=s["student_name"],
            total_sessions=s["total_sessions"],
            attended=s["attended"],
            missed=s["missed"],
            late_cancelled=s["late_cancelled"],
            attendance_rate=attendance_rate,
            reliability_score=reliability_score,
            trend=trend,
        ))

    return StudentReliabilityResponse(students=students)


# ==================== Appointment CRUD ====================

@appointments_router.get("/appointments", response_model=list[AppointmentResponse])
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


@appointments_router.get("/day/{date_str}", response_model=list[AppointmentResponse])
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


@appointments_router.get("/week/{date_str}", response_model=dict[str, list[AppointmentResponse]])
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

    by_date: dict[str, list[AppointmentResponse]] = {}
    for a in appointments:
        date_key = a.date_time.strftime("%Y-%m-%d")
        if date_key not in by_date:
            by_date[date_key] = []
        by_date[date_key].append(_appointment_to_response(a))

    return by_date


@appointments_router.post("/appointments", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_appointment(
    request: AppointmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Create a new appointment."""
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if request.service_plan_id:
        from src.domains.billing.models import ServicePlan as BillingServicePlan

        plan = await db.get(BillingServicePlan, request.service_plan_id)
        if not plan or not plan.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service plan not found or inactive")
        if plan.student_id != request.student_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Service plan does not belong to this student")

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

    return _appointment_to_response(appointment, trainer_name=current_user.name, student_name=student.name)


@appointments_router.get("/appointments/upcoming", response_model=UpcomingAppointmentsResponse)
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

    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    query = query.order_by(Appointment.date_time).limit(limit)
    result = await db.execute(query)
    appointments = list(result.scalars().all())

    return UpcomingAppointmentsResponse(
        appointments=[_appointment_to_response(a) for a in appointments],
        total_count=total_count,
    )


@appointments_router.post("/appointments/recurring", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
async def create_recurring_appointments(
    request: RecurringAppointmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AppointmentResponse]:
    """Create recurring appointments based on a pattern."""
    student = await db.get(User, request.student_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if request.recurrence_pattern.value == "daily":
        interval = timedelta(days=1)
    elif request.recurrence_pattern.value == "weekly":
        interval = timedelta(weeks=1)
    elif request.recurrence_pattern.value == "biweekly":
        interval = timedelta(weeks=2)
    else:
        interval = timedelta(days=30)

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
    for appointment in appointments:
        await db.refresh(appointment)

    return [
        _appointment_to_response(a, trainer_name=current_user.name, student_name=student.name)
        for a in appointments
    ]


@appointments_router.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Get a specific appointment."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return _appointment_to_response(appointment)


@appointments_router.put("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: UUID,
    request: AppointmentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Update an appointment (trainer only)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the trainer can update this appointment")

    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a cancelled or completed session")

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


@appointments_router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentResponse)
async def cancel_appointment(
    appointment_id: UUID,
    request: AppointmentCancel,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Cancel an appointment."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if appointment.status in (AppointmentStatus.CANCELLED, AppointmentStatus.COMPLETED):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel a session that is already cancelled or completed")

    now = datetime.now()
    trainer_settings = await _get_or_create_trainer_settings(db, appointment.trainer_id)
    hours_until = (appointment.date_time.replace(tzinfo=None) - now).total_seconds() / 3600

    if hours_until <= trainer_settings.late_cancel_window_hours:
        policy = trainer_settings.late_cancel_policy

        if policy == "block":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cancelamento não permitido dentro de {trainer_settings.late_cancel_window_hours} horas da sessão",
            )

        if policy == "charge":
            appointment.attendance_status = AttendanceStatus.LATE_CANCELLED
            if appointment.service_plan_id and not appointment.is_complimentary:
                from src.domains.billing.models import ServicePlan, ServicePlanType

                plan = await db.get(ServicePlan, appointment.service_plan_id)
                if plan and plan.plan_type == ServicePlanType.PACKAGE and plan.remaining_sessions is not None:
                    plan.remaining_sessions = max(0, plan.remaining_sessions - 1)

        if policy == "warn":
            appointment.attendance_status = AttendanceStatus.LATE_CANCELLED

    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = request.reason

    await db.commit()
    await db.refresh(appointment)

    try:
        await send_push_notification(
            db, appointment.student_id,
            "Sessão Cancelada",
            f"Sua sessão de {appointment.date_time.strftime('%d/%m às %H:%M')} foi cancelada.",
            data={"type": "APPOINTMENT_CANCELLED", "appointment_id": str(appointment.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Push notification failed on cancel: %s", e)

    return _appointment_to_response(appointment)


@appointments_router.post("/appointments/{appointment_id}/confirm", response_model=AppointmentResponse)
async def confirm_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Confirm an appointment (trainer or student)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if appointment.status != AppointmentStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only confirm pending sessions")

    appointment.status = AppointmentStatus.CONFIRMED
    await db.commit()
    await db.refresh(appointment)

    try:
        notify_user_id = appointment.student_id if current_user.id == appointment.trainer_id else appointment.trainer_id
        await send_push_notification(
            db, notify_user_id,
            "Sessão Confirmada",
            f"Sessão de {appointment.date_time.strftime('%d/%m às %H:%M')} foi confirmada.",
            data={"type": "APPOINTMENT_CONFIRMED", "appointment_id": str(appointment.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Push notification failed on confirm: %s", e)

    return _appointment_to_response(appointment)


@appointments_router.delete("/appointments/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_appointment(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an appointment (trainer only)."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the trainer can delete this appointment")

    if appointment.status == AppointmentStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete a completed session with attendance records")

    await db.delete(appointment)
    await db.commit()


@appointments_router.patch("/appointments/{appointment_id}/reschedule", response_model=AppointmentResponse)
async def reschedule_appointment(
    appointment_id: UUID,
    request: AppointmentReschedule,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Reschedule an appointment to a new date/time."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the trainer can reschedule this appointment")

    if appointment.status in [AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot reschedule {appointment.status.value} appointment")

    appointment.date_time = request.new_date_time
    if request.reason:
        appointment.notes = f"{appointment.notes or ''}\nRescheduled: {request.reason}".strip()

    await db.commit()
    await db.refresh(appointment)
    return _appointment_to_response(appointment)


@appointments_router.post("/appointments/{appointment_id}/complete", response_model=AppointmentResponse)
async def complete_appointment(
    appointment_id: UUID,
    request: AppointmentComplete,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Mark an appointment as completed."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found")

    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the trainer can complete this appointment")

    if appointment.status == AppointmentStatus.CANCELLED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot complete a cancelled appointment")

    appointment.status = AppointmentStatus.COMPLETED
    if request.notes:
        appointment.notes = f"{appointment.notes or ''}\nCompletion notes: {request.notes}".strip()

    await db.commit()
    await db.refresh(appointment)
    return _appointment_to_response(appointment)


# ==================== Attendance ====================

@appointments_router.patch("/appointments/{appointment_id}/attendance", response_model=AppointmentResponse)
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mark attendance on a cancelled session")

    appointment.attendance_status = request.attendance_status
    if request.notes:
        appointment.notes = f"{appointment.notes or ''}\nAttendance: {request.notes}".strip()

    if request.attendance_status == AttendanceStatus.ATTENDED:
        appointment.status = AppointmentStatus.COMPLETED

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

    # Package depletion alerts
    if request.attendance_status == AttendanceStatus.ATTENDED and appointment.service_plan_id and not appointment.is_complimentary:
        try:
            from src.domains.billing.models import ServicePlan, ServicePlanType
            _plan = await db.get(ServicePlan, appointment.service_plan_id)
            if _plan and _plan.plan_type == ServicePlanType.PACKAGE and _plan.remaining_sessions is not None:
                student_name = appointment.student.name if appointment.student else "Aluno"
                if _plan.remaining_sessions == 0:
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
        except (ConnectionError, OSError, RuntimeError) as e:
            schedule_logger.debug("Package expiry notification failed: %s", e)

    makeup_appointment = None
    if request.attendance_status == AttendanceStatus.MISSED and request.grant_makeup:
        makeup_appointment = Appointment(
            trainer_id=appointment.trainer_id,
            student_id=appointment.student_id,
            organization_id=appointment.organization_id,
            date_time=datetime.now() + timedelta(days=7),
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
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Attendance notification failed: %s", e)

    try:
        await send_push_notification(
            db, appointment.student_id,
            label,
            f"{label}{makeup_note} para sessão de {appointment.date_time.strftime('%d/%m %H:%M')}",
            data={"type": "ATTENDANCE_MARKED", "appointment_id": str(appointment.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Push notification failed on attendance update: %s", e)

    return _appointment_to_response(appointment)


# ==================== Group Sessions ====================

@appointments_router.post("/appointments/group", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_group_session(
    request: GroupSessionCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Create a group session with multiple participants."""
    if len(request.student_ids) < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pelo menos 1 aluno é necessário para sessão em grupo")

    if len(request.student_ids) > request.max_participants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Número de alunos ({len(request.student_ids)}) excede o máximo de participantes ({request.max_participants})")

    students = []
    for sid in request.student_ids:
        student = await db.get(User, sid)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno não encontrado: {sid}")
        students.append(student)

    appointment = Appointment(
        trainer_id=current_user.id,
        student_id=request.student_ids[0],
        organization_id=request.organization_id,
        date_time=request.date_time,
        duration_minutes=request.duration_minutes,
        workout_type=request.workout_type,
        notes=request.notes,
        status=AppointmentStatus.PENDING,
        is_group=True,
        max_participants=request.max_participants,
    )
    db.add(appointment)
    await db.flush()

    for student in students:
        participant = AppointmentParticipant(
            appointment_id=appointment.id,
            student_id=student.id,
            attendance_status=AttendanceStatus.SCHEDULED,
        )
        db.add(participant)

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(appointment, trainer_name=current_user.name)


@appointments_router.post("/appointments/{appointment_id}/participants", response_model=list[ParticipantResponse])
async def add_participants(
    appointment_id: UUID,
    request: AddParticipantsRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ParticipantResponse]:
    """Add participants to an existing group session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o treinador pode adicionar participantes")
    if not appointment.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta sessão não é um grupo. Converta para grupo primeiro.")

    current_count = len(appointment.participants) if appointment.participants else 0
    max_p = appointment.max_participants or 50
    if current_count + len(request.student_ids) > max_p:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Limite de participantes excedido. Atual: {current_count}, Máximo: {max_p}")

    existing_student_ids = {p.student_id for p in (appointment.participants or [])}

    for sid in request.student_ids:
        if sid in existing_student_ids:
            continue
        student = await db.get(User, sid)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Aluno não encontrado: {sid}")

        participant = AppointmentParticipant(
            appointment_id=appointment.id,
            student_id=sid,
            attendance_status=AttendanceStatus.SCHEDULED,
        )
        db.add(participant)

    await db.commit()
    await db.refresh(appointment)

    return [
        ParticipantResponse(
            id=p.id,
            student_id=p.student_id,
            student_name=p.student.name if p.student else None,
            student_avatar_url=p.student.avatar_url if p.student and hasattr(p.student, "avatar_url") else None,
            attendance_status=p.attendance_status.value if hasattr(p.attendance_status, "value") else str(p.attendance_status),
            service_plan_id=p.service_plan_id,
            is_complimentary=p.is_complimentary,
            notes=p.notes,
        )
        for p in (appointment.participants or [])
    ]


@appointments_router.delete("/appointments/{appointment_id}/participants/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant(
    appointment_id: UUID,
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a participant from a group session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o treinador pode remover participantes")
    if not appointment.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta sessão não é um grupo")

    participant = None
    for p in (appointment.participants or []):
        if p.student_id == student_id:
            participant = p
            break

    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante não encontrado nesta sessão")

    await db.delete(participant)
    await db.commit()


@appointments_router.patch("/appointments/{appointment_id}/participants/{student_id}/attendance", response_model=ParticipantResponse)
async def update_participant_attendance(
    appointment_id: UUID,
    student_id: UUID,
    request: ParticipantAttendanceUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ParticipantResponse:
    """Mark attendance for a single participant in a group session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")
    if appointment.trainer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o treinador pode marcar presença")
    if not appointment.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Esta sessão não é um grupo. Use o endpoint de presença padrão.")

    participant = None
    for p in (appointment.participants or []):
        if p.student_id == student_id:
            participant = p
            break

    if not participant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Participante não encontrado nesta sessão")

    participant.attendance_status = request.attendance_status
    if request.notes:
        participant.notes = f"{participant.notes or ''}\nPresença: {request.notes}".strip()

    if request.attendance_status == AttendanceStatus.ATTENDED:
        if participant.service_plan_id and not participant.is_complimentary:
            from src.domains.billing.models import Payment, PaymentStatus, PaymentType, ServicePlan, ServicePlanType

            plan = await db.get(ServicePlan, participant.service_plan_id)
            if plan:
                if plan.plan_type == ServicePlanType.PACKAGE and plan.remaining_sessions is not None:
                    plan.remaining_sessions = max(0, plan.remaining_sessions - 1)
                elif plan.plan_type == ServicePlanType.DROP_IN and plan.per_session_cents:
                    payment = Payment(
                        payer_id=participant.student_id,
                        payee_id=appointment.trainer_id,
                        organization_id=appointment.organization_id,
                        payment_type=PaymentType.SESSION,
                        description=f"Sessão em grupo - {appointment.date_time.strftime('%d/%m/%Y %H:%M')}",
                        amount_cents=plan.per_session_cents,
                        status=PaymentStatus.PENDING,
                        due_date=appointment.date_time.date(),
                        service_plan_id=plan.id,
                    )
                    db.add(payment)

    if request.attendance_status == AttendanceStatus.MISSED and request.grant_makeup:
        makeup = Appointment(
            trainer_id=appointment.trainer_id,
            student_id=student_id,
            organization_id=appointment.organization_id,
            date_time=datetime.now() + timedelta(days=7),
            duration_minutes=appointment.duration_minutes,
            workout_type=appointment.workout_type,
            status=AppointmentStatus.PENDING,
            service_plan_id=participant.service_plan_id,
            session_type=SessionType.MAKEUP,
            notes="Reposição de falta (sessão em grupo)",
        )
        db.add(makeup)

    await db.commit()
    await db.refresh(participant)

    return ParticipantResponse(
        id=participant.id,
        student_id=participant.student_id,
        student_name=participant.student.name if participant.student else None,
        student_avatar_url=participant.student.avatar_url if participant.student and hasattr(participant.student, "avatar_url") else None,
        attendance_status=participant.attendance_status.value if hasattr(participant.attendance_status, "value") else str(participant.attendance_status),
        service_plan_id=participant.service_plan_id,
        is_complimentary=participant.is_complimentary,
        notes=participant.notes,
    )


@appointments_router.get("/appointments/{appointment_id}/participants", response_model=list[ParticipantResponse])
async def list_participants(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ParticipantResponse]:
    """List participants of a group session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    return [
        ParticipantResponse(
            id=p.id,
            student_id=p.student_id,
            student_name=p.student.name if p.student else None,
            student_avatar_url=p.student.avatar_url if p.student and hasattr(p.student, "avatar_url") else None,
            attendance_status=p.attendance_status.value if hasattr(p.attendance_status, "value") else str(p.attendance_status),
            service_plan_id=p.service_plan_id,
            is_complimentary=p.is_complimentary,
            notes=p.notes,
        )
        for p in (appointment.participants or [])
    ]


# ==================== Evaluations ====================

@appointments_router.post("/appointments/{appointment_id}/evaluate", response_model=SessionEvaluationResponse, status_code=status.HTTP_201_CREATED)
async def create_evaluation(
    appointment_id: UUID,
    request: SessionEvaluationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionEvaluationResponse:
    """Create a post-session evaluation/feedback."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        is_participant = False
        if appointment.is_group and appointment.participants:
            is_participant = any(p.student_id == current_user.id for p in appointment.participants)
        if not is_participant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    if appointment.status != AppointmentStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Só é possível avaliar sessões concluídas")

    if current_user.id == appointment.trainer_id:
        evaluator_role = EvaluatorRole.TRAINER
    else:
        evaluator_role = EvaluatorRole.STUDENT

    existing_query = select(SessionEvaluation).where(
        and_(
            SessionEvaluation.appointment_id == appointment_id,
            SessionEvaluation.evaluator_id == current_user.id,
        )
    )
    result = await db.execute(existing_query)
    if result.scalar():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Você já avaliou esta sessão")

    difficulty_value = None
    if request.difficulty:
        try:
            difficulty_value = DifficultyLevel(request.difficulty)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dificuldade inválida. Use: too_easy, just_right, too_hard")

    evaluation = SessionEvaluation(
        appointment_id=appointment_id,
        evaluator_id=current_user.id,
        evaluator_role=evaluator_role,
        overall_rating=request.overall_rating,
        difficulty=difficulty_value,
        energy_level=request.energy_level,
        notes=request.notes,
    )
    db.add(evaluation)
    await db.commit()
    await db.refresh(evaluation)

    return SessionEvaluationResponse(
        id=evaluation.id,
        appointment_id=evaluation.appointment_id,
        evaluator_id=evaluation.evaluator_id,
        evaluator_role=evaluation.evaluator_role.value,
        evaluator_name=current_user.name,
        overall_rating=evaluation.overall_rating,
        difficulty=evaluation.difficulty.value if evaluation.difficulty else None,
        energy_level=evaluation.energy_level,
        notes=evaluation.notes,
        created_at=evaluation.created_at,
    )


@appointments_router.get("/appointments/{appointment_id}/evaluations", response_model=list[SessionEvaluationResponse])
async def list_evaluations(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionEvaluationResponse]:
    """List evaluations for a session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        is_participant = False
        if appointment.is_group and appointment.participants:
            is_participant = any(p.student_id == current_user.id for p in appointment.participants)
        if not is_participant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    query = select(SessionEvaluation).where(
        SessionEvaluation.appointment_id == appointment_id
    ).order_by(SessionEvaluation.created_at)
    result = await db.execute(query)
    evaluations = list(result.scalars().all())

    return [
        SessionEvaluationResponse(
            id=ev.id,
            appointment_id=ev.appointment_id,
            evaluator_id=ev.evaluator_id,
            evaluator_role=ev.evaluator_role.value if hasattr(ev.evaluator_role, "value") else str(ev.evaluator_role),
            evaluator_name=ev.evaluator.name if ev.evaluator else None,
            overall_rating=ev.overall_rating,
            difficulty=ev.difficulty.value if ev.difficulty else None,
            energy_level=ev.energy_level,
            notes=ev.notes,
            created_at=ev.created_at,
        )
        for ev in evaluations
    ]


# ==================== Calendar Export (.ics) ====================

def _generate_ics(appointments: list) -> str:
    """Generate iCalendar (.ics) content from a list of appointments."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MyFit//Schedule//PT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for apt in appointments:
        dt_start = apt.date_time.strftime("%Y%m%dT%H%M%S")
        dt_end = (apt.date_time + timedelta(minutes=apt.duration_minutes)).strftime("%Y%m%dT%H%M%S")

        is_group = getattr(apt, "is_group", False) or False
        if is_group and hasattr(apt, "participants") and apt.participants:
            names = ", ".join(
                p.student.name if p.student else "Aluno"
                for p in apt.participants[:3]
            )
            if len(apt.participants) > 3:
                names += f" +{len(apt.participants) - 3}"
            summary = f"Grupo ({len(apt.participants)}) - {apt.workout_type.value if apt.workout_type else 'Treino'}"
        else:
            summary = f"{apt.student.name if apt.student else 'Sessão'} - {apt.workout_type.value if apt.workout_type else 'Treino'}"

        location = apt.organization.name if apt.organization else ""
        description = (apt.notes or "").replace("\n", "\\n")

        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{apt.id}@myfit.app",
            f"DTSTART:{dt_start}",
            f"DTEND:{dt_end}",
            f"SUMMARY:{summary}",
            f"LOCATION:{location}",
            f"DESCRIPTION:{description}",
            f"STATUS:{'CANCELLED' if apt.status == AppointmentStatus.CANCELLED else 'CONFIRMED'}",
            "END:VEVENT",
        ])
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


@appointments_router.get("/appointments/{appointment_id}/calendar")
async def export_appointment_calendar(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Export a single appointment as .ics calendar file."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    ics_content = _generate_ics([appointment])

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="sessao-{appointment_id}.ics"'},
    )


@appointments_router.get("/export")
async def export_schedule_calendar(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Annotated[date, Query()],
    to_date: Annotated[date, Query()],
) -> Response:
    """Export all appointments in a date range as .ics calendar file."""
    start_dt = datetime.combine(from_date, datetime.min.time())
    end_dt = datetime.combine(to_date, datetime.max.time())

    query = (
        select(Appointment)
        .where(and_(
            Appointment.trainer_id == current_user.id,
            Appointment.date_time >= start_dt,
            Appointment.date_time <= end_dt,
        ))
        .order_by(Appointment.date_time)
    )

    result = await db.execute(query)
    appointments = list(result.scalars().all())

    ics_content = _generate_ics(appointments)

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="agenda-{from_date}-{to_date}.ics"'},
    )
