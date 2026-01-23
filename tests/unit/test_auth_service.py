"""Tests for AuthService - authentication and authorization logic."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password, verify_password
from src.domains.auth.service import AuthService
from src.domains.users.models import User, UserSettings


class TestCreateUser:
    """Tests for user creation."""

    async def test_create_user_normalizes_email_to_lowercase(self, db_session: AsyncSession):
        """Email should be lowercased on user creation."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="Test.User@EXAMPLE.com",
            password="securepassword123",
            name="Test User",
        )

        assert user.email == "test.user@example.com"

    async def test_create_user_hashes_password(self, db_session: AsyncSession):
        """Password should be hashed, not stored in plain text."""
        service = AuthService(db_session)
        plain_password = "securepassword123"

        user = await service.create_user(
            email="test@example.com",
            password=plain_password,
            name="Test User",
        )

        assert user.password_hash != plain_password
        assert verify_password(plain_password, user.password_hash)

    async def test_create_user_creates_default_settings(self, db_session: AsyncSession):
        """UserSettings should be created with defaults."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="test@example.com",
            password="securepassword123",
            name="Test User",
        )

        # Query for user settings
        from sqlalchemy import select

        result = await db_session.execute(
            select(UserSettings).where(UserSettings.user_id == user.id)
        )
        settings = result.scalar_one_or_none()

        assert settings is not None
        assert settings.user_id == user.id

    async def test_create_user_sets_active_by_default(self, db_session: AsyncSession):
        """New users should be active by default."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="test@example.com",
            password="securepassword123",
            name="Test User",
        )

        assert user.is_active is True

    async def test_create_user_sets_unverified_by_default(self, db_session: AsyncSession):
        """New users should be unverified by default."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="test@example.com",
            password="securepassword123",
            name="Test User",
        )

        assert user.is_verified is False


class TestAuthenticateUser:
    """Tests for user authentication."""

    async def test_authenticate_user_success(self, db_session: AsyncSession):
        """Valid credentials should return user."""
        service = AuthService(db_session)
        password = "correctpassword"

        # Create user
        created_user = await service.create_user(
            email="auth@example.com",
            password=password,
            name="Auth User",
        )

        # Authenticate
        user = await service.authenticate_user("auth@example.com", password)

        assert user is not None
        assert user.id == created_user.id

    async def test_authenticate_user_wrong_password(self, db_session: AsyncSession):
        """Wrong password should return None."""
        service = AuthService(db_session)

        await service.create_user(
            email="auth@example.com",
            password="correctpassword",
            name="Auth User",
        )

        user = await service.authenticate_user("auth@example.com", "wrongpassword")

        assert user is None

    async def test_authenticate_user_nonexistent_email(self, db_session: AsyncSession):
        """Nonexistent email should return None."""
        service = AuthService(db_session)

        user = await service.authenticate_user("nonexistent@example.com", "anypassword")

        assert user is None

    async def test_authenticate_user_case_insensitive_email(self, db_session: AsyncSession):
        """Email matching should be case insensitive."""
        service = AuthService(db_session)
        password = "password123"

        await service.create_user(
            email="user@example.com",
            password=password,
            name="User",
        )

        # Try with uppercase
        user = await service.authenticate_user("USER@EXAMPLE.COM", password)

        assert user is not None


class TestGetUserByEmail:
    """Tests for get_user_by_email."""

    async def test_get_user_by_email_found(self, db_session: AsyncSession):
        """Should return user when email exists."""
        service = AuthService(db_session)

        created = await service.create_user(
            email="find@example.com",
            password="password",
            name="Find User",
        )

        user = await service.get_user_by_email("find@example.com")

        assert user is not None
        assert user.id == created.id

    async def test_get_user_by_email_not_found(self, db_session: AsyncSession):
        """Should return None when email does not exist."""
        service = AuthService(db_session)

        user = await service.get_user_by_email("notfound@example.com")

        assert user is None

    async def test_get_user_by_email_case_insensitive(self, db_session: AsyncSession):
        """Email lookup should be case insensitive."""
        service = AuthService(db_session)

        await service.create_user(
            email="case@example.com",
            password="password",
            name="Case User",
        )

        user = await service.get_user_by_email("CASE@EXAMPLE.COM")

        assert user is not None


class TestGetUserById:
    """Tests for get_user_by_id."""

    async def test_get_user_by_id_found(self, db_session: AsyncSession):
        """Should return user when ID exists."""
        service = AuthService(db_session)

        created = await service.create_user(
            email="id@example.com",
            password="password",
            name="ID User",
        )

        user = await service.get_user_by_id(created.id)

        assert user is not None
        assert user.email == "id@example.com"

    async def test_get_user_by_id_not_found(self, db_session: AsyncSession):
        """Should return None when ID does not exist."""
        service = AuthService(db_session)

        user = await service.get_user_by_id(uuid.uuid4())

        assert user is None


class TestGenerateTokens:
    """Tests for token generation."""

    async def test_generate_tokens_returns_pair(self, db_session: AsyncSession):
        """Should return both access and refresh tokens."""
        service = AuthService(db_session)
        user_id = uuid.uuid4()

        access_token, refresh_token = service.generate_tokens(user_id)

        assert access_token is not None
        assert refresh_token is not None
        assert access_token != refresh_token

    async def test_generate_tokens_are_valid_jwt(self, db_session: AsyncSession):
        """Generated tokens should be valid JWTs."""
        from src.core.security import decode_token

        service = AuthService(db_session)
        user_id = uuid.uuid4()

        access_token, refresh_token = service.generate_tokens(user_id)

        access_data = decode_token(access_token, is_refresh=False)
        refresh_data = decode_token(refresh_token, is_refresh=True)

        assert access_data is not None
        assert access_data.user_id == str(user_id)
        assert access_data.token_type == "access"

        assert refresh_data is not None
        assert refresh_data.user_id == str(user_id)
        assert refresh_data.token_type == "refresh"


class TestRefreshTokens:
    """Tests for token refresh."""

    async def test_refresh_tokens_success(self, db_session: AsyncSession):
        """Valid refresh token should return new token pair."""
        service = AuthService(db_session)

        # Create user
        user = await service.create_user(
            email="refresh@example.com",
            password="password",
            name="Refresh User",
        )

        # Generate initial tokens
        _, refresh_token = service.generate_tokens(user.id)

        # Mock the blacklist
        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.is_blacklisted = AsyncMock(return_value=False)
            mock_blacklist.add_to_blacklist = AsyncMock()

            new_tokens = await service.refresh_tokens(refresh_token)

        assert new_tokens is not None
        new_access, new_refresh = new_tokens
        assert new_access is not None
        assert new_refresh is not None

    async def test_refresh_tokens_blacklisted_token(self, db_session: AsyncSession):
        """Blacklisted refresh token should return None."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="blacklist@example.com",
            password="password",
            name="Blacklist User",
        )

        _, refresh_token = service.generate_tokens(user.id)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.is_blacklisted = AsyncMock(return_value=True)

            result = await service.refresh_tokens(refresh_token)

        assert result is None

    async def test_refresh_tokens_invalid_token(self, db_session: AsyncSession):
        """Invalid token should return None."""
        service = AuthService(db_session)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.is_blacklisted = AsyncMock(return_value=False)

            result = await service.refresh_tokens("invalid.token.here")

        assert result is None

    async def test_refresh_tokens_inactive_user(self, db_session: AsyncSession):
        """Inactive user's refresh token should return None."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="inactive@example.com",
            password="password",
            name="Inactive User",
        )

        _, refresh_token = service.generate_tokens(user.id)

        # Deactivate user
        user.is_active = False
        await db_session.commit()

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.is_blacklisted = AsyncMock(return_value=False)

            result = await service.refresh_tokens(refresh_token)

        assert result is None

    async def test_refresh_tokens_blacklists_old_token(self, db_session: AsyncSession):
        """Old refresh token should be blacklisted after successful refresh."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="oldtoken@example.com",
            password="password",
            name="OldToken User",
        )

        _, refresh_token = service.generate_tokens(user.id)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.is_blacklisted = AsyncMock(return_value=False)
            mock_blacklist.add_to_blacklist = AsyncMock()

            await service.refresh_tokens(refresh_token)

            mock_blacklist.add_to_blacklist.assert_called_once()
            call_args = mock_blacklist.add_to_blacklist.call_args
            assert call_args[0][0] == refresh_token


class TestLogout:
    """Tests for logout."""

    async def test_logout_blacklists_access_token(self, db_session: AsyncSession):
        """Access token should be blacklisted on logout."""
        service = AuthService(db_session)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.add_to_blacklist = AsyncMock()

            await service.logout("access_token_here")

            mock_blacklist.add_to_blacklist.assert_called()

    async def test_logout_blacklists_both_tokens(self, db_session: AsyncSession):
        """Both tokens should be blacklisted when refresh token is provided."""
        service = AuthService(db_session)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.add_to_blacklist = AsyncMock()

            await service.logout("access_token", "refresh_token")

            assert mock_blacklist.add_to_blacklist.call_count == 2

    async def test_logout_without_refresh_token(self, db_session: AsyncSession):
        """Should work with only access token."""
        service = AuthService(db_session)

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.add_to_blacklist = AsyncMock()

            await service.logout("access_token_only")

            assert mock_blacklist.add_to_blacklist.call_count == 1


class TestChangePassword:
    """Tests for password change."""

    async def test_change_password_updates_hash(self, db_session: AsyncSession):
        """Password hash should be updated."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="changepw@example.com",
            password="oldpassword",
            name="ChangePW User",
        )

        old_hash = user.password_hash

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.invalidate_all_user_tokens = AsyncMock()

            await service.change_password(user, "newpassword")

        assert user.password_hash != old_hash
        assert verify_password("newpassword", user.password_hash)

    async def test_change_password_invalidates_all_tokens(self, db_session: AsyncSession):
        """All user tokens should be invalidated on password change."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="invalidate@example.com",
            password="oldpassword",
            name="Invalidate User",
        )

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.invalidate_all_user_tokens = AsyncMock()

            await service.change_password(user, "newpassword")

            mock_blacklist.invalidate_all_user_tokens.assert_called_once_with(str(user.id))

    async def test_change_password_old_password_no_longer_works(
        self, db_session: AsyncSession
    ):
        """Old password should no longer authenticate after change."""
        service = AuthService(db_session)

        user = await service.create_user(
            email="oldpw@example.com",
            password="oldpassword",
            name="OldPW User",
        )

        with patch("src.domains.auth.service.TokenBlacklist") as mock_blacklist:
            mock_blacklist.invalidate_all_user_tokens = AsyncMock()

            await service.change_password(user, "newpassword")

        # Old password should not work
        assert not verify_password("oldpassword", user.password_hash)
        # New password should work
        assert verify_password("newpassword", user.password_hash)
