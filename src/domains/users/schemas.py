"""User schemas for request/response validation."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.users.models import Gender, Theme, Units


class UserProfileResponse(BaseModel):
    """Full user profile response."""

    id: UUID
    email: str
    name: str
    phone: str | None = None
    avatar_url: str | None = None
    birth_date: date | None = None
    gender: Gender | None = None
    height_cm: float | None = None
    bio: str | None = None
    is_active: bool
    is_verified: bool
    user_type: str = "student"  # "personal" or "student"
    # Professional credentials
    cref: str | None = None
    cref_verified: bool = False
    # Trainer onboarding fields
    specialties: list[str] | None = None
    years_of_experience: int | None = None
    # Student onboarding fields
    fitness_goal: str | None = None
    fitness_goal_other: str | None = None
    experience_level: str | None = None
    weight_kg: float | None = None
    age: int | None = None
    weekly_frequency: int | None = None
    injuries: list[str] | None = None
    injuries_other: str | None = None
    # Onboarding tracking
    onboarding_completed: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    """User profile update request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    phone: str | None = Field(None, max_length=50)
    birth_date: date | None = None
    gender: Gender | None = None
    height_cm: float | None = Field(None, ge=50, le=300)
    bio: str | None = Field(None, max_length=1000)
    # Professional credentials (for trainers)
    cref: str | None = Field(None, max_length=20, description="CREF registration number")
    # Trainer onboarding fields
    specialties: list[str] | None = None
    years_of_experience: int | None = Field(None, ge=0, le=60)
    # Student onboarding fields
    fitness_goal: str | None = Field(None, max_length=50)
    fitness_goal_other: str | None = Field(None, max_length=200)
    experience_level: str | None = Field(None, max_length=20)
    weight_kg: float | None = Field(None, ge=20, le=500)
    age: int | None = Field(None, ge=10, le=120)
    weekly_frequency: int | None = Field(None, ge=1, le=7)
    injuries: list[str] | None = None
    injuries_other: str | None = Field(None, max_length=200)
    # Onboarding tracking
    onboarding_completed: bool | None = None


class UserSettingsResponse(BaseModel):
    """User settings response."""

    id: UUID
    user_id: UUID
    theme: Theme
    language: str
    units: Units
    notifications_enabled: bool
    # Do Not Disturb settings
    dnd_enabled: bool = False
    dnd_start_time: str | None = None  # HH:MM format
    dnd_end_time: str | None = None  # HH:MM format
    goal_weight: float | None = None
    target_calories: int | None = None

    model_config = ConfigDict(from_attributes=True)


class UserSettingsUpdate(BaseModel):
    """User settings update request."""

    theme: Theme | None = None
    language: str | None = Field(None, min_length=2, max_length=5)
    units: Units | None = None
    notifications_enabled: bool | None = None
    # Do Not Disturb settings
    dnd_enabled: bool | None = None
    dnd_start_time: str | None = Field(None, pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM format
    dnd_end_time: str | None = Field(None, pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")  # HH:MM format
    goal_weight: float | None = Field(None, ge=20, le=500)
    target_calories: int | None = Field(None, ge=500, le=10000)


class PasswordChangeRequest(BaseModel):
    """Password change request."""

    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class AvatarUploadResponse(BaseModel):
    """Avatar upload response."""

    avatar_url: str


class UserListResponse(BaseModel):
    """User list item for admin/search results."""

    id: UUID
    email: str
    name: str
    avatar_url: str | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# ==================== Student Dashboard Schemas ====================


class StudentStatsResponse(BaseModel):
    """Student statistics."""

    total_workouts: int = 0
    adherence_percent: int = 0
    weight_change_kg: float | None = None
    current_streak: int = 0


class TodayWorkoutResponse(BaseModel):
    """Today's workout info."""

    id: UUID
    name: str
    label: str  # "TREINO A", "TREINO B", etc.
    duration_minutes: int = 60
    exercises_count: int = 0
    plan_id: UUID | None = None
    workout_id: UUID


class WeeklyProgressResponse(BaseModel):
    """Weekly workout progress."""

    completed: int = 0
    target: int = 5
    days: list[str | None] = []  # ["seg", "ter", "qua", None, None]


class RecentActivityResponse(BaseModel):
    """Recent activity item."""

    title: str
    subtitle: str
    time: str
    type: str  # "workout", "diet", "measurement", "achievement"


class TrainerInfoResponse(BaseModel):
    """Trainer info for student dashboard."""

    id: UUID
    name: str
    avatar_url: str | None = None
    is_online: bool = False
    cref: str | None = None
    cref_verified: bool = False  # Verified badge/seal


class PlanProgressResponse(BaseModel):
    """Current plan progress."""

    plan_id: UUID
    plan_name: str
    current_week: int = 1
    total_weeks: int | None = None
    percent_complete: int = 0
    training_mode: str = "presencial"  # "presencial", "online", "hibrido"


class StudentDashboardResponse(BaseModel):
    """Consolidated student dashboard response."""

    stats: StudentStatsResponse
    today_workout: TodayWorkoutResponse | None = None
    weekly_progress: WeeklyProgressResponse
    recent_activity: list[RecentActivityResponse] = []
    trainer: TrainerInfoResponse | None = None
    plan_progress: PlanProgressResponse | None = None
    unread_notes_count: int = 0
