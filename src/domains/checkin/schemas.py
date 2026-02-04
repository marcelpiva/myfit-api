"""Check-in schemas for request/response validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.checkin.models import CheckInMethod, CheckInStatus, TrainingMode


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

    model_config = ConfigDict(from_attributes=True)


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
    initiated_by: UUID | None = None
    accepted_at: datetime | None = None
    notes: str | None = None
    is_active: bool
    duration_minutes: int | None = None
    training_mode: str | None = None
    gym: GymResponse | None = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


# Check-in request schemas

class ManualCheckinForStudentRequest(BaseModel):
    """Trainer creates check-in on behalf of a student."""

    student_id: UUID
    gym_id: UUID
    training_mode: TrainingMode
    notes: str | None = Field(None, max_length=500)


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
    approver_name: str | None = None
    requester_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_request(cls, req) -> "CheckInRequestResponse":
        """Create response from ORM model with user relationships loaded."""
        data = {
            "id": req.id,
            "user_id": req.user_id,
            "gym_id": req.gym_id,
            "approver_id": req.approver_id,
            "status": req.status,
            "reason": req.reason,
            "responded_at": req.responded_at,
            "response_note": req.response_note,
            "created_at": req.created_at,
            "gym": GymResponse.model_validate(req.gym) if req.gym else None,
            "approver_name": req.approver.name if hasattr(req, "approver") and req.approver else None,
            "requester_name": req.user.name if hasattr(req, "user") and req.user else None,
        }
        return cls(**data)


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


class NearbyGymResponse(BaseModel):
    """Nearby gym detection response (read-only, no check-in created)."""

    found: bool
    gym: GymResponse | None = None
    distance_meters: float | None = None
    within_radius: bool = False


# Trainer location schemas

class NearbyTrainerInfo(BaseModel):
    """Info about a nearby trainer."""

    trainer_id: UUID
    trainer_name: str
    distance_meters: float
    source: str  # "checkin" or "gps"
    gym_id: UUID | None = None
    gym_name: str | None = None
    session_active: bool = False


class NearbyTrainerResponse(BaseModel):
    """Nearby trainer detection response."""

    found: bool
    trainers: list[NearbyTrainerInfo] = []


class UpdateTrainerLocationRequest(BaseModel):
    """Trainer shares GPS location."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CheckInNearTrainerRequest(BaseModel):
    """Student check-in near a trainer."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    trainer_id: UUID


# Training session schemas

class StartTrainingSessionRequest(BaseModel):
    """Start a training session."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class TrainingSessionResponse(BaseModel):
    """Training session info."""

    id: UUID
    started_at: datetime
    status: str
    latitude: float
    longitude: float


class SessionCheckinInfo(BaseModel):
    """Check-in info within a training session."""

    id: UUID
    student_name: str
    student_avatar: str | None = None
    checked_in_at: datetime
    elapsed_minutes: int
    status: str
    checked_out_at: datetime | None = None


class ActiveSessionResponse(BaseModel):
    """Active training session with check-ins."""

    session: TrainingSessionResponse
    checkins: list[SessionCheckinInfo] = []


# Pending acceptance schemas

class PendingAcceptanceResponse(BaseModel):
    """Check-in pending acceptance response."""

    id: UUID
    initiated_by_name: str
    initiated_by_avatar: str | None = None
    initiated_by_role: str
    initiated_by_id: UUID
    user_id: UUID
    user_name: str
    gym_name: str | None = None
    gym_id: UUID
    method: CheckInMethod
    training_mode: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
