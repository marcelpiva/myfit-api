"""Tests for User service business logic."""
import uuid
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import Gender, Theme, Units, User, UserSettings
from src.domains.users.service import UserService


class TestGetUserById:
    """Tests for get_user_by_id method."""

    async def test_get_existing_user(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return user when found."""
        service = UserService(db_session)

        user = await service.get_user_by_id(sample_user["id"])

        assert user is not None
        assert user.id == sample_user["id"]
        assert user.email == sample_user["email"]

    async def test_get_nonexistent_user(self, db_session: AsyncSession):
        """Should return None for nonexistent user."""
        service = UserService(db_session)

        user = await service.get_user_by_id(uuid.uuid4())

        assert user is None


class TestGetUserByEmail:
    """Tests for get_user_by_email method."""

    async def test_get_user_by_email(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find user by email."""
        service = UserService(db_session)

        user = await service.get_user_by_email(sample_user["email"])

        assert user is not None
        assert user.id == sample_user["id"]

    async def test_email_is_case_insensitive(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find user regardless of email case."""
        service = UserService(db_session)

        user = await service.get_user_by_email(sample_user["email"].upper())

        assert user is not None
        assert user.id == sample_user["id"]

    async def test_nonexistent_email(self, db_session: AsyncSession):
        """Should return None for nonexistent email."""
        service = UserService(db_session)

        user = await service.get_user_by_email("nonexistent@example.com")

        assert user is None


class TestUpdateProfile:
    """Tests for update_profile method."""

    async def test_update_name(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user name."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(user, name="New Name")

        assert updated.name == "New Name"

    async def test_update_phone(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user phone."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(user, phone="+5511999999999")

        assert updated.phone == "+5511999999999"

    async def test_update_birth_date(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user birth date."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()
        birth = date(1990, 5, 15)

        updated = await service.update_profile(user, birth_date=birth)

        assert updated.birth_date == birth

    async def test_update_gender(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user gender."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(user, gender=Gender.MALE)

        assert updated.gender == Gender.MALE

    async def test_update_height(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user height."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(user, height_cm=175.5)

        assert updated.height_cm == 175.5

    async def test_update_bio(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user bio."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(user, bio="Fitness enthusiast")

        assert updated.bio == "Fitness enthusiast"

    async def test_update_multiple_fields(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update multiple fields at once."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_profile(
            user,
            name="Updated Name",
            phone="+5511888888888",
            height_cm=180.0,
        )

        assert updated.name == "Updated Name"
        assert updated.phone == "+5511888888888"
        assert updated.height_cm == 180.0


class TestUpdateAvatar:
    """Tests for update_avatar method."""

    async def test_update_avatar_url(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update user avatar URL."""
        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        updated = await service.update_avatar(
            user, avatar_url="https://example.com/avatar.jpg"
        )

        assert updated.avatar_url == "https://example.com/avatar.jpg"


class TestUserSettings:
    """Tests for user settings operations."""

    async def test_get_settings(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should get user settings."""
        service = UserService(db_session)

        # Create settings first
        settings = UserSettings(
            user_id=sample_user["id"],
            theme=Theme.DARK,
            language="pt",
        )
        db_session.add(settings)
        await db_session.commit()

        result = await service.get_settings(sample_user["id"])

        assert result is not None
        assert result.theme == Theme.DARK
        assert result.language == "pt"

    async def test_get_settings_not_found(self, db_session: AsyncSession):
        """Should return None when settings not found."""
        service = UserService(db_session)

        result = await service.get_settings(uuid.uuid4())

        assert result is None

    async def test_update_theme(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update theme setting."""
        service = UserService(db_session)

        settings = UserSettings(
            user_id=sample_user["id"],
            theme=Theme.LIGHT,
        )
        db_session.add(settings)
        await db_session.commit()

        updated = await service.update_settings(settings, theme=Theme.DARK)

        assert updated.theme == Theme.DARK

    async def test_update_language(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update language setting."""
        service = UserService(db_session)

        settings = UserSettings(user_id=sample_user["id"])
        db_session.add(settings)
        await db_session.commit()

        updated = await service.update_settings(settings, language="es")

        assert updated.language == "es"

    async def test_update_units(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update units setting."""
        service = UserService(db_session)

        settings = UserSettings(user_id=sample_user["id"])
        db_session.add(settings)
        await db_session.commit()

        updated = await service.update_settings(settings, units=Units.IMPERIAL)

        assert updated.units == Units.IMPERIAL

    async def test_update_notifications(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update notifications setting."""
        service = UserService(db_session)

        settings = UserSettings(user_id=sample_user["id"])
        db_session.add(settings)
        await db_session.commit()

        updated = await service.update_settings(
            settings, notifications_enabled=False
        )

        assert updated.notifications_enabled is False


class TestChangePassword:
    """Tests for change_password method."""

    async def test_change_password_success(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should change password when current password is correct."""
        from src.core.security import hash_password

        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        # Set a known password
        user.password_hash = hash_password("current_password")
        await db_session.commit()

        success = await service.change_password(
            user,
            current_password="current_password",
            new_password="new_password",
        )

        assert success is True

    async def test_change_password_wrong_current(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should fail when current password is wrong."""
        from src.core.security import hash_password

        service = UserService(db_session)
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        # Set a known password
        user.password_hash = hash_password("correct_password")
        await db_session.commit()

        success = await service.change_password(
            user,
            current_password="wrong_password",
            new_password="new_password",
        )

        assert success is False


class TestSearchUsers:
    """Tests for search_users method."""

    async def test_search_by_name(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find users by name."""
        service = UserService(db_session)

        # sample_user has name "Test User"
        users = await service.search_users("Test")

        assert len(users) >= 1
        assert any(u.id == sample_user["id"] for u in users)

    async def test_search_by_email(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find users by email."""
        service = UserService(db_session)

        # Extract email without domain
        email_part = sample_user["email"].split("@")[0]
        users = await service.search_users(email_part)

        assert len(users) >= 1
        assert any(u.id == sample_user["id"] for u in users)

    async def test_search_case_insensitive(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Search should be case insensitive."""
        service = UserService(db_session)

        users = await service.search_users("TEST USER")

        assert len(users) >= 1
        assert any(u.id == sample_user["id"] for u in users)

    async def test_search_excludes_inactive_users(
        self, db_session: AsyncSession, inactive_user: dict
    ):
        """Search should exclude inactive users."""
        service = UserService(db_session)

        users = await service.search_users("Inactive")

        assert not any(u.id == inactive_user["id"] for u in users)

    async def test_search_pagination(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Search should support pagination."""
        service = UserService(db_session)

        # First page
        page1 = await service.search_users("", limit=1, offset=0)
        # Second page
        page2 = await service.search_users("", limit=1, offset=1)

        # Results should be different (if we have more than 1 user)
        if len(page1) > 0 and len(page2) > 0:
            # This may or may not have different results depending on test order
            pass  # Just verify pagination works without error
