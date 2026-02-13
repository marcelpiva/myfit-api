"""Schedule router for appointment management."""
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

schedule_logger = logging.getLogger(__name__)

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
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
    SessionTemplate,
    SessionType,
    TrainerAvailability,
    TrainerBlockedSlot,
    TrainerSettings,
    WaitlistEntry,
    WaitlistStatus,
)
from .schemas import (
    AddParticipantsRequest,
    AppointmentCancel,
    AppointmentComplete,
    AppointmentCreate,
    AppointmentReschedule,
    AppointmentResponse,
    AppointmentUpdate,
    ApplyTemplateRequest,
    AttendanceUpdate,
    AutoGenerateScheduleRequest,
    AvailableSlotResponse,
    AvailableSlotsResponse,
    ConflictCheckResponse,
    ConflictDetail,
    DayOfWeekAnalytics,
    DuplicateWeekRequest,
    GroupSessionCreate,
    HourAnalytics,
    ParticipantAttendanceUpdate,
    ParticipantResponse,
    RecurringAppointmentCreate,
    ScheduleAnalyticsResponse,
    SessionEvaluationCreate,
    SessionEvaluationResponse,
    SessionTemplateCreate,
    SessionTemplateResponse,
    SessionTemplateUpdate,
    StudentAnalytics,
    StudentBookSessionRequest,
    StudentReliability,
    StudentReliabilityResponse,
    TrainerAvailabilityCreate,
    TrainerAvailabilityResponse,
    TrainerAvailabilitySlot,
    TrainerBlockedSlotCreate,
    TrainerBlockedSlotResponse,
    TrainerFullAvailabilityResponse,
    TrainerSettingsResponse,
    TrainerSettingsUpdate,
    UpcomingAppointmentsResponse,
    WaitlistEntryCreate,
    WaitlistEntryResponse,
    WaitlistOfferRequest,
)

from src.domains.notifications.push_service import send_push_notification

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _appointment_to_response(
    appointment: Appointment,
    trainer_name: str | None = None,
    student_name: str | None = None,
) -> AppointmentResponse:
    """Convert appointment model to response."""
    # Build participants list for group sessions
    participants_list = []
    if hasattr(appointment, "participants") and appointment.participants:
        for p in appointment.participants:
            participants_list.append(ParticipantResponse(
                id=p.id,
                student_id=p.student_id,
                student_name=p.student.name if p.student else None,
                student_avatar_url=p.student.avatar_url if p.student and hasattr(p.student, "avatar_url") else None,
                attendance_status=p.attendance_status.value if hasattr(p.attendance_status, "value") else str(p.attendance_status),
                service_plan_id=p.service_plan_id,
                is_complimentary=p.is_complimentary,
                notes=p.notes,
            ))

    # Evaluation data
    has_evaluation = False
    trainer_rating = None
    student_rating = None
    if hasattr(appointment, "evaluations") and appointment.evaluations:
        has_evaluation = True
        for ev in appointment.evaluations:
            role = ev.evaluator_role.value if hasattr(ev.evaluator_role, "value") else str(ev.evaluator_role)
            if role == "trainer":
                trainer_rating = ev.overall_rating
            elif role == "student":
                student_rating = ev.overall_rating

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
        is_group=getattr(appointment, "is_group", False) or False,
        max_participants=getattr(appointment, "max_participants", None),
        participants=participants_list,
        participant_count=len(participants_list),
        has_evaluation=has_evaluation,
        trainer_rating=trainer_rating,
        student_rating=student_rating,
    )


@router.get("/analytics", response_model=ScheduleAnalyticsResponse)
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


@router.get("/student-reliability", response_model=StudentReliabilityResponse)
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

    # Base filter: trainer's appointments in the last 90 days
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

    # Group by student
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
                # For trend: last 30 days vs prior 30 days (days 31-60)
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

        # Trend buckets
        apt_dt = a.date_time if isinstance(a.date_time, datetime) else datetime.combine(a.date_time, datetime.min.time())
        if apt_dt >= window_30_mid:
            # Last 30 days
            student_data[sid]["recent_total"] += 1
            if a.attendance_status == AttendanceStatus.ATTENDED:
                student_data[sid]["recent_attended"] += 1
        elif apt_dt >= window_60_start:
            # Prior 30 days (days 31-60)
            student_data[sid]["prior_total"] += 1
            if a.attendance_status == AttendanceStatus.ATTENDED:
                student_data[sid]["prior_attended"] += 1

    students = []
    for s in student_data.values():
        denom = s["attended"] + s["missed"] + s["late_cancelled"]
        attendance_rate = round((s["attended"] / denom * 100), 1) if denom > 0 else 0.0

        # Reliability score
        if attendance_rate >= 90:
            reliability_score = "high"
        elif attendance_rate >= 70:
            reliability_score = "medium"
        else:
            reliability_score = "low"

        # Trend: compare recent rate vs prior rate
        recent_rate = (
            (s["recent_attended"] / s["recent_total"] * 100)
            if s["recent_total"] > 0
            else 0.0
        )
        prior_rate = (
            (s["prior_attended"] / s["prior_total"] * 100)
            if s["prior_total"] > 0
            else 0.0
        )

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

    # Late cancellation policy check
    now = datetime.now()
    is_late = False
    trainer_settings = await _get_or_create_trainer_settings(db, appointment.trainer_id)
    hours_until = (appointment.date_time.replace(tzinfo=None) - now).total_seconds() / 3600

    if hours_until <= trainer_settings.late_cancel_window_hours:
        is_late = True
        policy = trainer_settings.late_cancel_policy

        if policy == "block":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cancelamento não permitido dentro de {trainer_settings.late_cancel_window_hours} horas da sessão",
            )

        if policy == "charge":
            appointment.attendance_status = AttendanceStatus.LATE_CANCELLED
            # Consume service plan credit for late cancellation
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

    # Send push notification to student
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

    # Send push notification about confirmation
    try:
        # Notify the other party (if trainer confirmed, notify student and vice versa)
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
            late_cancel_window_hours=24,
            late_cancel_policy="warn",
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
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Push notification failed on booking: %s", e)

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
        except (ConnectionError, OSError, RuntimeError) as e:
            schedule_logger.debug("Package expiry notification failed: %s", e)

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
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Attendance notification failed: %s", e)

    # Send push notification for attendance update
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


# --- Group Sessions ---


@router.post("/appointments/group", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
async def create_group_session(
    request: GroupSessionCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AppointmentResponse:
    """Create a group session with multiple participants."""
    if len(request.student_ids) < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pelo menos 1 aluno é necessário para sessão em grupo",
        )

    if len(request.student_ids) > request.max_participants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Número de alunos ({len(request.student_ids)}) excede o máximo de participantes ({request.max_participants})",
        )

    # Validate all student_ids exist
    students = []
    for sid in request.student_ids:
        student = await db.get(User, sid)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Aluno não encontrado: {sid}",
            )
        students.append(student)

    # Create the group appointment (student_id = first student for backwards compat)
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
    await db.flush()  # Get appointment.id

    # Create participant rows
    for student in students:
        participant = AppointmentParticipant(
            appointment_id=appointment.id,
            student_id=student.id,
            attendance_status=AttendanceStatus.SCHEDULED,
        )
        db.add(participant)

    await db.commit()
    await db.refresh(appointment)

    return _appointment_to_response(
        appointment,
        trainer_name=current_user.name,
    )


@router.post("/appointments/{appointment_id}/participants", response_model=list[ParticipantResponse])
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta sessão não é um grupo. Converta para grupo primeiro.",
        )

    # Check max_participants limit
    current_count = len(appointment.participants) if appointment.participants else 0
    max_p = appointment.max_participants or 50
    if current_count + len(request.student_ids) > max_p:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Limite de participantes excedido. Atual: {current_count}, Máximo: {max_p}",
        )

    # Check for duplicates
    existing_student_ids = {p.student_id for p in (appointment.participants or [])}

    new_participants = []
    for sid in request.student_ids:
        if sid in existing_student_ids:
            continue  # Skip duplicates

        student = await db.get(User, sid)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Aluno não encontrado: {sid}",
            )

        participant = AppointmentParticipant(
            appointment_id=appointment.id,
            student_id=sid,
            attendance_status=AttendanceStatus.SCHEDULED,
        )
        db.add(participant)
        new_participants.append(participant)

    await db.commit()

    # Refresh to get relationships
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


@router.delete("/appointments/{appointment_id}/participants/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta sessão não é um grupo",
        )

    # Find the participant
    participant = None
    for p in (appointment.participants or []):
        if p.student_id == student_id:
            participant = p
            break

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participante não encontrado nesta sessão",
        )

    await db.delete(participant)
    await db.commit()


@router.patch(
    "/appointments/{appointment_id}/participants/{student_id}/attendance",
    response_model=ParticipantResponse,
)
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta sessão não é um grupo. Use o endpoint de presença padrão.",
        )

    # Find the participant
    participant = None
    for p in (appointment.participants or []):
        if p.student_id == student_id:
            participant = p
            break

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participante não encontrado nesta sessão",
        )

    participant.attendance_status = request.attendance_status
    if request.notes:
        participant.notes = f"{participant.notes or ''}\nPresença: {request.notes}".strip()

    # Handle billing per participant's service_plan
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

    # If missed + grant_makeup, create makeup placeholder
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


@router.get("/appointments/{appointment_id}/participants", response_model=list[ParticipantResponse])
async def list_participants(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ParticipantResponse]:
    """List participants of a group session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    # Check access
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


# --- Post-Session Feedback ---


@router.post("/appointments/{appointment_id}/evaluate", response_model=SessionEvaluationResponse, status_code=status.HTTP_201_CREATED)
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

    # Check access
    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        # Also check if user is a participant in group sessions
        is_participant = False
        if appointment.is_group and appointment.participants:
            is_participant = any(p.student_id == current_user.id for p in appointment.participants)
        if not is_participant:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    # Must be completed
    if appointment.status != AppointmentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Só é possível avaliar sessões concluídas",
        )

    # Determine evaluator role
    if current_user.id == appointment.trainer_id:
        evaluator_role = EvaluatorRole.TRAINER
    else:
        evaluator_role = EvaluatorRole.STUDENT

    # Check for duplicate evaluation (same appointment + same evaluator)
    existing_query = select(SessionEvaluation).where(
        and_(
            SessionEvaluation.appointment_id == appointment_id,
            SessionEvaluation.evaluator_id == current_user.id,
        )
    )
    result = await db.execute(existing_query)
    if result.scalar():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já avaliou esta sessão",
        )

    # Parse difficulty if provided
    difficulty_value = None
    if request.difficulty:
        try:
            difficulty_value = DifficultyLevel(request.difficulty)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Dificuldade inválida. Use: too_easy, just_right, too_hard",
            )

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


@router.get("/appointments/{appointment_id}/evaluations", response_model=list[SessionEvaluationResponse])
async def list_evaluations(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[SessionEvaluationResponse]:
    """List evaluations for a session."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    # Check access
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


# --- Calendar Export (.ics) ---


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
            summary = f"{apt.student.name if apt.student else 'Sessao'} - {apt.workout_type.value if apt.workout_type else 'Treino'}"

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


@router.get("/appointments/{appointment_id}/calendar")
async def export_appointment_calendar(
    appointment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Export a single appointment as .ics calendar file."""
    appointment = await db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada")

    # Check access
    if appointment.trainer_id != current_user.id and appointment.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado")

    ics_content = _generate_ics([appointment])

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="sessao-{appointment_id}.ics"',
        },
    )


@router.get("/export")
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
        .where(
            and_(
                Appointment.trainer_id == current_user.id,
                Appointment.date_time >= start_dt,
                Appointment.date_time <= end_dt,
            )
        )
        .order_by(Appointment.date_time)
    )

    result = await db.execute(query)
    appointments = list(result.scalars().all())

    ics_content = _generate_ics(appointments)

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="agenda-{from_date}-{to_date}.ics"',
        },
    )


# --- Waitlist ---


@router.post("/waitlist", response_model=WaitlistEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_waitlist_entry(
    request: WaitlistEntryCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WaitlistEntryResponse:
    """Student creates a waitlist entry for a trainer."""
    # Verify the trainer exists
    trainer = await db.get(User, request.trainer_id)
    if not trainer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treinador não encontrado",
        )

    entry = WaitlistEntry(
        student_id=current_user.id,
        trainer_id=request.trainer_id,
        preferred_day_of_week=request.preferred_day_of_week,
        preferred_time_start=request.preferred_time_start,
        preferred_time_end=request.preferred_time_end,
        notes=request.notes,
        status=WaitlistStatus.WAITING,
        organization_id=request.organization_id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    # Notify trainer about new waitlist entry
    try:
        student_name = current_user.name or "Aluno"
        await send_push_notification(
            db, request.trainer_id,
            "Nova entrada na lista de espera",
            f"{student_name} está na lista de espera para horário.",
            data={"type": "WAITLIST_NEW", "waitlist_id": str(entry.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Waitlist notification failed: %s", e)

    return WaitlistEntryResponse(
        id=entry.id,
        student_id=entry.student_id,
        student_name=current_user.name,
        trainer_id=entry.trainer_id,
        trainer_name=trainer.name if trainer else None,
        preferred_day_of_week=entry.preferred_day_of_week,
        preferred_time_start=entry.preferred_time_start,
        preferred_time_end=entry.preferred_time_end,
        notes=entry.notes,
        status=entry.status.value if hasattr(entry.status, "value") else str(entry.status),
        offered_appointment_id=entry.offered_appointment_id,
        organization_id=entry.organization_id,
        created_at=entry.created_at,
    )


@router.get("/waitlist", response_model=list[WaitlistEntryResponse])
async def list_waitlist(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    day_of_week: Annotated[int | None, Query(ge=0, le=6)] = None,
    waitlist_status: Annotated[str | None, Query(alias="status")] = None,
) -> list[WaitlistEntryResponse]:
    """Trainer lists their waitlist entries with optional filters."""
    filters = [WaitlistEntry.trainer_id == current_user.id]

    if day_of_week is not None:
        filters.append(WaitlistEntry.preferred_day_of_week == day_of_week)
    if waitlist_status:
        try:
            ws = WaitlistStatus(waitlist_status)
            filters.append(WaitlistEntry.status == ws)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Status inválido: {waitlist_status}. Use: waiting, offered, accepted, expired",
            )

    query = select(WaitlistEntry).where(and_(*filters)).order_by(WaitlistEntry.created_at.desc())
    result = await db.execute(query)
    entries = list(result.scalars().all())

    return [
        WaitlistEntryResponse(
            id=e.id,
            student_id=e.student_id,
            student_name=e.student.name if e.student else None,
            trainer_id=e.trainer_id,
            trainer_name=e.trainer.name if e.trainer else None,
            preferred_day_of_week=e.preferred_day_of_week,
            preferred_time_start=e.preferred_time_start,
            preferred_time_end=e.preferred_time_end,
            notes=e.notes,
            status=e.status.value if hasattr(e.status, "value") else str(e.status),
            offered_appointment_id=e.offered_appointment_id,
            organization_id=e.organization_id,
            created_at=e.created_at,
        )
        for e in entries
    ]


@router.delete("/waitlist/{waitlist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_waitlist_entry(
    waitlist_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a waitlist entry."""
    entry = await db.get(WaitlistEntry, waitlist_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada na lista de espera não encontrada",
        )

    # Both student and trainer can remove
    if entry.student_id != current_user.id and entry.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado",
        )

    await db.delete(entry)
    await db.commit()


@router.post("/waitlist/{waitlist_id}/offer", response_model=WaitlistEntryResponse)
async def offer_waitlist_slot(
    waitlist_id: UUID,
    request: WaitlistOfferRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WaitlistEntryResponse:
    """Trainer offers a slot to a waitlist entry (creates pending appointment)."""
    entry = await db.get(WaitlistEntry, waitlist_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada na lista de espera não encontrada",
        )

    if entry.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o treinador pode oferecer horários",
        )

    if entry.status != WaitlistStatus.WAITING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta entrada não está em estado de espera",
        )

    # Parse workout type if provided
    workout_type_value = None
    if request.workout_type:
        try:
            workout_type_value = AppointmentType(request.workout_type)
        except ValueError:
            pass

    # Create a pending appointment for the offer
    appointment = Appointment(
        trainer_id=current_user.id,
        student_id=entry.student_id,
        organization_id=entry.organization_id,
        date_time=request.date_time,
        duration_minutes=request.duration_minutes,
        workout_type=workout_type_value,
        status=AppointmentStatus.PENDING,
        notes=f"Oferta da lista de espera",
    )
    db.add(appointment)
    await db.flush()

    # Update waitlist entry
    entry.status = WaitlistStatus.OFFERED
    entry.offered_appointment_id = appointment.id

    await db.commit()
    await db.refresh(entry)

    # Notify student about the offer
    try:
        dt_str = request.date_time.strftime("%d/%m às %H:%M")
        await send_push_notification(
            db, entry.student_id,
            "Horário Disponível!",
            f"Um horário foi oferecido para você: {dt_str}. Aceite agora!",
            data={"type": "WAITLIST_OFFER", "waitlist_id": str(entry.id), "appointment_id": str(appointment.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Waitlist offer notification failed: %s", e)

    return WaitlistEntryResponse(
        id=entry.id,
        student_id=entry.student_id,
        student_name=entry.student.name if entry.student else None,
        trainer_id=entry.trainer_id,
        trainer_name=entry.trainer.name if entry.trainer else None,
        preferred_day_of_week=entry.preferred_day_of_week,
        preferred_time_start=entry.preferred_time_start,
        preferred_time_end=entry.preferred_time_end,
        notes=entry.notes,
        status=entry.status.value if hasattr(entry.status, "value") else str(entry.status),
        offered_appointment_id=entry.offered_appointment_id,
        organization_id=entry.organization_id,
        created_at=entry.created_at,
    )


@router.patch("/waitlist/{waitlist_id}/accept", response_model=WaitlistEntryResponse)
async def accept_waitlist_offer(
    waitlist_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WaitlistEntryResponse:
    """Student accepts a waitlist offer (confirms the appointment)."""
    entry = await db.get(WaitlistEntry, waitlist_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrada na lista de espera não encontrada",
        )

    if entry.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o aluno pode aceitar a oferta",
        )

    if entry.status != WaitlistStatus.OFFERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Esta entrada não tem uma oferta pendente",
        )

    if not entry.offered_appointment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nenhuma sessão vinculada a esta oferta",
        )

    # Confirm the appointment
    appointment = await db.get(Appointment, entry.offered_appointment_id)
    if appointment:
        appointment.status = AppointmentStatus.CONFIRMED

    # Update waitlist entry
    entry.status = WaitlistStatus.ACCEPTED

    await db.commit()
    await db.refresh(entry)

    # Notify trainer that offer was accepted
    try:
        student_name = current_user.name or "Aluno"
        await send_push_notification(
            db, entry.trainer_id,
            "Oferta Aceita",
            f"{student_name} aceitou o horário oferecido da lista de espera.",
            data={"type": "WAITLIST_ACCEPTED", "waitlist_id": str(entry.id)},
        )
    except (ConnectionError, OSError, RuntimeError) as e:
        schedule_logger.debug("Waitlist accepted notification failed: %s", e)

    return WaitlistEntryResponse(
        id=entry.id,
        student_id=entry.student_id,
        student_name=entry.student.name if entry.student else None,
        trainer_id=entry.trainer_id,
        trainer_name=entry.trainer.name if entry.trainer else None,
        preferred_day_of_week=entry.preferred_day_of_week,
        preferred_time_start=entry.preferred_time_start,
        preferred_time_end=entry.preferred_time_end,
        notes=entry.notes,
        status=entry.status.value if hasattr(entry.status, "value") else str(entry.status),
        offered_appointment_id=entry.offered_appointment_id,
        organization_id=entry.organization_id,
        created_at=entry.created_at,
    )


# --- Session Templates ---


@router.post("/templates", response_model=SessionTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    request: SessionTemplateCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionTemplateResponse:
    """Trainer creates a reusable session template."""
    # Parse workout type if provided
    workout_type_value = None
    if request.workout_type:
        try:
            workout_type_value = AppointmentType(request.workout_type)
        except ValueError:
            pass

    template = SessionTemplate(
        trainer_id=current_user.id,
        name=request.name,
        day_of_week=request.day_of_week,
        start_time=request.start_time,
        duration_minutes=request.duration_minutes,
        workout_type=workout_type_value,
        is_group=request.is_group,
        max_participants=request.max_participants,
        notes=request.notes,
        organization_id=request.organization_id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return SessionTemplateResponse(
        id=template.id,
        trainer_id=template.trainer_id,
        name=template.name,
        day_of_week=template.day_of_week,
        start_time=template.start_time,
        duration_minutes=template.duration_minutes,
        workout_type=template.workout_type.value if template.workout_type else None,
        is_group=template.is_group,
        max_participants=template.max_participants,
        notes=template.notes,
        is_active=template.is_active,
        organization_id=template.organization_id,
        created_at=template.created_at,
    )


@router.get("/templates", response_model=list[SessionTemplateResponse])
async def list_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: Annotated[bool, Query()] = True,
) -> list[SessionTemplateResponse]:
    """List trainer's session templates."""
    filters = [SessionTemplate.trainer_id == current_user.id]
    if active_only:
        filters.append(SessionTemplate.is_active == True)

    query = select(SessionTemplate).where(and_(*filters)).order_by(SessionTemplate.day_of_week, SessionTemplate.start_time)
    result = await db.execute(query)
    templates = list(result.scalars().all())

    return [
        SessionTemplateResponse(
            id=t.id,
            trainer_id=t.trainer_id,
            name=t.name,
            day_of_week=t.day_of_week,
            start_time=t.start_time,
            duration_minutes=t.duration_minutes,
            workout_type=t.workout_type.value if t.workout_type else None,
            is_group=t.is_group,
            max_participants=t.max_participants,
            notes=t.notes,
            is_active=t.is_active,
            organization_id=t.organization_id,
            created_at=t.created_at,
        )
        for t in templates
    ]


@router.put("/templates/{template_id}", response_model=SessionTemplateResponse)
async def update_template(
    template_id: UUID,
    request: SessionTemplateUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionTemplateResponse:
    """Update a session template."""
    template = await db.get(SessionTemplate, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    if template.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o treinador pode editar este template",
        )

    # Update fields that were provided
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "workout_type" and value is not None:
            try:
                value = AppointmentType(value)
            except ValueError:
                value = None
        setattr(template, field, value)

    await db.commit()
    await db.refresh(template)

    return SessionTemplateResponse(
        id=template.id,
        trainer_id=template.trainer_id,
        name=template.name,
        day_of_week=template.day_of_week,
        start_time=template.start_time,
        duration_minutes=template.duration_minutes,
        workout_type=template.workout_type.value if template.workout_type else None,
        is_group=template.is_group,
        max_participants=template.max_participants,
        notes=template.notes,
        is_active=template.is_active,
        organization_id=template.organization_id,
        created_at=template.created_at,
    )


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a session template."""
    template = await db.get(SessionTemplate, template_id)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template não encontrado",
        )

    if template.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o treinador pode excluir este template",
        )

    await db.delete(template)
    await db.commit()


@router.post("/templates/apply", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
async def apply_templates(
    request: ApplyTemplateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AppointmentResponse]:
    """Apply templates to a specific week, creating appointments in bulk."""
    created_appointments = []

    for template_id in request.template_ids:
        template = await db.get(SessionTemplate, template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template não encontrado: {template_id}",
            )

        if template.trainer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado ao template: {template_id}",
            )

        if not template.is_active:
            continue  # Skip inactive templates

        # Calculate the date_time from week_start_date + day_of_week offset + start_time
        target_date = request.week_start_date + timedelta(days=template.day_of_week)
        target_datetime = datetime.combine(target_date, template.start_time)

        # For the apply templates endpoint, we need at least a student
        # Since templates don't have a student, we create the appointment with
        # trainer as both trainer and student (placeholder) - the trainer can assign students later
        # Actually, create as trainer's own placeholder appointment
        appointment = Appointment(
            trainer_id=current_user.id,
            student_id=current_user.id,  # Placeholder - trainer assigns student later
            organization_id=template.organization_id,
            date_time=target_datetime,
            duration_minutes=template.duration_minutes,
            workout_type=template.workout_type,
            status=AppointmentStatus.CONFIRMED if request.auto_confirm else AppointmentStatus.PENDING,
            notes=f"Criado do template: {template.name}",
            is_group=template.is_group,
            max_participants=template.max_participants,
        )
        db.add(appointment)
        await db.flush()
        created_appointments.append(appointment)

    await db.commit()

    # Refresh all appointments to load relationships
    responses = []
    for apt in created_appointments:
        await db.refresh(apt)
        responses.append(_appointment_to_response(apt, trainer_name=current_user.name))

    return responses
