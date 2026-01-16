from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """User registration request."""

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=2, max_length=100)


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
    is_active: bool
    is_verified: bool

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    """Complete authentication response."""

    user: UserResponse
    tokens: TokenResponse


class PasswordChangeRequest(BaseModel):
    """Password change request."""

    current_password: str
    new_password: str = Field(min_length=6, max_length=128)
