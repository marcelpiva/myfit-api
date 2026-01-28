"""Authentication service with database operations."""
import logging
import uuid
from typing import Any

import httpx
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
from src.domains.users.models import AuthProvider, User, UserSettings

logger = logging.getLogger(__name__)


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

        # User registered via social login (no password)
        if not user.password_hash:
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

    # ==================== Social Login Methods ====================

    async def get_user_by_google_id(self, google_id: str) -> User | None:
        """Get a user by Google ID.

        Args:
            google_id: The Google user ID

        Returns:
            The User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()

    async def get_user_by_apple_id(self, apple_id: str) -> User | None:
        """Get a user by Apple ID.

        Args:
            apple_id: The Apple user ID

        Returns:
            The User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.apple_id == apple_id)
        )
        return result.scalar_one_or_none()

    async def verify_google_token(self, id_token: str) -> dict[str, Any] | None:
        """Verify Google ID token and return user info.

        Args:
            id_token: The Google ID token

        Returns:
            Dict with user info (sub, email, name, picture) or None if invalid
        """
        try:
            # Verify with Google's tokeninfo endpoint
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
                )

                if response.status_code != 200:
                    logger.warning(f"Google token verification failed: {response.text}")
                    return None

                data = response.json()

                # Verify the token is for our app
                valid_client_ids = [
                    settings.GOOGLE_CLIENT_ID,
                    settings.GOOGLE_CLIENT_ID_IOS,
                    settings.GOOGLE_CLIENT_ID_ANDROID,
                ]
                # Filter out empty strings
                valid_client_ids = [cid for cid in valid_client_ids if cid]

                if data.get("aud") not in valid_client_ids:
                    logger.warning(
                        f"Google token aud mismatch. Got: {data.get('aud')}, "
                        f"Expected one of: {valid_client_ids}"
                    )
                    return None

                return {
                    "sub": data.get("sub"),  # Google user ID
                    "email": data.get("email"),
                    "name": data.get("name", ""),
                    "picture": data.get("picture"),
                    "email_verified": data.get("email_verified") == "true",
                }

        except Exception as e:
            logger.error(f"Error verifying Google token: {e}")
            return None

    async def verify_apple_token(self, id_token: str) -> dict[str, Any] | None:
        """Verify Apple ID token and return user info.

        Args:
            id_token: The Apple ID token

        Returns:
            Dict with user info (sub, email) or None if invalid
        """
        try:
            import jwt
            from jwt import PyJWKClient

            # Get Apple's public keys
            jwks_client = PyJWKClient("https://appleid.apple.com/auth/keys")
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)

            # Decode and verify the token
            data = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.APPLE_CLIENT_ID,
                issuer="https://appleid.apple.com",
            )

            return {
                "sub": data.get("sub"),  # Apple user ID
                "email": data.get("email"),
                "email_verified": data.get("email_verified", False),
            }

        except Exception as e:
            logger.error(f"Error verifying Apple token: {e}")
            return None

    async def authenticate_or_create_google_user(
        self,
        id_token: str,
        user_type: str | None = None,
    ) -> tuple[User, bool] | None:
        """Authenticate or create user via Google Sign-In.

        Args:
            id_token: The Google ID token
            user_type: Optional user type ('student' or 'trainer')

        Returns:
            Tuple of (User, is_new_user) or None if token is invalid
        """
        # Verify the token
        google_data = await self.verify_google_token(id_token)
        if not google_data:
            return None

        google_id = google_data["sub"]
        email = google_data.get("email")
        name = google_data.get("name", "")
        picture = google_data.get("picture")

        if not email:
            logger.warning("Google token missing email")
            return None

        # Check if user exists by Google ID
        user = await self.get_user_by_google_id(google_id)
        if user:
            # Update avatar if changed
            if picture and user.avatar_url != picture:
                user.avatar_url = picture
                await self.db.commit()
            return user, False

        # Check if user exists by email (link accounts)
        user = await self.get_user_by_email(email)
        if user:
            # Link Google account to existing user
            user.google_id = google_id
            user.auth_provider = AuthProvider.GOOGLE
            if picture and not user.avatar_url:
                user.avatar_url = picture
            await self.db.commit()
            return user, False

        # Create new user
        user = User(
            email=email.lower(),
            password_hash=hash_password(uuid.uuid4().hex),  # Random password
            name=name or email.split("@")[0],
            google_id=google_id,
            auth_provider=AuthProvider.GOOGLE,
            avatar_url=picture,
            is_active=True,
            is_verified=True,  # Google emails are verified
        )
        self.db.add(user)
        await self.db.flush()

        # Create default settings
        user_settings = UserSettings(user_id=user.id)
        self.db.add(user_settings)

        # If user_type is trainer, create a personal organization
        if user_type == "trainer":
            # Import here to avoid circular import
            from src.domains.organizations.models import OrganizationType
            from src.domains.organizations.service import OrganizationService
            org_service = OrganizationService(self.db)
            await org_service.create_organization(
                owner=user,
                name=f"Personal {name or email.split('@')[0]}",
                org_type=OrganizationType.PERSONAL,
            )

        await self.db.commit()
        await self.db.refresh(user)

        return user, True

    async def authenticate_or_create_apple_user(
        self,
        id_token: str,
        user_name: str | None = None,
    ) -> tuple[User, bool] | None:
        """Authenticate or create user via Apple Sign-In.

        Args:
            id_token: The Apple ID token
            user_name: Optional user name (only provided on first login)

        Returns:
            Tuple of (User, is_new_user) or None if token is invalid
        """
        # Verify the token
        apple_data = await self.verify_apple_token(id_token)
        if not apple_data:
            return None

        apple_id = apple_data["sub"]
        email = apple_data.get("email")

        # Check if user exists by Apple ID
        user = await self.get_user_by_apple_id(apple_id)
        if user:
            return user, False

        # Apple might not provide email on subsequent logins
        if email:
            # Check if user exists by email (link accounts)
            user = await self.get_user_by_email(email)
            if user:
                # Link Apple account to existing user
                user.apple_id = apple_id
                user.auth_provider = AuthProvider.APPLE
                await self.db.commit()
                return user, False

        # Create new user
        # Use provided name, or email prefix, or "Apple User"
        name = user_name or (email.split("@")[0] if email else "Apple User")

        user = User(
            email=(email or f"{apple_id}@privaterelay.appleid.com").lower(),
            password_hash=hash_password(uuid.uuid4().hex),  # Random password
            name=name,
            apple_id=apple_id,
            auth_provider=AuthProvider.APPLE,
            is_active=True,
            is_verified=True,  # Apple emails are verified
        )
        self.db.add(user)
        await self.db.flush()

        # Create default settings
        user_settings = UserSettings(user_id=user.id)
        self.db.add(user_settings)
        await self.db.commit()
        await self.db.refresh(user)

        return user, True

    # ==================== Email Verification Methods ====================

    async def create_verification_code(
        self,
        email: str,
        purpose: str = "registration",
    ) -> str:
        """Create a new email verification code.

        Args:
            email: The email address to verify
            purpose: Purpose of verification ("registration", "password_reset")

        Returns:
            The 6-digit verification code
        """
        import random
        from datetime import datetime, timedelta, timezone

        from src.domains.users.models import EmailVerification

        # Generate 6-digit code
        code = "".join([str(random.randint(0, 9)) for _ in range(6)])

        # Invalidate any existing codes for this email and purpose
        from sqlalchemy import update

        await self.db.execute(
            update(EmailVerification)
            .where(
                EmailVerification.email == email.lower(),
                EmailVerification.purpose == purpose,
                EmailVerification.is_used == False,  # noqa: E712
            )
            .values(is_used=True)
        )

        # Create new verification record
        verification = EmailVerification(
            email=email.lower(),
            code=code,
            purpose=purpose,
            is_used=False,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        self.db.add(verification)
        await self.db.commit()

        return code

    async def verify_code(
        self,
        email: str,
        code: str,
        purpose: str = "registration",
    ) -> bool:
        """Verify an email verification code.

        Args:
            email: The email address
            code: The verification code
            purpose: Purpose of verification

        Returns:
            True if code is valid, False otherwise
        """
        from datetime import datetime, timezone

        from sqlalchemy import and_

        from src.domains.users.models import EmailVerification

        result = await self.db.execute(
            select(EmailVerification).where(
                and_(
                    EmailVerification.email == email.lower(),
                    EmailVerification.code == code,
                    EmailVerification.purpose == purpose,
                    EmailVerification.is_used == False,  # noqa: E712
                    EmailVerification.expires_at > datetime.now(timezone.utc),
                )
            )
        )
        verification = result.scalar_one_or_none()

        if not verification:
            return False

        # Mark as used
        verification.is_used = True
        await self.db.commit()

        return True

    async def verify_user_email(self, user: User) -> None:
        """Mark a user's email as verified.

        Args:
            user: The User object to verify
        """
        user.is_verified = True
        await self.db.commit()

    async def send_verification_email(
        self,
        email: str,
        name: str,
    ) -> bool:
        """Generate and send a verification code to an email address.

        Args:
            email: The email address
            name: The user's name

        Returns:
            True if email was sent successfully
        """
        from src.core.email import send_verification_code_email

        # Create verification code
        code = await self.create_verification_code(email, "registration")

        # Send email
        return await send_verification_code_email(
            to_email=email,
            name=name,
            code=code,
        )
