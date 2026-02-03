"""Check-in router with gym and check-in endpoints."""
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.checkin.models import CheckInMethod, CheckInStatus
from src.domains.checkin.schemas import (
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
    """Create a manual check-in."""
    service = CheckInService(db)

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já tem um check-in ativo. Faça checkout primeiro.",
        )

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    checkin = await service.create_checkin(
        user_id=current_user.id,
        gym_id=request.gym_id,
        method=request.method,
        notes=request.notes,
    )
    return CheckInResponse.model_validate(checkin)


@router.post("/code", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
async def checkin_by_code(
    request: CheckInByCodeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CheckInResponse:
    """Check in using a code."""
    service = CheckInService(db)

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já tem um check-in ativo. Faça checkout primeiro.",
        )

    # Find and validate code
    code = await service.get_code_by_value(request.code)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código de check-in inválido",
        )

    if not code.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código expirado ou esgotado",
        )

    # Use the code
    await service.use_code(code)

    # Create check-in
    checkin = await service.create_checkin(
        user_id=current_user.id,
        gym_id=code.gym_id,
        method=CheckInMethod.CODE,
    )

    # Load gym relationship
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
    """Check in by location."""
    service = CheckInService(db)
    org_id = UUID(x_organization_id) if x_organization_id else None

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já tem um check-in ativo. Faça checkout primeiro.",
        )

    checkin, gym, distance = await service.checkin_by_location(
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
        organization_id=org_id,
    )

    if checkin:
        checkin = await service.get_checkin_by_id(checkin.id)
        return LocationCheckInResponse(
            success=True,
            checkin=CheckInResponse.model_validate(checkin),
            nearest_gym=GymResponse.model_validate(gym) if gym else None,
            distance_meters=distance,
            message=f"Check-in realizado em {gym.name}",
        )
    else:
        return LocationCheckInResponse(
            success=False,
            checkin=None,
            nearest_gym=GymResponse.model_validate(gym) if gym else None,
            distance_meters=distance,
            message=f"Você está a {int(distance)}m da academia mais próxima" if gym and distance else "Nenhuma academia encontrada",
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
    """Create a check-in request for approval."""
    service = CheckInService(db)

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já tem um check-in ativo. Faça checkout primeiro.",
        )

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Academia não encontrada",
        )

    req = await service.create_request(
        user_id=current_user.id,
        gym_id=request.gym_id,
        approver_id=request.approver_id,
        reason=request.reason,
    )

    # Send push notification to approver
    try:
        await send_push_notification(
            db=db,
            user_id=request.approver_id,
            title="Solicitação de Check-in",
            body=f"{current_user.name} solicitou check-in",
            data={
                "type": "checkin_request_created",
                "request_id": str(req.id),
                "gym_id": str(request.gym_id),
            },
        )
    except Exception:
        pass  # Don't fail the request if push fails

    return CheckInRequestResponse.model_validate(req)


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

    # Verify caller is trainer/admin in the gym's organization
    result = await db.execute(
        sa_select(OrganizationMembership).where(
            OrganizationMembership.organization_id == gym.organization_id,
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.is_active == True,
            OrganizationMembership.role.in_([
                UserRole.TRAINER, UserRole.COACH,
                UserRole.GYM_ADMIN, UserRole.GYM_OWNER,
            ]),
        )
    )
    trainer_membership = result.scalar_one_or_none()
    if not trainer_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas personal trainers ou administradores podem registrar check-in de alunos",
        )

    # Verify student is member of the same organization
    result = await db.execute(
        sa_select(OrganizationMembership).where(
            OrganizationMembership.organization_id == gym.organization_id,
            OrganizationMembership.user_id == request.student_id,
            OrganizationMembership.is_active == True,
        )
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

    # Create check-in for the student
    checkin = await service.create_checkin(
        user_id=request.student_id,
        gym_id=request.gym_id,
        method=CheckInMethod.MANUAL,
        approved_by_id=current_user.id,
        notes=request.notes,
    )

    # Send push notification to student
    try:
        await send_push_notification(
            db=db,
            user_id=request.student_id,
            title="Check-in registrado",
            body=f"{current_user.name} registrou seu check-in",
            data={
                "type": "checkin_manual",
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
    """Student checks in near their trainer."""
    if not x_organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organização não identificada",
        )

    service = CheckInService(db)

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Você já tem um check-in ativo. Faça checkout primeiro.",
        )

    # Get trainer location and verify proximity
    trainer_loc = await service.get_trainer_location(request.trainer_id)
    if not trainer_loc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Localização do personal não disponível",
        )

    t_lat, t_lng, source, gym_id, gym_name = trainer_loc
    distance = service.calculate_distance(
        request.latitude, request.longitude, t_lat, t_lng,
    )

    if distance > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Você está a {int(distance)}m do personal. Aproxime-se (máx. 200m).",
        )

    # If trainer has an active check-in at a gym, use that gym_id
    # Otherwise, find the nearest gym to the trainer's GPS
    if not gym_id:
        org_id = UUID(x_organization_id)
        gym, _ = await service.find_nearest_gym(
            latitude=t_lat,
            longitude=t_lng,
            organization_id=org_id,
        )
        if gym:
            gym_id = gym.id

    if not gym_id:
        # Fallback: find or create gym for organization
        org_id = UUID(x_organization_id)
        org_gyms = await service.list_gyms(organization_id=org_id, limit=1)
        if org_gyms:
            gym_id = org_gyms[0].id
        else:
            # Auto-create gym at trainer's location
            new_gym = await service.create_gym(
                organization_id=org_id,
                name="Local do Personal Trainer",
                address="Localização do Personal Trainer",
                latitude=t_lat,
                longitude=t_lng,
                radius_meters=200,
            )
            gym_id = new_gym.id

    # Create check-in linked to trainer
    checkin = await service.create_checkin(
        user_id=current_user.id,
        gym_id=gym_id,
        method=CheckInMethod.LOCATION,
        approved_by_id=request.trainer_id,
    )

    # Send push notification to trainer
    try:
        await send_push_notification(
            db=db,
            user_id=request.trainer_id,
            title="Check-in do aluno",
            body=f"{current_user.name} fez check-in próximo a você",
            data={
                "type": "checkin_near_trainer",
                "checkin_id": str(checkin.id),
                "student_id": str(current_user.id),
            },
        )
    except Exception:
        pass

    checkin = await service.get_checkin_by_id(checkin.id)
    return CheckInResponse.model_validate(checkin)


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
