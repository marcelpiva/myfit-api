"""Workout session endpoints including co-training, feedback, and SSE streaming."""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.notifications.models import NotificationType
from src.domains.notifications.push_service import send_push_notification
from src.domains.notifications.router import create_notification
from src.domains.notifications.schemas import NotificationCreate
from src.domains.users.service import UserService
from src.domains.workouts.schemas import (
    ActiveSessionResponse,
    ExerciseFeedbackCreate,
    ExerciseFeedbackRespondRequest,
    ExerciseFeedbackResponse,
    SessionComplete,
    SessionFeedbackUpdate,
    SessionJoinResponse,
    SessionListResponse,
    SessionMessageCreate,
    SessionMessageResponse,
    SessionResponse,
    SessionSetInput,
    SessionSetResponse,
    SessionStart,
    SessionStatusUpdate,
    TrainerAdjustmentCreate,
    TrainerAdjustmentResponse,
)
from src.domains.workouts.service import WorkoutService

logger = logging.getLogger(__name__)

sessions_router = APIRouter()


# Session endpoints

@sessions_router.get("/sessions", response_model=list[SessionListResponse])
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


@sessions_router.get("/sessions/active", response_model=list[ActiveSessionResponse])
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
    if not trainer_membership.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não é membro desta organização",
        )

    workout_service = WorkoutService(db)

    # Auto-expire stale sessions inline (Celery beat not running on Railway)
    await workout_service.auto_expire_sessions()

    sessions = await workout_service.list_active_sessions(
        trainer_id=current_user.id,
        organization_id=organization_id,
    )
    return sessions


@sessions_router.post("/sessions/cleanup")
async def cleanup_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Force-expire all non-completed sessions. Trainer cleanup tool."""
    workout_service = WorkoutService(db)
    count = await workout_service.force_expire_all_sessions()
    return {"expired": count}


@sessions_router.get("/sessions/my-active", response_model=SessionResponse | None)
async def get_my_active_session(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse | None:
    """Get the current user's active or paused shared session, if any.

    Used by the student app to offer session resumption after app restart.
    """
    workout_service = WorkoutService(db)
    await workout_service.auto_expire_sessions()
    session = await workout_service.get_user_active_session(user_id=current_user.id)
    if session is None:
        return None
    return SessionResponse.model_validate(session)


@sessions_router.get("/sessions/{session_id}", response_model=SessionResponse)
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
        # Also allow trainers who share an organization with the session owner
        from sqlalchemy import and_, select
        from src.domains.organizations.models import OrganizationMembership

        user_orgs = await db.execute(
            select(OrganizationMembership.organization_id).where(
                and_(
                    OrganizationMembership.user_id == current_user.id,
                    OrganizationMembership.is_active == True,
                )
            )
        )
        user_org_ids = {row[0] for row in user_orgs.all()}

        session_owner_orgs = await db.execute(
            select(OrganizationMembership.organization_id).where(
                and_(
                    OrganizationMembership.user_id == session.user_id,
                    OrganizationMembership.is_active == True,
                )
            )
        )
        session_owner_org_ids = {row[0] for row in session_owner_orgs.all()}

        if not user_org_ids & session_owner_org_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

    return SessionResponse.model_validate(session)


@sessions_router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
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
        except (ConnectionError, OSError, RuntimeError) as e:
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


@sessions_router.post("/sessions/{session_id}/complete", response_model=SessionResponse)
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


@sessions_router.patch("/sessions/{session_id}/feedback", response_model=SessionResponse)
async def update_session_feedback(
    session_id: UUID,
    request: SessionFeedbackUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionResponse:
    """Update feedback/rating on a completed session."""
    workout_service = WorkoutService(db)
    session = await workout_service.get_session_by_id(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    # Student can update rating/feedback, trainer can update notes
    is_student = session.user_id == current_user.id
    is_trainer = session.trainer_id == current_user.id
    if not is_student and not is_trainer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if request.rating is not None and is_student:
        session.rating = request.rating
    if request.student_feedback is not None and is_student:
        session.student_feedback = request.student_feedback
    if request.trainer_notes is not None and is_trainer:
        session.trainer_notes = request.trainer_notes

    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@sessions_router.post("/sessions/{session_id}/sets", response_model=SessionSetResponse, status_code=status.HTTP_201_CREATED)
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

    # Broadcast set completion to trainer via SSE
    if session.is_shared:
        from src.domains.workouts.realtime import notify_set_completed
        await notify_set_completed(
            session_id=session_id,
            user_id=current_user.id,
            exercise_id=request.exercise_id,
            set_number=request.set_number,
            reps=request.reps_completed,
            weight_kg=request.weight_kg,
        )

    return SessionSetResponse.model_validate(session_set)


# Exercise Feedback endpoints

@sessions_router.post(
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
        except (ConnectionError, OSError, RuntimeError) as e:
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


@sessions_router.get("/sessions/{session_id}/feedbacks", response_model=list[ExerciseFeedbackResponse])
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


@sessions_router.get("/trainer/exercise-feedbacks", response_model=list[ExerciseFeedbackResponse])
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


@sessions_router.put("/feedbacks/{feedback_id}/respond", response_model=ExerciseFeedbackResponse)
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
    except (ConnectionError, OSError, RuntimeError) as e:
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


# Co-Training endpoints

@sessions_router.post("/sessions/{session_id}/join", response_model=SessionJoinResponse)
async def join_session(
    session_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SessionJoinResponse:
    """Trainer joins a student's session for co-training."""
    from src.domains.workouts.realtime import notify_trainer_joined, get_session_snapshot

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

    # Cache session state BEFORE broadcasting (so SYNC_RESPONSE has data)
    await get_session_snapshot(db, session_id)

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


@sessions_router.post("/sessions/{session_id}/leave")
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


@sessions_router.put("/sessions/{session_id}/status", response_model=SessionResponse)
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


@sessions_router.post("/sessions/{session_id}/adjustments", response_model=TrainerAdjustmentResponse, status_code=status.HTTP_201_CREATED)
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


@sessions_router.post("/sessions/{session_id}/messages", response_model=SessionMessageResponse, status_code=status.HTTP_201_CREATED)
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


@sessions_router.get("/sessions/{session_id}/messages", response_model=list[SessionMessageResponse])
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


@sessions_router.get("/sessions/{session_id}/stream")
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
