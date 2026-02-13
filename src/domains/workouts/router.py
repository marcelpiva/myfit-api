"""Workout router — thin entry point that includes all sub-routers.

Sub-routers:
  - exercises_router: Exercise CRUD + media upload + AI suggestions
  - plans_router: Training plan CRUD, assignments, and versioning
  - sessions_router: Workout sessions, co-training, feedback, SSE
  - assignments_router: Workout assignment endpoints
"""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.notifications.push_service import send_push_notification
from src.domains.workouts.models import NoteAuthorRole, NoteContextType
from src.domains.workouts.schemas import (
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

# Sub-routers
from src.domains.workouts.assignments_router import assignments_router
from src.domains.workouts.exercises_router import exercises_router
from src.domains.workouts.plans_router import plans_router
from src.domains.workouts.sessions_router import sessions_router

logger = logging.getLogger(__name__)

router = APIRouter()

# Include sub-routers (no prefix — the main app adds /api/v1/workouts)
router.include_router(exercises_router)
router.include_router(plans_router)
router.include_router(sessions_router)
router.include_router(assignments_router)


# ==================== Workout list ====================

@router.get("", response_model=list[WorkoutListResponse])
async def list_workouts(
    request: Request,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkoutListResponse]:
    """List workouts for the current user."""
    # Use query param if provided, otherwise fallback to X-Organization-ID header
    org_id = organization_id
    if org_id is None:
        header_org = request.headers.get("x-organization-id")
        if header_org:
            try:
                org_id = UUID(header_org)
            except ValueError:
                pass

    logger.warning(
        "[DEBUG] list_workouts: user=%s, query_org=%s, header_org=%s, resolved_org=%s",
        current_user.id, organization_id, request.headers.get("x-organization-id"), org_id,
    )

    workout_service = WorkoutService(db)
    workouts = await workout_service.list_workouts(
        user_id=current_user.id,
        organization_id=org_id,
        templates_only=templates_only,
        search=search,
        limit=limit,
        offset=offset,
    )

    logger.warning(
        "[DEBUG] list_workouts: returning %d workouts: %s",
        len(workouts),
        [(str(w.id)[:8], w.name, str(w.organization_id)[:8] if w.organization_id else None) for w in workouts],
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


# ==================== Individual workout routes (must be at end to avoid path conflicts) ====================

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


# ==================== Workout CRUD ====================

@router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    raw_request: Request,
    request: WorkoutCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Create a new workout."""
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
            except (ConnectionError, OSError, RuntimeError) as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except (SQLAlchemyError, RuntimeError) as e:
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
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-ID")] = None,
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

    # Resolve organization_id from header
    org_id = None
    if x_organization_id:
        try:
            org_id = UUID(x_organization_id)
        except ValueError:
            pass

    new_workout = await workout_service.duplicate_workout(
        workout=workout,
        new_owner_id=current_user.id,
        organization_id=org_id,
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
            except (ConnectionError, OSError, RuntimeError) as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except (SQLAlchemyError, RuntimeError) as e:
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
            except (ConnectionError, OSError, RuntimeError) as e:
                logger.warning(f"Failed to send push notification to student {student_id}: {e}")
    except (SQLAlchemyError, RuntimeError) as e:
        logger.error(f"Failed to notify students about workout update: {e}")
