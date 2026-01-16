"""Authentication service with database operations."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.core.redis import TokenBlacklist
from src.core.security import (
    create_token_pair,
    decode_token,
    hash_password,
    verify_password,
)
from src.domains.users.models import User, UserSettings


class AuthService:
    """Service for handling authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email address.

        Args:
            email: The user's email

        Returns:
            The User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        """Get a user by ID.

        Args:
            user_id: The user's UUID

        Returns:
            The User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password: str,
        name: str,
    ) -> User:
        """Create a new user with default settings.

        Args:
            email: User's email
            password: Plain text password
            name: User's full name

        Returns:
            The created User object
        """
        # Create user
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            name=name,
            is_active=True,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()  # Get the user ID

        # Create default settings
        user_settings = UserSettings(
            user_id=user.id,
        )
        self.db.add(user_settings)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User | None:
        """Authenticate a user by email and password.

        Args:
            email: User's email
            password: Plain text password

        Returns:
            The User object if authentication succeeds, None otherwise
        """
        user = await self.get_user_by_email(email)
        if not user:
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    def generate_tokens(self, user_id: uuid.UUID) -> tuple[str, str]:
        """Generate access and refresh tokens for a user.

        Args:
            user_id: The user's UUID

        Returns:
            Tuple of (access_token, refresh_token)
        """
        return create_token_pair(str(user_id))

    async def refresh_tokens(
        self,
        refresh_token: str,
    ) -> tuple[str, str] | None:
        """Validate refresh token and generate new token pair.

        Args:
            refresh_token: The refresh token to validate

        Returns:
            Tuple of (access_token, refresh_token) if valid, None otherwise
        """
        # Check if token is blacklisted
        if await TokenBlacklist.is_blacklisted(refresh_token):
            return None

        # Decode and validate
        token_data = decode_token(refresh_token, is_refresh=True)
        if not token_data:
            return None

        # Verify user still exists and is active
        try:
            user_id = uuid.UUID(token_data.user_id)
        except ValueError:
            return None

        user = await self.get_user_by_id(user_id)
        if not user or not user.is_active:
            return None

        # Blacklist the old refresh token
        refresh_expire_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await TokenBlacklist.add_to_blacklist(refresh_token, refresh_expire_seconds)

        # Generate new tokens
        return self.generate_tokens(user.id)

    async def logout(
        self,
        access_token: str,
        refresh_token: str | None = None,
    ) -> None:
        """Logout user by blacklisting tokens.

        Args:
            access_token: The access token to invalidate
            refresh_token: Optional refresh token to invalidate
        """
        # Blacklist access token
        access_expire_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        await TokenBlacklist.add_to_blacklist(access_token, access_expire_seconds)

        # Blacklist refresh token if provided
        if refresh_token:
            refresh_expire_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
            await TokenBlacklist.add_to_blacklist(refresh_token, refresh_expire_seconds)

    async def change_password(
        self,
        user: User,
        new_password: str,
    ) -> None:
        """Change user's password and invalidate all tokens.

        Args:
            user: The User object
            new_password: The new plain text password
        """
        user.password_hash = hash_password(new_password)
        await self.db.commit()

        # Invalidate all user's refresh tokens
        await TokenBlacklist.invalidate_all_user_tokens(str(user.id))
