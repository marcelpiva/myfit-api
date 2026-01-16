"""User schemas for request/response validation."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

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

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    """User profile update request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    phone: str | None = Field(None, max_length=50)
    birth_date: date | None = None
    gender: Gender | None = None
    height_cm: float | None = Field(None, ge=50, le=300)
    bio: str | None = Field(None, max_length=1000)


class UserSettingsResponse(BaseModel):
    """User settings response."""

    id: UUID
    user_id: UUID
    theme: Theme
    language: str
    units: Units
    notifications_enabled: bool
    goal_weight: float | None = None
    target_calories: int | None = None

    class Config:
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """User settings update request."""

    theme: Theme | None = None
    language: str | None = Field(None, min_length=2, max_length=5)
    units: Units | None = None
    notifications_enabled: bool | None = None
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

    class Config:
        from_attributes = True
