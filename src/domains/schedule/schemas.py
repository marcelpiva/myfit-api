"""Schedule schemas for API validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from .models import AppointmentStatus, AppointmentType


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

    class Config:
        from_attributes = True
