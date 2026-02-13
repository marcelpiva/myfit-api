"""Auto-generate, duplicate week, waitlist, and session template endpoints."""
import logging
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.notifications.push_service import send_push_notification
from src.domains.users.models import User

from .models import (
    Appointment,
    AppointmentStatus,
    AppointmentType,
    SessionTemplate,
    SessionType,
    WaitlistEntry,
    WaitlistStatus,
)
from .schemas import (
    AppointmentResponse,
    ApplyTemplateRequest,
    AutoGenerateScheduleRequest,
    DuplicateWeekRequest,
    SessionTemplateCreate,
    SessionTemplateResponse,
    SessionTemplateUpdate,
    WaitlistEntryCreate,
    WaitlistEntryResponse,
    WaitlistOfferRequest,
)
from .shared import _appointment_to_response

schedule_logger = logging.getLogger(__name__)

recurring_router = APIRouter()


# ==================== Auto-generate Schedule ====================

@recurring_router.post("/auto-generate", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
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
                continue  # Skip -- already exists

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


# ==================== Duplicate Week ====================

@recurring_router.post("/duplicate-week")
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


# ==================== Waitlist ====================

@recurring_router.post("/waitlist", response_model=WaitlistEntryResponse, status_code=status.HTTP_201_CREATED)
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


@recurring_router.get("/waitlist", response_model=list[WaitlistEntryResponse])
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


@recurring_router.delete("/waitlist/{waitlist_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@recurring_router.post("/waitlist/{waitlist_id}/offer", response_model=WaitlistEntryResponse)
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
        notes="Oferta da lista de espera",
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


@recurring_router.patch("/waitlist/{waitlist_id}/accept", response_model=WaitlistEntryResponse)
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


# ==================== Session Templates ====================

@recurring_router.post("/templates", response_model=SessionTemplateResponse, status_code=status.HTTP_201_CREATED)
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


@recurring_router.get("/templates", response_model=list[SessionTemplateResponse])
async def list_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: Annotated[bool, Query()] = True,
) -> list[SessionTemplateResponse]:
    """List trainer's session templates."""
    filters = [SessionTemplate.trainer_id == current_user.id]
    if active_only:
        filters.append(SessionTemplate.is_active == True)  # noqa: E712

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


@recurring_router.put("/templates/{template_id}", response_model=SessionTemplateResponse)
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


@recurring_router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@recurring_router.post("/templates/apply", response_model=list[AppointmentResponse], status_code=status.HTTP_201_CREATED)
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
