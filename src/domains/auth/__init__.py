"""Auth domain package."""
from src.domains.auth.dependencies import (
    ActiveUser,
    CurrentUser,
    VerifiedUser,
    get_current_active_user,
    get_current_user,
    get_current_verified_user,
)
from src.domains.auth.router import router
from src.domains.auth.service import AuthService

__all__ = [
    "router",
    "AuthService",
    "CurrentUser",
    "ActiveUser",
    "VerifiedUser",
    "get_current_user",
    "get_current_active_user",
    "get_current_verified_user",
]
