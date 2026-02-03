"""User service with database operations."""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import and_, select
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
        cref: str | None = None,
        specialties: list[str] | None = None,
        years_of_experience: int | None = None,
        fitness_goal: str | None = None,
        fitness_goal_other: str | None = None,
        experience_level: str | None = None,
        weight_kg: float | None = None,
        age: int | None = None,
        weekly_frequency: int | None = None,
        injuries: list[str] | None = None,
        injuries_other: str | None = None,
        preferred_duration: str | None = None,
        training_location: list[str] | None = None,
        preferred_activities: list[str] | None = None,
        can_do_impact: bool | None = None,
        onboarding_completed: bool | None = None,
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
            cref: CREF registration number (optional)
            specialties: List of specialties for trainers (optional)
            years_of_experience: Years of experience for trainers (optional)
            fitness_goal: Fitness goal for students (optional)
            fitness_goal_other: Custom fitness goal (optional)
            experience_level: Experience level for students (optional)
            weight_kg: Weight in kg (optional)
            age: Age (optional)
            weekly_frequency: Weekly workout frequency (optional)
            injuries: List of injuries (optional)
            injuries_other: Custom injuries description (optional)
            onboarding_completed: Whether onboarding is completed (optional)

        Returns:
            The updated User object
        """
        import json

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
        if cref is not None:
            user.cref = cref
        if specialties is not None:
            user.specialties = json.dumps(specialties)
        if years_of_experience is not None:
            user.years_of_experience = years_of_experience
        if fitness_goal is not None:
            user.fitness_goal = fitness_goal
        if fitness_goal_other is not None:
            user.fitness_goal_other = fitness_goal_other
        if experience_level is not None:
            user.experience_level = experience_level
        if weight_kg is not None:
            user.weight_kg = weight_kg
        if age is not None:
            user.age = age
        if weekly_frequency is not None:
            user.weekly_frequency = weekly_frequency
        if injuries is not None:
            user.injuries = json.dumps(injuries)
        if injuries_other is not None:
            user.injuries_other = injuries_other
        if preferred_duration is not None:
            user.preferred_duration = preferred_duration
        if training_location is not None:
            user.training_location = json.dumps(training_location)
        if preferred_activities is not None:
            user.preferred_activities = json.dumps(preferred_activities)
        if can_do_impact is not None:
            user.can_do_impact = can_do_impact
        if onboarding_completed is not None:
            user.onboarding_completed = onboarding_completed

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

    async def delete_account(self, user: User) -> None:
        """Soft-delete a user account.

        - Archives all organizations where user is owner
        - Deactivates all user memberships
        - Sets user is_active=False

        Args:
            user: The User to delete
        """
        from src.domains.organizations.models import (
            Organization,
            OrganizationMembership,
        )
        from src.domains.workouts.models import WorkoutAssignment

        # 1. Archive organizations where user is owner
        owned_orgs_result = await self.db.execute(
            select(Organization).where(
                and_(
                    Organization.owner_id == user.id,
                    Organization.is_active == True,
                )
            )
        )
        owned_orgs = owned_orgs_result.scalars().all()
        for org in owned_orgs:
            org.archived_at = datetime.now(timezone.utc)
            # Deactivate workout assignments in owned orgs
            assignments_result = await self.db.execute(
                select(WorkoutAssignment).where(
                    and_(
                        WorkoutAssignment.organization_id == org.id,
                        WorkoutAssignment.is_active == True,
                    )
                )
            )
            for assignment in assignments_result.scalars().all():
                assignment.is_active = False

        # 2. Deactivate all user memberships
        memberships_result = await self.db.execute(
            select(OrganizationMembership).where(
                and_(
                    OrganizationMembership.user_id == user.id,
                    OrganizationMembership.is_active == True,
                )
            )
        )
        for membership in memberships_result.scalars().all():
            membership.is_active = False

        # 3. Soft-delete user
        user.is_active = False

        await self.db.commit()
