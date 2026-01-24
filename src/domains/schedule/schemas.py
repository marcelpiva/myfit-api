"""Schedule schemas for API validation."""
from datetime import datetime, time
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import AppointmentStatus, AppointmentType


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

    # Enriched fields
    trainer_name: str | None = None
    student_name: str | None = None

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
