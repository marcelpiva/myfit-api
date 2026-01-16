"""Progress schemas for request/response validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.progress.models import PhotoAngle


# Weight log schemas

class WeightLogCreate(BaseModel):
    """Create weight log request."""

    weight_kg: float = Field(gt=0, le=500)
    logged_at: datetime | None = None
    notes: str | None = Field(None, max_length=500)


class WeightLogUpdate(BaseModel):
    """Update weight log request."""

    weight_kg: float | None = Field(None, gt=0, le=500)
    logged_at: datetime | None = None
    notes: str | None = Field(None, max_length=500)


class WeightLogResponse(BaseModel):
    """Weight log response."""

    id: UUID
    user_id: UUID
    weight_kg: float
    logged_at: datetime
    notes: str | None = None

    class Config:
        from_attributes = True


# Measurement log schemas

class MeasurementLogCreate(BaseModel):
    """Create measurement log request."""

    logged_at: datetime | None = None
    chest_cm: float | None = Field(None, gt=0, le=300)
    waist_cm: float | None = Field(None, gt=0, le=300)
    hips_cm: float | None = Field(None, gt=0, le=300)
    biceps_cm: float | None = Field(None, gt=0, le=100)
    thigh_cm: float | None = Field(None, gt=0, le=150)
    calf_cm: float | None = Field(None, gt=0, le=100)
    neck_cm: float | None = Field(None, gt=0, le=100)
    forearm_cm: float | None = Field(None, gt=0, le=100)
    notes: str | None = Field(None, max_length=500)


class MeasurementLogUpdate(BaseModel):
    """Update measurement log request."""

    chest_cm: float | None = Field(None, gt=0, le=300)
    waist_cm: float | None = Field(None, gt=0, le=300)
    hips_cm: float | None = Field(None, gt=0, le=300)
    biceps_cm: float | None = Field(None, gt=0, le=100)
    thigh_cm: float | None = Field(None, gt=0, le=150)
    calf_cm: float | None = Field(None, gt=0, le=100)
    neck_cm: float | None = Field(None, gt=0, le=100)
    forearm_cm: float | None = Field(None, gt=0, le=100)
    notes: str | None = Field(None, max_length=500)


class MeasurementLogResponse(BaseModel):
    """Measurement log response."""

    id: UUID
    user_id: UUID
    logged_at: datetime
    chest_cm: float | None = None
    waist_cm: float | None = None
    hips_cm: float | None = None
    biceps_cm: float | None = None
    thigh_cm: float | None = None
    calf_cm: float | None = None
    neck_cm: float | None = None
    forearm_cm: float | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


# Progress photo schemas

class ProgressPhotoCreate(BaseModel):
    """Create progress photo request."""

    photo_url: str = Field(max_length=500)
    thumbnail_url: str | None = Field(None, max_length=500)
    angle: PhotoAngle
    logged_at: datetime | None = None
    notes: str | None = Field(None, max_length=500)
    weight_log_id: UUID | None = None
    measurement_log_id: UUID | None = None


class ProgressPhotoResponse(BaseModel):
    """Progress photo response."""

    id: UUID
    user_id: UUID
    photo_url: str
    thumbnail_url: str | None = None
    angle: PhotoAngle
    logged_at: datetime
    notes: str | None = None
    weight_log_id: UUID | None = None
    measurement_log_id: UUID | None = None

    class Config:
        from_attributes = True


# Weight goal schemas

class WeightGoalCreate(BaseModel):
    """Create or update weight goal request."""

    target_weight_kg: float = Field(gt=0, le=500)
    start_weight_kg: float = Field(gt=0, le=500)
    target_date: datetime | None = None
    notes: str | None = None


class WeightGoalResponse(BaseModel):
    """Weight goal response."""

    id: UUID
    user_id: UUID
    target_weight_kg: float
    start_weight_kg: float
    target_date: datetime | None = None
    started_at: datetime
    notes: str | None = None
    weight_to_lose: float

    class Config:
        from_attributes = True


# Stats schema

class ProgressStatsResponse(BaseModel):
    """Progress statistics response."""

    period_days: int
    weight_logs_count: int
    measurement_logs_count: int
    latest_weight_kg: float | None = None
    starting_weight_kg: float | None = None
    weight_change_kg: float
    goal_weight_kg: float | None = None
    goal_progress_percent: float | None = None
