"""Workout assignment endpoints."""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.redis import RateLimiter
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.service import UserService
from src.domains.workouts.schemas import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
)
from src.domains.workouts.service import WorkoutService

logger = logging.getLogger(__name__)

assignments_router = APIRouter()


@assignments_router.get("/assignments", response_model=list[AssignmentResponse])
async def list_assignments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    active_only: Annotated[bool, Query()] = True,
) -> list[AssignmentResponse]:
    """List workout assignments (as student or trainer)."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    if as_trainer:
        assignments = await workout_service.list_trainer_assignments(
            trainer_id=current_user.id,
            active_only=active_only,
        )
    else:
        assignments = await workout_service.list_student_assignments(
            student_id=current_user.id,
            active_only=active_only,
        )

    result = []
    for a in assignments:
        student = await user_service.get_user_by_id(a.student_id)
        result.append(
            AssignmentResponse(
                id=a.id,
                workout_id=a.workout_id,
                student_id=a.student_id,
                trainer_id=a.trainer_id,
                organization_id=a.organization_id,
                start_date=a.start_date,
                end_date=a.end_date,
                is_active=a.is_active,
                notes=a.notes,
                created_at=a.created_at,
                workout_name=a.workout.name if a.workout else "",
                student_name=student.name if student else "",
            )
        )

    return result


@assignments_router.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    request: AssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Assign a workout to a student."""
    from src.domains.organizations.models import OrganizationMembership

    # Rate limiting: max 50 assignments per hour per trainer
    is_allowed, current_count = await RateLimiter.check_rate_limit(
        identifier=str(current_user.id),
        action="workout_assignment",
        max_requests=50,
        window_seconds=3600,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite de atribuições excedido. Tente novamente mais tarde. ({current_count}/50 por hora)",
        )

    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Verify workout exists
    workout = await workout_service.get_workout_by_id(request.workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Verify student exists
    student = await user_service.get_user_by_id(request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # SECURITY: Validate trainer and student share an organization
    if request.organization_id:
        from sqlalchemy import and_, select

        # Check if both trainer and student are members of the specified organization
        trainer_membership = await db.execute(
            select(OrganizationMembership).where(
                and_(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.organization_id == request.organization_id,
                    OrganizationMembership.is_active == True,
                )
            )
        )
        if not trainer_membership.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não é membro desta organização",
            )

        student_membership = await db.execute(
            select(OrganizationMembership).where(
                and_(
                    OrganizationMembership.user_id == request.student_id,
                    OrganizationMembership.organization_id == request.organization_id,
                    OrganizationMembership.is_active == True,
                )
            )
        )
        if not student_membership.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="O aluno não é membro desta organização",
            )

    assignment = await workout_service.create_assignment(
        workout_id=request.workout_id,
        student_id=request.student_id,
        trainer_id=current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        notes=request.notes,
        organization_id=request.organization_id,
    )

    return AssignmentResponse(
        id=assignment.id,
        workout_id=assignment.workout_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        created_at=assignment.created_at,
        workout_name=workout.name,
        student_name=student.name,
    )


@assignments_router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: UUID,
    request: AssignmentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AssignmentResponse:
    """Update an assignment (trainer only)."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    assignment = await workout_service.get_assignment_by_id(assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found",
        )

    if assignment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own assignments",
        )

    updated = await workout_service.update_assignment(
        assignment=assignment,
        start_date=request.start_date,
        end_date=request.end_date,
        is_active=request.is_active,
        notes=request.notes,
    )

    student = await user_service.get_user_by_id(updated.student_id)

    return AssignmentResponse(
        id=updated.id,
        workout_id=updated.workout_id,
        student_id=updated.student_id,
        trainer_id=updated.trainer_id,
        organization_id=updated.organization_id,
        start_date=updated.start_date,
        end_date=updated.end_date,
        is_active=updated.is_active,
        notes=updated.notes,
        created_at=updated.created_at,
        workout_name=updated.workout.name if updated.workout else "",
        student_name=student.name if student else "",
    )
