"""Check-in router with gym and check-in endpoints."""
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
)
from src.domains.checkin.service import CheckInService

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
            detail="Gym not found",
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
            detail="Gym not found",
        )

    updated = await service.update_gym(
        gym=gym,
        **request.model_dump(exclude_unset=True),
    )
    return GymResponse.model_validate(updated)


# Check-in endpoints

@router.get("/", response_model=list[CheckInResponse])
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


@router.post("/", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
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
            detail="Already checked in. Please check out first.",
        )

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gym not found",
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
            detail="Already checked in. Please check out first.",
        )

    # Find and validate code
    code = await service.get_code_by_value(request.code)
    if not code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid check-in code",
        )

    if not code.is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in code is expired or has reached maximum uses",
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


@router.post("/location", response_model=LocationCheckInResponse)
async def checkin_by_location(
    request: CheckInByLocationRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LocationCheckInResponse:
    """Check in by location."""
    service = CheckInService(db)

    # Check if already checked in
    active = await service.get_active_checkin(current_user.id)
    if active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked in. Please check out first.",
        )

    checkin, gym, distance = await service.checkin_by_location(
        user_id=current_user.id,
        latitude=request.latitude,
        longitude=request.longitude,
    )

    if checkin:
        checkin = await service.get_checkin_by_id(checkin.id)
        return LocationCheckInResponse(
            success=True,
            checkin=CheckInResponse.model_validate(checkin),
            nearest_gym=GymResponse.model_validate(gym) if gym else None,
            distance_meters=distance,
            message=f"Checked in at {gym.name}",
        )
    else:
        return LocationCheckInResponse(
            success=False,
            checkin=None,
            nearest_gym=GymResponse.model_validate(gym) if gym else None,
            distance_meters=distance,
            message=f"Too far from nearest gym ({int(distance)}m away)" if gym else "No gyms found",
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
            detail="Not currently checked in",
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
            detail="Gym not found",
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
            detail="Code not found",
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
            detail="Already checked in. Please check out first.",
        )

    # Verify gym exists
    gym = await service.get_gym_by_id(request.gym_id)
    if not gym:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gym not found",
        )

    req = await service.create_request(
        user_id=current_user.id,
        gym_id=request.gym_id,
        approver_id=request.approver_id,
        reason=request.reason,
    )
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
            detail="Request not found",
        )

    if req.approver_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to respond to this request",
        )

    if req.status != CheckInStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request already responded to",
        )

    updated_req, _ = await service.respond_to_request(
        request=req,
        approved=response.approved,
        response_note=response.response_note,
    )
    return CheckInRequestResponse.model_validate(updated_req)


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
