"""Progress router with weight, measurement, and photo endpoints."""
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.progress.models import PhotoAngle
from src.domains.progress.schemas import (
    MeasurementLogCreate,
    MeasurementLogResponse,
    MeasurementLogUpdate,
    ProgressPhotoCreate,
    ProgressPhotoResponse,
    ProgressStatsResponse,
    WeightGoalCreate,
    WeightGoalResponse,
    WeightLogCreate,
    WeightLogResponse,
    WeightLogUpdate,
)
from src.domains.progress.service import ProgressService

router = APIRouter()


# Weight endpoints

@router.get("/weight", response_model=list[WeightLogResponse])
async def list_weight_logs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WeightLogResponse]:
    """List weight logs for the current user."""
    service = ProgressService(db)
    logs = await service.list_weight_logs(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return [WeightLogResponse.model_validate(log) for log in logs]


@router.post("/weight", response_model=WeightLogResponse, status_code=status.HTTP_201_CREATED)
async def create_weight_log(
    request: WeightLogCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightLogResponse:
    """Log a new weight entry."""
    service = ProgressService(db)
    log = await service.create_weight_log(
        user_id=current_user.id,
        weight_kg=request.weight_kg,
        logged_at=request.logged_at,
        notes=request.notes,
    )
    return WeightLogResponse.model_validate(log)


@router.get("/weight/latest", response_model=WeightLogResponse | None)
async def get_latest_weight(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightLogResponse | None:
    """Get the most recent weight log."""
    service = ProgressService(db)
    log = await service.get_latest_weight(current_user.id)
    if log:
        return WeightLogResponse.model_validate(log)
    return None


@router.get("/weight/{log_id}", response_model=WeightLogResponse)
async def get_weight_log(
    log_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightLogResponse:
    """Get a specific weight log."""
    service = ProgressService(db)
    log = await service.get_weight_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this log",
        )

    return WeightLogResponse.model_validate(log)


@router.put("/weight/{log_id}", response_model=WeightLogResponse)
async def update_weight_log(
    log_id: UUID,
    request: WeightLogUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightLogResponse:
    """Update a weight log."""
    service = ProgressService(db)
    log = await service.get_weight_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this log",
        )

    updated = await service.update_weight_log(
        log=log,
        weight_kg=request.weight_kg,
        logged_at=request.logged_at,
        notes=request.notes,
    )
    return WeightLogResponse.model_validate(updated)


@router.delete("/weight/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weight_log(
    log_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a weight log."""
    service = ProgressService(db)
    log = await service.get_weight_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this log",
        )

    await service.delete_weight_log(log)


# Measurement endpoints

@router.get("/measurements", response_model=list[MeasurementLogResponse])
async def list_measurement_logs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MeasurementLogResponse]:
    """List measurement logs for the current user."""
    service = ProgressService(db)
    logs = await service.list_measurement_logs(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return [MeasurementLogResponse.model_validate(log) for log in logs]


@router.post("/measurements", response_model=MeasurementLogResponse, status_code=status.HTTP_201_CREATED)
async def create_measurement_log(
    request: MeasurementLogCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeasurementLogResponse:
    """Log new body measurements."""
    service = ProgressService(db)
    log = await service.create_measurement_log(
        user_id=current_user.id,
        logged_at=request.logged_at,
        chest_cm=request.chest_cm,
        waist_cm=request.waist_cm,
        hips_cm=request.hips_cm,
        biceps_cm=request.biceps_cm,
        thigh_cm=request.thigh_cm,
        calf_cm=request.calf_cm,
        neck_cm=request.neck_cm,
        forearm_cm=request.forearm_cm,
        notes=request.notes,
    )
    return MeasurementLogResponse.model_validate(log)


@router.get("/measurements/latest", response_model=MeasurementLogResponse | None)
async def get_latest_measurements(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeasurementLogResponse | None:
    """Get the most recent measurement log."""
    service = ProgressService(db)
    log = await service.get_latest_measurements(current_user.id)
    if log:
        return MeasurementLogResponse.model_validate(log)
    return None


@router.get("/measurements/{log_id}", response_model=MeasurementLogResponse)
async def get_measurement_log(
    log_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeasurementLogResponse:
    """Get a specific measurement log."""
    service = ProgressService(db)
    log = await service.get_measurement_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Measurement log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this log",
        )

    return MeasurementLogResponse.model_validate(log)


@router.put("/measurements/{log_id}", response_model=MeasurementLogResponse)
async def update_measurement_log(
    log_id: UUID,
    request: MeasurementLogUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeasurementLogResponse:
    """Update a measurement log."""
    service = ProgressService(db)
    log = await service.get_measurement_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Measurement log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this log",
        )

    updated = await service.update_measurement_log(
        log=log,
        **request.model_dump(exclude_unset=True),
    )
    return MeasurementLogResponse.model_validate(updated)


@router.delete("/measurements/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_measurement_log(
    log_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a measurement log."""
    service = ProgressService(db)
    log = await service.get_measurement_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Measurement log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this log",
        )

    await service.delete_measurement_log(log)


# Photo endpoints

@router.get("/photos", response_model=list[ProgressPhotoResponse])
async def list_photos(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    angle: Annotated[PhotoAngle | None, Query()] = None,
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProgressPhotoResponse]:
    """List progress photos for the current user."""
    service = ProgressService(db)
    photos = await service.list_photos(
        user_id=current_user.id,
        angle=angle,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return [ProgressPhotoResponse.model_validate(p) for p in photos]


@router.post("/photos", response_model=ProgressPhotoResponse, status_code=status.HTTP_201_CREATED)
async def create_photo(
    request: ProgressPhotoCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgressPhotoResponse:
    """Add a progress photo."""
    service = ProgressService(db)
    photo = await service.create_photo(
        user_id=current_user.id,
        photo_url=request.photo_url,
        thumbnail_url=request.thumbnail_url,
        angle=request.angle,
        logged_at=request.logged_at,
        notes=request.notes,
        weight_log_id=request.weight_log_id,
        measurement_log_id=request.measurement_log_id,
    )
    return ProgressPhotoResponse.model_validate(photo)


@router.delete("/photos/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a progress photo."""
    service = ProgressService(db)
    photo = await service.get_photo_by_id(photo_id)

    if not photo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    if photo.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this photo",
        )

    await service.delete_photo(photo)


# Weight goal endpoints

@router.get("/goal", response_model=WeightGoalResponse | None)
async def get_weight_goal(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightGoalResponse | None:
    """Get the current user's weight goal."""
    service = ProgressService(db)
    goal = await service.get_weight_goal(current_user.id)
    if goal:
        return WeightGoalResponse.model_validate(goal)
    return None


@router.post("/goal", response_model=WeightGoalResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_weight_goal(
    request: WeightGoalCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WeightGoalResponse:
    """Create or update weight goal."""
    service = ProgressService(db)
    goal = await service.create_or_update_weight_goal(
        user_id=current_user.id,
        target_weight_kg=request.target_weight_kg,
        start_weight_kg=request.start_weight_kg,
        target_date=request.target_date,
        notes=request.notes,
    )
    return WeightGoalResponse.model_validate(goal)


@router.delete("/goal", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weight_goal(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete weight goal."""
    service = ProgressService(db)
    goal = await service.get_weight_goal(current_user.id)

    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Weight goal not found",
        )

    await service.delete_weight_goal(goal)


# Stats endpoint

@router.get("/stats", response_model=ProgressStatsResponse)
async def get_progress_stats(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=7, le=365)] = 30,
) -> ProgressStatsResponse:
    """Get progress statistics for the current user."""
    service = ProgressService(db)
    stats = await service.get_progress_stats(
        user_id=current_user.id,
        days=days,
    )
    return ProgressStatsResponse(**stats)
