"""Workout router with exercise, workout, assignment, and session endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.service import UserService
from src.domains.workouts.models import Difficulty, MuscleGroup, SplitType, WorkoutGoal
from src.domains.workouts.schemas import (
    AIGenerateProgramRequest,
    AIGenerateProgramResponse,
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    CatalogProgramResponse,
    ExerciseCreate,
    ExerciseResponse,
    ExerciseSuggestionRequest,
    ExerciseSuggestionResponse,
    ExerciseUpdate,
    ProgramAssignmentCreate,
    ProgramAssignmentResponse,
    ProgramAssignmentUpdate,
    ProgramCreate,
    ProgramListResponse,
    ProgramResponse,
    ProgramUpdate,
    ProgramWorkoutInput,
    SessionComplete,
    SessionListResponse,
    SessionResponse,
    SessionSetInput,
    SessionSetResponse,
    SessionStart,
    SuggestedExercise,
    WorkoutCreate,
    WorkoutExerciseInput,
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
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
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

    result = await ai_service.suggest_exercises(
        available_exercises=exercises_data,
        muscle_groups=request.muscle_groups,
        goal=request.goal,
        difficulty=request.difficulty,
        count=request.count,
        exclude_ids=exclude_ids,
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


# Program endpoints

@router.get("/programs", response_model=list[ProgramListResponse])
async def list_programs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProgramListResponse]:
    """List workout programs for the current user."""
    workout_service = WorkoutService(db)
    programs = await workout_service.list_programs(
        user_id=current_user.id,
        organization_id=organization_id,
        templates_only=templates_only,
        search=search,
        limit=limit,
        offset=offset,
    )

    return [
        ProgramListResponse(
            id=p.id,
            name=p.name,
            goal=p.goal,
            difficulty=p.difficulty,
            split_type=p.split_type,
            duration_weeks=p.duration_weeks,
            is_template=p.is_template,
            is_public=p.is_public,
            workout_count=len(p.program_workouts),
            created_at=p.created_at,
        )
        for p in programs
    ]


@router.get("/programs/catalog", response_model=list[CatalogProgramResponse])
async def get_catalog_templates(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    goal: Annotated[WorkoutGoal | None, Query()] = None,
    difficulty: Annotated[Difficulty | None, Query()] = None,
    split_type: Annotated[SplitType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CatalogProgramResponse]:
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
    return [CatalogProgramResponse(**t) for t in templates]


@router.post("/programs/generate-ai", response_model=AIGenerateProgramResponse)
async def generate_program_with_ai(
    request: AIGenerateProgramRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AIGenerateProgramResponse:
    """Generate a workout program using AI based on questionnaire answers."""
    workout_service = WorkoutService(db)
    result = await workout_service.generate_program_with_ai(
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
    return AIGenerateProgramResponse(**result)


@router.get("/programs/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramResponse:
    """Get program details with workouts."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    # Check access
    if (
        not program.is_public
        and program.created_by_id != current_user.id
        and program.organization_id is None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ProgramResponse.model_validate(program)


@router.post("/programs", response_model=ProgramResponse, status_code=status.HTTP_201_CREATED)
async def create_program(
    request: ProgramCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramResponse:
    """Create a new workout program."""
    workout_service = WorkoutService(db)

    program = await workout_service.create_program(
        created_by_id=current_user.id,
        name=request.name,
        description=request.description,
        goal=request.goal,
        difficulty=request.difficulty,
        split_type=request.split_type,
        duration_weeks=request.duration_weeks,
        is_template=request.is_template,
        is_public=request.is_public,
        organization_id=request.organization_id,
    )

    # Add workouts if provided
    if request.workouts:
        for pw in request.workouts:
            if pw.workout_id:
                # Use existing workout
                await workout_service.add_workout_to_program(
                    program_id=program.id,
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
                        )
                # Add to program
                await workout_service.add_workout_to_program(
                    program_id=program.id,
                    workout_id=new_workout.id,
                    label=pw.label,
                    order=pw.order,
                    day_of_week=pw.day_of_week,
                )

        # Refresh to get workouts
        program = await workout_service.get_program_by_id(program.id)

    return ProgramResponse.model_validate(program)


@router.put("/programs/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: UUID,
    request: ProgramUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramResponse:
    """Update a program (owner only)."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    if program.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own programs",
        )

    updated = await workout_service.update_program(
        program=program,
        name=request.name,
        description=request.description,
        goal=request.goal,
        difficulty=request.difficulty,
        split_type=request.split_type,
        duration_weeks=request.duration_weeks,
        is_template=request.is_template,
        is_public=request.is_public,
    )

    return ProgramResponse.model_validate(updated)


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program(
    program_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a program (owner only)."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    if program.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own programs",
        )

    await workout_service.delete_program(program)


@router.post("/programs/{program_id}/duplicate", response_model=ProgramResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_program(
    program_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    duplicate_workouts: Annotated[bool, Query()] = True,
) -> ProgramResponse:
    """Duplicate a program for the current user."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    # Check access
    if not program.is_public and program.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    new_program = await workout_service.duplicate_program(
        program=program,
        new_owner_id=current_user.id,
        duplicate_workouts=duplicate_workouts,
    )

    # Refresh to get full data
    new_program = await workout_service.get_program_by_id(new_program.id)
    return ProgramResponse.model_validate(new_program)


@router.post("/programs/{program_id}/workouts", response_model=ProgramResponse)
async def add_workout_to_program(
    program_id: UUID,
    request: ProgramWorkoutInput,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramResponse:
    """Add a workout to a program."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    if program.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own programs",
        )

    if request.workout_id:
        await workout_service.add_workout_to_program(
            program_id=program_id,
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
            difficulty=program.difficulty,
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
                )
        await workout_service.add_workout_to_program(
            program_id=program_id,
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

    # Refresh program
    program = await workout_service.get_program_by_id(program_id)
    return ProgramResponse.model_validate(program)


@router.delete("/programs/{program_id}/workouts/{program_workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_workout_from_program(
    program_id: UUID,
    program_workout_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a workout from a program."""
    workout_service = WorkoutService(db)
    program = await workout_service.get_program_by_id(program_id)

    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    if program.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own programs",
        )

    await workout_service.remove_workout_from_program(program_workout_id)


# Program assignment endpoints

@router.get("/programs/assignments", response_model=list[ProgramAssignmentResponse])
async def list_program_assignments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    as_trainer: Annotated[bool, Query()] = False,
    active_only: Annotated[bool, Query()] = True,
) -> list[ProgramAssignmentResponse]:
    """List program assignments (as student or trainer)."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    if as_trainer:
        assignments = await workout_service.list_trainer_program_assignments(
            trainer_id=current_user.id,
            active_only=active_only,
        )
    else:
        assignments = await workout_service.list_student_program_assignments(
            student_id=current_user.id,
            active_only=active_only,
        )

    result = []
    for a in assignments:
        student = await user_service.get_user_by_id(a.student_id)
        result.append(
            ProgramAssignmentResponse(
                id=a.id,
                program_id=a.program_id,
                student_id=a.student_id,
                trainer_id=a.trainer_id,
                organization_id=a.organization_id,
                start_date=a.start_date,
                end_date=a.end_date,
                is_active=a.is_active,
                notes=a.notes,
                created_at=a.created_at,
                program_name=a.program.name if a.program else "",
                student_name=student.name if student else "",
            )
        )

    return result


@router.post("/programs/assignments", response_model=ProgramAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_program_assignment(
    request: ProgramAssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramAssignmentResponse:
    """Assign a program to a student."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    # Verify program exists
    program = await workout_service.get_program_by_id(request.program_id)
    if not program:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Program not found",
        )

    # Verify student exists
    student = await user_service.get_user_by_id(request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )

    assignment = await workout_service.create_program_assignment(
        program_id=request.program_id,
        student_id=request.student_id,
        trainer_id=current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        notes=request.notes,
        organization_id=request.organization_id,
    )

    return ProgramAssignmentResponse(
        id=assignment.id,
        program_id=assignment.program_id,
        student_id=assignment.student_id,
        trainer_id=assignment.trainer_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        created_at=assignment.created_at,
        program_name=program.name,
        student_name=student.name,
    )


@router.put("/programs/assignments/{assignment_id}", response_model=ProgramAssignmentResponse)
async def update_program_assignment(
    assignment_id: UUID,
    request: ProgramAssignmentUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProgramAssignmentResponse:
    """Update a program assignment (trainer only)."""
    workout_service = WorkoutService(db)
    user_service = UserService(db)

    assignment = await workout_service.get_program_assignment_by_id(assignment_id)
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

    updated = await workout_service.update_program_assignment(
        assignment=assignment,
        start_date=request.start_date,
        end_date=request.end_date,
        is_active=request.is_active,
        notes=request.notes,
    )

    student = await user_service.get_user_by_id(updated.student_id)

    return ProgramAssignmentResponse(
        id=updated.id,
        program_id=updated.program_id,
        student_id=updated.student_id,
        trainer_id=updated.trainer_id,
        organization_id=updated.organization_id,
        start_date=updated.start_date,
        end_date=updated.end_date,
        is_active=updated.is_active,
        notes=updated.notes,
        created_at=updated.created_at,
        program_name=updated.program.name if updated.program else "",
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
