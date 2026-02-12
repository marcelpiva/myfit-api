"""Schedule schemas for API validation."""
from datetime import date, datetime, time
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import AppointmentStatus, AppointmentType, AttendanceStatus, SessionType


class RecurrencePattern(str, Enum):
    """Pattern for recurring appointments."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class AppointmentCreate(BaseModel):
    """Schema for creating an appointment."""

    student_id: UUID
    date_time: datetime
    duration_minutes: int = Field(default=60, ge=15, le=240)
    workout_type: AppointmentType | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    service_plan_id: UUID | None = None
    session_type: SessionType = SessionType.SCHEDULED
    is_complimentary: bool = False


class AppointmentUpdate(BaseModel):
    """Schema for updating an appointment."""

    date_time: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=240)
    workout_type: AppointmentType | None = None
    notes: str | None = None


class AppointmentCancel(BaseModel):
    """Schema for cancelling an appointment."""

    reason: str | None = None


class AppointmentResponse(BaseModel):
    """Schema for appointment response."""

    id: UUID
    trainer_id: UUID
    student_id: UUID
    organization_id: UUID | None
    date_time: datetime
    duration_minutes: int
    workout_type: AppointmentType | None
    status: AppointmentStatus
    notes: str | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime | None

    # Service plan & billing fields
    service_plan_id: UUID | None = None
    payment_id: UUID | None = None
    session_type: SessionType = SessionType.SCHEDULED
    attendance_status: AttendanceStatus = AttendanceStatus.SCHEDULED
    is_complimentary: bool = False

    # Enriched fields
    trainer_name: str | None = None
    student_name: str | None = None
    service_plan_name: str | None = None

    # Group session fields
    is_group: bool = False
    max_participants: int | None = None
    participants: list["ParticipantResponse"] = []
    participant_count: int = 0

    # Evaluation fields
    has_evaluation: bool = False
    trainer_rating: int | None = None
    student_rating: int | None = None

    model_config = ConfigDict(from_attributes=True)


class RecurringAppointmentCreate(BaseModel):
    """Schema for creating recurring appointments."""

    student_id: UUID
    start_date: datetime
    duration_minutes: int = Field(default=60, ge=15, le=240)
    workout_type: AppointmentType | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    recurrence_pattern: RecurrencePattern
    occurrences: int = Field(ge=1, le=52)  # Max 1 year of weekly appointments


class AppointmentReschedule(BaseModel):
    """Schema for rescheduling an appointment."""

    new_date_time: datetime
    reason: str | None = None


class AppointmentComplete(BaseModel):
    """Schema for completing an appointment."""

    notes: str | None = None
    rating: int | None = Field(default=None, ge=1, le=5)


class TrainerAvailabilitySlot(BaseModel):
    """Single availability slot."""

    day_of_week: int = Field(ge=0, le=6)  # 0=Monday, 6=Sunday
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")  # HH:MM format
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")  # HH:MM format


class TrainerAvailabilityCreate(BaseModel):
    """Schema for setting trainer availability."""

    slots: list[TrainerAvailabilitySlot]


class TrainerAvailabilityResponse(BaseModel):
    """Schema for trainer availability response."""

    trainer_id: UUID
    slots: list[TrainerAvailabilitySlot]


class UpcomingAppointmentsResponse(BaseModel):
    """Schema for upcoming appointments response."""

    appointments: list[AppointmentResponse]
    total_count: int


class ConflictDetail(BaseModel):
    """A single scheduling conflict."""

    type: str  # "trainer_overlap", "student_overlap", "outside_availability", "buffer_too_short"
    message: str
    conflicting_appointment_id: UUID | None = None
    conflicting_student_name: str | None = None
    conflicting_time: datetime | None = None


class ConflictCheckResponse(BaseModel):
    """Response from conflict check endpoint."""

    has_conflicts: bool
    conflicts: list[ConflictDetail] = []
    warnings: list[ConflictDetail] = []


class AutoGenerateScheduleRequest(BaseModel):
    """Request to auto-generate appointments from a service plan."""

    service_plan_id: UUID
    weeks_ahead: int = Field(default=4, ge=1, le=12)
    auto_confirm: bool = False  # If True, appointments are created as CONFIRMED


# --- Self-service booking schemas ---


class AvailableSlotResponse(BaseModel):
    """A single available time slot."""

    time: str  # HH:MM
    available: bool


class AvailableSlotsResponse(BaseModel):
    """List of slots for a given day."""

    date: date
    trainer_id: UUID
    slots: list[AvailableSlotResponse]


class StudentBookSessionRequest(BaseModel):
    """Request for a student to book a session."""

    trainer_id: UUID
    date_time: datetime
    service_plan_id: UUID
    duration_minutes: int = Field(default=60, ge=15, le=240)
    workout_type: AppointmentType | None = None


class TrainerBlockedSlotCreate(BaseModel):
    """Create a blocked time slot for a trainer."""

    day_of_week: int | None = Field(default=None, ge=0, le=6)
    specific_date: date | None = None
    start_time: time
    end_time: time
    reason: str | None = None
    is_recurring: bool = False


class TrainerBlockedSlotResponse(BaseModel):
    """Response for a blocked time slot."""

    id: UUID
    trainer_id: UUID
    day_of_week: int | None
    specific_date: date | None
    start_time: time
    end_time: time
    reason: str | None
    is_recurring: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TrainerSettingsUpdate(BaseModel):
    """Update trainer scheduling settings."""

    default_start_time: time | None = None
    default_end_time: time | None = None
    session_duration_minutes: int | None = Field(default=None, ge=15, le=240)
    slot_interval_minutes: int | None = Field(default=None, ge=15, le=60)
    late_cancel_window_hours: int | None = Field(default=None, ge=0, le=168)
    late_cancel_policy: str | None = None  # charge, warn, block


class TrainerSettingsResponse(BaseModel):
    """Trainer scheduling settings response."""

    trainer_id: UUID
    default_start_time: time
    default_end_time: time
    session_duration_minutes: int
    slot_interval_minutes: int
    late_cancel_window_hours: int = 24
    late_cancel_policy: str = "warn"

    model_config = ConfigDict(from_attributes=True)


class TrainerFullAvailabilityResponse(BaseModel):
    """Full trainer availability: settings + blocked slots."""

    settings: TrainerSettingsResponse
    blocked_slots: list[TrainerBlockedSlotResponse]


class AttendanceUpdate(BaseModel):
    """Update attendance status for an appointment."""

    attendance_status: AttendanceStatus
    grant_makeup: bool = False
    notes: str | None = None


class GroupSessionCreate(BaseModel):
    """Schema for creating a group session."""

    student_ids: list[UUID]
    date_time: datetime
    duration_minutes: int = Field(default=60, ge=15, le=240)
    workout_type: AppointmentType | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    max_participants: int = Field(default=10, ge=2, le=50)


class ParticipantResponse(BaseModel):
    """Schema for a group session participant."""

    id: UUID
    student_id: UUID
    student_name: str | None = None
    student_avatar_url: str | None = None
    attendance_status: str = "scheduled"
    service_plan_id: UUID | None = None
    is_complimentary: bool = False
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ParticipantAttendanceUpdate(BaseModel):
    """Update attendance for a single participant in a group session."""

    attendance_status: AttendanceStatus
    grant_makeup: bool = False
    notes: str | None = None


class AddParticipantsRequest(BaseModel):
    """Request to add participants to a group session."""

    student_ids: list[UUID]


class SessionEvaluationCreate(BaseModel):
    """Schema for creating a session evaluation."""

    overall_rating: int = Field(ge=1, le=5)
    difficulty: str | None = None  # too_easy, just_right, too_hard
    energy_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


class SessionEvaluationResponse(BaseModel):
    """Schema for session evaluation response."""

    id: UUID
    appointment_id: UUID
    evaluator_id: UUID
    evaluator_role: str
    evaluator_name: str | None = None
    overall_rating: int
    difficulty: str | None = None
    energy_level: int | None = None
    notes: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DuplicateWeekRequest(BaseModel):
    """Request to duplicate a week of appointments to another week."""

    source_week_start: date
    target_week_start: date
    skip_conflicts: bool = False


# --- Analytics schemas ---


class StudentAnalytics(BaseModel):
    """Per-student analytics breakdown."""

    student_id: str
    student_name: str
    total: int
    attended: int
    missed: int
    rate: float


class DayOfWeekAnalytics(BaseModel):
    """Analytics breakdown by day of week."""

    day: int  # 0=Monday...6=Sunday
    total: int
    attended: int


class HourAnalytics(BaseModel):
    """Analytics breakdown by hour."""

    hour: int  # 0-23
    total: int
    attended: int


class ScheduleAnalyticsResponse(BaseModel):
    """Full schedule analytics response."""

    total: int
    attended: int
    missed: int
    late_cancelled: int
    cancelled: int
    pending: int
    attendance_rate: float
    by_student: list[StudentAnalytics]
    by_day_of_week: list[DayOfWeekAnalytics]
    by_hour: list[HourAnalytics]


# --- Student reliability schemas ---


class StudentReliability(BaseModel):
    """Reliability score for a single student."""

    student_id: str
    student_name: str
    total_sessions: int
    attended: int
    missed: int
    late_cancelled: int
    attendance_rate: float
    reliability_score: str  # "high", "medium", "low"
    trend: str  # "improving", "stable", "declining"


class StudentReliabilityResponse(BaseModel):
    """Student reliability scores response."""

    students: list[StudentReliability]
