"""Workout router with exercise, workout, assignment, and session endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status


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
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.service import UserService
from src.domains.workouts.models import Difficulty, MuscleGroup, NoteAuthorRole, NoteContextType, SessionStatus, SplitType, TechniqueType, WorkoutGoal
from src.domains.workouts.schemas import (
    ActiveSessionResponse,
    AIGeneratePlanRequest,
    AIGeneratePlanResponse,
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    CatalogPlanResponse,
    ExerciseCreate,
    ExerciseResponse,
    ExerciseSuggestionRequest,
    ExerciseSuggestionResponse,
    ExerciseUpdate,
    PlanAssignmentCreate,
    PlanAssignmentResponse,
    PlanAssignmentUpdate,
    PlanCreate,
    PlanListResponse,
    PlanResponse,
    PlanUpdate,
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

@router.get("/", response_model=list[WorkoutListResponse])
async def list_workouts(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[WorkoutListResponse]:
    """List workouts for the current user."""
    workout_service = WorkoutService(db)
    workouts = await workout_service.list_workouts(
        user_id=current_user.id,
        organization_id=organization_id,
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

    if session.user_id != current_user.id:
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
    """Start a new workout session."""
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


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanResponse:
    """Get plan details with workouts."""
    workout_service = WorkoutService(db)
    plan = await workout_service.get_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found",
        )

    # Check access
    if (
        not plan.is_public
        and plan.created_by_id != current_user.id
        and plan.organization_id is None
    ):
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
        # Get existing plan_workouts and their workout IDs
        existing_workout_ids = [pw.workout_id for pw in plan.plan_workouts]

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


# Plan assignment endpoints

@router.get("/plans/assignments", response_model=list[PlanAssignmentResponse])
async def list_plan_assignments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    active_only: Annotated[bool, Query()] = True,
    student_id: Annotated[UUID | None, Query()] = None,
) -> list[PlanAssignmentResponse]:
    """List plan assignments (as student or trainer).

    If as_trainer=True and student_id is provided, returns assignments for that specific student.
    If as_trainer=True and student_id is None, returns all assignments where current user is trainer.
    If as_trainer=False, returns assignments for current user as student.
    """
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    if as_trainer:
        if student_id:
            # Filter by specific student
            assignments = await workout_service.list_trainer_plan_assignments(
                trainer_id=current_user.id,
                student_id=student_id,
                active_only=active_only,
            )
        else:
            # All trainer's assignments
            assignments = await workout_service.list_trainer_plan_assignments(
                trainer_id=current_user.id,
                active_only=active_only,
            )
    else:
        assignments = await workout_service.list_student_plan_assignments(
            student_id=current_user.id,
            active_only=active_only,
        )

    result = []
    for a in assignments:
        student = await user_service.get_user_by_id(a.student_id)
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
                created_at=a.created_at,
                plan_name=a.plan.name if a.plan else "",
                student_name=student.name if student else "",
            )
        )

    return result


@router.post("/plans/assignments", response_model=PlanAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_plan_assignment(
    request: PlanAssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlanAssignmentResponse:
    """Assign a plan to a student."""
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

    assignment = await workout_service.create_plan_assignment(
        plan_id=request.plan_id,
        student_id=request.student_id,
        trainer_id=current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        notes=request.notes,
        organization_id=request.organization_id,
    )

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
        created_at=assignment.created_at,
        plan_name=plan.name,
        student_name=student.name,
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
        created_at=updated.created_at,
        plan_name=updated.plan.name if updated.plan else "",
        student_name=student.name if student else "",
    )


# Individual workout routes (moved to end to avoid conflicts)
@router.get("/{workout_id}", response_model=WorkoutResponse)
async def get_workout(
    workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Get workout details with exercises."""
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Check access
    if (
        not workout.is_public
        and workout.created_by_id != current_user.id
        and workout.organization_id is None
    ):
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
    workout_service = WorkoutService(db)
    workout = await workout_service.get_workout_by_id(workout_id)

    if not workout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workout not found",
        )

    # Check access
    if (
        not workout.is_public
        and workout.created_by_id != current_user.id
        and workout.organization_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return [WorkoutExerciseResponse.model_validate(we) for we in workout.workout_exercises]


@router.post("/", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
async def create_workout(
    request: WorkoutCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkoutResponse:
    """Create a new workout."""
    workout_service = WorkoutService(db)

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
        organization_id=request.organization_id,
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


# Co-Training endpoints

@router.get("/sessions/active", response_model=list[ActiveSessionResponse])
async def list_active_sessions(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> list[ActiveSessionResponse]:
    """List active sessions for students (trainer view - 'Students Now')."""
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


# ==================== Migration Endpoint ====================

@router.post("/migrate/rename-program-to-plan")
async def run_migration_rename_program_to_plan(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Run database migration to rename program tables to plan.

    Requires a secret key for security.
    """
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    results = []

    async with db.begin():
        # Check if old tables exist
        check_old = await db.execute(
            text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'workout_programs'
            """)
        )
        has_old = check_old.fetchone() is not None

        check_new = await db.execute(
            text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = 'training_plans'
            """)
        )
        has_new = check_new.fetchone() is not None

        if has_new and not has_old:
            return {"status": "already_migrated", "message": "Migration already completed"}

        if not has_old and not has_new:
            return {"status": "fresh_install", "message": "No tables to migrate"}

        # Both old and new tables exist - drop empty new tables and rename old ones
        try:
            if has_new and has_old:
                # Check if new tables are empty (SQLAlchemy created them)
                count_new = await db.execute(text("SELECT COUNT(*) FROM training_plans"))
                new_count = count_new.scalar() or 0

                count_old = await db.execute(text("SELECT COUNT(*) FROM workout_programs"))
                old_count = count_old.scalar() or 0

                results.append(f"Old workout_programs has {old_count} rows, new training_plans has {new_count} rows")

                if new_count == 0 and old_count > 0:
                    # Drop empty new tables and rename old ones
                    # First drop tables that depend on training_plans
                    await db.execute(text("DROP TABLE IF EXISTS plan_workouts CASCADE"))
                    results.append("Dropped empty plan_workouts")

                    await db.execute(text("DROP TABLE IF EXISTS plan_assignments CASCADE"))
                    results.append("Dropped empty plan_assignments")

                    await db.execute(text("DROP TABLE IF EXISTS training_plans CASCADE"))
                    results.append("Dropped empty training_plans")

            # 1. Rename workout_programs -> training_plans
            await db.execute(text("ALTER TABLE workout_programs RENAME TO training_plans"))
            results.append("Renamed workout_programs -> training_plans")

            # 2. Rename program_workouts -> plan_workouts
            await db.execute(text("ALTER TABLE program_workouts RENAME TO plan_workouts"))
            results.append("Renamed program_workouts -> plan_workouts")

            # 3. Rename program_id column in plan_workouts
            await db.execute(text("ALTER TABLE plan_workouts RENAME COLUMN program_id TO plan_id"))
            results.append("Renamed plan_workouts.program_id -> plan_id")

            # 4. Rename program_assignments -> plan_assignments
            await db.execute(text("ALTER TABLE program_assignments RENAME TO plan_assignments"))
            results.append("Renamed program_assignments -> plan_assignments")

            # 5. Rename program_id column in plan_assignments
            await db.execute(text("ALTER TABLE plan_assignments RENAME COLUMN program_id TO plan_id"))
            results.append("Renamed plan_assignments.program_id -> plan_id")

        except Exception as e:
            return {"status": "error", "message": str(e), "completed": results}

    return {"status": "success", "message": "Migration completed", "results": results}


@router.get("/debug/table-columns")
async def debug_table_columns(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Debug secret key"),
    table_name: str = Query(..., description="Table name"),
) -> dict:
    """Debug endpoint to check table columns."""
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret",
        )

    from sqlalchemy import text

    result = await db.execute(text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = :table_name
        ORDER BY ordinal_position
    """), {"table_name": table_name})
    columns = [{"name": row[0], "type": row[1], "nullable": row[2]} for row in result.fetchall()]

    return {"table": table_name, "columns": columns}


@router.get("/debug/test-list-plans")
async def debug_test_list_plans(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Debug secret key"),
) -> dict:
    """Debug endpoint to test list_plans query."""
    import os
    import traceback
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret",
        )

    from sqlalchemy import text

    try:
        # Try a simple query first
        result = await db.execute(text("SELECT COUNT(*) FROM training_plans"))
        count = result.scalar()

        # Try to get one record
        result2 = await db.execute(text("SELECT id, name, created_by_id FROM training_plans LIMIT 1"))
        row = result2.fetchone()

        return {
            "count": count,
            "sample_row": {"id": str(row[0]), "name": row[1], "created_by_id": str(row[2]) if row[2] else None} if row else None
        }
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.get("/debug/test-orm-plan")
async def debug_test_orm_plan(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Debug secret key"),
) -> dict:
    """Debug endpoint to test ORM query for training plans."""
    import os
    import traceback
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid secret",
        )

    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from src.domains.workouts.models import TrainingPlan

        # Test ORM query
        query = select(TrainingPlan).options(selectinload(TrainingPlan.plan_workouts)).limit(1)
        result = await db.execute(query)
        plan = result.scalars().first()

        if plan:
            return {
                "id": str(plan.id),
                "name": plan.name,
                "goal": plan.goal.value if plan.goal else None,
                "difficulty": plan.difficulty.value if plan.difficulty else None,
                "plan_workouts_count": len(plan.plan_workouts) if plan.plan_workouts else 0,
            }
        return {"message": "No plan found"}
    except Exception as e:
        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/migrate/add-source-template-id")
async def run_migration_add_source_template_id(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Add missing source_template_id column to training_plans table."""
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    async with db.begin():
        check_col = await db.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'training_plans'
                AND column_name = 'source_template_id'
            """)
        )
        if check_col.fetchone() is None:
            await db.execute(text("ALTER TABLE training_plans ADD COLUMN source_template_id UUID"))
            return {"status": "success", "message": "Added source_template_id column"}
        else:
            return {"status": "already_exists", "message": "source_template_id column already exists"}


@router.post("/migrate/fix-created-by-nullable")
async def run_migration_fix_created_by_nullable(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Fix created_by_id column to allow NULL for system templates."""
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    async with db.begin():
        try:
            await db.execute(text("ALTER TABLE training_plans ALTER COLUMN created_by_id DROP NOT NULL"))
            return {"status": "success", "message": "Made created_by_id nullable"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


@router.post("/migrate/add-workout-exercise-columns")
async def run_migration_add_workout_exercise_columns(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Add missing advanced technique columns to workout_exercises table."""
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    results = []

    async with db.begin():
        try:
            columns_to_add = [
                ("execution_instructions", "TEXT"),
                ("group_instructions", "TEXT"),
                ("isometric_seconds", "INTEGER"),
                ("exercise_group_id", "VARCHAR(50)"),
                ("exercise_group_order", "INTEGER DEFAULT 0 NOT NULL"),
            ]

            for col_name, col_type in columns_to_add:
                check_col = await db.execute(
                    text("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'workout_exercises'
                        AND column_name = :col_name
                    """),
                    {"col_name": col_name}
                )
                if check_col.fetchone() is None:
                    await db.execute(
                        text(f"ALTER TABLE workout_exercises ADD COLUMN {col_name} {col_type}")
                    )
                    results.append(f"Added column {col_name}")
                else:
                    results.append(f"Column {col_name} already exists")

            # Create technique_type enum if it doesn't exist
            check_enum = await db.execute(
                text("SELECT 1 FROM pg_type WHERE typname = 'technique_type_enum'")
            )
            if check_enum.fetchone() is None:
                await db.execute(text("""
                    CREATE TYPE technique_type_enum AS ENUM (
                        'Normal', 'Bi-Set', 'Tri-Set', 'Giant Set', 'Super-Set',
                        'Drop Set', 'Rest-Pause', 'Isometric', 'FST-7'
                    )
                """))
                results.append("Created technique_type_enum")
            else:
                results.append("technique_type_enum already exists")

            # Get enum values to find the correct default
            enum_values = await db.execute(
                text("SELECT enumlabel FROM pg_enum WHERE enumtypid = 'technique_type_enum'::regtype ORDER BY enumsortorder")
            )
            enum_list = [row[0] for row in enum_values.fetchall()]
            results.append(f"Enum values: {enum_list}")

            # Add technique_type column if it doesn't exist
            check_col = await db.execute(
                text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = 'workout_exercises'
                    AND column_name = 'technique_type'
                """)
            )
            if check_col.fetchone() is None:
                # Use the first enum value as default
                default_value = enum_list[0] if enum_list else "normal"
                await db.execute(
                    text(f"ALTER TABLE workout_exercises ADD COLUMN technique_type technique_type_enum DEFAULT '{default_value}' NOT NULL")
                )
                results.append(f"Added column technique_type with default '{default_value}'")
            else:
                results.append("Column technique_type already exists")

        except Exception as e:
            return {"status": "error", "message": str(e), "completed": results}

    return {"status": "success", "message": "Migration completed", "results": results}


@router.post("/migrate/add-plan-diet-columns")
async def run_migration_add_plan_diet_columns(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Add missing diet columns to training_plans table.

    Requires a secret key for security.
    """
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    results = []

    async with db.begin():
        try:
            # Check which columns are missing and add them
            columns_to_add = [
                ("include_diet", "BOOLEAN DEFAULT FALSE NOT NULL"),
                ("diet_type", "VARCHAR(50)"),
                ("daily_calories", "INTEGER"),
                ("protein_grams", "INTEGER"),
                ("carbs_grams", "INTEGER"),
                ("fat_grams", "INTEGER"),
                ("meals_per_day", "INTEGER"),
                ("diet_notes", "TEXT"),
            ]

            for col_name, col_type in columns_to_add:
                # Check if column exists
                check_col = await db.execute(
                    text("""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = 'public'
                        AND table_name = 'training_plans'
                        AND column_name = :col_name
                    """),
                    {"col_name": col_name}
                )
                if check_col.fetchone() is None:
                    await db.execute(
                        text(f"ALTER TABLE training_plans ADD COLUMN {col_name} {col_type}")
                    )
                    results.append(f"Added column {col_name}")
                else:
                    results.append(f"Column {col_name} already exists")

        except Exception as e:
            return {"status": "error", "message": str(e), "completed": results}

    return {"status": "success", "message": "Migration completed", "results": results}


# Prescription Notes endpoints

@router.post("/notes", response_model=PrescriptionNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_prescription_note(
    request: PrescriptionNoteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Create a new prescription note.

    Notes can be attached to:
    - plan: Training plan
    - workout: Specific workout
    - exercise: Workout exercise configuration
    - session: Completed session

    Trainers and students can both create notes.
    """
    from src.domains.users.models import UserRole

    # Determine author role based on user's primary role
    user_service = UserService(db)
    user = await user_service.get_user_by_id(current_user.id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Determine role - if user has TRAINER role, they're a trainer
    author_role = NoteAuthorRole.TRAINER if user.role == UserRole.TRAINER else NoteAuthorRole.STUDENT

    workout_service = WorkoutService(db)
    note = await workout_service.create_prescription_note(
        context_type=request.context_type,
        context_id=request.context_id,
        author_id=current_user.id,
        author_role=author_role,
        content=request.content,
        is_pinned=request.is_pinned,
        organization_id=request.organization_id,
    )

    return PrescriptionNoteResponse(
        id=note.id,
        context_type=note.context_type,
        context_id=note.context_id,
        author_id=note.author_id,
        author_role=note.author_role,
        author_name=user.name,
        content=note.content,
        is_pinned=note.is_pinned,
        read_at=note.read_at,
        read_by_id=note.read_by_id,
        organization_id=note.organization_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("/notes", response_model=PrescriptionNoteListResponse)
async def list_prescription_notes(
    context_type: Annotated[NoteContextType, Query()],
    context_id: Annotated[UUID, Query()],
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
) -> PrescriptionNoteListResponse:
    """List prescription notes for a specific context.

    Returns notes attached to the specified plan, workout, exercise, or session.
    """
    from src.domains.users.models import UserRole

    workout_service = WorkoutService(db)
    notes = await workout_service.list_prescription_notes(
        context_type=context_type,
        context_id=context_id,
        organization_id=organization_id,
    )

    # Get author names
    user_service = UserService(db)
    author_ids = {note.author_id for note in notes}
    authors = {}
    for author_id in author_ids:
        user = await user_service.get_user_by_id(author_id)
        if user:
            authors[author_id] = user.name

    # Determine current user's role for unread count
    user = await user_service.get_user_by_id(current_user.id)
    user_role = NoteAuthorRole.TRAINER if user and user.role == UserRole.TRAINER else NoteAuthorRole.STUDENT

    unread_count = await workout_service.count_unread_notes(
        context_type=context_type,
        context_id=context_id,
        for_role=user_role,
    )

    return PrescriptionNoteListResponse(
        notes=[
            PrescriptionNoteResponse(
                id=note.id,
                context_type=note.context_type,
                context_id=note.context_id,
                author_id=note.author_id,
                author_role=note.author_role,
                author_name=authors.get(note.author_id),
                content=note.content,
                is_pinned=note.is_pinned,
                read_at=note.read_at,
                read_by_id=note.read_by_id,
                organization_id=note.organization_id,
                created_at=note.created_at,
                updated_at=note.updated_at,
            )
            for note in notes
        ],
        total=len(notes),
        unread_count=unread_count,
    )


@router.get("/notes/{note_id}", response_model=PrescriptionNoteResponse)
async def get_prescription_note(
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
            detail="Note not found",
        )

    author_name = None
    if note.author:
        author_name = note.author.name

    return PrescriptionNoteResponse(
        id=note.id,
        context_type=note.context_type,
        context_id=note.context_id,
        author_id=note.author_id,
        author_role=note.author_role,
        author_name=author_name,
        content=note.content,
        is_pinned=note.is_pinned,
        read_at=note.read_at,
        read_by_id=note.read_by_id,
        organization_id=note.organization_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.put("/notes/{note_id}", response_model=PrescriptionNoteResponse)
async def update_prescription_note(
    note_id: UUID,
    request: PrescriptionNoteUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Update a prescription note.

    Only the author can update their own notes.
    """
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can update
    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can update this note",
        )

    note = await workout_service.update_prescription_note(
        note=note,
        content=request.content,
        is_pinned=request.is_pinned,
    )

    author_name = None
    if note.author:
        author_name = note.author.name

    return PrescriptionNoteResponse(
        id=note.id,
        context_type=note.context_type,
        context_id=note.context_id,
        author_id=note.author_id,
        author_role=note.author_role,
        author_name=author_name,
        content=note.content,
        is_pinned=note.is_pinned,
        read_at=note.read_at,
        read_by_id=note.read_by_id,
        organization_id=note.organization_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.post("/notes/{note_id}/read", response_model=PrescriptionNoteResponse)
async def mark_note_as_read(
    note_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrescriptionNoteResponse:
    """Mark a prescription note as read by the current user."""
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    note = await workout_service.mark_note_as_read(
        note=note,
        user_id=current_user.id,
    )

    author_name = None
    if note.author:
        author_name = note.author.name

    return PrescriptionNoteResponse(
        id=note.id,
        context_type=note.context_type,
        context_id=note.context_id,
        author_id=note.author_id,
        author_role=note.author_role,
        author_name=author_name,
        content=note.content,
        is_pinned=note.is_pinned,
        read_at=note.read_at,
        read_by_id=note.read_by_id,
        organization_id=note.organization_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prescription_note(
    note_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a prescription note.

    Only the author can delete their own notes.
    """
    workout_service = WorkoutService(db)
    note = await workout_service.get_prescription_note_by_id(note_id)

    if not note:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Note not found",
        )

    # Only author can delete
    if note.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author can delete this note",
        )

    await workout_service.delete_prescription_note(note)


@router.post("/migrate/add-prescription-notes-table")
async def run_migration_add_prescription_notes(
    db: Annotated[AsyncSession, Depends(get_db)],
    secret: str = Query(..., description="Migration secret key"),
) -> dict:
    """Create the prescription_notes table.

    Requires a secret key for security.
    """
    import os
    expected_secret = os.environ.get("MIGRATION_SECRET", "myfit-migrate-2026")

    if secret != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid migration secret",
        )

    from sqlalchemy import text

    results = []

    async with db.begin():
        try:
            # Check if table exists
            check_table = await db.execute(
                text("""
                    SELECT table_name FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_name = 'prescription_notes'
                """)
            )
            if check_table.fetchone() is not None:
                results.append("Table prescription_notes already exists")
                return {"status": "success", "message": "Table already exists", "results": results}

            # Create enum types first
            await db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'note_context_type_enum') THEN
                        CREATE TYPE note_context_type_enum AS ENUM ('plan', 'workout', 'exercise', 'session');
                    END IF;
                END
                $$;
            """))
            results.append("Created enum note_context_type_enum")

            await db.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'note_author_role_enum') THEN
                        CREATE TYPE note_author_role_enum AS ENUM ('trainer', 'student');
                    END IF;
                END
                $$;
            """))
            results.append("Created enum note_author_role_enum")

            # Create the table
            await db.execute(text("""
                CREATE TABLE prescription_notes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    context_type note_context_type_enum NOT NULL,
                    context_id UUID NOT NULL,
                    author_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    author_role note_author_role_enum NOT NULL,
                    content TEXT NOT NULL,
                    is_pinned BOOLEAN DEFAULT FALSE NOT NULL,
                    read_at TIMESTAMPTZ,
                    read_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
                );
            """))
            results.append("Created table prescription_notes")

            # Create indexes
            await db.execute(text("""
                CREATE INDEX idx_prescription_notes_context ON prescription_notes(context_type, context_id);
            """))
            results.append("Created index idx_prescription_notes_context")

            await db.execute(text("""
                CREATE INDEX idx_prescription_notes_author ON prescription_notes(author_id);
            """))
            results.append("Created index idx_prescription_notes_author")

            await db.execute(text("""
                CREATE INDEX idx_prescription_notes_org ON prescription_notes(organization_id);
            """))
            results.append("Created index idx_prescription_notes_org")

        except Exception as e:
            return {"status": "error", "message": str(e), "completed": results}

    return {"status": "success", "message": "Migration completed", "results": results}