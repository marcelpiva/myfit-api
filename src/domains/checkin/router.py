"""Check-in router with gym and check-in endpoints."""
import logging
from datetime import date, datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.checkin.models import CheckInMethod, CheckInStatus
from src.domains.checkin.schemas import (
    ActiveSessionResponse,
    CheckInByCodeRequest,
    CheckInByLocationRequest,
    CheckInCodeCreate,
    CheckInCodeResponse,
    CheckInCreate,
    CheckInNearTrainerRequest,
    CheckInRequestCreate,
    CheckInRequestRespond,
    CheckInRequestResponse,
    CheckInResponse,
    CheckInStatsResponse,
    CheckOutRequest,
    GymCreate,
    GymResponse,
    GymUpdate,
    LocationCheckInResponse,
    ManualCheckinForStudentRequest,
    NearbyGymResponse,
    NearbyTrainerInfo,
    NearbyTrainerResponse,
    PendingAcceptanceResponse,
    StartTrainingSessionRequest,
    UpdateTrainerLocationRequest,
)
from src.domains.checkin.service import CheckInService
from src.domains.notifications.push_service import send_push_notification
from src.domains.users.models import User

router = APIRouter()


# Gym endpoints

@router.get("/gyms", response_model=list[GymResponse])
async def list_gyms(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[GymResponse]:
    """List gyms."""
    service = CheckInService(db)
    gyms = await service.list_gyms(
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    return [GymResponse.model_validate(g) for g in gyms]


@router.post("/gyms", response_model=GymResponse, status_code=status.HTTP_201_CREATED)
async def create_gym(
    request: GymCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GymResponse:
    """Create a new gym."""
    service = CheckInService(db)
    gym = await service.create_gym(
        organization_id=request.organization_id,
        name=request.name,
        address=request.address,
        latitude=request.latitude,
        longitude=request.longitude,
        phone=request.phone,
        radius_meters=request.radius_meters,
    )
    return GymResponse.model_validate(gym)


@router.get("/gyms/{gym_id}", response_model=GymResponse)
async def get_gym(
    gym_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GymResponse:
    """Get gym details."""
    service = CheckInService(db)
    gym = await service.get_gym_by_id(gym_id)

    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    return GymResponse.model_validate(gym)


@router.put("/gyms/{gym_id}", response_model=GymResponse)
async def update_gym(
    gym_id: UUID,
    request: GymUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GymResponse:
    """Update a gym."""
    service = CheckInService(db)
    gym = await service.get_gym_by_id(gym_id)

    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    updated = await service.update_gym(
        gym=gym,
        **request.model_dump(exclude_unset=True),
    )
    return GymResponse.model_validate(updated)


# Check-in endpoints

@router.get("", response_model=list[CheckInResponse])
async def list_checkins(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    gym_id: Annotated[UUID | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CheckInResponse]:
    """List user's check-ins."""
    service = CheckInService(db)
    checkins = await service.list_checkins(
        user_id=current_user.id,
        gym_id=gym_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return [CheckInResponse.model_validate(c) for c in checkins]


@router.get("/active", response_model=CheckInResponse | None)
async def get_active_checkin(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse | None:
    """Get user's active check-in."""
    service = CheckInService(db)
    checkin = await service.get_active_checkin(current_user.id)
    if checkin:
        return CheckInResponse.model_validate(checkin)
    return None


@router.post("", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
async def create_checkin(
    request: CheckInCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Create a manual check-in. DISABLED: Use /manual-for-student instead."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Check-in manual desabilitado. O personal trainer deve iniciar o check-in via /manual-for-student.",
    )


@router.post("/code", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
async def checkin_by_code(
    request: CheckInByCodeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Check in using a code (QR or manual entry)."""
    service = CheckInService(db)

    # Validate code
    code = await service.get_code_by_value(request.code)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código não encontrado.",
        )
    if not code.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido ou expirado.",
        )

    # Check if user already has an active check-in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Você já possui um check-in ativo.",
        )

    # Create check-in (confirmed immediately for code-based)
    checkin = await service.create_checkin(
        user_id=current_user.id,
        gym_id=code.gym_id,
        method=CheckInMethod.CODE,
        status=CheckInStatus.CONFIRMED,
        initiated_by=current_user.id,
    )

    # Increment code usage
    await service.use_code(code)

    # Reload with gym relationship
    checkin = await service.get_checkin_by_id(checkin.id)

    return CheckInResponse.model_validate(checkin)


@router.post("/nearby", response_model=NearbyGymResponse)
async def detect_nearby_gym(
    request: CheckInByLocationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> NearbyGymResponse:
    """Detect the nearest gym without creating a check-in."""
    service = CheckInService(db)
    org_id = UUID(x_organization_id) if x_organization_id else None

    gym, distance = await service.find_nearest_gym(
        latitude=request.latitude,
        longitude=request.longitude,
        organization_id=org_id,
    )

    if gym:
        return NearbyGymResponse(
            found=True,
            gym=GymResponse.model_validate(gym),
            distance_meters=distance,
            within_radius=distance is not None and distance <= gym.radius_meters,
        )
    return NearbyGymResponse(found=False)


@router.post("/location", response_model=LocationCheckInResponse)
async def checkin_by_location(
    request: CheckInByLocationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> LocationCheckInResponse:
    """Check in by location. DISABLED: Use /manual-for-student instead."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Check-in por localização desabilitado. O personal trainer deve iniciar o check-in.",
    )


@router.post("/checkout", response_model=CheckInResponse)
async def checkout(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: CheckOutRequest | None = None,
) -> CheckInResponse:
    """Check out from current gym."""
    service = CheckInService(db)

    active = await service.get_active_checkin(current_user.id)
    if not active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você não tem check-in ativo",
        )

    notes = request.notes if request else None
    checkin = await service.checkout(active, notes=notes)

    # Send push notification to counterparty
    try:
        notify_user_id = None
        if checkin.approved_by_id and checkin.approved_by_id != current_user.id:
            notify_user_id = checkin.approved_by_id
        elif checkin.user_id != current_user.id:
            notify_user_id = checkin.user_id
        if notify_user_id:
            await send_push_notification(
                db=db,
                user_id=notify_user_id,
                title="Sessão encerrada",
                body=f"{current_user.name} encerrou a sessão",
                data={"type": "checkin_ended", "checkin_id": str(checkin.id)},
            )
    except Exception:
        pass  # Push failure should not block checkout

    return CheckInResponse.model_validate(checkin)


# Check-in code management

@router.post("/codes", response_model=CheckInCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_code(
    request: CheckInCodeCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInCodeResponse:
    """Create a check-in code for a gym."""
    service = CheckInService(db)

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    code = await service.create_code(
        gym_id=request.gym_id,
        expires_at=request.expires_at,
        max_uses=request.max_uses,
    )
    return CheckInCodeResponse.model_validate(code)


@router.delete("/codes/{code}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_code(
    code: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Deactivate a check-in code."""
    service = CheckInService(db)

    code_obj = await service.get_code_by_value(code)
    if not code_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código não encontrado",
        )

    await service.deactivate_code(code_obj)


# Check-in requests

@router.get("/requests", response_model=list[CheckInRequestResponse])
async def list_pending_requests(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    gym_id: Annotated[UUID | None, Query()] = None,
) -> list[CheckInRequestResponse]:
    """List pending check-in requests (for approvers)."""
    service = CheckInService(db)
    requests = await service.list_pending_requests(
        approver_id=current_user.id,
        gym_id=gym_id,
    )
    return [CheckInRequestResponse.model_validate(r) for r in requests]


@router.post("/requests", response_model=CheckInRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_request(
    request: CheckInRequestCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInRequestResponse:
    """Create a check-in request for approval. DISABLED: Use /manual-for-student instead."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Solicitação de check-in desabilitada. O personal trainer deve iniciar o check-in.",
    )


@router.post("/requests/{request_id}/respond", response_model=CheckInRequestResponse)
async def respond_to_request(
    request_id: UUID,
    response: CheckInRequestRespond,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInRequestResponse:
    """Respond to a check-in request (approve/deny)."""
    service = CheckInService(db)

    req = await service.get_request_by_id(request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Solicitação não encontrada",
        )

    if req.approver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem autorização para responder esta solicitação",
        )

    if req.status != CheckInStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solicitação já foi respondida",
        )

    updated_req, _ = await service.respond_to_request(
        request=req,
        approved=response.approved,
        response_note=response.response_note,
    )

    # Send push notification to the student
    try:
        if response.approved:
            title = "Check-in aprovado!"
            body = f"{current_user.name} aprovou seu check-in"
            ntype = "checkin_request_approved"
        else:
            title = "Check-in recusado"
            body = f"{current_user.name} recusou seu check-in"
            ntype = "checkin_request_rejected"

        await send_push_notification(
            db=db,
            user_id=req.user_id,
            title=title,
            body=body,
            data={
                "type": ntype,
                "request_id": str(request_id),
            },
        )
    except Exception:
        pass  # Don't fail the response if push fails

    return CheckInRequestResponse.model_validate(updated_req)


@router.get("/my-requests", response_model=list[CheckInRequestResponse])
async def list_my_requests(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[CheckInStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[CheckInRequestResponse]:
    """List check-in requests created by the current user (student sees their own requests)."""
    service = CheckInService(db)
    requests = await service.list_user_requests(
        user_id=current_user.id,
        status_filter=status_filter,
        limit=limit,
    )
    return [CheckInRequestResponse.from_request(r) for r in requests]


@router.post("/manual-for-student", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
async def manual_checkin_for_student(
    request: ManualCheckinForStudentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Trainer creates a manual check-in on behalf of a student."""
    from sqlalchemy import select as sa_select
    from src.domains.organizations.models import OrganizationMembership, UserRole

    service = CheckInService(db)

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    # Verify caller is trainer/admin in any organization
    result = await db.execute(
        sa_select(OrganizationMembership).where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.is_active == True,
            OrganizationMembership.role.in_([
                UserRole.TRAINER, UserRole.COACH,
                UserRole.GYM_ADMIN, UserRole.GYM_OWNER,
            ]),
        ).limit(1)
    )
    trainer_membership = result.scalar_one_or_none()
    if not trainer_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas personal trainers ou administradores podem registrar check-in de alunos",
        )

    # Verify student is member of the same organization as the trainer
    result = await db.execute(
        sa_select(OrganizationMembership).where(
            OrganizationMembership.organization_id == trainer_membership.organization_id,
            OrganizationMembership.user_id == request.student_id,
            OrganizationMembership.is_active == True,
        ).limit(1)
    )
    student_membership = result.scalar_one_or_none()
    if not student_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado nesta organização",
        )

    # Check if student already checked in
    active = await service.get_active_checkin(request.student_id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aluno já tem um check-in ativo",
        )

    # Create check-in for the student with pending_acceptance status
    checkin = await service.create_checkin(
        user_id=request.student_id,
        gym_id=request.gym_id,
        method=CheckInMethod.MANUAL,
        status=CheckInStatus.PENDING_ACCEPTANCE,
        approved_by_id=current_user.id,
        notes=request.notes,
        initiated_by=current_user.id,
        expires_in_minutes=5,
        training_mode=request.training_mode.value,
    )

    # Send push notification to student (needs to accept)
    try:
        await send_push_notification(
            db=db,
            user_id=request.student_id,
            title="Solicitação de Check-in",
            body=f"{current_user.name} quer fazer check-in com você",
            data={
                "type": "checkin_pending_acceptance",
                "checkin_id": str(checkin.id),
            },
        )
    except Exception:
        pass

    checkin = await service.get_checkin_by_id(checkin.id)
    return CheckInResponse.model_validate(checkin)


# Trainer location endpoints

@router.post("/nearby-trainer", response_model=NearbyTrainerResponse)
async def detect_nearby_trainer(
    request: CheckInByLocationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> NearbyTrainerResponse:
    """Detect nearby trainers for a student (read-only, no check-in created)."""
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organização não identificada",
        )

    service = CheckInService(db)
    org_id = UUID(x_organization_id)

    trainers = await service.find_nearby_trainers(
        student_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
        organization_id=org_id,
    )

    return NearbyTrainerResponse(
        found=len(trainers) > 0,
        trainers=[NearbyTrainerInfo(**t) for t in trainers],
    )


@router.post("/trainer-location")
async def update_trainer_location(
    request: UpdateTrainerLocationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Trainer shares their GPS location for student proximity detection."""
    service = CheckInService(db)
    loc = await service.update_trainer_location(
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
    )
    return {"success": True, "expires_at": loc.expires_at.isoformat()}


@router.post("/checkin-near-trainer", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
async def checkin_near_trainer(
    request: CheckInNearTrainerRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> CheckInResponse:
    """Student checks in near their trainer. DISABLED: Use /manual-for-student instead."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Check-in por proximidade desabilitado. O personal trainer deve iniciar o check-in.",
    )


# Stats

@router.get("/stats", response_model=CheckInStatsResponse)
async def get_checkin_stats(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> CheckInStatsResponse:
    """Get check-in statistics for the current user."""
    service = CheckInService(db)
    stats = await service.get_user_checkin_stats(
        user_id=current_user.id,
        days=days,
    )
    return CheckInStatsResponse(**stats)


# Check-in acceptance endpoints

@router.get("/pending-acceptance", response_model=list[PendingAcceptanceResponse])
async def get_pending_acceptance(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PendingAcceptanceResponse]:
    """Get check-ins pending acceptance from the current user."""
    from src.domains.organizations.models import OrganizationMembership

    service = CheckInService(db)
    checkins = await service.get_pending_acceptance_for_user(current_user.id)

    results = []
    for c in checkins:
        # Determine initiated_by role
        initiated_by_role = "student"
        if c.initiated_by and c.approved_by_id == c.user_id:
            # Trainer initiated for student
            initiated_by_role = "trainer"
        elif c.initiated_by == c.approved_by_id:
            initiated_by_role = "trainer"
        elif c.initiated_by and c.initiated_by != c.user_id:
            initiated_by_role = "trainer"

        initiator = c.initiated_by_user
        results.append(PendingAcceptanceResponse(
            id=c.id,
            initiated_by_name=initiator.name if initiator else "Usuário",
            initiated_by_avatar=initiator.avatar_url if initiator and hasattr(initiator, 'avatar_url') else None,
            initiated_by_role=initiated_by_role,
            initiated_by_id=c.initiated_by,
            user_id=c.user_id,
            user_name=c.user.name if c.user else "Aluno",
            gym_name=c.gym.name if c.gym else None,
            gym_id=c.gym_id,
            method=c.method,
            training_mode=c.training_mode,
            created_at=c.checked_in_at,
            expires_at=c.expires_at,
        ))

    return results


@router.get("/my-initiated-pending", response_model=list[CheckInResponse])
async def get_my_initiated_pending(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[CheckInResponse]:
    """Get check-ins that the current user initiated and are still pending acceptance."""
    service = CheckInService(db)
    checkins = await service.get_my_pending_checkins(current_user.id)
    results = []
    for c in checkins:
        reloaded = await service.get_checkin_by_id(c.id)
        if reloaded:
            results.append(CheckInResponse.model_validate(reloaded))
    return results


@router.get("/{checkin_id}", response_model=CheckInResponse)
async def get_checkin(
    checkin_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Get a single check-in by ID."""
    service = CheckInService(db)
    checkin = await service.get_checkin_by_id(checkin_id)
    if not checkin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check-in não encontrado",
        )
    # Verify user is involved
    if (
        current_user.id != checkin.user_id
        and current_user.id != checkin.approved_by_id
        and current_user.id != checkin.initiated_by
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão",
        )
    return CheckInResponse.model_validate(checkin)


@router.post("/{checkin_id}/accept", response_model=CheckInResponse)
async def accept_checkin(
    checkin_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Accept a pending check-in (counterparty accepts)."""
    service = CheckInService(db)

    checkin = await service.get_checkin_by_id(checkin_id)
    if not checkin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check-in não encontrado",
        )

    if checkin.status != CheckInStatus.PENDING_ACCEPTANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in não está pendente de aceite",
        )

    # Verify current user is the counterparty (not the initiator)
    if checkin.initiated_by == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não pode aceitar um check-in que você mesmo iniciou",
        )

    # Verify user is involved (student or approver)
    if current_user.id != checkin.user_id and current_user.id != checkin.approved_by_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para aceitar este check-in",
        )

    # Check expiration (handle naive datetimes from DB)
    if checkin.expires_at:
        exp = checkin.expires_at.replace(tzinfo=timezone.utc) if checkin.expires_at.tzinfo is None else checkin.expires_at
        if exp < datetime.now(timezone.utc):
            checkin = await service.reject_checkin(checkin)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Check-in expirou",
            )

    logger = logging.getLogger(__name__)
    try:
        checkin = await service.accept_checkin(checkin)
    except Exception as e:
        logger.exception(f"accept_checkin FAILED for checkin_id={checkin_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao aceitar check-in: {str(e)}",
        )

    # Send push notification to initiator
    try:
        await send_push_notification(
            db=db,
            user_id=checkin.initiated_by,
            title="Check-in aceito!",
            body=f"{current_user.name} aceitou o check-in",
            data={
                "type": "checkin_accepted",
                "checkin_id": str(checkin.id),
            },
        )
    except Exception:
        pass

    try:
        checkin = await service.get_checkin_by_id(checkin.id)
        return CheckInResponse.model_validate(checkin)
    except Exception as e:
        logger.exception(f"accept_checkin serialization FAILED for checkin_id={checkin_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao serializar check-in: {str(e)}",
        )


@router.post("/{checkin_id}/reject", response_model=CheckInResponse)
async def reject_checkin(
    checkin_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Reject/cancel a pending check-in."""
    service = CheckInService(db)

    checkin = await service.get_checkin_by_id(checkin_id)
    if not checkin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Check-in não encontrado",
        )

    if checkin.status != CheckInStatus.PENDING_ACCEPTANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in não está pendente de aceite",
        )

    # Both initiator (cancel) and counterparty (reject) can reject
    if current_user.id != checkin.user_id and current_user.id != checkin.approved_by_id and current_user.id != checkin.initiated_by:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para rejeitar este check-in",
        )

    logger = logging.getLogger(__name__)
    try:
        checkin = await service.reject_checkin(checkin)
    except Exception as e:
        logger.exception(f"reject_checkin FAILED for checkin_id={checkin_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao rejeitar check-in: {str(e)}",
        )

    # Notify the other party
    notify_user_id = checkin.initiated_by if current_user.id != checkin.initiated_by else (
        checkin.user_id if current_user.id != checkin.user_id else checkin.approved_by_id
    )
    if notify_user_id and notify_user_id != current_user.id:
        try:
            await send_push_notification(
                db=db,
                user_id=notify_user_id,
                title="Check-in recusado",
                body=f"{current_user.name} recusou o check-in",
                data={
                    "type": "checkin_rejected",
                    "checkin_id": str(checkin.id),
                },
            )
        except Exception:
            pass

    try:
        checkin = await service.get_checkin_by_id(checkin.id)
        return CheckInResponse.model_validate(checkin)
    except Exception as e:
        logger.exception(f"reject_checkin serialization FAILED for checkin_id={checkin_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao serializar check-in: {str(e)}",
        )


# Training Session endpoints

@router.post("/training-sessions/start")
async def start_training_session(
    request: StartTrainingSessionRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str, Header()],
):
    """Trainer starts a training session (becomes available for students)."""
    service = CheckInService(db)
    loc = await service.start_training_session(
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
    )
    return {
        "session_id": str(loc.id),
        "started_at": loc.session_started_at.isoformat() if loc.session_started_at else None,
        "status": "active",
    }


@router.post("/training-sessions/end")
async def end_training_session(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str, Header()],
):
    """Trainer ends the training session and checks out all students."""
    service = CheckInService(db)
    student_ids = await service.end_training_session(
        user_id=current_user.id,
        organization_id=UUID(x_organization_id),
    )

    # Send push notification to all students whose sessions were ended
    for sid in student_ids:
        try:
            await send_push_notification(
                db=db,
                user_id=sid,
                title="Sessão encerrada",
                body=f"{current_user.name} encerrou a sessão de treino",
                data={"type": "checkin_ended"},
            )
        except Exception:
            pass  # Push failure should not block session end

    return {"status": "ended"}


@router.get("/training-sessions/active")
async def get_active_session(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get trainer's active training session with student check-ins."""
    service = CheckInService(db)
    session = await service.get_active_session(user_id=current_user.id)
    if not session:
        return {"session": None, "checkins": []}
    return session
