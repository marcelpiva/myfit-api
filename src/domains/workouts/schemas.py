"""Workout schemas for request/response validation."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.workouts.models import Difficulty, MuscleGroup, SplitType, WorkoutGoal


# Exercise schemas

class ExerciseCreate(BaseModel):
    """Create exercise request."""

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    muscle_group: MuscleGroup
    secondary_muscles: list[str] | None = None
    equipment: list[str] | None = None
    video_url: str | None = Field(None, max_length=500)
    image_url: str | None = Field(None, max_length=500)
    instructions: str | None = None


class ExerciseUpdate(BaseModel):
    """Update exercise request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    muscle_group: MuscleGroup | None = None
    secondary_muscles: list[str] | None = None
    equipment: list[str] | None = None
    video_url: str | None = Field(None, max_length=500)
    image_url: str | None = Field(None, max_length=500)
    instructions: str | None = None


class ExerciseResponse(BaseModel):
    """Exercise response."""

    id: UUID
    name: str
    description: str | None = None
    muscle_group: MuscleGroup
    secondary_muscles: list[str] | None = None
    equipment: list[str] | None = None
    video_url: str | None = None
    image_url: str | None = None
    instructions: str | None = None
    is_custom: bool
    is_public: bool
    created_by_id: UUID | None = None

    class Config:
        from_attributes = True


# Workout schemas

class WorkoutExerciseInput(BaseModel):
    """Input for adding exercise to workout."""

    exercise_id: UUID
    order: int = 0
    sets: int = Field(default=3, ge=1, le=20)
    reps: str = Field(default="10-12", max_length=50)
    rest_seconds: int = Field(default=60, ge=0, le=600)
    notes: str | None = None
    superset_with: UUID | None = None


class WorkoutExerciseResponse(BaseModel):
    """Workout exercise response."""

    id: UUID
    exercise_id: UUID
    order: int
    sets: int
    reps: str
    rest_seconds: int
    notes: str | None = None
    superset_with: UUID | None = None
    exercise: ExerciseResponse

    class Config:
        from_attributes = True


class WorkoutCreate(BaseModel):
    """Create workout request."""

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    estimated_duration_min: int = Field(default=60, ge=10, le=300)
    target_muscles: list[str] | None = None
    tags: list[str] | None = None
    is_template: bool = False
    is_public: bool = False
    organization_id: UUID | None = None
    exercises: list[WorkoutExerciseInput] | None = None


class WorkoutUpdate(BaseModel):
    """Update workout request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    difficulty: Difficulty | None = None
    estimated_duration_min: int | None = Field(None, ge=10, le=300)
    target_muscles: list[str] | None = None
    tags: list[str] | None = None
    is_template: bool | None = None
    is_public: bool | None = None


class WorkoutResponse(BaseModel):
    """Workout response."""

    id: UUID
    name: str
    description: str | None = None
    difficulty: Difficulty
    estimated_duration_min: int
    target_muscles: list[str] | None = None
    tags: list[str] | None = None
    is_template: bool
    is_public: bool
    created_by_id: UUID
    organization_id: UUID | None = None
    created_at: datetime
    exercises: list[WorkoutExerciseResponse] = []

    class Config:
        from_attributes = True


class WorkoutListResponse(BaseModel):
    """Workout list item response."""

    id: UUID
    name: str
    difficulty: Difficulty
    estimated_duration_min: int
    is_template: bool
    exercise_count: int = 0

    class Config:
        from_attributes = True


# Assignment schemas

class AssignmentCreate(BaseModel):
    """Create assignment request."""

    workout_id: UUID
    student_id: UUID
    start_date: date
    end_date: date | None = None
    notes: str | None = None
    organization_id: UUID | None = None


class AssignmentUpdate(BaseModel):
    """Update assignment request."""

    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class AssignmentResponse(BaseModel):
    """Assignment response."""

    id: UUID
    workout_id: UUID
    student_id: UUID
    trainer_id: UUID
    organization_id: UUID | None = None
    start_date: date
    end_date: date | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    workout_name: str
    student_name: str

    class Config:
        from_attributes = True


# Session schemas

class SessionSetInput(BaseModel):
    """Input for recording a set."""

    exercise_id: UUID
    set_number: int = Field(ge=1)
    reps_completed: int = Field(ge=0)
    weight_kg: float | None = Field(None, ge=0)
    duration_seconds: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)


class SessionSetResponse(BaseModel):
    """Session set response."""

    id: UUID
    exercise_id: UUID
    set_number: int
    reps_completed: int
    weight_kg: float | None = None
    duration_seconds: int | None = None
    notes: str | None = None
    performed_at: datetime

    class Config:
        from_attributes = True


class SessionStart(BaseModel):
    """Start session request."""

    workout_id: UUID
    assignment_id: UUID | None = None


class SessionComplete(BaseModel):
    """Complete session request."""

    notes: str | None = None
    rating: int | None = Field(None, ge=1, le=5)


class SessionResponse(BaseModel):
    """Session response."""

    id: UUID
    workout_id: UUID
    assignment_id: UUID | None = None
    user_id: UUID
    started_at: datetime
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    rating: int | None = None
    is_completed: bool
    sets: list[SessionSetResponse] = []

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Session list item response."""

    id: UUID
    workout_id: UUID
    workout_name: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    is_completed: bool

    class Config:
        from_attributes = True


# Program schemas

class ProgramWorkoutInput(BaseModel):
    """Input for adding workout to program."""

    workout_id: UUID | None = None  # None if creating new workout inline
    label: str = Field(default="A", max_length=50)
    order: int = 0
    day_of_week: int | None = Field(None, ge=0, le=6)
    # For inline workout creation
    workout_name: str | None = Field(None, min_length=2, max_length=255)
    workout_exercises: list[WorkoutExerciseInput] | None = None


class ProgramWorkoutResponse(BaseModel):
    """Program workout response."""

    id: UUID
    workout_id: UUID
    order: int
    label: str
    day_of_week: int | None = None
    workout: WorkoutResponse

    class Config:
        from_attributes = True


class ProgramCreate(BaseModel):
    """Create program request."""

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    goal: WorkoutGoal = WorkoutGoal.HYPERTROPHY
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    split_type: SplitType = SplitType.ABC
    duration_weeks: int | None = Field(None, ge=1, le=52)
    is_template: bool = False
    is_public: bool = False
    organization_id: UUID | None = None
    workouts: list[ProgramWorkoutInput] | None = None


class ProgramUpdate(BaseModel):
    """Update program request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    goal: WorkoutGoal | None = None
    difficulty: Difficulty | None = None
    split_type: SplitType | None = None
    duration_weeks: int | None = Field(None, ge=1, le=52)
    is_template: bool | None = None
    is_public: bool | None = None


class ProgramResponse(BaseModel):
    """Program response."""

    id: UUID
    name: str
    description: str | None = None
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    is_template: bool
    is_public: bool
    created_by_id: UUID
    organization_id: UUID | None = None
    created_at: datetime
    program_workouts: list[ProgramWorkoutResponse] = []

    class Config:
        from_attributes = True


class ProgramListResponse(BaseModel):
    """Program list item response."""

    id: UUID
    name: str
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    is_template: bool
    is_public: bool
    workout_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class CatalogProgramResponse(BaseModel):
    """Catalog template response with creator info."""

    id: UUID
    name: str
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    workout_count: int = 0
    creator_name: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# Program assignment schemas

class ProgramAssignmentCreate(BaseModel):
    """Create program assignment request."""

    program_id: UUID
    student_id: UUID
    start_date: date
    end_date: date | None = None
    notes: str | None = None
    organization_id: UUID | None = None


class ProgramAssignmentUpdate(BaseModel):
    """Update program assignment request."""

    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class ProgramAssignmentResponse(BaseModel):
    """Program assignment response."""

    id: UUID
    program_id: UUID
    student_id: UUID
    trainer_id: UUID
    organization_id: UUID | None = None
    start_date: date
    end_date: date | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    program_name: str
    student_name: str

    class Config:
        from_attributes = True


# AI Suggestion schemas

class ExerciseSuggestionRequest(BaseModel):
    """Request for AI exercise suggestions."""

    muscle_groups: list[str] = Field(..., min_length=1, description="Target muscle groups")
    goal: WorkoutGoal = Field(default=WorkoutGoal.HYPERTROPHY, description="Training goal")
    difficulty: Difficulty = Field(default=Difficulty.INTERMEDIATE, description="Difficulty level")
    count: int = Field(default=6, ge=1, le=12, description="Number of exercises to suggest")
    exclude_exercise_ids: list[UUID] | None = Field(default=None, description="Exercises to exclude")


class SuggestedExercise(BaseModel):
    """A suggested exercise with configuration."""

    exercise_id: UUID
    name: str
    muscle_group: MuscleGroup
    sets: int = Field(default=3, ge=1, le=10)
    reps: str = Field(default="10-12")
    rest_seconds: int = Field(default=60, ge=0, le=300)
    order: int = 0
    reason: str | None = Field(default=None, description="AI reason for this suggestion")


class ExerciseSuggestionResponse(BaseModel):
    """Response with AI exercise suggestions."""

    suggestions: list[SuggestedExercise]
    message: str | None = Field(default=None, description="AI explanation or tips")


# AI Program Generation schemas

class EquipmentType(str):
    """Equipment availability types."""

    FULL_GYM = "full_gym"
    HOME_BASIC = "home_basic"
    HOME_DUMBBELLS = "home_dumbbells"
    HOME_FULL = "home_full"
    BODYWEIGHT = "bodyweight"


class TrainingPreference(str):
    """Training preference types."""

    MACHINES = "machines"
    FREE_WEIGHTS = "free_weights"
    MIXED = "mixed"
    BODYWEIGHT = "bodyweight"


class AIGenerateProgramRequest(BaseModel):
    """Request for AI-generated workout program."""

    goal: WorkoutGoal = Field(..., description="Training goal")
    difficulty: Difficulty = Field(..., description="Experience level")
    days_per_week: int = Field(..., ge=2, le=6, description="Training days per week")
    minutes_per_session: int = Field(..., ge=20, le=120, description="Minutes available per session")
    equipment: str = Field(..., description="Equipment availability")
    injuries: list[str] | None = Field(default=None, description="Injuries or restrictions")
    preferences: str = Field(default="mixed", description="Training preferences")
    duration_weeks: int = Field(default=8, ge=4, le=16, description="Program duration in weeks")


class AIGeneratedWorkout(BaseModel):
    """AI-generated workout structure."""

    label: str
    name: str
    order: int
    exercises: list[SuggestedExercise]


class AIGenerateProgramResponse(BaseModel):
    """Response with AI-generated program structure."""

    name: str
    description: str | None = None
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int
    workouts: list[AIGeneratedWorkout]
    message: str | None = Field(default=None, description="AI tips or recommendations")
