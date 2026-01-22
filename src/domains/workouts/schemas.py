"""Workout schemas for request/response validation."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.domains.workouts.models import AssignmentStatus, Difficulty, ExerciseMode, MuscleGroup, NoteAuthorRole, NoteContextType, SessionStatus, SplitType, TechniqueType, WorkoutGoal


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
    # Advanced technique fields
    execution_instructions: str | None = None
    group_instructions: str | None = None
    isometric_seconds: int | None = Field(None, ge=0, le=60)
    technique_type: TechniqueType = TechniqueType.NORMAL
    exercise_group_id: str | None = Field(None, max_length=50)
    exercise_group_order: int = 0
    # Structured technique parameters
    drop_count: int | None = Field(None, ge=2, le=5)  # Dropset: number of drops
    rest_between_drops: int | None = Field(None, ge=0, le=30)  # Dropset: seconds between drops
    pause_duration: int | None = Field(None, ge=5, le=60)  # Rest-Pause/Cluster: pause in seconds
    mini_set_count: int | None = Field(None, ge=2, le=10)  # Cluster: number of mini-sets
    # Exercise mode (strength vs aerobic)
    exercise_mode: ExerciseMode = ExerciseMode.STRENGTH
    # Aerobic exercise fields - Duration mode
    duration_minutes: int | None = Field(None, ge=1, le=180)  # Total duration in minutes
    intensity: str | None = Field(None, max_length=20)  # low, moderate, high, max
    # Aerobic exercise fields - Interval mode
    work_seconds: int | None = Field(None, ge=5, le=300)  # Work interval duration
    interval_rest_seconds: int | None = Field(None, ge=5, le=300)  # Rest between intervals
    rounds: int | None = Field(None, ge=1, le=50)  # Number of rounds
    # Aerobic exercise fields - Distance mode
    distance_km: float | None = Field(None, ge=0.1, le=100)  # Distance in kilometers
    target_pace_min_per_km: float | None = Field(None, ge=2, le=15)  # Target pace (min/km)


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
    # Advanced technique fields
    execution_instructions: str | None = None
    group_instructions: str | None = None
    isometric_seconds: int | None = None
    technique_type: TechniqueType = TechniqueType.NORMAL
    exercise_group_id: str | None = None
    exercise_group_order: int = 0
    # Structured technique parameters
    drop_count: int | None = None
    rest_between_drops: int | None = None
    pause_duration: int | None = None
    mini_set_count: int | None = None
    # Exercise mode (strength vs aerobic)
    exercise_mode: ExerciseMode = ExerciseMode.STRENGTH
    # Aerobic exercise fields - Duration mode
    duration_minutes: int | None = None
    intensity: str | None = None
    # Aerobic exercise fields - Interval mode
    work_seconds: int | None = None
    interval_rest_seconds: int | None = None
    rounds: int | None = None
    # Aerobic exercise fields - Distance mode
    distance_km: float | None = None
    target_pace_min_per_km: float | None = None
    estimated_seconds: int = Field(default=0, description="Estimated time in seconds for this exercise")
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
    is_shared: bool = False  # If true, creates a shared co-training session


class SessionComplete(BaseModel):
    """Complete session request."""

    notes: str | None = None
    rating: int | None = Field(None, ge=1, le=5)
    student_feedback: str | None = None


class SessionResponse(BaseModel):
    """Session response."""

    id: UUID
    workout_id: UUID
    assignment_id: UUID | None = None
    user_id: UUID
    trainer_id: UUID | None = None
    is_shared: bool = False
    status: SessionStatus = SessionStatus.WAITING
    started_at: datetime
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    notes: str | None = None
    rating: int | None = None
    student_feedback: str | None = None
    trainer_notes: str | None = None
    is_completed: bool
    sets: list[SessionSetResponse] = []

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Session list item response."""

    id: UUID
    workout_id: UUID
    workout_name: str
    trainer_id: UUID | None = None
    is_shared: bool = False
    status: SessionStatus = SessionStatus.WAITING
    started_at: datetime
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    is_completed: bool

    class Config:
        from_attributes = True


# Co-Training schemas

class SessionJoinRequest(BaseModel):
    """Request for trainer to join a session."""

    session_id: UUID


class SessionJoinResponse(BaseModel):
    """Response after trainer joins session."""

    session_id: UUID
    trainer_id: UUID
    student_id: UUID
    workout_name: str
    is_shared: bool = True
    status: SessionStatus
    message: str = "Conectado a sessao com sucesso"

    class Config:
        from_attributes = True


class SessionLeaveRequest(BaseModel):
    """Request for trainer to leave a session."""

    session_id: UUID


class TrainerAdjustmentCreate(BaseModel):
    """Create trainer adjustment during co-training."""

    session_id: UUID
    exercise_id: UUID
    set_number: int | None = Field(None, ge=1)
    suggested_weight_kg: float | None = Field(None, ge=0)
    suggested_reps: int | None = Field(None, ge=1)
    note: str | None = Field(None, max_length=255)


class TrainerAdjustmentResponse(BaseModel):
    """Trainer adjustment response."""

    id: UUID
    session_id: UUID
    trainer_id: UUID
    exercise_id: UUID
    set_number: int | None = None
    suggested_weight_kg: float | None = None
    suggested_reps: int | None = None
    note: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class SessionMessageCreate(BaseModel):
    """Create message during co-training session."""

    session_id: UUID
    message: str = Field(..., min_length=1, max_length=500)


class SessionMessageResponse(BaseModel):
    """Session message response."""

    id: UUID
    session_id: UUID
    sender_id: UUID
    sender_name: str | None = None
    message: str
    sent_at: datetime
    is_read: bool = False

    class Config:
        from_attributes = True


class SessionStatusUpdate(BaseModel):
    """Update session status."""

    status: SessionStatus


class ActiveSessionResponse(BaseModel):
    """Response for active sessions (students currently training)."""

    id: UUID
    workout_id: UUID
    workout_name: str
    user_id: UUID
    student_name: str
    student_avatar: str | None = None
    trainer_id: UUID | None = None
    is_shared: bool = False
    status: SessionStatus
    started_at: datetime
    current_exercise_index: int = 0
    total_exercises: int = 0
    completed_sets: int = 0

    class Config:
        from_attributes = True


# Plan schemas

class PlanWorkoutInput(BaseModel):
    """Input for adding workout to plan."""

    workout_id: UUID | None = None  # None if creating new workout inline
    label: str = Field(default="A", max_length=50)
    order: int = 0
    day_of_week: int | None = Field(None, ge=0, le=6)
    # For inline workout creation
    workout_name: str | None = Field(None, min_length=2, max_length=255)
    workout_exercises: list[WorkoutExerciseInput] | None = None
    # Target muscle groups for this workout
    muscle_groups: list[str] | None = Field(default=None, description="Target muscle groups")


class PlanWorkoutResponse(BaseModel):
    """Plan workout response."""

    id: UUID
    workout_id: UUID
    order: int
    label: str
    day_of_week: int | None = None
    workout: WorkoutResponse

    class Config:
        from_attributes = True


class PlanCreate(BaseModel):
    """Create plan request."""

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    goal: WorkoutGoal = WorkoutGoal.HYPERTROPHY
    difficulty: Difficulty = Difficulty.INTERMEDIATE
    split_type: SplitType = SplitType.ABC
    duration_weeks: int | None = Field(None, ge=1, le=52)
    target_workout_minutes: int | None = Field(None, ge=15, le=180)
    # Diet configuration
    include_diet: bool = False
    diet_type: str | None = Field(None, max_length=50)
    daily_calories: int | None = Field(None, ge=500, le=10000)
    protein_grams: int | None = Field(None, ge=0, le=1000)
    carbs_grams: int | None = Field(None, ge=0, le=2000)
    fat_grams: int | None = Field(None, ge=0, le=500)
    meals_per_day: int | None = Field(None, ge=1, le=10)
    diet_notes: str | None = None
    # Flags
    is_template: bool = False
    is_public: bool = False
    organization_id: UUID | None = None
    workouts: list[PlanWorkoutInput] | None = None


class PlanUpdate(BaseModel):
    """Update plan request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    goal: WorkoutGoal | None = None
    difficulty: Difficulty | None = None
    split_type: SplitType | None = None
    duration_weeks: int | None = Field(None, ge=1, le=52)
    clear_duration_weeks: bool = Field(False, description="Set to true to clear duration (continuous plan)")
    target_workout_minutes: int | None = Field(None, ge=15, le=180)
    # Diet configuration
    include_diet: bool | None = None
    diet_type: str | None = Field(None, max_length=50)
    daily_calories: int | None = Field(None, ge=500, le=10000)
    protein_grams: int | None = Field(None, ge=0, le=1000)
    carbs_grams: int | None = Field(None, ge=0, le=2000)
    fat_grams: int | None = Field(None, ge=0, le=500)
    meals_per_day: int | None = Field(None, ge=1, le=10)
    diet_notes: str | None = None
    # Flags
    is_template: bool | None = None
    is_public: bool | None = None
    workouts: list[PlanWorkoutInput] | None = None


class PlanResponse(BaseModel):
    """Plan response."""

    id: UUID
    name: str
    description: str | None = None
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    target_workout_minutes: int | None = None
    # Diet configuration
    include_diet: bool = False
    diet_type: str | None = None
    daily_calories: int | None = None
    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    meals_per_day: int | None = None
    diet_notes: str | None = None
    # Flags
    is_template: bool
    is_public: bool
    created_by_id: UUID
    organization_id: UUID | None = None
    source_template_id: UUID | None = None
    created_at: datetime
    plan_workouts: list[PlanWorkoutResponse] = []

    @field_validator("source_template_id", mode="before")
    @classmethod
    def convert_source_template_id(cls, v: str | UUID | None) -> UUID | None:
        """Convert string to UUID for SQLite TEXT column compatibility."""
        if v is None:
            return None
        if isinstance(v, UUID):
            return v
        try:
            return UUID(v)
        except (ValueError, TypeError):
            return None

    class Config:
        from_attributes = True


class PlanListResponse(BaseModel):
    """Plan list item response."""

    id: UUID
    name: str
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    is_template: bool
    is_public: bool
    workout_count: int = 0
    created_by_id: UUID | None = None
    source_template_id: UUID | None = None
    created_at: datetime

    @field_validator("source_template_id", mode="before")
    @classmethod
    def convert_source_template_id(cls, v: str | UUID | None) -> UUID | None:
        """Convert string to UUID for SQLite TEXT column compatibility."""
        if v is None:
            return None
        if isinstance(v, UUID):
            return v
        try:
            return UUID(v)
        except (ValueError, TypeError):
            return None

    class Config:
        from_attributes = True


class CatalogPlanResponse(BaseModel):
    """Catalog template response with creator info."""

    id: UUID
    name: str
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int | None = None
    workout_count: int = 0
    creator_name: str | None = None
    created_by_id: UUID | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# Plan assignment schemas

class PlanAssignmentCreate(BaseModel):
    """Create plan assignment request."""

    plan_id: UUID
    student_id: UUID
    start_date: date
    end_date: date | None = None
    notes: str | None = None
    organization_id: UUID | None = None


class PlanAssignmentUpdate(BaseModel):
    """Update plan assignment request."""

    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class PlanAssignmentResponse(BaseModel):
    """Plan assignment response."""

    id: UUID
    plan_id: UUID
    student_id: UUID
    trainer_id: UUID
    organization_id: UUID | None = None
    start_date: date
    end_date: date | None = None
    is_active: bool
    notes: str | None = None
    status: AssignmentStatus = AssignmentStatus.PENDING
    accepted_at: datetime | None = None
    declined_reason: str | None = None
    created_at: datetime
    plan_name: str
    student_name: str
    plan_duration_weeks: int | None = None

    class Config:
        from_attributes = True


class AssignmentAcceptRequest(BaseModel):
    """Request to accept or decline a plan assignment."""

    accept: bool = True
    declined_reason: str | None = Field(None, max_length=500)


# AI Suggestion schemas

class WorkoutContextInfo(BaseModel):
    """Workout context information for AI suggestions."""

    workout_name: str | None = Field(default=None, description="Name of the workout")
    workout_label: str | None = Field(default=None, description="Workout label (A, B, C, etc.)")
    plan_name: str | None = Field(default=None, description="Name of the plan")
    plan_goal: WorkoutGoal | None = Field(default=None, description="Plan training goal")
    plan_split_type: SplitType | None = Field(default=None, description="Plan split type")
    existing_exercises: list[str] | None = Field(default=None, description="Existing exercise names in workout")
    existing_exercise_count: int = Field(default=0, description="Number of exercises already in workout")


class ExerciseSuggestionRequest(BaseModel):
    """Request for AI exercise suggestions."""

    muscle_groups: list[str] = Field(..., min_length=1, description="Target muscle groups")
    goal: WorkoutGoal = Field(default=WorkoutGoal.HYPERTROPHY, description="Training goal")
    difficulty: Difficulty = Field(default=Difficulty.INTERMEDIATE, description="Difficulty level")
    count: int = Field(default=6, ge=1, le=12, description="Number of exercises to suggest")
    exclude_exercise_ids: list[UUID] | None = Field(default=None, description="Exercises to exclude")
    # Workout context
    context: WorkoutContextInfo | None = Field(default=None, description="Workout/program context")
    allow_advanced_techniques: bool = Field(default=True, description="Allow suggesting advanced techniques")
    allowed_techniques: list[str] | None = Field(
        default=None,
        description="Specific techniques to use. If provided, ONLY these techniques are allowed (e.g., ['biset', 'superset'])"
    )


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
    # Advanced technique fields
    technique_type: TechniqueType = Field(default=TechniqueType.NORMAL, description="Exercise technique type")
    exercise_group_id: str | None = Field(default=None, description="Group ID for bi-set, tri-set, etc.")
    exercise_group_order: int = Field(default=0, description="Order within group")
    execution_instructions: str | None = Field(default=None, description="Execution instructions")
    isometric_seconds: int | None = Field(default=None, description="Isometric hold duration")


class ExerciseSuggestionResponse(BaseModel):
    """Response with AI exercise suggestions."""

    suggestions: list[SuggestedExercise]
    message: str | None = Field(default=None, description="AI explanation or tips")


# AI Plan Generation schemas

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


class AIGeneratePlanRequest(BaseModel):
    """Request for AI-generated training plan."""

    goal: WorkoutGoal = Field(..., description="Training goal")
    difficulty: Difficulty = Field(..., description="Experience level")
    days_per_week: int = Field(..., ge=2, le=6, description="Training days per week")
    minutes_per_session: int = Field(..., ge=20, le=120, description="Minutes available per session")
    equipment: str = Field(..., description="Equipment availability")
    injuries: list[str] | None = Field(default=None, description="Injuries or restrictions")
    preferences: str = Field(default="mixed", description="Training preferences")
    duration_weeks: int = Field(default=8, ge=4, le=16, description="Plan duration in weeks")


class AIGeneratedWorkout(BaseModel):
    """AI-generated workout structure."""

    label: str
    name: str
    order: int
    target_muscles: list[str] = Field(default_factory=list, description="Target muscle groups for this workout")
    exercises: list[SuggestedExercise]


class AIGeneratePlanResponse(BaseModel):
    """Response with AI-generated plan structure."""

    name: str
    description: str | None = None
    goal: WorkoutGoal
    difficulty: Difficulty
    split_type: SplitType
    duration_weeks: int
    workouts: list[AIGeneratedWorkout]
    message: str | None = Field(default=None, description="AI tips or recommendations")


# Prescription Note schemas

class PrescriptionNoteCreate(BaseModel):
    """Create prescription note request."""

    context_type: NoteContextType
    context_id: UUID
    content: str = Field(min_length=1, max_length=5000)
    is_pinned: bool = False
    organization_id: UUID | None = None


class PrescriptionNoteUpdate(BaseModel):
    """Update prescription note request."""

    content: str | None = Field(None, min_length=1, max_length=5000)
    is_pinned: bool | None = None


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class PrescriptionNoteResponse(BaseModel):
    """Prescription note response."""

    id: UUID
    context_type: NoteContextType
    context_id: UUID
    author_id: UUID
    author_role: NoteAuthorRole
    author_name: str | None = None
    content: str
    is_pinned: bool
    read_at: datetime | None = None
    read_by_id: UUID | None = None
    organization_id: UUID | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
        alias_generator = to_camel
        populate_by_name = True


class PrescriptionNoteListResponse(BaseModel):
    """List of prescription notes response."""

    notes: list[PrescriptionNoteResponse]
    total: int
    unread_count: int = 0

    class Config:
        alias_generator = to_camel
        populate_by_name = True
