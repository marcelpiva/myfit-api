"""Shared helpers for schedule sub-routers."""
from datetime import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Appointment,
    AppointmentStatus,
    TrainerSettings,
)
from .schemas import (
    AppointmentResponse,
    ParticipantResponse,
)


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
