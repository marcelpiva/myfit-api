"""User service with database operations."""
import uuid
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import hash_password, verify_password
from src.domains.users.models import Gender, Theme, Units, User, UserSettings


class UserService:
    """Service for handling user operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

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

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email.

        Args:
            email: The user's email

        Returns:
            The User object if found, None otherwise
        """
        result = await self.db.execute(
            select(User).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def update_profile(
        self,
        user: User,
        name: str | None = None,
        phone: str | None = None,
        birth_date: date | None = None,
        gender: Gender | None = None,
        height_cm: float | None = None,
        bio: str | None = None,
    ) -> User:
        """Update user profile.

        Args:
            user: The User object to update
            name: New name (optional)
            phone: New phone (optional)
            birth_date: New birth date (optional)
            gender: New gender (optional)
            height_cm: New height in cm (optional)
            bio: New bio (optional)

        Returns:
            The updated User object
        """
        if name is not None:
            user.name = name
        if phone is not None:
            user.phone = phone
        if birth_date is not None:
            user.birth_date = birth_date
        if gender is not None:
            user.gender = gender
        if height_cm is not None:
            user.height_cm = height_cm
        if bio is not None:
            user.bio = bio

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_avatar(self, user: User, avatar_url: str) -> User:
        """Update user avatar URL.

        Args:
            user: The User object to update
            avatar_url: The new avatar URL

        Returns:
            The updated User object
        """
        user.avatar_url = avatar_url
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def get_settings(self, user_id: uuid.UUID) -> UserSettings | None:
        """Get user settings.

        Args:
            user_id: The user's UUID

        Returns:
            The UserSettings object if found, None otherwise
        """
        result = await self.db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_settings(
        self,
        settings: UserSettings,
        theme: Theme | None = None,
        language: str | None = None,
        units: Units | None = None,
        notifications_enabled: bool | None = None,
        goal_weight: float | None = None,
        target_calories: int | None = None,
    ) -> UserSettings:
        """Update user settings.

        Args:
            settings: The UserSettings object to update
            theme: New theme (optional)
            language: New language (optional)
            units: New units (optional)
            notifications_enabled: New notifications setting (optional)
            goal_weight: New goal weight (optional)
            target_calories: New target calories (optional)

        Returns:
            The updated UserSettings object
        """
        if theme is not None:
            settings.theme = theme
        if language is not None:
            settings.language = language
        if units is not None:
            settings.units = units
        if notifications_enabled is not None:
            settings.notifications_enabled = notifications_enabled
        if goal_weight is not None:
            settings.goal_weight = goal_weight
        if target_calories is not None:
            settings.target_calories = target_calories

        await self.db.commit()
        await self.db.refresh(settings)
        return settings

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
    ) -> bool:
        """Change user's password.

        Args:
            user: The User object
            current_password: The current password
            new_password: The new password

        Returns:
            True if password was changed, False if current password is wrong
        """
        if not verify_password(current_password, user.password_hash):
            return False

        user.password_hash = hash_password(new_password)
        await self.db.commit()
        return True

    async def search_users(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[User]:
        """Search users by name or email.

        Args:
            query: Search query
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of matching users
        """
        search_pattern = f"%{query}%"
        result = await self.db.execute(
            select(User)
            .where(
                (User.name.ilike(search_pattern)) |
                (User.email.ilike(search_pattern))
            )
            .where(User.is_active == True)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
