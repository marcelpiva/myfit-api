"""Gamification router with points, achievements, and leaderboard endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.gamification.schemas import (
    AchievementCreate,
    AchievementResponse,
    AwardAchievementRequest,
    AwardPointsRequest,
    GamificationStatsResponse,
    LeaderboardEntryResponse,
    PointTransactionResponse,
    UserAchievementResponse,
    UserPointsResponse,
)
from src.domains.gamification.service import GamificationService

router = APIRouter()


# User Points endpoints

@router.get("/points", response_model=UserPointsResponse)
async def get_my_points(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPointsResponse:
    """Get current user's points."""
    service = GamificationService(db)
    points = await service.get_or_create_user_points(current_user.id)
    return UserPointsResponse.model_validate(points)


@router.post("/points", response_model=UserPointsResponse, status_code=status.HTTP_201_CREATED)
async def award_points(
    request: AwardPointsRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPointsResponse:
    """Award points to current user."""
    service = GamificationService(db)
    points, _ = await service.award_points(
        user_id=current_user.id,
        points=request.points,
        reason=request.reason,
        description=request.description,
        reference_type=request.reference_type,
        reference_id=request.reference_id,
    )
    return UserPointsResponse.model_validate(points)


@router.get("/points/history", response_model=list[PointTransactionResponse])
async def get_points_history(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PointTransactionResponse]:
    """Get user's point transaction history."""
    service = GamificationService(db)
    transactions = await service.get_point_transactions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [PointTransactionResponse.model_validate(t) for t in transactions]


@router.post("/points/streak", response_model=UserPointsResponse)
async def update_streak(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPointsResponse:
    """Update user's activity streak."""
    service = GamificationService(db)
    points = await service.update_streak(current_user.id)
    return UserPointsResponse.model_validate(points)


# Achievement endpoints

@router.get("/achievements", response_model=list[AchievementResponse])
async def list_achievements(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Annotated[str | None, Query()] = None,
) -> list[AchievementResponse]:
    """List all available achievements."""
    service = GamificationService(db)
    achievements = await service.list_achievements(category=category)
    return [AchievementResponse.model_validate(a) for a in achievements]


@router.post("/achievements", response_model=AchievementResponse, status_code=status.HTTP_201_CREATED)
async def create_achievement(
    request: AchievementCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AchievementResponse:
    """Create a new achievement (admin only)."""
    service = GamificationService(db)
    achievement = await service.create_achievement(
        name=request.name,
        description=request.description,
        icon=request.icon,
        points_reward=request.points_reward,
        category=request.category,
        condition=request.condition,
        order=request.order,
    )
    return AchievementResponse.model_validate(achievement)


@router.get("/achievements/mine", response_model=list[UserAchievementResponse])
async def get_my_achievements(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserAchievementResponse]:
    """Get current user's earned achievements."""
    service = GamificationService(db)
    achievements = await service.get_user_achievements(current_user.id)
    return [UserAchievementResponse.model_validate(a) for a in achievements]


@router.post("/achievements/award", response_model=UserAchievementResponse, status_code=status.HTTP_201_CREATED)
async def award_achievement(
    request: AwardAchievementRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserAchievementResponse:
    """Award an achievement to current user."""
    service = GamificationService(db)

    try:
        user_achievement, _ = await service.award_achievement(
            user_id=current_user.id,
            achievement_id=request.achievement_id,
            progress=request.progress,
        )
        return UserAchievementResponse.model_validate(user_achievement)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# Leaderboard endpoints

@router.get("/leaderboard", response_model=list[LeaderboardEntryResponse])
async def get_leaderboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[str, Query(pattern="^(weekly|monthly|all_time)$")] = "all_time",
    organization_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[LeaderboardEntryResponse]:
    """Get leaderboard rankings."""
    service = GamificationService(db)
    entries = await service.get_leaderboard(
        period=period,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    return [LeaderboardEntryResponse.model_validate(e) for e in entries]


@router.get("/leaderboard/me", response_model=LeaderboardEntryResponse | None)
async def get_my_rank(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[str, Query(pattern="^(weekly|monthly|all_time)$")] = "all_time",
    organization_id: Annotated[UUID | None, Query()] = None,
) -> LeaderboardEntryResponse | None:
    """Get current user's leaderboard position."""
    service = GamificationService(db)
    entry = await service.get_user_rank(
        user_id=current_user.id,
        period=period,
        organization_id=organization_id,
    )
    if entry:
        return LeaderboardEntryResponse.model_validate(entry)
    return None


@router.post("/leaderboard/refresh", response_model=list[LeaderboardEntryResponse])
async def refresh_leaderboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    period: Annotated[str, Query(pattern="^(weekly|monthly|all_time)$")] = "all_time",
    organization_id: Annotated[UUID | None, Query()] = None,
) -> list[LeaderboardEntryResponse]:
    """Refresh leaderboard rankings (admin only)."""
    service = GamificationService(db)
    entries = await service.update_leaderboard(
        period=period,
        organization_id=organization_id,
    )
    return [LeaderboardEntryResponse.model_validate(e) for e in entries]


# Stats endpoint

@router.get("/stats", response_model=GamificationStatsResponse)
async def get_gamification_stats(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GamificationStatsResponse:
    """Get gamification statistics for the current user."""
    service = GamificationService(db)
    stats = await service.get_gamification_stats(current_user.id)
    return GamificationStatsResponse(**stats)
