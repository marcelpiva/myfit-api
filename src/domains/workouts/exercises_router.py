"""Exercise-related endpoints."""
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from fastapi import status as http_status
from fastapi.exceptions import HTTPException
from pydantic import BaseModel as PydanticBaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.workouts.models import MuscleGroup, TechniqueType
from src.domains.workouts.schemas import (
    ExerciseCreate,
    ExerciseResponse,
    ExerciseSuggestionRequest,
    ExerciseSuggestionResponse,
    ExerciseUpdate,
    SuggestedExercise,
)
from src.domains.workouts.service import WorkoutService

logger = logging.getLogger(__name__)

exercises_router = APIRouter()


@exercises_router.get("/exercises", response_model=list[ExerciseResponse])
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


@exercises_router.get("/exercises/{exercise_id}", response_model=ExerciseResponse)
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
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    # Check access
    if not exercise.is_public and exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return ExerciseResponse.model_validate(exercise)


@exercises_router.post("/exercises", response_model=ExerciseResponse, status_code=http_status.HTTP_201_CREATED)
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


@exercises_router.put("/exercises/{exercise_id}", response_model=ExerciseResponse)
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
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    if exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
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


class ExerciseMediaUploadResponse(PydanticBaseModel):
    """Response for exercise media upload."""

    url: str
    content_type: str


@exercises_router.post("/exercises/{exercise_id}/media")
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
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Exercise not found",
        )

    # Only owner can upload media for custom exercises
    if exercise.created_by_id != current_user.id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
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
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Images: JPEG, PNG, WebP, GIF. Videos: MP4, MOV, WebM",
        )
    except FileTooLargeError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except StorageError as e:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
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


@exercises_router.post("/exercises/suggest", response_model=ExerciseSuggestionResponse)
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
