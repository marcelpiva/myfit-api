from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=2, max_length=100)
    user_type: Literal["personal", "student"] = Field(
        default="student",
        description="User type: 'personal' for trainers, 'student' for clients",
    )


class LoginRequest(BaseModel):
    """User login request."""

    email: EmailStr
    password: str


class LogoutRequest(BaseModel):
    """User logout request."""

    refresh_token: str | None = None


class TokenResponse(BaseModel):
    """Authentication token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class UserResponse(BaseModel):
    """User information response."""

    id: UUID
    email: str
    name: str
    phone: str | None = None
    avatar_url: str | None = None
    birth_date: str | None = None
    gender: str | None = None
    height_cm: float | None = None
    bio: str | None = None
    is_active: bool
    is_verified: bool
    auth_provider: str = "email"
    user_type: str = "student"  # "personal" or "student"
    # Professional credentials
    cref: str | None = None
    cref_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    """Complete authentication response."""

    user: UserResponse
    tokens: TokenResponse


class PasswordChangeRequest(BaseModel):
    """Password change request."""

    current_password: str
    new_password: str = Field(min_length=6, max_length=128)


class GoogleLoginRequest(BaseModel):
    """Google Sign-In request."""

    id_token: str = Field(..., description="Google ID token from client")


class AppleLoginRequest(BaseModel):
    """Apple Sign-In request."""

    id_token: str = Field(..., description="Apple ID token from client")
    user_name: str | None = Field(None, description="User's name (only provided on first login)")


class SocialAuthResponse(BaseModel):
    """Social authentication response."""

    user: "UserResponse"
    tokens: TokenResponse
    is_new_user: bool = Field(..., description="Whether this is a new registration")


class SendVerificationCodeRequest(BaseModel):
    """Request to send verification code."""

    email: EmailStr


class VerifyCodeRequest(BaseModel):
    """Request to verify email code."""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")


class VerifyCodeResponse(BaseModel):
    """Response for email verification."""

    verified: bool
    message: str


class ResendVerificationCodeRequest(BaseModel):
    """Request to resend verification code."""

    email: EmailStr
