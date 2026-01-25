"""User router with profile and settings endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile, status
from uuid import UUID
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.redis import TokenBlacklist
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.schemas import (
    AvatarUploadResponse,
    PasswordChangeRequest,
    PlanProgressResponse,
    RecentActivityResponse,
    StudentDashboardResponse,
    StudentStatsResponse,
    TodayWorkoutResponse,
    TrainerInfoResponse,
    UserListResponse,
    UserProfileResponse,
    UserProfileUpdate,
    UserSettingsResponse,
    UserSettingsUpdate,
    WeeklyProgressResponse,
)
from src.domains.users.service import UserService
from src.domains.organizations.service import OrganizationService
from src.domains.organizations.models import OrganizationMembership, UserRole
from src.domains.organizations.schemas import UserMembershipResponse, OrganizationInMembership, InviteResponse
from src.domains.trainers.models import StudentNote
from src.domains.trainers.schemas import ProgressNoteResponse
from src.domains.workouts.models import (
    AssignmentStatus,
    PlanAssignment,
    PlanWorkout,
    PrescriptionNote,
    TrainingPlan,
    Workout,
    WorkoutExercise,
    WorkoutSession,
)
from src.domains.gamification.service import GamificationService
from src.domains.progress.models import WeightLog

router = APIRouter()


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: CurrentUser,
) -> UserProfileResponse:
    """Get current user's profile."""
    return UserProfileResponse.model_validate(current_user)


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: UserProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileResponse:
    """Update current user's profile."""
    user_service = UserService(db)

    updated_user = await user_service.update_profile(
        user=current_user,
        name=request.name,
        phone=request.phone,
        birth_date=request.birth_date,
        gender=request.gender,
        height_cm=request.height_cm,
        bio=request.bio,
    )

    return UserProfileResponse.model_validate(updated_user)


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AvatarUploadResponse:
    """Upload user avatar image.

    Supports JPEG, PNG, WebP, and GIF formats. Maximum size: 5MB.
    Uploads to configured storage (S3/R2 or local filesystem).
    """
    from src.core.storage import (
        FileTooLargeError,
        InvalidContentTypeError,
        StorageError,
        storage_service,
    )

    # Read file content
    content = await file.read()

    try:
        # Upload to storage (validation happens inside)
        avatar_url = await storage_service.upload_avatar(
            user_id=str(current_user.id),
            file_content=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except InvalidContentTypeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: JPEG, PNG, WebP, GIF",
        )
    except FileTooLargeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size: 5MB",
        )
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )

    # Delete old avatar if it exists
    user_service = UserService(db)
    if current_user.avatar_url:
        await storage_service.delete_file(current_user.avatar_url)

    # Update user with new avatar URL
    await user_service.update_avatar(current_user, avatar_url)

    return AvatarUploadResponse(avatar_url=avatar_url)


@router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSettingsResponse:
    """Get current user's settings."""
    user_service = UserService(db)
    settings = await user_service.get_settings(current_user.id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    return UserSettingsResponse.model_validate(settings)


@router.put("/settings", response_model=UserSettingsResponse)
async def update_settings(
    request: UserSettingsUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSettingsResponse:
    """Update current user's settings."""
    user_service = UserService(db)
    settings = await user_service.get_settings(current_user.id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    updated_settings = await user_service.update_settings(
        settings=settings,
        theme=request.theme,
        language=request.language,
        units=request.units,
        notifications_enabled=request.notifications_enabled,
        goal_weight=request.goal_weight,
        target_calories=request.target_calories,
    )

    return UserSettingsResponse.model_validate(updated_settings)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: PasswordChangeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Change current user's password.

    This also invalidates all existing tokens for security.
    """
    user_service = UserService(db)

    success = await user_service.change_password(
        user=current_user,
        current_password=request.current_password,
        new_password=request.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Invalidate all user tokens
    await TokenBlacklist.invalidate_all_user_tokens(str(current_user.id))


@router.get("/search", response_model=list[UserListResponse])
async def search_users(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserListResponse]:
    """Search for users by name or email."""
    user_service = UserService(db)
    users = await user_service.search_users(q, limit, offset)
    return [UserListResponse.model_validate(u) for u in users]


@router.get("/me/memberships", response_model=list[UserMembershipResponse])
async def get_my_memberships(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserMembershipResponse]:
    """Get all memberships for the current user with organization details."""
    org_service = OrganizationService(db)
    memberships = await org_service.get_user_memberships_with_orgs(current_user.id)

    result = []
    for membership in memberships:
        org = membership.organization
        result.append(
            UserMembershipResponse(
                id=membership.id,
                organization=OrganizationInMembership(
                    id=org.id,
                    name=org.name,
                    type=org.type,
                    logo_url=org.logo_url,
                    member_count=org.member_count,
                    created_at=org.created_at,
                ),
                role=membership.role,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
                invited_by=None,  # TODO: Get inviter name if needed
            )
        )

    return result


@router.get("/me/pending-invites", response_model=list[InviteResponse])
async def get_my_pending_invites(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InviteResponse]:
    """Get all pending invites for the current user's email."""
    org_service = OrganizationService(db)
    invites = await org_service.get_pending_invites_for_email(current_user.email)
    return [
        InviteResponse(
            id=invite.id,
            email=invite.email,
            role=invite.role,
            organization_id=invite.organization_id,
            organization_name=invite.organization.name if invite.organization else "Unknown",
            invited_by_name=invite.invited_by.name if invite.invited_by else "Unknown",
            expires_at=invite.expires_at,
            created_at=invite.created_at,
            is_expired=invite.is_expired,
            is_accepted=invite.is_accepted,
            token=invite.token,  # Include token for accept functionality
        )
        for invite in invites
        if not invite.is_expired and not invite.is_accepted
    ]


@router.get("/me/trainer-notes", response_model=list[ProgressNoteResponse])
async def get_my_trainer_notes(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProgressNoteResponse]:
    """Get notes written by trainers about the current user (student view).

    SECURITY FIX: VULN-5 - Students can now see notes written about them.
    This endpoint returns StudentNotes where the current user is the student.

    When X-Organization-ID header is provided, filters notes by organization
    (useful when student has multiple trainers).
    """
    filters = [StudentNote.student_id == current_user.id]

    # Filter by organization if provided
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
            filters.append(
                or_(
                    StudentNote.organization_id == org_id,
                    StudentNote.organization_id.is_(None),  # Backward compatibility
                )
            )
        except ValueError:
            pass  # Invalid UUID, ignore

    result = await db.execute(
        select(StudentNote)
        .where(*filters)
        .order_by(StudentNote.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    notes = result.scalars().all()

    return [
        ProgressNoteResponse(
            id=note.id,
            student_id=note.student_id,
            trainer_id=note.trainer_id,
            content=note.content,
            category=note.category,
            created_at=note.created_at,
        )
        for note in notes
    ]


@router.get("/me/dashboard", response_model=StudentDashboardResponse)
async def get_student_dashboard(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> StudentDashboardResponse:
    """Get consolidated dashboard data for the student.

    Returns all data needed for the student home page:
    - Stats (total workouts, adherence, weight change, streak)
    - Today's workout (from active plan)
    - Weekly progress
    - Recent activity
    - Trainer info
    - Plan progress
    - Unread notes count
    """
    now = datetime.now(timezone.utc)
    today = now.date()
    start_of_week = now - timedelta(days=now.weekday())

    # ==================== Stats ====================
    # Total workouts completed
    total_workouts = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.completed_at.isnot(None),
        )
    ) or 0

    # Workouts this month (for adherence calculation)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    workouts_this_month = await db.scalar(
        select(func.count(WorkoutSession.id))
        .where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.started_at >= start_of_month,
        )
    ) or 0

    # Calculate adherence (workouts per week target: 5, so ~20 per month)
    days_in_month = (now - start_of_month).days + 1
    expected_workouts = max(1, int((days_in_month / 7) * 5))
    adherence_percent = min(100, int((workouts_this_month / expected_workouts) * 100))

    # Weight change (latest vs oldest measurement)
    weight_change_kg = None
    latest_weight = await db.execute(
        select(WeightLog)
        .where(WeightLog.user_id == current_user.id)
        .order_by(WeightLog.logged_at.desc())
        .limit(1)
    )
    latest = latest_weight.scalar_one_or_none()

    oldest_weight = await db.execute(
        select(WeightLog)
        .where(WeightLog.user_id == current_user.id)
        .order_by(WeightLog.logged_at.asc())
        .limit(1)
    )
    oldest = oldest_weight.scalar_one_or_none()

    if latest and oldest and latest.id != oldest.id:
        weight_change_kg = round(latest.weight_kg - oldest.weight_kg, 1)

    # Current streak
    gamification_service = GamificationService(db)
    user_points = await gamification_service.get_user_points(current_user.id)
    current_streak = user_points.current_streak if user_points else 0

    stats = StudentStatsResponse(
        total_workouts=total_workouts,
        adherence_percent=adherence_percent,
        weight_change_kg=weight_change_kg,
        current_streak=current_streak,
    )

    # ==================== Today's Workout ====================
    today_workout = None
    plan_progress = None

    # Parse organization ID if provided
    org_id = None
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass  # Invalid UUID, ignore

    # Build filter conditions for plan assignment
    assignment_filters = [
        PlanAssignment.student_id == current_user.id,
        PlanAssignment.is_active == True,
        PlanAssignment.status == AssignmentStatus.ACCEPTED,  # Only show accepted plans
        PlanAssignment.start_date <= today,
    ]
    # Filter by organization if provided (include NULL for backward compatibility)
    if org_id:
        assignment_filters.append(
            or_(
                PlanAssignment.organization_id == org_id,
                PlanAssignment.organization_id.is_(None),  # Backward compatibility
            )
        )

    # Find active plan assignment
    active_assignment_result = await db.execute(
        select(PlanAssignment)
        .where(*assignment_filters)
        .order_by(PlanAssignment.start_date.desc())
        .limit(1)
    )
    active_assignment = active_assignment_result.scalar_one_or_none()

    if active_assignment:
        # Get the plan with workouts
        plan_result = await db.execute(
            select(TrainingPlan)
            .where(TrainingPlan.id == active_assignment.plan_id)
        )
        plan = plan_result.scalar_one_or_none()

        if plan:
            # Get plan workouts
            plan_workouts_result = await db.execute(
                select(PlanWorkout)
                .where(PlanWorkout.plan_id == plan.id)
                .order_by(PlanWorkout.order)
            )
            plan_workouts = plan_workouts_result.scalars().all()

            if plan_workouts:
                # Simple rotation: use number of completed sessions to determine next workout
                completed_sessions = await db.scalar(
                    select(func.count(WorkoutSession.id))
                    .where(
                        WorkoutSession.user_id == current_user.id,
                        WorkoutSession.completed_at.isnot(None),
                        WorkoutSession.started_at >= active_assignment.start_date,
                    )
                ) or 0

                workout_index = completed_sessions % len(plan_workouts)
                current_plan_workout = plan_workouts[workout_index]

                # Get workout details
                workout_result = await db.execute(
                    select(Workout)
                    .where(Workout.id == current_plan_workout.workout_id)
                )
                workout = workout_result.scalar_one_or_none()

                if workout:
                    # Count exercises
                    exercises_count = await db.scalar(
                        select(func.count(WorkoutExercise.id))
                        .where(WorkoutExercise.workout_id == workout.id)
                    ) or 0

                    today_workout = TodayWorkoutResponse(
                        id=current_plan_workout.id,
                        name=workout.name,
                        label=f"TREINO {current_plan_workout.label}",
                        duration_minutes=workout.estimated_duration_min,
                        exercises_count=exercises_count,
                        plan_id=plan.id,
                        workout_id=workout.id,
                    )

            # Calculate plan progress
            total_weeks = plan.duration_weeks or 12
            days_since_start = (today - active_assignment.start_date).days
            current_week = min(total_weeks, max(1, (days_since_start // 7) + 1))
            percent_complete = min(100, int((current_week / total_weeks) * 100))

            plan_progress = PlanProgressResponse(
                plan_id=plan.id,
                plan_name=plan.name,
                current_week=current_week,
                total_weeks=total_weeks,
                percent_complete=percent_complete,
                training_mode=active_assignment.training_mode.value,
            )

    # ==================== Weekly Progress ====================
    # Get workouts completed this week with their days
    week_sessions_result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.completed_at.isnot(None),
            WorkoutSession.started_at >= start_of_week,
        )
    )
    week_sessions = week_sessions_result.scalars().all()

    # Build days array
    day_names = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
    days_completed = set()
    for session in week_sessions:
        if session.started_at:
            days_completed.add(session.started_at.weekday())

    days = [day_names[i] if i in days_completed else None for i in range(7)]

    weekly_progress = WeeklyProgressResponse(
        completed=len(days_completed),
        target=5,  # Default target
        days=days,
    )

    # ==================== Recent Activity ====================
    recent_activity = []

    # Recent completed workouts
    recent_workouts_result = await db.execute(
        select(WorkoutSession)
        .where(
            WorkoutSession.user_id == current_user.id,
            WorkoutSession.completed_at.isnot(None),
        )
        .order_by(WorkoutSession.completed_at.desc())
        .limit(3)
    )
    recent_workouts = recent_workouts_result.scalars().all()

    for session in recent_workouts:
        # Get workout name
        workout_result = await db.execute(
            select(Workout).where(Workout.id == session.workout_id)
        )
        workout = workout_result.scalar_one_or_none()
        workout_name = workout.name if workout else "Treino"

        # Format time
        time_diff = now - session.completed_at.replace(tzinfo=timezone.utc)
        if time_diff.days > 1:
            time_str = f"{time_diff.days} dias atrás"
        elif time_diff.days == 1:
            time_str = "Ontem"
        else:
            hours = time_diff.seconds // 3600
            if hours > 0:
                time_str = f"{hours}h atrás"
            else:
                time_str = "Agora mesmo"

        recent_activity.append(
            RecentActivityResponse(
                title="Treino Completado",
                subtitle=workout_name,
                time=time_str,
                type="workout",
            )
        )

    # Recent weight measurements
    recent_measurements_result = await db.execute(
        select(WeightLog)
        .where(WeightLog.user_id == current_user.id)
        .order_by(WeightLog.logged_at.desc())
        .limit(1)
    )
    recent_measurement = recent_measurements_result.scalar_one_or_none()

    if recent_measurement:
        time_diff = now - recent_measurement.logged_at.replace(tzinfo=timezone.utc)
        if time_diff.days > 1:
            time_str = f"{time_diff.days} dias atrás"
        elif time_diff.days == 1:
            time_str = "Ontem"
        else:
            time_str = "Hoje"

        recent_activity.append(
            RecentActivityResponse(
                title="Medição Atualizada",
                subtitle=f"Peso: {recent_measurement.weight_kg}kg",
                time=time_str,
                type="measurement",
            )
        )

    # Sort by time and limit
    recent_activity = recent_activity[:5]

    # ==================== Trainer Info ====================
    trainer_info = None
    user_service = UserService(db)

    # Build filter conditions for student membership
    membership_filters = [
        OrganizationMembership.user_id == current_user.id,
        OrganizationMembership.role == UserRole.STUDENT,
        OrganizationMembership.is_active == True,
    ]
    # Filter by organization if provided
    if org_id:
        membership_filters.append(OrganizationMembership.organization_id == org_id)

    # Find student's membership in the specified organization (or any if not specified)
    memberships_result = await db.execute(
        select(OrganizationMembership)
        .where(*membership_filters)
        .limit(1)
    )
    student_membership = memberships_result.scalar_one_or_none()

    if student_membership:
        # Find trainer in the same organization
        trainer_membership_result = await db.execute(
            select(OrganizationMembership)
            .where(
                OrganizationMembership.organization_id == student_membership.organization_id,
                OrganizationMembership.role.in_([
                    UserRole.TRAINER,
                    UserRole.GYM_OWNER,
                    UserRole.COACH,
                ]),
                OrganizationMembership.is_active == True,
            )
            .limit(1)
        )
        trainer_membership = trainer_membership_result.scalar_one_or_none()

        if trainer_membership:
            trainer_user = await user_service.get_user_by_id(trainer_membership.user_id)
            if trainer_user:
                trainer_info = TrainerInfoResponse(
                    id=trainer_user.id,
                    name=trainer_user.name,
                    avatar_url=trainer_user.avatar_url,
                    is_online=False,  # TODO: Implement online status
                )

    # ==================== Unread Notes Count ====================
    unread_notes_count = await db.scalar(
        select(func.count(PrescriptionNote.id))
        .where(
            # Notes where current user is the student (via plan assignment or direct)
            PrescriptionNote.read_at.is_(None),
            PrescriptionNote.author_id != current_user.id,
        )
    ) or 0

    return StudentDashboardResponse(
        stats=stats,
        today_workout=today_workout,
        weekly_progress=weekly_progress,
        recent_activity=recent_activity,
        trainer=trainer_info,
        plan_progress=plan_progress,
        unread_notes_count=unread_notes_count,
    )
