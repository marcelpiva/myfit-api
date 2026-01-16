"""Schemas for trainer endpoints."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class StudentResponse(BaseModel):
    """Response schema for student."""
    id: UUID
    user_id: UUID
    name: str
    email: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    joined_at: datetime
    is_active: bool = True
    goal: Optional[str] = None
    notes: Optional[str] = None
    # Computed stats
    workouts_count: int = 0
    last_workout_at: Optional[datetime] = None


class StudentStatsResponse(BaseModel):
    """Response schema for student statistics."""
    total_workouts: int = 0
    workouts_this_week: int = 0
    workouts_this_month: int = 0
    average_duration_minutes: int = 0
    total_exercises: int = 0
    streak_days: int = 0
    last_workout_at: Optional[datetime] = None


class StudentRegisterRequest(BaseModel):
    """Request schema for registering a new student."""
    name: str
    email: EmailStr
    phone: Optional[str] = None
    goal: Optional[str] = None
    notes: Optional[str] = None


class AddStudentRequest(BaseModel):
    """Request schema for adding an existing user as student."""
    user_id: UUID


class InviteCodeResponse(BaseModel):
    """Response schema for invite code."""
    code: str
    url: str
    expires_at: Optional[datetime] = None


class SendInviteRequest(BaseModel):
    """Request schema for sending invite email."""
    email: EmailStr
