"""Check-in schemas for request/response validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.checkin.models import CheckInMethod, CheckInStatus


# Gym schemas

class GymCreate(BaseModel):
    """Create gym request."""

    organization_id: UUID
    name: str = Field(min_length=2, max_length=255)
    address: str = Field(min_length=5, max_length=500)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    phone: str | None = Field(None, max_length=50)
    radius_meters: int = Field(default=100, ge=10, le=1000)


class GymUpdate(BaseModel):
    """Update gym request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    address: str | None = Field(None, min_length=5, max_length=500)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    phone: str | None = Field(None, max_length=50)
    radius_meters: int | None = Field(None, ge=10, le=1000)
    is_active: bool | None = None


class GymResponse(BaseModel):
    """Gym response."""

    id: UUID
    organization_id: UUID
    name: str
    address: str
    latitude: float
    longitude: float
    phone: str | None = None
    radius_meters: int
    is_active: bool

    class Config:
        from_attributes = True


# Check-in schemas

class CheckInCreate(BaseModel):
    """Create check-in request."""

    gym_id: UUID
    method: CheckInMethod = CheckInMethod.MANUAL
    notes: str | None = Field(None, max_length=500)


class CheckInByCodeRequest(BaseModel):
    """Check-in by code request."""

    code: str = Field(min_length=4, max_length=20)


class CheckInByLocationRequest(BaseModel):
    """Check-in by location request."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CheckOutRequest(BaseModel):
    """Check-out request."""

    notes: str | None = Field(None, max_length=500)


class CheckInResponse(BaseModel):
    """Check-in response."""

    id: UUID
    user_id: UUID
    gym_id: UUID
    method: CheckInMethod
    status: CheckInStatus
    checked_in_at: datetime
    checked_out_at: datetime | None = None
    approved_by_id: UUID | None = None
    notes: str | None = None
    is_active: bool
    duration_minutes: int | None = None
    gym: GymResponse | None = None

    class Config:
        from_attributes = True


# Check-in code schemas

class CheckInCodeCreate(BaseModel):
    """Create check-in code request."""

    gym_id: UUID
    expires_at: datetime | None = None
    max_uses: int | None = Field(None, ge=1)


class CheckInCodeResponse(BaseModel):
    """Check-in code response."""

    id: UUID
    gym_id: UUID
    code: str
    expires_at: datetime | None = None
    is_active: bool
    uses_count: int
    max_uses: int | None = None
    is_valid: bool

    class Config:
        from_attributes = True


# Check-in request schemas

class CheckInRequestCreate(BaseModel):
    """Create check-in request."""

    gym_id: UUID
    approver_id: UUID
    reason: str | None = Field(None, max_length=500)


class CheckInRequestRespond(BaseModel):
    """Respond to check-in request."""

    approved: bool
    response_note: str | None = Field(None, max_length=500)


class CheckInRequestResponse(BaseModel):
    """Check-in request response."""

    id: UUID
    user_id: UUID
    gym_id: UUID
    approver_id: UUID
    status: CheckInStatus
    reason: str | None = None
    responded_at: datetime | None = None
    response_note: str | None = None
    created_at: datetime
    gym: GymResponse | None = None

    class Config:
        from_attributes = True


# Stats schema

class CheckInStatsResponse(BaseModel):
    """Check-in statistics response."""

    period_days: int
    total_checkins: int
    total_duration_minutes: int
    avg_duration_minutes: float


# Location check-in response

class LocationCheckInResponse(BaseModel):
    """Location-based check-in response."""

    success: bool
    checkin: CheckInResponse | None = None
    nearest_gym: GymResponse | None = None
    distance_meters: float | None = None
    message: str
