"""Trainer router - provides trainer-centric API for managing students."""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.organizations.models import OrganizationMembership, UserRole
from src.domains.organizations.service import OrganizationService
from src.domains.trainers.schemas import (
    AddStudentRequest,
    InviteCodeResponse,
    SendInviteRequest,
    StudentRegisterRequest,
    StudentResponse,
    StudentStatsResponse,
)
from src.domains.users.models import User
from src.domains.users.service import UserService
from src.domains.workouts.models import WorkoutSession

router = APIRouter()


async def _get_trainer_organization(
    current_user: User,
    db: AsyncSession,
) -> UUID:
    """Get the trainer's primary organization ID."""
    org_service = OrganizationService(db)

    # Get organizations where user is owner or trainer
    orgs = await org_service.get_user_organizations(current_user.id)

    # Find first org where user is owner or trainer
    for org in orgs:
        membership = await org_service.get_membership(org.id, current_user.id)
        if membership and membership.role in [
            UserRole.GYM_OWNER,
            UserRole.GYM_ADMIN,
            UserRole.TRAINER,
            UserRole.COACH,
        ]:
            return org.id

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Você não tem permissão de treinador. Crie uma organização primeiro.",
    )


# ==================== Students ====================

@router.get("/students", response_model=list[StudentResponse])
async def list_students(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[Optional[str], Query(alias="status")] = None,
    query: Annotated[Optional[str], Query(alias="q", max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StudentResponse]:
    """Get list of trainer's students."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)
    user_service = UserService(db)

    # Get students (members with student role)
    members = await org_service.get_organization_members(org_id, role="student")

    result = []
    for m in members:
        # Apply status filter
        if status_filter == "active" and not m.is_active:
            continue
        if status_filter == "inactive" and m.is_active:
            continue

        user = await user_service.get_user_by_id(m.user_id)
        if not user:
            continue

        # Apply search query
        if query:
            query_lower = query.lower()
            if query_lower not in user.name.lower() and query_lower not in user.email.lower():
                continue

        # Get workout stats
        workouts_count = await db.scalar(
            select(func.count(WorkoutSession.id))
            .where(WorkoutSession.user_id == m.user_id)
        ) or 0

        last_workout = await db.scalar(
            select(func.max(WorkoutSession.started_at))
            .where(WorkoutSession.user_id == m.user_id)
        )

        result.append(
            StudentResponse(
                id=m.id,
                user_id=m.user_id,
                name=user.name,
                email=user.email,
                avatar_url=user.avatar_url,
                phone=user.phone,
                joined_at=m.joined_at,
                is_active=m.is_active,
                goal=None,  # Could be stored in member metadata
                notes=None,
                workouts_count=workouts_count,
                last_workout_at=last_workout,
            )
        )

    # Apply pagination
    return result[offset:offset + limit]


@router.get("/students/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentResponse:
    """Get student details."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)
    user_service = UserService(db)

    # Find member by ID
    member = await db.get(OrganizationMembership, student_id)
    if not member or member.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado",
        )

    user = await user_service.get_user_by_id(member.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    # Get workout stats
    workouts_count = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(WorkoutSession.user_id == member.user_id)
    ) or 0

    last_workout = await db.scalar(
        select(func.max(WorkoutSession.started_at))
        .where(WorkoutSession.user_id == member.user_id)
    )

    return StudentResponse(
        id=member.id,
        user_id=member.user_id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        phone=user.phone,
        joined_at=member.joined_at,
        is_active=member.is_active,
        goal=None,
        notes=None,
        workouts_count=workouts_count,
        last_workout_at=last_workout,
    )


@router.get("/students/{student_id}/stats", response_model=StudentStatsResponse)
async def get_student_stats(
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> StudentStatsResponse:
    """Get student statistics."""
    org_id = await _get_trainer_organization(current_user, db)

    # Find member by ID
    member = await db.get(OrganizationMembership, student_id)
    if not member or member.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado",
        )

    now = datetime.now(timezone.utc)
    start_of_week = now - timedelta(days=now.weekday())
    start_of_month = now.replace(day=1)

    # Total workouts
    total_workouts = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(WorkoutSession.user_id == member.user_id)
    ) or 0

    # Workouts this week
    workouts_this_week = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(
            WorkoutSession.user_id == member.user_id,
            WorkoutSession.started_at >= start_of_week,
        )
    ) or 0

    # Workouts this month
    workouts_this_month = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(
            WorkoutSession.user_id == member.user_id,
            WorkoutSession.started_at >= start_of_month,
        )
    ) or 0

    # Average duration
    avg_duration = await db.scalar(
        select(func.avg(WorkoutSession.duration_minutes))
        .where(
            WorkoutSession.user_id == member.user_id,
            WorkoutSession.duration_minutes.isnot(None),
        )
    ) or 0

    # Last workout
    last_workout = await db.scalar(
        select(func.max(WorkoutSession.started_at))
        .where(WorkoutSession.user_id == member.user_id)
    )

    return StudentStatsResponse(
        total_workouts=total_workouts,
        workouts_this_week=workouts_this_week,
        workouts_this_month=workouts_this_month,
        average_duration_minutes=int(avg_duration),
        total_exercises=0,  # Would require joining with workout exercises
        streak_days=0,  # Would require more complex calculation
        last_workout_at=last_workout,
    )


@router.get("/students/{student_id}/workouts")
async def get_student_workouts(
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[dict]:
    """Get student's workouts."""
    org_id = await _get_trainer_organization(current_user, db)

    # Find member by ID
    member = await db.get(OrganizationMembership, student_id)
    if not member or member.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado",
        )

    # Get recent workout sessions
    result = await db.execute(
        select(WorkoutSession)
        .where(WorkoutSession.user_id == member.user_id)
        .order_by(WorkoutSession.started_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "workout_id": str(s.workout_id) if s.workout_id else None,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "duration_minutes": s.duration_minutes,
            "status": s.status,
        }
        for s in sessions
    ]


@router.get("/students/{student_id}/progress")
async def get_student_progress(
    student_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get student's progress summary."""
    org_id = await _get_trainer_organization(current_user, db)

    # Find member by ID
    member = await db.get(OrganizationMembership, student_id)
    if not member or member.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aluno não encontrado",
        )

    # For now, return basic progress data
    # This could be expanded to include body measurements, PRs, etc.
    return {
        "user_id": str(member.user_id),
        "total_sessions": 0,
        "total_volume": 0,
        "streak_days": 0,
        "achievements": [],
    }


@router.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def add_student(
    request: AddStudentRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentResponse:
    """Add an existing user as a student."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)
    user_service = UserService(db)

    # Verify user exists
    user = await user_service.get_user_by_id(request.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado",
        )

    # Check if already a member
    existing = await org_service.get_membership(org_id, request.user_id)
    if existing and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuário já é membro",
        )

    # Add as student
    membership = await org_service.add_member(
        org_id=org_id,
        user_id=request.user_id,
        role=UserRole.STUDENT,
        invited_by_id=current_user.id,
    )

    return StudentResponse(
        id=membership.id,
        user_id=membership.user_id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        phone=user.phone,
        joined_at=membership.joined_at,
        is_active=membership.is_active,
        workouts_count=0,
        last_workout_at=None,
    )


@router.post("/students/register", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def register_student(
    request: StudentRegisterRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StudentResponse:
    """Register a new student (creates user account and adds to trainer's organization)."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)
    user_service = UserService(db)

    # Check if email already exists
    existing_user = await user_service.get_user_by_email(request.email)
    if existing_user:
        # User exists - check if already a member
        existing_member = await org_service.get_membership(org_id, existing_user.id)
        if existing_member and existing_member.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email já cadastrado como aluno",
            )

        # Add existing user as student
        membership = await org_service.add_member(
            org_id=org_id,
            user_id=existing_user.id,
            role=UserRole.STUDENT,
            invited_by_id=current_user.id,
        )

        return StudentResponse(
            id=membership.id,
            user_id=membership.user_id,
            name=existing_user.name,
            email=existing_user.email,
            avatar_url=existing_user.avatar_url,
            phone=existing_user.phone,
            joined_at=membership.joined_at,
            is_active=membership.is_active,
            goal=request.goal,
            notes=request.notes,
            workouts_count=0,
            last_workout_at=None,
        )

    # Create new user account
    temp_password = secrets.token_urlsafe(12)
    new_user = await user_service.create_user(
        email=request.email,
        password=temp_password,
        name=request.name,
        phone=request.phone,
    )

    # Add to organization as student
    membership = await org_service.add_member(
        org_id=org_id,
        user_id=new_user.id,
        role=UserRole.STUDENT,
        invited_by_id=current_user.id,
    )

    # TODO: Send welcome email with temp password

    return StudentResponse(
        id=membership.id,
        user_id=membership.user_id,
        name=new_user.name,
        email=new_user.email,
        avatar_url=new_user.avatar_url,
        phone=new_user.phone,
        joined_at=membership.joined_at,
        is_active=membership.is_active,
        goal=request.goal,
        notes=request.notes,
        workouts_count=0,
        last_workout_at=None,
    )


# ==================== Invite Code ====================

@router.get("/my-invite-code", response_model=InviteCodeResponse)
async def get_invite_code(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteCodeResponse:
    """Get the trainer's invite code for students to join."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)

    org = await org_service.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organização não encontrada",
        )

    # Generate a simple code based on org ID
    # In production, this should be a separate stored invite code
    code = f"MYFIT-{str(org_id)[:8].upper()}"

    return InviteCodeResponse(
        code=code,
        url=f"https://myfit.app/join/{code}",
        expires_at=None,
    )


@router.post("/my-invite-code", response_model=InviteCodeResponse, status_code=status.HTTP_201_CREATED)
async def regenerate_invite_code(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteCodeResponse:
    """Regenerate the trainer's invite code."""
    org_id = await _get_trainer_organization(current_user, db)

    # Generate a new code
    code = f"MYFIT-{secrets.token_hex(4).upper()}"

    return InviteCodeResponse(
        code=code,
        url=f"https://myfit.app/join/{code}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )


@router.post("/my-invite-code/send", status_code=status.HTTP_200_OK)
async def send_invite_email(
    request: SendInviteRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Send invite email to a potential student."""
    org_id = await _get_trainer_organization(current_user, db)
    org_service = OrganizationService(db)

    # Create an invitation
    invite = await org_service.create_invite(
        org_id=org_id,
        email=request.email,
        role=UserRole.STUDENT,
        invited_by_id=current_user.id,
    )

    # TODO: Send actual email

    return {
        "message": f"Convite enviado para {request.email}",
        "invite_id": str(invite.id),
    }
