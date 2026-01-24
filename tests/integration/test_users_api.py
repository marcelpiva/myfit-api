"""Integration tests for users API endpoints."""
import uuid
from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.users.models import Gender, Theme, Units, User, UserSettings


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def user_with_settings(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> dict[str, Any]:
    """Create a user with associated settings."""
    settings = UserSettings(
        user_id=sample_user["id"],
        theme=Theme.DARK,
        language="pt",
        units=Units.METRIC,
        notifications_enabled=True,
        goal_weight=75.0,
        target_calories=2000,
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(settings)

    return {
        **sample_user,
        "settings_id": settings.id,
    }


@pytest.fixture
async def other_user(
    db_session: AsyncSession, sample_organization_id: uuid.UUID
) -> dict[str, Any]:
    """Create another user for testing user-to-user interactions."""
    from src.domains.organizations.models import OrganizationMembership, UserRole

    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"other-{user_id}@example.com",
        name="Other User",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)

    # Create membership
    membership = OrganizationMembership(
        user_id=user_id,
        organization_id=sample_organization_id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)

    return {
        "id": user_id,
        "email": user.email,
        "name": user.name,
        "organization_id": sample_organization_id,
        "model": user,
    }


# =============================================================================
# Get Profile Tests
# =============================================================================


class TestGetProfile:
    """Tests for GET /api/v1/users/profile."""

    async def test_get_profile_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can get their profile."""
        response = await authenticated_client.get("/api/v1/users/profile")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == sample_user["email"]
        assert data["name"] == sample_user["name"]
        assert "id" in data
        assert "is_active" in data
        assert "is_verified" in data

    async def test_get_profile_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/profile")

        assert response.status_code == 401

    async def test_get_profile_contains_expected_fields(
        self, authenticated_client: AsyncClient
    ):
        """Profile response contains all expected fields."""
        response = await authenticated_client.get("/api/v1/users/profile")

        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "id", "email", "name", "phone", "avatar_url",
            "birth_date", "gender", "height_cm", "bio",
            "is_active", "is_verified"
        ]
        for field in expected_fields:
            assert field in data


# =============================================================================
# Update Profile Tests
# =============================================================================


class TestUpdateProfile:
    """Tests for PUT /api/v1/users/profile."""

    async def test_update_profile_name(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Can update user name."""
        payload = {"name": "Updated Name"}

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    async def test_update_profile_all_fields(
        self, authenticated_client: AsyncClient
    ):
        """Can update multiple profile fields at once."""
        payload = {
            "name": "Complete Profile",
            "phone": "+55 11 99999-9999",
            "birth_date": "1990-05-15",
            "gender": "male",
            "height_cm": 180.5,
            "bio": "Fitness enthusiast and personal trainer.",
        }

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Complete Profile"
        assert data["phone"] == "+55 11 99999-9999"
        assert data["birth_date"] == "1990-05-15"
        assert data["gender"] == "male"
        assert data["height_cm"] == 180.5
        assert data["bio"] == "Fitness enthusiast and personal trainer."

    async def test_update_profile_invalid_height(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid height values."""
        payload = {"height_cm": 500}  # Exceeds maximum of 300

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 422

    async def test_update_profile_name_too_short(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for name that is too short."""
        payload = {"name": "A"}  # Minimum length is 2

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 422

    async def test_update_profile_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {"name": "New Name"}

        response = await client.put("/api/v1/users/profile", json=payload)

        assert response.status_code == 401


# =============================================================================
# Get Settings Tests
# =============================================================================


class TestGetSettings:
    """Tests for GET /api/v1/users/settings."""

    async def test_get_settings_authenticated(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Authenticated user can get their settings."""
        response = await authenticated_client.get("/api/v1/users/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "dark"
        assert data["language"] == "pt"
        assert data["units"] == "metric"
        assert data["notifications_enabled"] is True
        assert data["goal_weight"] == 75.0
        assert data["target_calories"] == 2000

    async def test_get_settings_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/settings")

        assert response.status_code == 401

    async def test_get_settings_not_found(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns 404 when user has no settings."""
        # sample_user without user_with_settings fixture has no settings
        response = await authenticated_client.get("/api/v1/users/settings")

        assert response.status_code == 404


# =============================================================================
# Update Settings Tests
# =============================================================================


class TestUpdateSettings:
    """Tests for PUT /api/v1/users/settings."""

    async def test_update_settings_theme(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can update theme setting."""
        payload = {"theme": "light"}

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "light"

    async def test_update_settings_all_fields(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can update multiple settings at once."""
        payload = {
            "theme": "system",
            "language": "en",
            "units": "imperial",
            "notifications_enabled": False,
            "goal_weight": 80.0,
            "target_calories": 2500,
        }

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["theme"] == "system"
        assert data["language"] == "en"
        assert data["units"] == "imperial"
        assert data["notifications_enabled"] is False
        assert data["goal_weight"] == 80.0
        assert data["target_calories"] == 2500

    async def test_update_settings_invalid_goal_weight(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Returns 422 for invalid goal weight."""
        payload = {"goal_weight": 10}  # Below minimum of 20

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 422

    async def test_update_settings_invalid_calories(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Returns 422 for invalid target calories."""
        payload = {"target_calories": 15000}  # Exceeds maximum of 10000

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 422

    async def test_update_settings_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {"theme": "dark"}

        response = await client.put("/api/v1/users/settings", json=payload)

        assert response.status_code == 401


# =============================================================================
# Search Users Tests
# =============================================================================


class TestSearchUsers:
    """Tests for GET /api/v1/users/search."""

    async def test_search_users_by_name(
        self, authenticated_client: AsyncClient, other_user: dict[str, Any]
    ):
        """Can search users by name."""
        response = await authenticated_client.get(
            "/api/v1/users/search", params={"q": "Other"}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(u["name"] == "Other User" for u in data)

    async def test_search_users_by_email(
        self, authenticated_client: AsyncClient, other_user: dict[str, Any]
    ):
        """Can search users by email."""
        response = await authenticated_client.get(
            "/api/v1/users/search", params={"q": "other-"}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_search_users_query_too_short(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for query shorter than 2 characters."""
        response = await authenticated_client.get(
            "/api/v1/users/search", params={"q": "a"}
        )

        assert response.status_code == 422

    async def test_search_users_pagination(
        self, authenticated_client: AsyncClient, other_user: dict[str, Any]
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/users/search", params={"q": "User", "limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 1

    async def test_search_users_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/search", params={"q": "test"})

        assert response.status_code == 401


# =============================================================================
# Get Memberships Tests
# =============================================================================


class TestGetMemberships:
    """Tests for GET /api/v1/users/me/memberships."""

    async def test_get_memberships_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can get their memberships."""
        response = await authenticated_client.get("/api/v1/users/me/memberships")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify membership structure
        membership = data[0]
        assert "id" in membership
        assert "organization" in membership
        assert "role" in membership
        assert "joined_at" in membership
        assert "is_active" in membership

    async def test_get_memberships_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/me/memberships")

        assert response.status_code == 401

    async def test_get_memberships_contains_organization_details(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Membership response includes organization details."""
        response = await authenticated_client.get("/api/v1/users/me/memberships")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        org = data[0]["organization"]
        assert "id" in org
        assert "name" in org
        assert "type" in org


# =============================================================================
# Student Dashboard Tests
# =============================================================================


class TestStudentDashboard:
    """Tests for GET /api/v1/users/me/dashboard."""

    async def test_get_dashboard_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can get their dashboard."""
        response = await authenticated_client.get("/api/v1/users/me/dashboard")

        assert response.status_code == 200
        data = response.json()
        # Verify dashboard structure
        assert "stats" in data
        assert "weekly_progress" in data
        assert "recent_activity" in data

    async def test_get_dashboard_stats_structure(
        self, authenticated_client: AsyncClient
    ):
        """Dashboard stats has expected structure."""
        response = await authenticated_client.get("/api/v1/users/me/dashboard")

        assert response.status_code == 200
        stats = response.json()["stats"]
        assert "total_workouts" in stats
        assert "adherence_percent" in stats
        assert "weight_change_kg" in stats
        assert "current_streak" in stats

    async def test_get_dashboard_weekly_progress_structure(
        self, authenticated_client: AsyncClient
    ):
        """Dashboard weekly progress has expected structure."""
        response = await authenticated_client.get("/api/v1/users/me/dashboard")

        assert response.status_code == 200
        weekly = response.json()["weekly_progress"]
        assert "completed" in weekly
        assert "target" in weekly
        assert "days" in weekly
        assert isinstance(weekly["days"], list)

    async def test_get_dashboard_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/me/dashboard")

        assert response.status_code == 401


# =============================================================================
# Get Trainer Notes Tests
# =============================================================================


class TestGetTrainerNotes:
    """Tests for GET /api/v1/users/me/trainer-notes."""

    async def test_get_trainer_notes_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Authenticated user can get trainer notes about them."""
        response = await authenticated_client.get("/api/v1/users/me/trainer-notes")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_trainer_notes_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/me/trainer-notes")

        assert response.status_code == 401

    async def test_get_trainer_notes_pagination(
        self, authenticated_client: AsyncClient
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/users/me/trainer-notes",
            params={"limit": 10, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


# =============================================================================
# Get Pending Invites Tests
# =============================================================================


class TestGetPendingInvites:
    """Tests for GET /api/v1/users/me/pending-invites."""

    async def test_get_pending_invites_authenticated(
        self, authenticated_client: AsyncClient
    ):
        """Authenticated user can get their pending invites."""
        response = await authenticated_client.get("/api/v1/users/me/pending-invites")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_pending_invites_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/users/me/pending-invites")

        assert response.status_code == 401


# =============================================================================
# Avatar Upload Tests
# =============================================================================


class TestUploadAvatar:
    """Tests for POST /api/v1/users/avatar."""

    async def test_upload_avatar_success_jpeg(
        self, authenticated_client: AsyncClient
    ):
        """Can upload a JPEG avatar image."""
        # Create a minimal JPEG file content (valid JPEG header)
        jpeg_content = bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46,
            0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
            0xFF, 0xD9
        ])
        files = {"file": ("avatar.jpg", jpeg_content, "image/jpeg")}

        response = await authenticated_client.post(
            "/api/v1/users/avatar", files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert "avatar_url" in data
        assert data["avatar_url"].endswith(".jpg")

    async def test_upload_avatar_success_png(
        self, authenticated_client: AsyncClient
    ):
        """Can upload a PNG avatar image."""
        # Create minimal PNG content
        png_content = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 pixel
            0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
            0xDE, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
            0x44, 0xAE, 0x42, 0x60, 0x82
        ])
        files = {"file": ("avatar.png", png_content, "image/png")}

        response = await authenticated_client.post(
            "/api/v1/users/avatar", files=files
        )

        assert response.status_code == 200
        data = response.json()
        assert "avatar_url" in data

    async def test_upload_avatar_invalid_file_type(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 for invalid file type."""
        # Try to upload a GIF (not allowed)
        gif_content = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
        files = {"file": ("avatar.gif", gif_content, "image/gif")}

        response = await authenticated_client.post(
            "/api/v1/users/avatar", files=files
        )

        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    async def test_upload_avatar_file_too_large(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 for file exceeding size limit."""
        # Create a file larger than 5MB
        large_content = b"x" * (6 * 1024 * 1024)  # 6MB
        files = {"file": ("large_avatar.jpg", large_content, "image/jpeg")}

        response = await authenticated_client.post(
            "/api/v1/users/avatar", files=files
        )

        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]

    async def test_upload_avatar_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        files = {"file": ("avatar.jpg", b"fake content", "image/jpeg")}

        response = await client.post("/api/v1/users/avatar", files=files)

        assert response.status_code == 401


# =============================================================================
# Password Change Tests
# =============================================================================


class TestChangePassword:
    """Tests for PUT /api/v1/users/password."""

    async def test_change_password_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {
            "current_password": "oldpassword",
            "new_password": "newpassword123",
        }

        response = await client.put("/api/v1/users/password", json=payload)

        assert response.status_code == 401

    async def test_change_password_new_too_short(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for new password that is too short."""
        payload = {
            "current_password": "currentpassword",
            "new_password": "short",  # Less than 6 characters
        }

        response = await authenticated_client.put(
            "/api/v1/users/password", json=payload
        )

        assert response.status_code == 422

    async def test_change_password_missing_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 when required fields are missing."""
        payload = {"new_password": "newpassword123"}  # Missing current_password

        response = await authenticated_client.put(
            "/api/v1/users/password", json=payload
        )

        assert response.status_code == 422


# =============================================================================
# Update Profile Edge Cases Tests
# =============================================================================


class TestUpdateProfileEdgeCases:
    """Additional edge case tests for profile updates."""

    async def test_update_profile_gender_female(
        self, authenticated_client: AsyncClient
    ):
        """Can update gender to female."""
        payload = {"gender": "female"}

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["gender"] == "female"

    async def test_update_profile_gender_other(
        self, authenticated_client: AsyncClient
    ):
        """Can update gender to other."""
        payload = {"gender": "other"}

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["gender"] == "other"

    async def test_update_profile_bio_max_length(
        self, authenticated_client: AsyncClient
    ):
        """Can set bio at maximum length."""
        long_bio = "A" * 1000  # Maximum allowed length

        payload = {"bio": long_bio}

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["bio"]) == 1000

    async def test_update_profile_height_min_value(
        self, authenticated_client: AsyncClient
    ):
        """Can set height at minimum allowed value."""
        payload = {"height_cm": 50}  # Minimum allowed

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["height_cm"] == 50

    async def test_update_profile_height_below_min(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for height below minimum."""
        payload = {"height_cm": 49}  # Below minimum of 50

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        assert response.status_code == 422

    async def test_update_profile_empty_payload(
        self, authenticated_client: AsyncClient
    ):
        """Can send empty payload (no changes)."""
        payload = {}

        response = await authenticated_client.put(
            "/api/v1/users/profile", json=payload
        )

        # Should succeed with no changes
        assert response.status_code == 200


# =============================================================================
# Update Settings Edge Cases Tests
# =============================================================================


class TestUpdateSettingsEdgeCases:
    """Additional edge case tests for settings updates."""

    async def test_update_settings_to_imperial_units(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can change units to imperial."""
        payload = {"units": "imperial"}

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["units"] == "imperial"

    async def test_update_settings_goal_weight_min(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can set goal weight at minimum value."""
        payload = {"goal_weight": 20.0}  # Minimum allowed

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["goal_weight"] == 20.0

    async def test_update_settings_goal_weight_max(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can set goal weight at maximum value."""
        payload = {"goal_weight": 500.0}  # Maximum allowed

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["goal_weight"] == 500.0

    async def test_update_settings_calories_min(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can set target calories at minimum value."""
        payload = {"target_calories": 500}  # Minimum allowed

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target_calories"] == 500

    async def test_update_settings_calories_max(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can set target calories at maximum value."""
        payload = {"target_calories": 10000}  # Maximum allowed

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target_calories"] == 10000

    async def test_update_settings_language_change(
        self, authenticated_client: AsyncClient, user_with_settings: dict[str, Any]
    ):
        """Can change language setting."""
        payload = {"language": "en"}

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"

    async def test_update_settings_not_found(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Returns 404 when trying to update settings that don't exist."""
        # sample_user without user_with_settings fixture has no settings
        payload = {"theme": "dark"}

        response = await authenticated_client.put(
            "/api/v1/users/settings", json=payload
        )

        assert response.status_code == 404
