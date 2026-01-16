from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from src.config.settings import settings


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str  # user_id
    exp: datetime
    iat: datetime
    type: str  # "access" | "refresh"


class TokenData(BaseModel):
    """Decoded token data."""

    user_id: str
    token_type: str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def hash_password(password: str) -> str:
    """Hash a password."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def create_access_token(
    user_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create an access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    """Create a refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.JWT_REFRESH_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, is_refresh: bool = False) -> TokenData | None:
    """Decode and validate a JWT token."""
    try:
        secret = settings.JWT_REFRESH_SECRET_KEY if is_refresh else settings.JWT_SECRET_KEY
        payload: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        token_type = payload.get("type")

        if user_id is None or token_type is None:
            return None

        expected_type = "refresh" if is_refresh else "access"
        if token_type != expected_type:
            return None

        return TokenData(user_id=user_id, token_type=token_type)

    except JWTError:
        return None


def create_token_pair(user_id: str) -> tuple[str, str]:
    """Create both access and refresh tokens."""
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    return access_token, refresh_token
