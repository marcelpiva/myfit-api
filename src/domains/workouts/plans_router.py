"""Training plan endpoints including plan CRUD, assignments, and versioning."""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.redis import RateLimiter
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.service import UserService
from src.domains.workouts.models import Difficulty, SplitType, WorkoutGoal
from src.domains.workouts.schemas import (
    AIGeneratePlanRequest,
    AIGeneratePlanResponse,
    AssignmentAcceptRequest,
    BatchPlanAssignmentCreate,
    BatchPlanAssignmentResponse,
    BatchPlanAssignmentResult,
    CatalogPlanResponse,
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
)
from src.domains.workouts.service import WorkoutService
from src.domains.notifications.push_service import send_push_notification
from src.domains.notifications.router import create_notification
from src.domains.notifications.schemas import NotificationCreate
from src.domains.notifications.models import NotificationType

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


plans_router = APIRouter()


@plans_router.get("/plans", response_model=list[PlanListResponse])
async def list_plans(
    request: Request,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PlanListResponse]:
    """List training plans for the current user."""
    # Use query param if provided, otherwise fallback to X-Organization-ID header
    org_id = organization_id
    if org_id is None:
        header_org = request.headers.get("x-organization-id")
        if header_org:
            try:
                org_id = UUID(header_org)
            except ValueError:
                pass

    workout_service = WorkoutService(db)
    plans = await workout_service.list_plans(
        user_id=current_user.id,
        organization_id=org_id,
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


@plans_router.get("/plans/catalog", response_model=list[CatalogPlanResponse])
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


@plans_router.post("/plans/generate-ai", response_model=AIGeneratePlanResponse)
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

@plans_router.get("/plans/assignments", response_model=list[PlanAssignmentResponse])
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


@plans_router.post("/plans/assignments", response_model=PlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
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
    except (ConnectionError, OSError, RuntimeError) as e:
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


@plans_router.post("/plans/assignments/batch", response_model=BatchPlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
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
            except (ConnectionError, OSError, RuntimeError) as e:
                logger.warning(f"Failed to send notifications to student {student_id}: {e}")

            results.append(BatchPlanAssignmentResult(
                student_id=student_id,
                student_name=student.name,
                success=True,
                assignment_id=assignment.id,
            ))
            successful += 1

        except (SQLAlchemyError, ValueError, RuntimeError) as e:
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


@plans_router.post("/plans/assignments/{assignment_id}/respond", response_model=PlanAssignmentResponse)
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
        except (ConnectionError, OSError, RuntimeError) as e:
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


@plans_router.post("/plans/assignments/{assignment_id}/acknowledge", response_model=PlanAssignmentResponse)
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
        except (ConnectionError, OSError, RuntimeError) as e:
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


@plans_router.put("/plans/assignments/{assignment_id}", response_model=PlanAssignmentResponse)
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


@plans_router.delete("/plans/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
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

@plans_router.get("/plans/assignments/{assignment_id}/versions", response_model=PlanVersionListResponse)
async def list_plan_versions(
    assignment_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionListResponse:
    """Get version history for a plan assignment.

    Both trainer and student can view versions for assignments they're involved in.
    """
    from sqlalchemy import select
    from src.domains.workouts.models import PlanVersion

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


@plans_router.get("/plans/assignments/{assignment_id}/versions/{version}", response_model=PlanVersionResponse)
async def get_plan_version(
    assignment_id: UUID,
    version: int,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanVersionResponse:
    """Get a specific version of a plan assignment."""
    from sqlalchemy import select
    from src.domains.workouts.models import PlanVersion

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


@plans_router.post("/plans/assignments/{assignment_id}/versions", response_model=PlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
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
    from src.domains.workouts.models import PlanVersion

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
    except (ConnectionError, OSError, RuntimeError) as e:
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


@plans_router.post("/plans/assignments/{assignment_id}/versions/viewed", response_model=PlanAssignmentResponse)
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


@plans_router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Get plan details with workouts."""
    from sqlalchemy import and_, select
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
    )

    # Check organization membership if plan belongs to an organization
    if not has_access and plan.organization_id is not None:
        from src.domains.organizations.models import OrganizationMembership
        membership_query = select(OrganizationMembership).where(
            and_(
                OrganizationMembership.user_id == current_user.id,
                OrganizationMembership.organization_id == plan.organization_id,
                OrganizationMembership.is_active == True,
            )
        )
        membership_result = await db.execute(membership_query)
        has_access = membership_result.scalar_one_or_none() is not None

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


@plans_router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    raw_request: Request,
    request: PlanCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Create a new training plan."""
    workout_service = WorkoutService(db)

    # Use request.organization_id if provided, otherwise fallback to X-Organization-ID header
    organization_id = request.organization_id
    if organization_id is None:
        header_org = raw_request.headers.get("x-organization-id")
        if header_org:
            try:
                organization_id = UUID(header_org)
            except ValueError:
                pass

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
        organization_id=organization_id,
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
                    organization_id=organization_id,
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
                            execution_instructions=ex.execution_instructions,
                            group_instructions=ex.group_instructions,
                            isometric_seconds=ex.isometric_seconds,
                            technique_type=ex.technique_type,
                            exercise_group_id=ex.exercise_group_id,
                            exercise_group_order=ex.exercise_group_order,
                            drop_count=ex.drop_count,
                            rest_between_drops=ex.rest_between_drops,
                            pause_duration=ex.pause_duration,
                            mini_set_count=ex.mini_set_count,
                            exercise_mode=ex.exercise_mode,
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


@plans_router.put("/plans/{plan_id}", response_model=PlanResponse)
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
        existing_workout_ids = [pw.workout_id for pw in plan.plan_workouts]
        logger.info(f"Deleting {len(existing_workout_ids)} existing workouts")

        for pw in list(plan.plan_workouts):
            await workout_service.remove_workout_from_plan(pw.id)

        for workout_id in existing_workout_ids:
            workout = await workout_service.get_workout_by_id(workout_id)
            if workout:
                await workout_service.delete_workout(workout)

        for pw in request.workouts:
            logger.info(f"Processing workout: label={pw.label}, workout_id={pw.workout_id}, workout_name={pw.workout_name}, exercises={len(pw.workout_exercises or [])}")
            if pw.workout_id:
                await workout_service.add_workout_to_plan(
                    plan_id=plan_id,
                    workout_id=pw.workout_id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )
            elif pw.workout_name:
                new_workout = await workout_service.create_workout(
                    created_by_id=current_user.id,
                    name=pw.workout_name,
                    difficulty=request.difficulty or plan.difficulty,
                    target_muscles=pw.muscle_groups,
                )
                logger.info(f"Created workout {new_workout.id} with name {new_workout.name}")
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
                            execution_instructions=ex.execution_instructions,
                            group_instructions=ex.group_instructions,
                            isometric_seconds=ex.isometric_seconds,
                            technique_type=ex.technique_type,
                            exercise_group_id=ex.exercise_group_id,
                            exercise_group_order=ex.exercise_group_order,
                            drop_count=ex.drop_count,
                            rest_between_drops=ex.rest_between_drops,
                            pause_duration=ex.pause_duration,
                            mini_set_count=ex.mini_set_count,
                            exercise_mode=ex.exercise_mode,
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
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )

        updated = await workout_service.get_plan_by_id(plan_id)

    return PlanResponse.model_validate(updated)


@plans_router.delete("/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
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


@plans_router.post("/plans/{plan_id}/duplicate", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
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

    if not plan.is_public and plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    source_template_id = plan_id if from_catalog else None

    org_id = None
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    new_plan = await workout_service.duplicate_plan(
        plan=plan,
        new_owner_id=current_user.id,
        new_name=new_name,
        duplicate_workouts=duplicate_workouts,
        source_template_id=source_template_id,
        organization_id=org_id,
    )

    new_plan = await workout_service.get_plan_by_id(new_plan.id)
    return PlanResponse.model_validate(new_plan)


@plans_router.post("/plans/{plan_id}/workouts", response_model=PlanResponse)
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
        new_workout = await workout_service.create_workout(
            created_by_id=current_user.id,
            name=request.workout_name,
            difficulty=plan.difficulty,
            target_muscles=request.muscle_groups,
            organization_id=plan.organization_id,
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
                    execution_instructions=ex.execution_instructions,
                    group_instructions=ex.group_instructions,
                    isometric_seconds=ex.isometric_seconds,
                    technique_type=ex.technique_type,
                    exercise_group_id=ex.exercise_group_id,
                    exercise_group_order=ex.exercise_group_order,
                    drop_count=ex.drop_count,
                    rest_between_drops=ex.rest_between_drops,
                    pause_duration=ex.pause_duration,
                    mini_set_count=ex.mini_set_count,
                    exercise_mode=ex.exercise_mode,
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

    plan = await workout_service.get_plan_by_id(plan_id)
    return PlanResponse.model_validate(plan)


@plans_router.delete("/plans/{plan_id}/workouts/{plan_workout_id}", status_code=status.HTTP_204_NO_CONTENT)
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
