"""Workout router with exercise, workout, assignment, and session endpoints."""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status

logger = logging.getLogger(__name__)


def _str_to_uuid(value: str | UUID | None) -> UUID | None:
    """Convert string to UUID, handling SQLite TEXT columns."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.redis import RateLimiter
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.service import UserService
from src.domains.workouts.models import Difficulty, MuscleGroup, NoteAuthorRole, NoteContextType, SplitType, TechniqueType, WorkoutGoal
from src.domains.workouts.schemas import (
    ActiveSessionResponse,
    AIGeneratePlanRequest,
    AIGeneratePlanResponse,
    AssignmentAcceptRequest,
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    BatchPlanAssignmentCreate,
    BatchPlanAssignmentResponse,
    BatchPlanAssignmentResult,
    CatalogPlanResponse,
    ExerciseCreate,
    ExerciseFeedbackCreate,
    ExerciseFeedbackRespondRequest,
    ExerciseFeedbackResponse,
    ExerciseResponse,
    ExerciseSuggestionRequest,
    ExerciseSuggestionResponse,
    ExerciseUpdate,
    MarkVersionViewedRequest,
    PlanAssignmentCreate,
    PlanAssignmentResponse,
    PlanAssignmentUpdate,
    PlanCreate,
    PlanListResponse,
    PlanResponse,
    PlanUpdate,
    PlanVersionListResponse,
    PlanVersionResponse,
    PlanVersionUpdateRequest,
    PlanWorkoutInput,
    SessionComplete,
    SessionJoinResponse,
    SessionListResponse,
    SessionMessageCreate,
    SessionMessageResponse,
    SessionResponse,
    SessionSetInput,
    SessionSetResponse,
    SessionStart,
    SessionStatusUpdate,
    SuggestedExercise,
    TrainerAdjustmentCreate,
    TrainerAdjustmentResponse,
    PrescriptionNoteCreate,
    PrescriptionNoteListResponse,
    PrescriptionNoteResponse,
    PrescriptionNoteUpdate,
    WorkoutCreate,
    WorkoutExerciseInput,
    WorkoutExerciseResponse,
    WorkoutListResponse,
    WorkoutResponse,
    WorkoutUpdate,
)
from src.domains.workouts.service import WorkoutService
from src.domains.notifications.push_service import send_push_notification
from src.domains.notifications.router import create_notification
from src.domains.notifications.schemas import NotificationCreate
from src.domains.notifications.models import NotificationType

router = APIRouter()


# Exercise endpoints

@router.get("/exercises", response_model=list[ExerciseResponse])
async def list_exercises(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    muscle_group: Annotated[MuscleGroup | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ExerciseResponse]:
    """List available exercises."""
    workout_service = WorkoutService(db)
    exercises = await workout_service.list_exercises(
        user_id=current_user.id,
        muscle_group=muscle_group,
        search=search,
        limit=limit,
        offset=offset,
    )
    return [ExerciseResponse.model_validate(e) for e in exercises]


@router.get("/exercises/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(
    exercise_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseResponse:
    """Get exercise details."""
    workout_service = WorkoutService(db)
    exercise = await workout_service.get_exercise_by_id(exercise_id)

    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    # Check access
    if not exercise.is_public and exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ExerciseResponse.model_validate(exercise)


@router.post("/exercises", response_model=ExerciseResponse, status_code=status.HTTP_201_CREATED)
async def create_exercise(
    request: ExerciseCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseResponse:
    """Create a custom exercise."""
    workout_service = WorkoutService(db)

    exercise = await workout_service.create_exercise(
        created_by_id=current_user.id,
        name=request.name,
        muscle_group=request.muscle_group,
        description=request.description,
        secondary_muscles=request.secondary_muscles,
        equipment=request.equipment,
        video_url=request.video_url,
        image_url=request.image_url,
        instructions=request.instructions,
    )

    return ExerciseResponse.model_validate(exercise)


@router.put("/exercises/{exercise_id}", response_model=ExerciseResponse)
async def update_exercise(
    exercise_id: UUID,
    request: ExerciseUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseResponse:
    """Update a custom exercise (owner only)."""
    workout_service = WorkoutService(db)
    exercise = await workout_service.get_exercise_by_id(exercise_id)

    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    if exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own exercises",
        )

    updated = await workout_service.update_exercise(
        exercise=exercise,
        name=request.name,
        description=request.description,
        muscle_group=request.muscle_group,
        secondary_muscles=request.secondary_muscles,
        equipment=request.equipment,
        video_url=request.video_url,
        image_url=request.image_url,
        instructions=request.instructions,
    )

    return ExerciseResponse.model_validate(updated)


from pydantic import BaseModel as PydanticBaseModel


class ExerciseMediaUploadResponse(PydanticBaseModel):
    """Response for exercise media upload."""

    url: str
    content_type: str


@router.post("/exercises/{exercise_id}/media")
async def upload_exercise_media(
    exercise_id: UUID,
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    media_type: Annotated[str, Query(description="Type of media: 'image' or 'video'")] = "image",
) -> ExerciseMediaUploadResponse:
    """Upload media (image or video) for a custom exercise.

    Supports JPEG, PNG, WebP, GIF for images.
    Supports MP4, MOV, WebM for videos.
    Maximum size: 5MB for images, 50MB for videos.

    After uploading, use PUT /exercises/{exercise_id} to update the
    exercise's image_url or video_url field with the returned URL.
    """
    from src.core.storage import (
        FileTooLargeError,
        InvalidContentTypeError,
        StorageError,
        storage_service,
    )

    # Verify exercise exists and user owns it
    workout_service = WorkoutService(db)
    exercise = await workout_service.get_exercise_by_id(exercise_id)

    if not exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    # Only owner can upload media for custom exercises
    if exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only upload media for your own exercises",
        )

    # Read file content
    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        # Upload to storage
        url = await storage_service.upload_exercise_media(
            file_content=content,
            content_type=content_type,
            user_id=str(current_user.id),
        )
    except InvalidContentTypeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Images: JPEG, PNG, WebP, GIF. Videos: MP4, MOV, WebM",
        )
    except FileTooLargeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except StorageError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}",
        )

    # Optionally auto-update the exercise with the new URL
    if media_type == "image":
        # Delete old image if exists
        if exercise.image_url:
            await storage_service.delete_file(exercise.image_url)
        await workout_service.update_exercise(
            exercise=exercise,
            image_url=url,
        )
    elif media_type == "video":
        # Delete old video if exists
        if exercise.video_url:
            await storage_service.delete_file(exercise.video_url)
        await workout_service.update_exercise(
            exercise=exercise,
            video_url=url,
        )

    return ExerciseMediaUploadResponse(url=url, content_type=content_type)


@router.post("/exercises/suggest", response_model=ExerciseSuggestionResponse)
async def suggest_exercises(
    request: ExerciseSuggestionRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseSuggestionResponse:
    """
    Suggest exercises based on muscle groups, goal, and difficulty.

    Uses AI (OpenAI) when available for intelligent selection,
    with fallback to rule-based suggestions.
    """
    from src.domains.workouts.ai_service import AIExerciseService

    workout_service = WorkoutService(db)
    ai_service = AIExerciseService()

    # Get all available exercises
    all_exercises = await workout_service.list_exercises(
        user_id=current_user.id,
        limit=500,
        offset=0,
    )

    # Convert to dict format for AI service
    exercises_data = [
        {
            "id": str(ex.id),
            "name": ex.name,
            "muscle_group": ex.muscle_group.value,
            "secondary_muscles": ex.secondary_muscles,
            "equipment": ex.equipment,
            "description": ex.description,
        }
        for ex in all_exercises
    ]

    # Get AI suggestions
    exclude_ids = [str(eid) for eid in request.exclude_exercise_ids] if request.exclude_exercise_ids else None

    # Build context dict if provided
    context_dict = None
    if request.context:
        context_dict = {
            "workout_name": request.context.workout_name,
            "workout_label": request.context.workout_label,
            "plan_name": request.context.plan_name,
            "plan_goal": request.context.plan_goal.value if request.context.plan_goal else None,
            "plan_split_type": request.context.plan_split_type.value if request.context.plan_split_type else None,
            "existing_exercises": request.context.existing_exercises,
            "existing_exercise_count": request.context.existing_exercise_count,
        }

    result = await ai_service.suggest_exercises(
        available_exercises=exercises_data,
        muscle_groups=request.muscle_groups,
        goal=request.goal,
        difficulty=request.difficulty,
        count=request.count,
        exclude_ids=exclude_ids,
        context=context_dict,
        allow_advanced_techniques=request.allow_advanced_techniques,
        allowed_techniques=request.allowed_techniques,
    )

    # Convert to response format
    suggestions = [
        SuggestedExercise(
            exercise_id=s["exercise_id"],
            name=s["name"],
            muscle_group=MuscleGroup(s["muscle_group"]),
            sets=s["sets"],
            reps=s["reps"],
            rest_seconds=s["rest_seconds"],
            order=s["order"],
            reason=s.get("reason"),
            technique_type=TechniqueType(s.get("technique_type", "normal")),
            exercise_group_id=s.get("exercise_group_id"),
            exercise_group_order=s.get("exercise_group_order", 0),
            execution_instructions=s.get("execution_instructions"),
            isometric_seconds=s.get("isometric_seconds"),
        )
        for s in result["suggestions"]
    ]

    return ExerciseSuggestionResponse(
        suggestions=suggestions,
        message=result.get("message", "Bom treino!"),
    )


# Workout endpoints

@router.get("", response_model=list[WorkoutListResponse])
async def list_workouts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> list[WorkoutListResponse]:
    """List workouts for the current user."""
    # Use query param if provided, otherwise fallback to header
    org_id = organization_id
    if org_id is None and x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    workout_service = WorkoutService(db)
    workouts = await workout_service.list_workouts(
        user_id=current_user.id,
        organization_id=org_id,
        templates_only=templates_only,
        search=search,
        limit=limit,
        offset=offset,
    )

    return [
        WorkoutListResponse(
            id=w.id,
            name=w.name,
            difficulty=w.difficulty,
            estimated_duration_min=w.estimated_duration_min,
            is_template=w.is_template,
            exercise_count=len(w.exercises),
        )
        for w in workouts
    ]


# Assignment endpoints

@router.get("/assignments", response_model=list[AssignmentResponse])
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


@router.post("/assignments", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
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


@router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
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


# Session endpoints

@router.get("/sessions", response_model=list[SessionListResponse])
async def list_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SessionListResponse]:
    """List workout sessions for the current user."""
    workout_service = WorkoutService(db)
    sessions = await workout_service.list_user_sessions(
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    return [
        SessionListResponse(
            id=s.id,
            workout_id=s.workout_id,
            workout_name=s.workout.name if s.workout else "",
            started_at=s.started_at,
            completed_at=s.completed_at,
            duration_minutes=s.duration_minutes,
            is_completed=s.is_completed,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    """Get session details."""
    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Allow both session owner (student) and trainer to access
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return SessionResponse.model_validate(session)


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    request: SessionStart,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    """Start a new workout session.

    If is_shared=True, creates a co-training session with status 'waiting'.
    The trainer will be notified and can join the session.
    """
    workout_service = WorkoutService(db)

    # Verify workout exists
    workout = await workout_service.get_workout_by_id(request.workout_id)
    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    session = await workout_service.start_session(
        user_id=current_user.id,
        workout_id=request.workout_id,
        assignment_id=request.assignment_id,
        is_shared=request.is_shared,
    )

    # Get the trainer to notify
    trainer_id = None
    if request.assignment_id:
        from sqlalchemy import select
        from src.domains.workouts.models import PlanAssignment
        assignment_query = select(PlanAssignment).where(
            PlanAssignment.id == request.assignment_id
        )
        assignment_result = await db.execute(assignment_query)
        assignment = assignment_result.scalar_one_or_none()
        if assignment:
            trainer_id = assignment.trainer_id

    # If no trainer from assignment, try to get from user's memberships
    # The trainer is the one who invited the student (invited_by_id)
    if not trainer_id:
        from sqlalchemy import select
        from src.domains.organizations.models import OrganizationMembership
        member_query = select(OrganizationMembership).where(
            OrganizationMembership.user_id == current_user.id,
            OrganizationMembership.role == "student",
            OrganizationMembership.invited_by_id.isnot(None),
        )
        member_result = await db.execute(member_query)
        member = member_result.scalars().first()
        if member:
            trainer_id = member.invited_by_id

    # Send notifications to trainer when student starts a workout
    # Don't send if trainer_id is the same as current_user (same person with both profiles)
    if trainer_id and trainer_id != current_user.id:
        try:
            # Create in-app notification
            await create_notification(
                db=db,
                notification_data=NotificationCreate(
                    user_id=trainer_id,
                    notification_type=NotificationType.WORKOUT_COMPLETED,  # Using WORKOUT_COMPLETED as closest match
                    title="Aluno iniciou treino",
                    body=f"{current_user.name or current_user.email} iniciou o treino '{workout.name}'",
                    icon="dumbbell",
                    action_type="navigate",
                    action_data=f'{{"route": "/cotraining/{session.id}"}}' if request.is_shared else f'{{"route": "/students/{current_user.id}"}}',
                    reference_type="workout_session",
                    reference_id=session.id,
                    sender_id=current_user.id,
                ),
            )

            # Send push notification
            await send_push_notification(
                db=db,
                user_id=trainer_id,
                title="Aluno iniciou treino",
                body=f"{current_user.name or current_user.email} iniciou o treino '{workout.name}'",
                data={
                    "type": "session_started",
                    "session_id": str(session.id),
                    "student_id": str(current_user.id),
                    "student_name": current_user.name or current_user.email,
                    "workout_id": str(workout.id),
                    "workout_name": workout.name,
                    "is_shared": str(request.is_shared).lower(),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to send notifications to trainer {trainer_id}: {e}")

        # If co-training requested, also send SSE notification
        if request.is_shared:
            from src.domains.workouts.realtime import notify_cotraining_request
            await notify_cotraining_request(
                session=session,
                student_name=current_user.name or current_user.email,
                workout_name=workout.name,
                trainer_id=trainer_id,
            )

    return SessionResponse.model_validate(session)


@router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
async def complete_session(
    session_id: UUID,
    request: SessionComplete,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    """Complete a workout session."""
    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if session.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session already completed",
        )

    completed = await workout_service.complete_session(
        session=session,
        notes=request.notes,
        rating=request.rating,
    )

    return SessionResponse.model_validate(completed)


@router.post("/sessions/{session_id}/sets", response_model=SessionSetResponse, status_code=status.HTTP_201_CREATED)
async def add_set(
    session_id: UUID,
    request: SessionSetInput,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionSetResponse:
    """Record a set during a session."""
    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if session.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add sets to a completed session",
        )

    session_set = await workout_service.add_session_set(
        session_id=session_id,
        exercise_id=request.exercise_id,
        set_number=request.set_number,
        reps_completed=request.reps_completed,
        weight_kg=request.weight_kg,
        duration_seconds=request.duration_seconds,
        notes=request.notes,
    )

    return SessionSetResponse.model_validate(session_set)


# Plan endpoints

@router.get("/plans", response_model=list[PlanListResponse])
async def list_plans(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PlanListResponse]:
    """List training plans for the current user."""
    workout_service = WorkoutService(db)
    plans = await workout_service.list_plans(
        user_id=current_user.id,
        organization_id=organization_id,
        templates_only=templates_only,
        search=search,
        limit=limit,
        offset=offset,
    )

    return [
        PlanListResponse(
            id=p.id,
            name=p.name,
            goal=p.goal,
            difficulty=p.difficulty,
            split_type=p.split_type,
            duration_weeks=p.duration_weeks,
            is_template=p.is_template,
            is_public=p.is_public,
            workout_count=len(p.plan_workouts),
            created_by_id=p.created_by_id,
            source_template_id=_str_to_uuid(p.source_template_id),
            created_at=p.created_at,
        )
        for p in plans
    ]


@router.get("/plans/catalog", response_model=list[CatalogPlanResponse])
async def get_catalog_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    goal: Annotated[WorkoutGoal | None, Query()] = None,
    difficulty: Annotated[Difficulty | None, Query()] = None,
    split_type: Annotated[SplitType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CatalogPlanResponse]:
    """Get public catalog templates (excluding user's own)."""
    workout_service = WorkoutService(db)
    templates = await workout_service.get_catalog_templates(
        exclude_user_id=current_user.id,
        search=search,
        goal=goal,
        difficulty=difficulty,
        split_type=split_type,
        limit=limit,
        offset=offset,
    )
    return [CatalogPlanResponse(**t) for t in templates]


@router.post("/plans/generate-ai", response_model=AIGeneratePlanResponse)
async def generate_plan_with_ai(
    request: AIGeneratePlanRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIGeneratePlanResponse:
    """Generate a training plan using AI (OpenAI) based on questionnaire answers."""
    workout_service = WorkoutService(db)

    # Get available exercises for AI to use
    all_exercises = await workout_service.list_exercises(user_id=current_user.id, limit=500)
    exercise_dicts = [
        {
            "id": str(ex.id),
            "name": ex.name,
            "muscle_group": ex.muscle_group.value if ex.muscle_group else "other",
        }
        for ex in all_exercises
    ]

    # Try AI-based generation first (100% AI with OpenAI)
    from src.domains.workouts.ai_service import AIExerciseService
    ai_service = AIExerciseService()

    ai_result = await ai_service.generate_full_plan(
        available_exercises=exercise_dicts,
        goal=request.goal,
        difficulty=request.difficulty,
        days_per_week=request.days_per_week,
        minutes_per_session=request.minutes_per_session,
        equipment=request.equipment,
        injuries=request.injuries,
        preferences=request.preferences,
        duration_weeks=request.duration_weeks,
    )

    if ai_result:
        # AI generation succeeded - return the result
        return AIGeneratePlanResponse(**ai_result)

    # Fallback to rule-based generation if AI is not available
    result = await workout_service.generate_plan_with_ai(
        user_id=current_user.id,
        goal=request.goal,
        difficulty=request.difficulty,
        days_per_week=request.days_per_week,
        minutes_per_session=request.minutes_per_session,
        equipment=request.equipment,
        injuries=request.injuries,
        preferences=request.preferences,
        duration_weeks=request.duration_weeks,
    )
    return AIGeneratePlanResponse(**result)

# Plan assignment endpoints

@router.get("/plans/assignments", response_model=list[PlanAssignmentResponse])
async def list_plan_assignments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    active_only: Annotated[bool, Query()] = True,
    student_id: Annotated[UUID | None, Query()] = None,
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> list[PlanAssignmentResponse]:
    """List plan assignments (as student or trainer).

    If as_trainer=True and student_id is provided, returns assignments for that specific student.
    If as_trainer=True and student_id is None, returns all assignments where current user is trainer.
    If as_trainer=False, returns assignments for current user as student.

    When X-Organization-ID header is provided, filters assignments by organization context.
    This is important for students with multiple trainers.
    """
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Parse organization_id from header if provided
    organization_id = UUID(x_organization_id) if x_organization_id else None

    if as_trainer:
        if student_id:
            # Filter by specific student
            assignments = await workout_service.list_trainer_plan_assignments(
                trainer_id=current_user.id,
                student_id=student_id,
                active_only=active_only,
                organization_id=organization_id,
            )
        else:
            # All trainer's assignments
            assignments = await workout_service.list_trainer_plan_assignments(
                trainer_id=current_user.id,
                active_only=active_only,
                organization_id=organization_id,
            )
    else:
        assignments = await workout_service.list_student_plan_assignments(
            student_id=current_user.id,
            active_only=active_only,
            prescribed_only=False,  # Allow trainers to follow their own plans
            organization_id=organization_id,
        )

    result = []
    for a in assignments:
        student = await user_service.get_user_by_id(a.student_id)

        # Build full plan response if plan exists
        plan_response = None
        if a.plan:
            plan_response = PlanResponse(
                id=a.plan.id,
                name=a.plan.name,
                description=a.plan.description,
                goal=a.plan.goal,
                difficulty=a.plan.difficulty,
                split_type=a.plan.split_type,
                duration_weeks=a.plan.duration_weeks,
                target_workout_minutes=a.plan.target_workout_minutes,
                include_diet=a.plan.include_diet,
                diet_type=a.plan.diet_type,
                daily_calories=a.plan.daily_calories,
                protein_grams=a.plan.protein_grams,
                carbs_grams=a.plan.carbs_grams,
                fat_grams=a.plan.fat_grams,
                meals_per_day=a.plan.meals_per_day,
                diet_notes=a.plan.diet_notes,
                is_template=a.plan.is_template,
                is_public=a.plan.is_public,
                created_by_id=a.plan.created_by_id,
                organization_id=a.plan.organization_id,
                source_template_id=a.plan.source_template_id,
                created_at=a.plan.created_at,
                plan_workouts=[],  # Will be populated if plan_workouts loaded
            )
            # Include plan workouts if loaded
            if hasattr(a.plan, 'plan_workouts') and a.plan.plan_workouts:
                from src.domains.workouts.schemas import PlanWorkoutResponse, WorkoutResponse
                plan_response.plan_workouts = [
                    PlanWorkoutResponse(
                        id=pw.id,
                        workout_id=pw.workout_id,
                        order=pw.order,
                        label=pw.label,
                        day_of_week=pw.day_of_week,
                        workout=WorkoutResponse.model_validate(pw.workout) if pw.workout else None,
                    )
                    for pw in a.plan.plan_workouts
                    # Don't filter - include all plan_workouts even if workout is None
                ]

        # Get version info
        version = getattr(a, 'version', 1)
        last_version_viewed = getattr(a, 'last_version_viewed', None)

        result.append(
            PlanAssignmentResponse(
                id=a.id,
                plan_id=a.plan_id,
                student_id=a.student_id,
                trainer_id=a.trainer_id,
                organization_id=a.organization_id,
                start_date=a.start_date,
                end_date=a.end_date,
                is_active=a.is_active,
                notes=a.notes,
                status=a.status,
                accepted_at=a.accepted_at,
                acknowledged_at=a.acknowledged_at,
                declined_reason=a.declined_reason,
                created_at=a.created_at,
                plan_name=a.plan.name if a.plan else "",
                student_name=student.name if student else "",
                plan_duration_weeks=a.plan.duration_weeks if a.plan else None,
                plan=plan_response,
                plan_snapshot=a.plan_snapshot,
                version=version,
                last_version_viewed=last_version_viewed,
                has_unviewed_updates=(
                    last_version_viewed is None or version > last_version_viewed
                ),
            )
        )

    return result


@router.post("/plans/assignments", response_model=PlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_plan_assignment(
    request: PlanAssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> PlanAssignmentResponse:
    """Assign a plan to a student."""
    # Rate limiting: max 20 plan assignments per hour per trainer
    is_allowed, current_count = await RateLimiter.check_rate_limit(
        identifier=str(current_user.id),
        action="plan_assignment",
        max_requests=20,
        window_seconds=3600,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite de atribuições de planos excedido. Tente novamente mais tarde. ({current_count}/20 por hora)",
        )

    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Verify plan exists
    plan = await workout_service.get_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Verify student exists
    student = await user_service.get_user_by_id(request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    # Check if same plan is already assigned and active for this student
    # Use prescribed_only=False to check all assignments (including self-assigned)
    existing_assignments = await workout_service.list_student_plan_assignments(
        student_id=request.student_id,
        active_only=True,
        prescribed_only=False,
    )
    for existing in existing_assignments:
        if existing.plan_id == request.plan_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este plano já está atribuído a este aluno",
            )

    # Use organization_id from request body, or fall back to header
    org_id = request.organization_id
    if org_id is None and x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass  # Invalid UUID, ignore

    assignment = await workout_service.create_plan_assignment(
        plan_id=request.plan_id,
        student_id=request.student_id,
        trainer_id=current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        notes=request.notes,
        organization_id=org_id,
    )

    # Send notifications to student about the new plan assignment
    try:
        # Create in-app notification
        await create_notification(
            db=db,
            notification_data=NotificationCreate(
                user_id=request.student_id,
                notification_type=NotificationType.PLAN_ASSIGNED,
                title="Novo plano de treino",
                body=f"{current_user.name} atribuiu o plano '{plan.name}' para você",
                icon="clipboard-list",
                action_type="navigate",
                action_data=f'{{"route": "/plans/{assignment.plan_id}"}}',
                reference_type="plan_assignment",
                reference_id=assignment.id,
                organization_id=org_id,
                sender_id=current_user.id,
            ),
        )

        # Send push notification
        await send_push_notification(
            db=db,
            user_id=request.student_id,
            title="Novo plano de treino",
            body=f"{current_user.name} atribuiu o plano '{plan.name}' para você",
            data={
                "type": "plan_assigned",
                "assignment_id": str(assignment.id),
                "plan_id": str(assignment.plan_id),
                "plan_name": plan.name,
                "trainer_id": str(current_user.id),
                "trainer_name": current_user.name or current_user.email,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to send notifications to student {request.student_id}: {e}")

    return PlanAssignmentResponse(
        id=assignment.id,
        plan_id=assignment.plan_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        status=assignment.status,
        accepted_at=assignment.accepted_at,
        declined_reason=assignment.declined_reason,
        created_at=assignment.created_at,
        plan_name=plan.name,
        student_name=student.name,
        plan_duration_weeks=plan.duration_weeks,
        plan_snapshot=assignment.plan_snapshot,
        version=getattr(assignment, 'version', 1),
        last_version_viewed=getattr(assignment, 'last_version_viewed', None),
        has_unviewed_updates=True,  # New assignment always has unviewed updates
    )


@router.post("/plans/assignments/batch", response_model=BatchPlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_batch_plan_assignment(
    request: BatchPlanAssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> BatchPlanAssignmentResponse:
    """Assign a plan to multiple students at once.

    This endpoint allows trainers to prescribe the same plan to multiple students
    in a single request, sending notifications to each student.

    Returns a summary of successful and failed assignments.
    """
    # Rate limiting: max 5 batch assignments per hour per trainer
    is_allowed, current_count = await RateLimiter.check_rate_limit(
        identifier=str(current_user.id),
        action="batch_plan_assignment",
        max_requests=5,
        window_seconds=3600,
    )
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Limite de prescrições em massa excedido. Tente novamente mais tarde. ({current_count}/5 por hora)",
        )

    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Verify plan exists
    plan = await workout_service.get_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Use organization_id from request body, or fall back to header
    org_id = request.organization_id
    if org_id is None and x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    results: list[BatchPlanAssignmentResult] = []
    successful = 0
    failed = 0

    for student_id in request.student_ids:
        try:
            # Verify student exists
            student = await user_service.get_user_by_id(student_id)
            if not student:
                results.append(BatchPlanAssignmentResult(
                    student_id=student_id,
                    student_name="Unknown",
                    success=False,
                    error="Aluno não encontrado",
                ))
                failed += 1
                continue

            # Check if plan is already assigned to this student
            existing_assignments = await workout_service.list_student_plan_assignments(
                student_id=student_id,
                active_only=True,
                prescribed_only=False,
            )
            already_assigned = any(a.plan_id == request.plan_id for a in existing_assignments)
            if already_assigned:
                results.append(BatchPlanAssignmentResult(
                    student_id=student_id,
                    student_name=student.name,
                    success=False,
                    error="Este plano já está atribuído a este aluno",
                ))
                failed += 1
                continue

            # Create assignment
            assignment = await workout_service.create_plan_assignment(
                plan_id=request.plan_id,
                student_id=student_id,
                trainer_id=current_user.id,
                start_date=request.start_date,
                end_date=request.end_date,
                notes=request.notes,
                organization_id=org_id,
            )

            # Send notifications
            try:
                await create_notification(
                    db=db,
                    notification_data=NotificationCreate(
                        user_id=student_id,
                        notification_type=NotificationType.PLAN_ASSIGNED,
                        title="Novo plano de treino",
                        body=f"{current_user.name} atribuiu o plano '{plan.name}' para você",
                        icon="clipboard-list",
                        action_type="navigate",
                        action_data=f'{{"route": "/plans/{assignment.plan_id}"}}',
                        reference_type="plan_assignment",
                        reference_id=assignment.id,
                        organization_id=org_id,
                        sender_id=current_user.id,
                    ),
                )

                await send_push_notification(
                    db=db,
                    user_id=student_id,
                    title="Novo plano de treino",
                    body=f"{current_user.name} atribuiu o plano '{plan.name}' para você",
                    data={
                        "type": "plan_assigned",
                        "assignment_id": str(assignment.id),
                        "plan_id": str(assignment.plan_id),
                        "plan_name": plan.name,
                        "trainer_id": str(current_user.id),
                        "trainer_name": current_user.name or current_user.email,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to send notifications to student {student_id}: {e}")

            results.append(BatchPlanAssignmentResult(
                student_id=student_id,
                student_name=student.name,
                success=True,
                assignment_id=assignment.id,
            ))
            successful += 1

        except Exception as e:
            logger.error(f"Error assigning plan to student {student_id}: {e}")
            student = await user_service.get_user_by_id(student_id)
            results.append(BatchPlanAssignmentResult(
                student_id=student_id,
                student_name=student.name if student else "Unknown",
                success=False,
                error=str(e),
            ))
            failed += 1

    return BatchPlanAssignmentResponse(
        plan_id=request.plan_id,
        plan_name=plan.name,
        total_students=len(request.student_ids),
        successful=successful,
        failed=failed,
        results=results,
    )


@router.post("/plans/assignments/{assignment_id}/respond", response_model=PlanAssignmentResponse)
async def respond_to_plan_assignment(
    assignment_id: UUID,
    request: AssignmentAcceptRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Accept or decline a plan assignment (student only)."""
    from datetime import datetime, timezone
    from src.domains.workouts.models import AssignmentStatus

    workout_service = WorkoutService(db)
    user_service = UserService(db)

    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Only the assigned student can respond
    if assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o aluno pode aceitar ou recusar esta atribuição",
        )

    # Can only respond to pending assignments
    if assignment.status != AssignmentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Esta atribuição já foi {assignment.status.value}",
        )

    # Update assignment status
    if request.accept:
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = datetime.now(timezone.utc)
        assignment.declined_reason = None
        # Also acknowledge if requested (avoids double notification)
        if request.acknowledge:
            assignment.acknowledged_at = datetime.now(timezone.utc)
    else:
        assignment.status = AssignmentStatus.DECLINED
        assignment.declined_reason = request.declined_reason
        assignment.is_active = False

    await db.commit()
    await db.refresh(assignment)

    # Get student and plan info for response
    student = await user_service.get_user_by_id(assignment.student_id)
    plan = await workout_service.get_plan_by_id(assignment.plan_id)

    # Send notification to trainer if acknowledging
    # Don't send if trainer_id is the same as current_user (same person with both profiles)
    if request.accept and request.acknowledge and assignment.trainer_id and assignment.trainer_id != current_user.id:
        try:
            # Create in-app notification
            await create_notification(
                db=db,
                notification_data=NotificationCreate(
                    user_id=assignment.trainer_id,
                    notification_type=NotificationType.STUDENT_PROGRESS,
                    title="Plano aceito",
                    body=f"{current_user.name or current_user.email} aceitou e visualizou o plano '{plan.name if plan else 'atribuído'}'",
                    icon="check-circle",
                    action_type="navigate",
                    action_data=f'{{"route": "/students/{assignment.student_id}"}}',
                    reference_type="plan_assignment",
                    reference_id=assignment.id,
                    organization_id=assignment.organization_id,
                    sender_id=current_user.id,
                ),
            )

            # Send push notification
            await send_push_notification(
                db=db,
                user_id=assignment.trainer_id,
                title="Plano aceito",
                body=f"{current_user.name or current_user.email} aceitou e visualizou o plano '{plan.name if plan else 'atribuído'}'",
                data={
                    "type": "plan_accepted_and_acknowledged",
                    "assignment_id": str(assignment.id),
                    "plan_id": str(assignment.plan_id),
                    "student_id": str(assignment.student_id),
                    "student_name": current_user.name or current_user.email,
                    "plan_name": plan.name if plan else "",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to send notification to trainer {assignment.trainer_id}: {e}")

    version = getattr(assignment, 'version', 1)
    last_version_viewed = getattr(assignment, 'last_version_viewed', None)

    return PlanAssignmentResponse(
        id=assignment.id,
        plan_id=assignment.plan_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        status=assignment.status,
        accepted_at=assignment.accepted_at,
        declined_reason=assignment.declined_reason,
        created_at=assignment.created_at,
        plan_name=plan.name if plan else "",
        student_name=student.name if student else "",
        plan_duration_weeks=plan.duration_weeks if plan else None,
        plan_snapshot=assignment.plan_snapshot,
        version=version,
        last_version_viewed=last_version_viewed,
        has_unviewed_updates=(
            last_version_viewed is None or version > last_version_viewed
        ),
    )


@router.post("/plans/assignments/{assignment_id}/acknowledge", response_model=PlanAssignmentResponse)
async def acknowledge_plan_assignment(
    assignment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Mark a plan assignment as acknowledged/viewed by the student."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Only the assigned student can acknowledge
    if assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o aluno pode marcar esta atribuição como visualizada",
        )

    # Acknowledge the assignment
    acknowledged = await workout_service.acknowledge_plan_assignment(assignment)

    # Get student and plan info for response
    student = await user_service.get_user_by_id(acknowledged.student_id)
    plan = await workout_service.get_plan_by_id(acknowledged.plan_id)

    # Send notification to trainer that student viewed the plan
    # Don't send if trainer_id is the same as current_user (same person with both profiles)
    if acknowledged.trainer_id and acknowledged.trainer_id != current_user.id:
        try:
            # Create in-app notification
            await create_notification(
                db=db,
                notification_data=NotificationCreate(
                    user_id=acknowledged.trainer_id,
                    notification_type=NotificationType.STUDENT_PROGRESS,
                    title="Plano visualizado",
                    body=f"{current_user.name or current_user.email} visualizou o plano '{plan.name if plan else 'atribuído'}'",
                    icon="eye",
                    action_type="navigate",
                    action_data=f'{{"route": "/students/{acknowledged.student_id}"}}',
                    reference_type="plan_assignment",
                    reference_id=acknowledged.id,
                    organization_id=acknowledged.organization_id,
                    sender_id=current_user.id,
                ),
            )

            # Send push notification
            await send_push_notification(
                db=db,
                user_id=acknowledged.trainer_id,
                title="Plano visualizado",
                body=f"{current_user.name or current_user.email} visualizou o plano '{plan.name if plan else 'atribuído'}'",
                data={
                    "type": "plan_acknowledged",
                    "assignment_id": str(acknowledged.id),
                    "plan_id": str(acknowledged.plan_id),
                    "student_id": str(acknowledged.student_id),
                    "student_name": current_user.name or current_user.email,
                    "plan_name": plan.name if plan else "",
                },
            )
        except Exception as e:
            logger.warning(f"Failed to send notification to trainer {acknowledged.trainer_id}: {e}")

    version = getattr(acknowledged, 'version', 1)
    last_version_viewed = getattr(acknowledged, 'last_version_viewed', None)

    return PlanAssignmentResponse(
        id=acknowledged.id,
        plan_id=acknowledged.plan_id,
        student_id=acknowledged.student_id,
        trainer_id=acknowledged.trainer_id,
        organization_id=acknowledged.organization_id,
        start_date=acknowledged.start_date,
        end_date=acknowledged.end_date,
        is_active=acknowledged.is_active,
        notes=acknowledged.notes,
        status=acknowledged.status,
        accepted_at=acknowledged.accepted_at,
        acknowledged_at=acknowledged.acknowledged_at,
        declined_reason=acknowledged.declined_reason,
        created_at=acknowledged.created_at,
        plan_name=plan.name if plan else "",
        student_name=student.name if student else "",
        plan_duration_weeks=plan.duration_weeks if plan else None,
        plan_snapshot=acknowledged.plan_snapshot,
        version=version,
        last_version_viewed=last_version_viewed,
        has_unviewed_updates=(
            last_version_viewed is None or version > last_version_viewed
        ),
    )


@router.put("/plans/assignments/{assignment_id}", response_model=PlanAssignmentResponse)
async def update_plan_assignment(
    assignment_id: UUID,
    request: PlanAssignmentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Update a plan assignment (trainer only)."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)
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

    updated = await workout_service.update_plan_assignment(
        assignment=assignment,
        start_date=request.start_date,
        end_date=request.end_date,
        is_active=request.is_active,
        notes=request.notes,
    )

    student = await user_service.get_user_by_id(updated.student_id)

    plan = await workout_service.get_plan_by_id(updated.plan_id)

    version = getattr(updated, 'version', 1)
    last_version_viewed = getattr(updated, 'last_version_viewed', None)

    return PlanAssignmentResponse(
        id=updated.id,
        plan_id=updated.plan_id,
        student_id=updated.student_id,
        trainer_id=updated.trainer_id,
        organization_id=updated.organization_id,
        start_date=updated.start_date,
        end_date=updated.end_date,
        is_active=updated.is_active,
        notes=updated.notes,
        status=updated.status,
        accepted_at=updated.accepted_at,
        declined_reason=updated.declined_reason,
        created_at=updated.created_at,
        plan_name=updated.plan.name if updated.plan else "",
        student_name=student.name if student else "",
        plan_duration_weeks=plan.duration_weeks if plan else None,
        plan_snapshot=updated.plan_snapshot,
        version=version,
        last_version_viewed=last_version_viewed,
        has_unviewed_updates=(
            last_version_viewed is None or version > last_version_viewed
        ),
    )


@router.delete("/plans/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan_assignment(
    assignment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete/cancel a plan assignment (trainer only, only if pending)."""
    from src.domains.workouts.models import AssignmentStatus

    workout_service = WorkoutService(db)

    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    if assignment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode cancelar suas próprias atribuições",
        )

    # Only allow deletion of pending assignments
    if assignment.status != AssignmentStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Apenas atribuições pendentes podem ser canceladas",
        )

    await db.delete(assignment)
    await db.commit()


# Plan Version History endpoints

@router.get("/plans/assignments/{assignment_id}/versions", response_model=PlanVersionListResponse)
async def list_plan_versions(
    assignment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionListResponse:
    """Get version history for a plan assignment.

    Both trainer and student can view versions for assignments they're involved in.
    """
    from sqlalchemy import select
    from src.domains.workouts.models import PlanAssignment, PlanVersion

    # Get assignment
    workout_service = WorkoutService(db)
    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Check access (trainer or student)
    if assignment.trainer_id != current_user.id and assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a esta atribuição",
        )

    # Get versions
    query = (
        select(PlanVersion)
        .where(PlanVersion.assignment_id == assignment_id)
        .order_by(PlanVersion.version.desc())
    )
    result = await db.execute(query)
    versions = result.scalars().all()

    # Build response with changed_by names
    version_responses = []
    for v in versions:
        changed_by_name = None
        if v.changed_by_id:
            user_service = UserService(db)
            changed_by = await user_service.get_user_by_id(v.changed_by_id)
            if changed_by:
                changed_by_name = changed_by.name

        version_responses.append(PlanVersionResponse(
            id=v.id,
            assignment_id=v.assignment_id,
            version=v.version,
            snapshot=v.snapshot,
            changed_at=v.changed_at,
            changed_by_id=v.changed_by_id,
            changed_by_name=changed_by_name,
            change_description=v.change_description,
        ))

    return PlanVersionListResponse(
        assignment_id=assignment_id,
        current_version=assignment.version,
        versions=version_responses,
        total=len(version_responses),
    )


@router.get("/plans/assignments/{assignment_id}/versions/{version}", response_model=PlanVersionResponse)
async def get_plan_version(
    assignment_id: UUID,
    version: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionResponse:
    """Get a specific version of a plan assignment."""
    from sqlalchemy import select
    from src.domains.workouts.models import PlanAssignment, PlanVersion

    # Get assignment
    workout_service = WorkoutService(db)
    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Check access
    if assignment.trainer_id != current_user.id and assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a esta atribuição",
        )

    # Get specific version
    query = (
        select(PlanVersion)
        .where(
            PlanVersion.assignment_id == assignment_id,
            PlanVersion.version == version,
        )
    )
    result = await db.execute(query)
    plan_version = result.scalar_one_or_none()

    if not plan_version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Versão {version} não encontrada",
        )

    # Get changed_by name
    changed_by_name = None
    if plan_version.changed_by_id:
        user_service = UserService(db)
        changed_by = await user_service.get_user_by_id(plan_version.changed_by_id)
        if changed_by:
            changed_by_name = changed_by.name

    return PlanVersionResponse(
        id=plan_version.id,
        assignment_id=plan_version.assignment_id,
        version=plan_version.version,
        snapshot=plan_version.snapshot,
        changed_at=plan_version.changed_at,
        changed_by_id=plan_version.changed_by_id,
        changed_by_name=changed_by_name,
        change_description=plan_version.change_description,
    )


@router.post("/plans/assignments/{assignment_id}/versions", response_model=PlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def update_plan_assignment_with_version(
    assignment_id: UUID,
    request: PlanVersionUpdateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Update a plan assignment's snapshot and create a new version (trainer only).

    This saves the current snapshot as a version before updating with the new data.
    The student will be notified of the update.
    """
    from datetime import datetime, timezone
    from src.domains.workouts.models import PlanAssignment, PlanVersion

    # Get assignment
    workout_service = WorkoutService(db)
    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Only trainer can update
    if assignment.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o personal pode atualizar a prescrição",
        )

    # Save current version before updating
    if assignment.plan_snapshot:
        version_record = PlanVersion(
            assignment_id=assignment_id,
            version=assignment.version,
            snapshot=assignment.plan_snapshot,
            changed_at=datetime.now(timezone.utc),
            changed_by_id=current_user.id,
            change_description=request.change_description or f"Versão {assignment.version}",
        )
        db.add(version_record)

    # Update assignment with new snapshot
    assignment.plan_snapshot = request.plan_snapshot
    assignment.version += 1
    assignment.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(assignment)

    # Get related data for response
    plan = await workout_service.get_plan_by_id(assignment.plan_id)
    user_service = UserService(db)
    student = await user_service.get_user_by_id(assignment.student_id)

    # Notify student of update
    try:
        await create_notification(
            db=db,
            notification_data=NotificationCreate(
                user_id=assignment.student_id,
                type=NotificationType.PLAN_UPDATED,
                title="Plano atualizado",
                message=f"Seu plano de treino foi atualizado por {current_user.name}",
                data={"assignment_id": str(assignment_id), "version": assignment.version},
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to create notification for plan update: {e}")

    return PlanAssignmentResponse(
        id=assignment.id,
        plan_id=assignment.plan_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        status=assignment.status,
        accepted_at=assignment.accepted_at,
        declined_reason=assignment.declined_reason,
        acknowledged_at=assignment.acknowledged_at,
        created_at=assignment.created_at,
        plan_name=plan.name if plan else "",
        student_name=student.name if student else "",
        plan_duration_weeks=plan.duration_weeks if plan else None,
        plan_snapshot=assignment.plan_snapshot,
        version=assignment.version,
        last_version_viewed=assignment.last_version_viewed,
        has_unviewed_updates=(
            assignment.last_version_viewed is None
            or assignment.version > assignment.last_version_viewed
        ),
    )


@router.post("/plans/assignments/{assignment_id}/versions/viewed", response_model=PlanAssignmentResponse)
async def mark_version_viewed(
    assignment_id: UUID,
    request: MarkVersionViewedRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Mark a plan version as viewed by the student.

    If no version is specified, marks the current version as viewed.
    """
    from datetime import datetime, timezone

    # Get assignment
    workout_service = WorkoutService(db)
    assignment = await workout_service.get_plan_assignment_by_id(assignment_id)

    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Atribuição não encontrada",
        )

    # Only student can mark as viewed
    if assignment.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas o aluno pode marcar como visualizado",
        )

    # Mark version as viewed
    version_to_mark = request.version if request.version is not None else assignment.version
    assignment.last_version_viewed = version_to_mark
    assignment.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(assignment)

    # Get related data for response
    plan = await workout_service.get_plan_by_id(assignment.plan_id)
    user_service = UserService(db)
    student = await user_service.get_user_by_id(assignment.student_id)

    return PlanAssignmentResponse(
        id=assignment.id,
        plan_id=assignment.plan_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        status=assignment.status,
        accepted_at=assignment.accepted_at,
        declined_reason=assignment.declined_reason,
        acknowledged_at=assignment.acknowledged_at,
        created_at=assignment.created_at,
        plan_name=plan.name if plan else "",
        student_name=student.name if student else "",
        plan_duration_weeks=plan.duration_weeks if plan else None,
        plan_snapshot=assignment.plan_snapshot,
        version=assignment.version,
        last_version_viewed=assignment.last_version_viewed,
        has_unviewed_updates=(
            assignment.last_version_viewed is None
            or assignment.version > assignment.last_version_viewed
        ),
    )


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Get plan details with workouts."""
    from sqlalchemy import select
    from src.domains.workouts.models import AssignmentStatus, PlanAssignment

    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Check access
    has_access = (
        plan.is_public
        or plan.created_by_id == current_user.id
        or plan.organization_id is not None
    )

    # If no direct access, check if user has a plan assignment (pending or accepted)
    if not has_access:
        assignment_query = (
            select(PlanAssignment)
            .where(
                PlanAssignment.plan_id == plan_id,
                PlanAssignment.student_id == current_user.id,
                PlanAssignment.is_active == True,
                # Allow both pending and accepted - student should see plan to accept/decline
                PlanAssignment.status.in_([AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]),
            )
            .limit(1)
        )
        result = await db.execute(assignment_query)
        has_assignment = result.scalar_one_or_none() is not None
        has_access = has_assignment

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return PlanResponse.model_validate(plan)


@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: PlanCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Create a new training plan."""
    workout_service = WorkoutService(db)

    plan = await workout_service.create_plan(
        created_by_id=current_user.id,
        name=request.name,
        description=request.description,
        goal=request.goal,
        difficulty=request.difficulty,
        split_type=request.split_type,
        duration_weeks=request.duration_weeks,
        target_workout_minutes=request.target_workout_minutes,
        is_template=request.is_template,
        is_public=request.is_public,
        organization_id=request.organization_id,
    )

    # Add workouts if provided
    if request.workouts:
        for pw in request.workouts:
            if pw.workout_id:
                # Use existing workout
                await workout_service.add_workout_to_plan(
                    plan_id=plan.id,
                    workout_id=pw.workout_id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )
            elif pw.workout_name:
                # Create new workout inline
                new_workout = await workout_service.create_workout(
                    created_by_id=current_user.id,
                    name=pw.workout_name,
                    difficulty=request.difficulty,
                    target_muscles=pw.muscle_groups,
                )
                # Add exercises to new workout if provided
                if pw.workout_exercises:
                    for ex in pw.workout_exercises:
                        await workout_service.add_exercise_to_workout(
                            workout_id=new_workout.id,
                            exercise_id=ex.exercise_id,
                            order=ex.order,
                            sets=ex.sets,
                            reps=ex.reps,
                            rest_seconds=ex.rest_seconds,
                            notes=ex.notes,
                            superset_with=ex.superset_with,
                            # Advanced technique fields
                            execution_instructions=ex.execution_instructions,
                            group_instructions=ex.group_instructions,
                            isometric_seconds=ex.isometric_seconds,
                            technique_type=ex.technique_type,
                            exercise_group_id=ex.exercise_group_id,
                            exercise_group_order=ex.exercise_group_order,
                            # Structured technique parameters
                            drop_count=ex.drop_count,
                            rest_between_drops=ex.rest_between_drops,
                            pause_duration=ex.pause_duration,
                            mini_set_count=ex.mini_set_count,
                            # Exercise mode (strength vs aerobic)
                            exercise_mode=ex.exercise_mode,
                            # Aerobic exercise fields
                            duration_minutes=ex.duration_minutes,
                            intensity=ex.intensity,
                            work_seconds=ex.work_seconds,
                            interval_rest_seconds=ex.interval_rest_seconds,
                            rounds=ex.rounds,
                            distance_km=ex.distance_km,
                            target_pace_min_per_km=ex.target_pace_min_per_km,
                        )
                # Add to plan
                await workout_service.add_workout_to_plan(
                    plan_id=plan.id,
                    workout_id=new_workout.id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )

        # Refresh to get workouts
        plan = await workout_service.get_plan_by_id(plan.id)

    return PlanResponse.model_validate(plan)


@router.put("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: UUID,
    request: PlanUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Update a plan (owner only)."""
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own plans",
        )

    updated = await workout_service.update_plan(
        plan=plan,
        name=request.name,
        description=request.description,
        goal=request.goal,
        difficulty=request.difficulty,
        split_type=request.split_type,
        duration_weeks=request.duration_weeks,
        clear_duration_weeks=request.clear_duration_weeks,
        target_workout_minutes=request.target_workout_minutes,
        is_template=request.is_template,
        is_public=request.is_public,
        # Diet fields
        include_diet=request.include_diet,
        diet_type=request.diet_type,
        daily_calories=request.daily_calories,
        protein_grams=request.protein_grams,
        carbs_grams=request.carbs_grams,
        fat_grams=request.fat_grams,
        meals_per_day=request.meals_per_day,
        diet_notes=request.diet_notes,
    )

    # Update workouts if provided
    if request.workouts is not None:
        logger.info(f"Updating plan {plan_id} workouts: {len(request.workouts)} workouts provided")
        # Get existing plan_workouts and their workout IDs
        existing_workout_ids = [pw.workout_id for pw in plan.plan_workouts]
        logger.info(f"Deleting {len(existing_workout_ids)} existing workouts")

        # Delete all existing plan_workouts
        for pw in list(plan.plan_workouts):
            await workout_service.remove_workout_from_plan(pw.id)

        # Delete the old workouts (they were created specifically for this plan)
        for workout_id in existing_workout_ids:
            workout = await workout_service.get_workout_by_id(workout_id)
            if workout:
                await workout_service.delete_workout(workout)

        # Create new workouts based on the provided data
        for pw in request.workouts:
            logger.info(f"Processing workout: label={pw.label}, workout_id={pw.workout_id}, workout_name={pw.workout_name}, exercises={len(pw.workout_exercises or [])}")
            if pw.workout_id:
                # Use existing workout
                await workout_service.add_workout_to_plan(
                    plan_id=plan_id,
                    workout_id=pw.workout_id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )
            elif pw.workout_name:
                # Create new workout inline
                new_workout = await workout_service.create_workout(
                    created_by_id=current_user.id,
                    name=pw.workout_name,
                    difficulty=request.difficulty or plan.difficulty,
                    target_muscles=pw.muscle_groups,
                )
                logger.info(f"Created workout {new_workout.id} with name {new_workout.name}")
                # Add exercises to new workout if provided
                if pw.workout_exercises:
                    logger.info(f"Adding {len(pw.workout_exercises)} exercises to workout {new_workout.id}")
                    for ex in pw.workout_exercises:
                        await workout_service.add_exercise_to_workout(
                            workout_id=new_workout.id,
                            exercise_id=ex.exercise_id,
                            order=ex.order,
                            sets=ex.sets,
                            reps=ex.reps,
                            rest_seconds=ex.rest_seconds,
                            notes=ex.notes,
                            superset_with=ex.superset_with,
                            # Advanced technique fields
                            execution_instructions=ex.execution_instructions,
                            group_instructions=ex.group_instructions,
                            isometric_seconds=ex.isometric_seconds,
                            technique_type=ex.technique_type,
                            exercise_group_id=ex.exercise_group_id,
                            exercise_group_order=ex.exercise_group_order,
                            # Structured technique parameters
                            drop_count=ex.drop_count,
                            rest_between_drops=ex.rest_between_drops,
                            pause_duration=ex.pause_duration,
                            mini_set_count=ex.mini_set_count,
                            # Exercise mode (strength vs aerobic)
                            exercise_mode=ex.exercise_mode,
                            # Aerobic exercise fields
                            duration_minutes=ex.duration_minutes,
                            intensity=ex.intensity,
                            work_seconds=ex.work_seconds,
                            interval_rest_seconds=ex.interval_rest_seconds,
                            rounds=ex.rounds,
                            distance_km=ex.distance_km,
                            target_pace_min_per_km=ex.target_pace_min_per_km,
                        )
                # Add to plan
                await workout_service.add_workout_to_plan(
                    plan_id=plan_id,
                    workout_id=new_workout.id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )

        # Refresh to get updated workouts
        updated = await workout_service.get_plan_by_id(plan_id)

    return PlanResponse.model_validate(updated)


@router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a plan (owner only)."""
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own plans",
        )

    await workout_service.delete_plan(plan)


@router.post("/plans/{plan_id}/duplicate", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    duplicate_workouts: Annotated[bool, Query()] = True,
    new_name: Annotated[str | None, Query(max_length=100)] = None,
    from_catalog: Annotated[bool, Query()] = False,
) -> PlanResponse:
    """Duplicate a plan for the current user.

    Args:
        from_catalog: If True, marks this as a catalog import and tracks the source template.
    """
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Check access
    if not plan.is_public and plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    # If importing from catalog, track the source template
    source_template_id = plan_id if from_catalog else None

    new_plan = await workout_service.duplicate_plan(
        plan=plan,
        new_owner_id=current_user.id,
        new_name=new_name,
        duplicate_workouts=duplicate_workouts,
        source_template_id=source_template_id,
    )

    # Refresh to get full data
    new_plan = await workout_service.get_plan_by_id(new_plan.id)
    return PlanResponse.model_validate(new_plan)


@router.post("/plans/{plan_id}/workouts", response_model=PlanResponse)
async def add_workout_to_plan(
    plan_id: UUID,
    request: PlanWorkoutInput,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Add a workout to a plan."""
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own plans",
        )

    if request.workout_id:
        await workout_service.add_workout_to_plan(
            plan_id=plan_id,
            workout_id=request.workout_id,
            label=request.label,
            order=request.order,
            day_of_week=request.day_of_week,
        )
    elif request.workout_name:
        # Create new workout inline
        new_workout = await workout_service.create_workout(
            created_by_id=current_user.id,
            name=request.workout_name,
            difficulty=plan.difficulty,
            target_muscles=request.muscle_groups,
        )
        if request.workout_exercises:
            for ex in request.workout_exercises:
                await workout_service.add_exercise_to_workout(
                    workout_id=new_workout.id,
                    exercise_id=ex.exercise_id,
                    order=ex.order,
                    sets=ex.sets,
                    reps=ex.reps,
                    rest_seconds=ex.rest_seconds,
                    notes=ex.notes,
                    superset_with=ex.superset_with,
                    # Advanced technique fields
                    execution_instructions=ex.execution_instructions,
                    group_instructions=ex.group_instructions,
                    isometric_seconds=ex.isometric_seconds,
                    technique_type=ex.technique_type,
                    exercise_group_id=ex.exercise_group_id,
                    exercise_group_order=ex.exercise_group_order,
                    # Structured technique parameters
                    drop_count=ex.drop_count,
                    rest_between_drops=ex.rest_between_drops,
                    pause_duration=ex.pause_duration,
                    mini_set_count=ex.mini_set_count,
                    # Exercise mode (strength vs aerobic)
                    exercise_mode=ex.exercise_mode,
                    # Aerobic exercise fields
                    duration_minutes=ex.duration_minutes,
                    intensity=ex.intensity,
                    work_seconds=ex.work_seconds,
                    interval_rest_seconds=ex.interval_rest_seconds,
                    rounds=ex.rounds,
                    distance_km=ex.distance_km,
                    target_pace_min_per_km=ex.target_pace_min_per_km,
                )
        await workout_service.add_workout_to_plan(
            plan_id=plan_id,
            workout_id=new_workout.id,
            label=request.label,
            order=request.order,
            day_of_week=request.day_of_week,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either workout_id or workout_name must be provided",
        )

    # Refresh plan
    plan = await workout_service.get_plan_by_id(plan_id)
    return PlanResponse.model_validate(plan)


@router.delete("/plans/{plan_id}/workouts/{plan_workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workout_from_plan(
    plan_id: UUID,
    plan_workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a workout from a plan."""
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own plans",
        )

    await workout_service.remove_workout_from_plan(plan_workout_id)


# ==================== Prescription Notes ====================
# NOTE: These routes MUST be defined before /{workout_id} routes to avoid path conflicts

@router.get("/notes", response_model=PrescriptionNoteListResponse, response_model_by_alias=True)
async def list_prescription_notes_endpoint(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    context_type: Annotated[NoteContextType, Query()],
    context_id: Annotated[UUID, Query()],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> PrescriptionNoteListResponse:
    """List prescription notes for a given context (plan, workout, session, or exercise)."""
    workout_service = WorkoutService(db)
    notes = await workout_service.list_prescription_notes(
        context_type=context_type,
        context_id=context_id,
        organization_id=organization_id,
    )
    note_responses = [PrescriptionNoteResponse.model_validate(n) for n in notes]
    return PrescriptionNoteListResponse(
        notes=note_responses,
        total=len(note_responses),
    )


@router.get("/notes/{note_id}", response_model=PrescriptionNoteResponse, response_model_by_alias=True)
async def get_prescription_note_endpoint(
    note_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Get a specific prescription note by ID."""
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )
    return PrescriptionNoteResponse.model_validate(note)


@router.post("/notes", response_model=PrescriptionNoteResponse, response_model_by_alias=True, status_code=status.HTTP_201_CREATED)
async def create_prescription_note_endpoint(
    request: PrescriptionNoteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Create a new prescription note."""
    workout_service = WorkoutService(db)
    author_role = NoteAuthorRole.TRAINER
    note = await workout_service.create_prescription_note(
        author_id=current_user.id,
        author_role=author_role,
        context_type=request.context_type,
        context_id=request.context_id,
        content=request.content,
        is_pinned=request.is_pinned or False,
        organization_id=request.organization_id,
    )
    return PrescriptionNoteResponse.model_validate(note)


@router.put("/notes/{note_id}", response_model=PrescriptionNoteResponse, response_model_by_alias=True)
async def update_prescription_note_endpoint(
    note_id: UUID,
    request: PrescriptionNoteUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Update a prescription note (author only)."""
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )
    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode editar suas próprias notas",
        )
    updated = await workout_service.update_prescription_note(
        note=note,
        content=request.content,
        is_pinned=request.is_pinned,
    )
    return PrescriptionNoteResponse.model_validate(updated)


@router.post("/notes/{note_id}/read", response_model=PrescriptionNoteResponse, response_model_by_alias=True)
async def mark_note_as_read_endpoint(
    note_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Mark a prescription note as read."""
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )
    updated = await workout_service.mark_note_as_read(note)
    return PrescriptionNoteResponse.model_validate(updated)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription_note_endpoint(
    note_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a prescription note (author only)."""
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)
    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )
    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode deletar suas próprias notas",
        )
    await workout_service.delete_prescription_note(note)


# Exercise Feedback endpoints

@router.post(
    "/sessions/{session_id}/exercises/{workout_exercise_id}/feedback",
    response_model=ExerciseFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_exercise_feedback(
    session_id: UUID,
    workout_exercise_id: UUID,
    request: ExerciseFeedbackCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header()] = None,
) -> ExerciseFeedbackResponse:
    """Create feedback for an exercise (student during workout)."""
    workout_service = WorkoutService(db)

    # Verify session exists and belongs to the user
    session = await workout_service.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você só pode dar feedback em suas próprias sessões",
        )

    # Get workout exercise to get exercise_id
    workout_exercise = await workout_service.get_workout_exercise_by_id(workout_exercise_id)
    if not workout_exercise:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exercício não encontrado no treino",
        )

    # Get organization_id from header if not provided
    org_id = None
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    feedback = await workout_service.create_exercise_feedback(
        session_id=session_id,
        workout_exercise_id=workout_exercise_id,
        exercise_id=workout_exercise.exercise_id,
        student_id=current_user.id,
        feedback_type=request.feedback_type,
        comment=request.comment,
        organization_id=org_id,
    )

    # Get exercise name
    exercise = await workout_service.get_exercise_by_id(feedback.exercise_id)
    exercise_name = exercise.name if exercise else "Exercício"

    # Send push notification to trainer if swap request
    if request.feedback_type == "swap" and org_id:
        try:
            # Find trainer for this student in the organization
            from src.domains.organizations.service import OrganizationService
            org_service = OrganizationService(db)
            membership = await org_service.get_membership(org_id, current_user.id)

            if membership and membership.invited_by_id:
                # Send push to trainer
                await send_push_notification(
                    db=db,
                    user_id=membership.invited_by_id,
                    title="Pedido de troca de exercício",
                    body=f"{current_user.name} pediu para trocar: {exercise_name}",
                    data={
                        "type": "feedback_swap",
                        "feedback_id": str(feedback.id),
                        "student_id": str(current_user.id),
                        "student_name": current_user.name,
                        "exercise_name": exercise_name,
                    },
                )
                logger.info(f"Push notification sent to trainer {membership.invited_by_id} for swap request")
        except Exception as e:
            # Don't fail the request if notification fails
            logger.error(f"Failed to send swap notification: {e}")

    return ExerciseFeedbackResponse(
        id=feedback.id,
        session_id=feedback.session_id,
        workout_exercise_id=feedback.workout_exercise_id,
        exercise_id=feedback.exercise_id,
        student_id=feedback.student_id,
        feedback_type=feedback.feedback_type,
        comment=feedback.comment,
        exercise_name=exercise_name,
        trainer_response=feedback.trainer_response,
        responded_at=feedback.responded_at,
        replacement_exercise_id=feedback.replacement_exercise_id,
        organization_id=feedback.organization_id,
        created_at=feedback.created_at,
    )


@router.get("/sessions/{session_id}/feedbacks", response_model=list[ExerciseFeedbackResponse])
async def list_session_feedbacks(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ExerciseFeedbackResponse]:
    """List all exercise feedbacks for a session."""
    workout_service = WorkoutService(db)

    # Verify session exists and user has access
    session = await workout_service.get_session_by_id(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sessão não encontrada",
        )
    # Allow access to session owner or trainer
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso a esta sessão",
        )

    feedbacks = await workout_service.list_exercise_feedbacks_for_session(session_id)

    result = []
    for fb in feedbacks:
        exercise = await workout_service.get_exercise_by_id(fb.exercise_id)
        replacement = None
        if fb.replacement_exercise_id:
            replacement = await workout_service.get_exercise_by_id(fb.replacement_exercise_id)

        result.append(ExerciseFeedbackResponse(
            id=fb.id,
            session_id=fb.session_id,
            workout_exercise_id=fb.workout_exercise_id,
            exercise_id=fb.exercise_id,
            student_id=fb.student_id,
            feedback_type=fb.feedback_type,
            comment=fb.comment,
            exercise_name=exercise.name if exercise else None,
            trainer_response=fb.trainer_response,
            responded_at=fb.responded_at,
            replacement_exercise_id=fb.replacement_exercise_id,
            replacement_exercise_name=replacement.name if replacement else None,
            organization_id=fb.organization_id,
            created_at=fb.created_at,
        ))

    return result


@router.get("/trainer/exercise-feedbacks", response_model=list[ExerciseFeedbackResponse])
async def list_trainer_exercise_feedbacks(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    student_id: Annotated[UUID | None, Query()] = None,
    x_organization_id: Annotated[str | None, Header()] = None,
) -> list[ExerciseFeedbackResponse]:
    """List pending swap requests for trainer to respond to."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Get organization_id from header
    org_id = None
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    feedbacks = await workout_service.list_pending_swap_requests(
        trainer_id=current_user.id,
        student_id=student_id,
        organization_id=org_id,
    )

    result = []
    for fb in feedbacks:
        exercise = await workout_service.get_exercise_by_id(fb.exercise_id)

        result.append(ExerciseFeedbackResponse(
            id=fb.id,
            session_id=fb.session_id,
            workout_exercise_id=fb.workout_exercise_id,
            exercise_id=fb.exercise_id,
            student_id=fb.student_id,
            feedback_type=fb.feedback_type,
            comment=fb.comment,
            exercise_name=exercise.name if exercise else None,
            trainer_response=fb.trainer_response,
            responded_at=fb.responded_at,
            replacement_exercise_id=fb.replacement_exercise_id,
            organization_id=fb.organization_id,
            created_at=fb.created_at,
        ))

    return result


@router.put("/feedbacks/{feedback_id}/respond", response_model=ExerciseFeedbackResponse)
async def respond_to_exercise_feedback(
    feedback_id: UUID,
    request: ExerciseFeedbackRespondRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ExerciseFeedbackResponse:
    """Trainer responds to an exercise feedback (especially swap requests)."""
    workout_service = WorkoutService(db)

    feedback = await workout_service.get_exercise_feedback_by_id(feedback_id)
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback não encontrado",
        )

    # Verify replacement exercise exists if provided
    replacement_exercise = None
    if request.replacement_exercise_id:
        replacement_exercise = await workout_service.get_exercise_by_id(
            request.replacement_exercise_id
        )
        if not replacement_exercise:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Exercício de substituição não encontrado",
            )

    updated = await workout_service.respond_to_exercise_feedback(
        feedback=feedback,
        trainer_response=request.trainer_response,
        replacement_exercise_id=request.replacement_exercise_id,
    )

    exercise = await workout_service.get_exercise_by_id(updated.exercise_id)
    exercise_name = exercise.name if exercise else "Exercício"

    # Send push notification to student about the response
    try:
        if replacement_exercise:
            title = "Exercício substituído"
            body = f"Seu personal trocou {exercise_name} por {replacement_exercise.name}"
        else:
            title = "Resposta do personal"
            body = f"Seu personal respondeu sobre {exercise_name}"

        await send_push_notification(
            db=db,
            user_id=feedback.student_id,
            title=title,
            body=body,
            data={
                "type": "feedback_response",
                "feedback_id": str(feedback.id),
                "exercise_name": exercise_name,
                "replacement_exercise_name": replacement_exercise.name if replacement_exercise else None,
            },
        )
        logger.info(f"Push notification sent to student {feedback.student_id} for feedback response")
    except Exception as e:
        # Don't fail the request if notification fails
        logger.error(f"Failed to send feedback response notification: {e}")

    return ExerciseFeedbackResponse(
        id=updated.id,
        session_id=updated.session_id,
        workout_exercise_id=updated.workout_exercise_id,
        exercise_id=updated.exercise_id,
        student_id=updated.student_id,
        feedback_type=updated.feedback_type,
        comment=updated.comment,
        exercise_name=exercise.name if exercise else None,
        trainer_response=updated.trainer_response,
        responded_at=updated.responded_at,
        replacement_exercise_id=updated.replacement_exercise_id,
        replacement_exercise_name=replacement_exercise.name if replacement_exercise else None,
        organization_id=updated.organization_id,
        created_at=updated.created_at,
    )


# Individual workout routes (moved to end to avoid conflicts)
@router.get("/{workout_id}", response_model=WorkoutResponse)
async def get_workout(
    workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Get workout details with exercises."""
    from sqlalchemy import and_, select
    from src.domains.organizations.models import OrganizationMembership
    from src.domains.workouts.models import AssignmentStatus, PlanAssignment, PlanWorkout

    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Check access: public, owner, or member of the workout's organization
    has_access = workout.is_public or workout.created_by_id == current_user.id

    # Check organization membership if workout belongs to an organization
    if not has_access and workout.organization_id is not None:
        membership_query = select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == workout.organization_id,
                OrganizationMembership.is_active == True,
            )
        )
        membership_result = await db.execute(membership_query)
        has_access = membership_result.scalar_one_or_none() is not None

    # If no direct access, check if user has a plan assignment that includes this workout
    if not has_access:
        plan_assignment_query = (
            select(PlanAssignment)
            .join(PlanWorkout, PlanWorkout.plan_id == PlanAssignment.plan_id)
            .where(
                PlanAssignment.student_id == current_user.id,
                PlanAssignment.is_active == True,
                PlanAssignment.status.in_([AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]),
                PlanWorkout.workout_id == workout_id,
            )
            .limit(1)
        )
        result = await db.execute(plan_assignment_query)
        has_assignment = result.scalar_one_or_none() is not None
        has_access = has_assignment

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return WorkoutResponse.model_validate(workout)


@router.get("/{workout_id}/exercises", response_model=list[WorkoutExerciseResponse])
async def get_workout_exercises(
    workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkoutExerciseResponse]:
    """Get exercises for a workout."""
    from sqlalchemy import and_, select
    from src.domains.organizations.models import OrganizationMembership
    from src.domains.workouts.models import AssignmentStatus, PlanAssignment, PlanWorkout

    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Check access: public, owner, or member of the workout's organization
    has_access = workout.is_public or workout.created_by_id == current_user.id

    # Check organization membership if workout belongs to an organization
    if not has_access and workout.organization_id is not None:
        membership_query = select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == workout.organization_id,
                OrganizationMembership.is_active == True,
            )
        )
        membership_result = await db.execute(membership_query)
        has_access = membership_result.scalar_one_or_none() is not None

    # If no direct access, check if user has an assignment that includes this workout
    if not has_access:
        # Check if user has an active plan assignment that includes this workout
        plan_assignment_query = (
            select(PlanAssignment)
            .join(PlanWorkout, PlanWorkout.plan_id == PlanAssignment.plan_id)
            .where(
                PlanAssignment.student_id == current_user.id,
                PlanAssignment.is_active == True,
                PlanAssignment.status.in_([AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED]),
                PlanWorkout.workout_id == workout_id,
            )
            .limit(1)
        )
        result = await db.execute(plan_assignment_query)
        has_assignment = result.scalar_one_or_none() is not None
        has_access = has_assignment

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return [WorkoutExerciseResponse.model_validate(we) for we in workout.exercises]


# ==================== Workouts ====================

@router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    request: WorkoutCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
) -> WorkoutResponse:
    """Create a new workout."""
    workout_service = WorkoutService(db)

    # Use request.organization_id if provided, otherwise fallback to header
    organization_id = request.organization_id
    if organization_id is None and x_organization_id:
        try:
            organization_id = UUID(x_organization_id)
        except ValueError:
            pass  # Invalid UUID in header, ignore

    workout = await workout_service.create_workout(
        created_by_id=current_user.id,
        name=request.name,
        description=request.description,
        difficulty=request.difficulty,
        estimated_duration_min=request.estimated_duration_min,
        target_muscles=request.target_muscles,
        tags=request.tags,
        is_template=request.is_template,
        is_public=request.is_public,
        organization_id=organization_id,
    )

    # Add exercises if provided
    if request.exercises:
        for ex in request.exercises:
            await workout_service.add_exercise_to_workout(
                workout_id=workout.id,
                exercise_id=ex.exercise_id,
                order=ex.order,
                sets=ex.sets,
                reps=ex.reps,
                rest_seconds=ex.rest_seconds,
                notes=ex.notes,
                superset_with=ex.superset_with,
                # Advanced technique fields
                execution_instructions=ex.execution_instructions,
                group_instructions=ex.group_instructions,
                isometric_seconds=ex.isometric_seconds,
                technique_type=ex.technique_type,
                exercise_group_id=ex.exercise_group_id,
                exercise_group_order=ex.exercise_group_order,
                # Structured technique parameters
                drop_count=ex.drop_count,
                rest_between_drops=ex.rest_between_drops,
                pause_duration=ex.pause_duration,
                mini_set_count=ex.mini_set_count,
                # Exercise mode (strength vs aerobic)
                exercise_mode=ex.exercise_mode,
                # Aerobic exercise fields
                duration_minutes=ex.duration_minutes,
                intensity=ex.intensity,
                work_seconds=ex.work_seconds,
                interval_rest_seconds=ex.interval_rest_seconds,
                rounds=ex.rounds,
                distance_km=ex.distance_km,
                target_pace_min_per_km=ex.target_pace_min_per_km,
            )
        # Refresh to get exercises
        workout = await workout_service.get_workout_by_id(workout.id)

    return WorkoutResponse.model_validate(workout)


@router.put("/{workout_id}", response_model=WorkoutResponse)
async def update_workout(
    workout_id: UUID,
    request: WorkoutUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Update a workout (owner only)."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    if workout.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own workouts",
        )

    updated = await workout_service.update_workout(
        workout=workout,
        name=request.name,
        description=request.description,
        difficulty=request.difficulty,
        estimated_duration_min=request.estimated_duration_min,
        target_muscles=request.target_muscles,
        tags=request.tags,
        is_template=request.is_template,
        is_public=request.is_public,
    )

    # Send push notification to all students with active assignments for this workout
    try:
        from sqlalchemy import select
        from src.domains.workouts.models import WorkoutAssignment

        result = await db.execute(
            select(WorkoutAssignment.student_id).where(
                WorkoutAssignment.workout_id == workout_id,
                WorkoutAssignment.is_active == True,
            )
        )
        student_ids = [row[0] for row in result.fetchall()]

        for student_id in student_ids:
            try:
                await send_push_notification(
                    db=db,
                    user_id=student_id,
                    title="Treino atualizado",
                    body=f"Seu treino '{updated.name}' foi atualizado pelo personal",
                    data={
                        "type": "workout_updated",
                        "workout_id": str(workout_id),
                        "workout_name": updated.name,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to notify students about workout update: {e}")

    return WorkoutResponse.model_validate(updated)


@router.delete("/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(
    workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a workout (owner only)."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    if workout.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own workouts",
        )

    await workout_service.delete_workout(workout)


@router.post("/{workout_id}/duplicate", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_workout(
    workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Duplicate a workout for the current user."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Check access
    if not workout.is_public and workout.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    new_workout = await workout_service.duplicate_workout(
        workout=workout,
        new_owner_id=current_user.id,
    )

    return WorkoutResponse.model_validate(new_workout)


@router.post("/{workout_id}/exercises", response_model=WorkoutResponse)
async def add_exercise(
    workout_id: UUID,
    request: WorkoutExerciseInput,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Add an exercise to a workout."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    if workout.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own workouts",
        )

    await workout_service.add_exercise_to_workout(
        workout_id=workout_id,
        exercise_id=request.exercise_id,
        order=request.order,
        sets=request.sets,
        reps=request.reps,
        rest_seconds=request.rest_seconds,
        notes=request.notes,
        superset_with=request.superset_with,
        # Advanced technique fields
        execution_instructions=request.execution_instructions,
        group_instructions=request.group_instructions,
        isometric_seconds=request.isometric_seconds,
        technique_type=request.technique_type,
        exercise_group_id=request.exercise_group_id,
        exercise_group_order=request.exercise_group_order,
        # Structured technique parameters
        drop_count=request.drop_count,
        rest_between_drops=request.rest_between_drops,
        pause_duration=request.pause_duration,
        mini_set_count=request.mini_set_count,
        # Exercise mode (strength vs aerobic)
        exercise_mode=request.exercise_mode,
        # Aerobic exercise fields
        duration_minutes=request.duration_minutes,
        intensity=request.intensity,
        work_seconds=request.work_seconds,
        interval_rest_seconds=request.interval_rest_seconds,
        rounds=request.rounds,
        distance_km=request.distance_km,
        target_pace_min_per_km=request.target_pace_min_per_km,
    )

    # Refresh workout
    workout = await workout_service.get_workout_by_id(workout_id)

    # Send push notification to all students with active assignments
    try:
        from sqlalchemy import select
        from src.domains.workouts.models import WorkoutAssignment

        result = await db.execute(
            select(WorkoutAssignment.student_id).where(
                WorkoutAssignment.workout_id == workout_id,
                WorkoutAssignment.is_active == True,
            )
        )
        student_ids = [row[0] for row in result.fetchall()]

        for student_id in student_ids:
            try:
                await send_push_notification(
                    db=db,
                    user_id=student_id,
                    title="Treino atualizado",
                    body=f"Seu treino '{workout.name}' foi atualizado pelo personal",
                    data={
                        "type": "workout_updated",
                        "workout_id": str(workout_id),
                        "workout_name": workout.name,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to notify students about workout update: {e}")

    return WorkoutResponse.model_validate(workout)


@router.delete("/{workout_id}/exercises/{workout_exercise_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_exercise(
    workout_id: UUID,
    workout_exercise_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove an exercise from a workout."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    if workout.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own workouts",
        )

    await workout_service.remove_exercise_from_workout(workout_exercise_id)

    # Send push notification to all students with active assignments
    try:
        from sqlalchemy import select
        from src.domains.workouts.models import WorkoutAssignment

        result = await db.execute(
            select(WorkoutAssignment.student_id).where(
                WorkoutAssignment.workout_id == workout_id,
                WorkoutAssignment.is_active == True,
            )
        )
        student_ids = [row[0] for row in result.fetchall()]

        for student_id in student_ids:
            try:
                await send_push_notification(
                    db=db,
                    user_id=student_id,
                    title="Treino atualizado",
                    body=f"Seu treino '{workout.name}' foi atualizado pelo personal",
                    data={
                        "type": "workout_updated",
                        "workout_id": str(workout_id),
                        "workout_name": workout.name,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except Exception as e:
        logger.error(f"Failed to notify students about workout update: {e}")


# Co-Training endpoints

@router.get("/sessions/active", response_model=list[ActiveSessionResponse])
async def list_active_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID, Query()],  # SECURITY: Now required to prevent cross-org access
) -> list[ActiveSessionResponse]:
    """List active sessions for students (trainer view - 'Students Now').

    Organization ID is required to ensure trainers only see sessions from their organization.
    """
    from sqlalchemy import and_, select
    from src.domains.organizations.models import OrganizationMembership

    # SECURITY: Verify trainer is a member of the specified organization
    trainer_membership = await db.execute(
        select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.is_active == True,
            )
        )
    )
    if not trainer_membership.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro desta organização",
        )

    workout_service = WorkoutService(db)
    sessions = await workout_service.list_active_sessions(
        trainer_id=current_user.id,
        organization_id=organization_id,
    )
    return sessions


@router.post("/sessions/{session_id}/join", response_model=SessionJoinResponse)
async def join_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionJoinResponse:
    """Trainer joins a student's session for co-training."""
    from src.domains.workouts.realtime import notify_trainer_joined

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot join a completed session",
        )

    # Update session with trainer
    updated_session = await workout_service.trainer_join_session(
        session=session,
        trainer_id=current_user.id,
    )

    # Notify via real-time
    await notify_trainer_joined(
        session_id=session_id,
        trainer_id=current_user.id,
        trainer_name=current_user.name,
    )

    return SessionJoinResponse(
        session_id=updated_session.id,
        trainer_id=current_user.id,
        student_id=updated_session.user_id,
        workout_name=updated_session.workout.name if updated_session.workout else "",
        is_shared=updated_session.is_shared,
        status=updated_session.status,
    )


@router.post("/sessions/{session_id}/leave")
async def leave_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Trainer leaves a co-training session."""
    from src.domains.workouts.realtime import notify_trainer_left

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the trainer of this session",
        )

    await workout_service.trainer_leave_session(session)

    # Notify via real-time
    await notify_trainer_left(
        session_id=session_id,
        trainer_id=current_user.id,
    )

    return {"message": "Left session successfully"}


@router.put("/sessions/{session_id}/status", response_model=SessionResponse)
async def update_session_status(
    session_id: UUID,
    request: SessionStatusUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    """Update session status (active, paused, etc.)."""
    from src.domains.workouts.realtime import notify_session_status_change

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Only session owner or trainer can update status
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    updated = await workout_service.update_session_status(
        session=session,
        status=request.status,
    )

    # Notify via real-time
    await notify_session_status_change(
        session_id=session_id,
        status=request.status,
        changed_by=current_user.id,
    )

    return SessionResponse.model_validate(updated)


@router.post("/sessions/{session_id}/adjustments", response_model=TrainerAdjustmentResponse, status_code=status.HTTP_201_CREATED)
async def create_trainer_adjustment(
    session_id: UUID,
    request: TrainerAdjustmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrainerAdjustmentResponse:
    """Trainer makes an adjustment during co-training (suggest weight/reps)."""
    from src.domains.workouts.realtime import notify_trainer_adjustment

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    if session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the session trainer can make adjustments",
        )

    if session.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot adjust a completed session",
        )

    adjustment = await workout_service.create_trainer_adjustment(
        session_id=session_id,
        trainer_id=current_user.id,
        exercise_id=request.exercise_id,
        set_number=request.set_number,
        suggested_weight_kg=request.suggested_weight_kg,
        suggested_reps=request.suggested_reps,
        note=request.note,
    )

    # Notify via real-time
    await notify_trainer_adjustment(
        session_id=session_id,
        trainer_id=current_user.id,
        exercise_id=request.exercise_id,
        set_number=request.set_number,
        suggested_weight_kg=request.suggested_weight_kg,
        suggested_reps=request.suggested_reps,
        note=request.note,
    )

    return TrainerAdjustmentResponse.model_validate(adjustment)


@router.post("/sessions/{session_id}/messages", response_model=SessionMessageResponse, status_code=status.HTTP_201_CREATED)
async def send_session_message(
    session_id: UUID,
    request: SessionMessageCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionMessageResponse:
    """Send a quick message during co-training session."""
    from src.domains.workouts.realtime import notify_message_sent

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Only session participants can send messages
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only session participants can send messages",
        )

    if session.is_completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot send messages to a completed session",
        )

    message = await workout_service.create_session_message(
        session_id=session_id,
        sender_id=current_user.id,
        message=request.message,
    )

    # Notify via real-time
    await notify_message_sent(
        session_id=session_id,
        sender_id=current_user.id,
        sender_name=current_user.name,
        message=request.message,
        message_id=message.id,
    )

    return SessionMessageResponse(
        id=message.id,
        session_id=message.session_id,
        sender_id=message.sender_id,
        sender_name=current_user.name,
        message=message.message,
        sent_at=message.sent_at,
        is_read=message.is_read,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[SessionMessageResponse])
async def list_session_messages(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[SessionMessageResponse]:
    """List messages from a co-training session."""
    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Only session participants can view messages
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    messages = await workout_service.list_session_messages(
        session_id=session_id,
        limit=limit,
    )

    return [
        SessionMessageResponse(
            id=m.id,
            session_id=m.session_id,
            sender_id=m.sender_id,
            sender_name=m.sender.name if m.sender else None,
            message=m.message,
            sent_at=m.sent_at,
            is_read=m.is_read,
        )
        for m in messages
    ]


@router.get("/sessions/{session_id}/stream")
async def stream_session_events(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Stream real-time session events via Server-Sent Events (SSE)."""
    from src.domains.workouts.realtime import stream_session_events as stream_events

    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Only session participants can subscribe
    if session.user_id != current_user.id and session.trainer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return StreamingResponse(
        stream_events(session_id, current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
