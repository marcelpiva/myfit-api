"""Integration tests for organizations API endpoints."""
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone

from src.domains.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.users.models import User


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def another_user(db_session: AsyncSession) -> User:
    """Create another user for testing member management."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"another-{user_id}@example.com",
        name="Another User",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def non_member_user(db_session: AsyncSession) -> User:
    """Create a user who is not a member of any organization."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"nonmember-{user_id}@example.com",
        name="Non Member User",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def owned_organization(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Organization:
    """Create an organization owned by the sample user."""
    org = Organization(
        name="Owned Gym",
        type=OrganizationType.GYM,
        description="A gym owned by the test user",
        owner_id=sample_user["id"],
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # Add owner as gym_owner member
    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=sample_user["id"],
        role=UserRole.GYM_OWNER,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def other_organization(db_session: AsyncSession, another_user: User) -> Organization:
    """Create an organization that the sample user is NOT a member of."""
    org = Organization(
        name="Other Gym",
        type=OrganizationType.GYM,
        description="A gym the test user is not part of",
        owner_id=another_user.id,
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # Add the other user as owner
    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=another_user.id,
        role=UserRole.GYM_OWNER,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def organization_with_members(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    another_user: User,
) -> Organization:
    """Create an organization with multiple members."""
    org = Organization(
        name="Multi-Member Gym",
        type=OrganizationType.GYM,
        description="A gym with multiple members",
        owner_id=sample_user["id"],
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    # Add owner as gym_owner
    owner_membership = OrganizationMembership(
        organization_id=org.id,
        user_id=sample_user["id"],
        role=UserRole.GYM_OWNER,
        is_active=True,
    )
    db_session.add(owner_membership)

    # Add another user as student
    student_membership = OrganizationMembership(
        organization_id=org.id,
        user_id=another_user.id,
        role=UserRole.STUDENT,
        is_active=True,
    )
    db_session.add(student_membership)

    await db_session.commit()
    await db_session.refresh(org)
    return org


# =============================================================================
# List Organizations Tests
# =============================================================================


class TestListOrganizations:
    """Tests for GET /api/v1/organizations."""

    async def test_list_organizations_authenticated(
        self, authenticated_client: AsyncClient, sample_user: dict[str, Any]
    ):
        """Authenticated user can list their organizations."""
        response = await authenticated_client.get("/api/v1/organizations/")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Sample user is created with a membership in conftest
        assert len(data) >= 1

    async def test_list_organizations_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/organizations/")

        assert response.status_code == 401

    async def test_list_organizations_returns_only_user_orgs(
        self,
        authenticated_client: AsyncClient,
        owned_organization: Organization,
        other_organization: Organization,
    ):
        """User only sees organizations they belong to."""
        response = await authenticated_client.get("/api/v1/organizations/")

        assert response.status_code == 200
        data = response.json()
        org_ids = [org["id"] for org in data]
        # User should see owned org but not other org
        assert str(owned_organization.id) in org_ids
        assert str(other_organization.id) not in org_ids


# =============================================================================
# Create Organization Tests
# =============================================================================


class TestCreateOrganization:
    """Tests for POST /api/v1/organizations."""

    async def test_create_organization_success(self, authenticated_client: AsyncClient):
        """Can create a new organization."""
        payload = {
            "name": "New Test Gym",
            "type": "gym",
            "description": "A brand new gym",
        }

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Test Gym"
        assert data["type"] == "gym"
        assert data["description"] == "A brand new gym"
        assert "id" in data

    async def test_create_organization_with_all_fields(
        self, authenticated_client: AsyncClient
    ):
        """Can create organization with all optional fields."""
        payload = {
            "name": "Complete Gym",
            "type": "gym",
            "description": "Full details gym",
            "address": "123 Fitness Street",
            "phone": "+1234567890",
            "email": "gym@example.com",
            "website": "https://completegym.com",
        }

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["address"] == "123 Fitness Street"
        assert data["phone"] == "+1234567890"
        assert data["email"] == "gym@example.com"
        assert data["website"] == "https://completegym.com"

    async def test_create_organization_personal_type(
        self, authenticated_client: AsyncClient
    ):
        """Can create a personal trainer organization."""
        payload = {
            "name": "Personal Training by Test",
            "type": "personal",
        }

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["type"] == "personal"

    async def test_create_organization_missing_required_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {"description": "Missing name and type"}

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 422

    async def test_create_organization_invalid_type(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid organization type."""
        payload = {
            "name": "Invalid Type Org",
            "type": "invalid_type",
        }

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 422

    async def test_create_organization_name_too_short(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for name that is too short."""
        payload = {
            "name": "X",
            "type": "gym",
        }

        response = await authenticated_client.post(
            "/api/v1/organizations/", json=payload
        )

        assert response.status_code == 422

    async def test_create_organization_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        payload = {
            "name": "Unauth Gym",
            "type": "gym",
        }

        response = await client.post("/api/v1/organizations/", json=payload)

        assert response.status_code == 401


# =============================================================================
# Get Organization Tests
# =============================================================================


class TestGetOrganization:
    """Tests for GET /api/v1/organizations/{org_id}."""

    async def test_get_own_organization(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Can get an organization user belongs to."""
        response = await authenticated_client.get(
            f"/api/v1/organizations/{owned_organization.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Owned Gym"
        assert data["type"] == "gym"
        assert data["id"] == str(owned_organization.id)

    async def test_get_organization_not_member(
        self, authenticated_client: AsyncClient, other_organization: Organization
    ):
        """Returns 403 for organization user is not a member of."""
        response = await authenticated_client.get(
            f"/api/v1/organizations/{other_organization.id}"
        )

        assert response.status_code == 403
        assert "not a member" in response.json()["detail"].lower()

    async def test_get_nonexistent_organization(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent organization."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(f"/api/v1/organizations/{fake_id}")

        assert response.status_code == 404

    async def test_get_organization_unauthenticated(
        self, client: AsyncClient, owned_organization: Organization
    ):
        """Unauthenticated request returns 401."""
        response = await client.get(f"/api/v1/organizations/{owned_organization.id}")

        assert response.status_code == 401


# =============================================================================
# Update Organization Tests
# =============================================================================


class TestUpdateOrganization:
    """Tests for PUT /api/v1/organizations/{org_id}."""

    async def test_update_organization_as_owner(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Owner can update their organization."""
        payload = {
            "name": "Updated Gym Name",
            "description": "Updated description",
        }

        response = await authenticated_client.put(
            f"/api/v1/organizations/{owned_organization.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Gym Name"
        assert data["description"] == "Updated description"

    async def test_update_organization_partial(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Can partially update an organization."""
        payload = {
            "phone": "+9876543210",
        }

        response = await authenticated_client.put(
            f"/api/v1/organizations/{owned_organization.id}", json=payload
        )

        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "+9876543210"
        # Original name should be preserved
        assert data["name"] == "Owned Gym"

    async def test_update_organization_not_admin(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        another_user: User,
    ):
        """Non-admin cannot update organization."""
        # Create org where sample_user is only a student
        org = Organization(
            name="Not Admin Org",
            type=OrganizationType.GYM,
            owner_id=another_user.id,
            is_active=True,
        )
        db_session.add(org)
        await db_session.flush()

        # Add sample_user as student (not admin)
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=sample_user["id"],
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(membership)
        await db_session.commit()

        payload = {"name": "Trying to update"}

        response = await authenticated_client.put(
            f"/api/v1/organizations/{org.id}", json=payload
        )

        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    async def test_update_nonexistent_organization(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent organization."""
        fake_id = uuid.uuid4()
        payload = {"name": "New Name"}

        response = await authenticated_client.put(
            f"/api/v1/organizations/{fake_id}", json=payload
        )

        assert response.status_code == 404


# =============================================================================
# List Members Tests
# =============================================================================


class TestListMembers:
    """Tests for GET /api/v1/organizations/{org_id}/members."""

    async def test_list_members_success(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
    ):
        """Can list members of an organization."""
        response = await authenticated_client.get(
            f"/api/v1/organizations/{organization_with_members.id}/members"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # Owner and student

    async def test_list_members_filter_by_role(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
    ):
        """Can filter members by role."""
        response = await authenticated_client.get(
            f"/api/v1/organizations/{organization_with_members.id}/members",
            params={"role": "student"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(member["role"] == "student" for member in data)

    async def test_list_members_not_member(
        self, authenticated_client: AsyncClient, other_organization: Organization
    ):
        """Returns 403 when not a member of the organization."""
        response = await authenticated_client.get(
            f"/api/v1/organizations/{other_organization.id}/members"
        )

        assert response.status_code == 403

    async def test_list_members_unauthenticated(
        self, client: AsyncClient, owned_organization: Organization
    ):
        """Unauthenticated request returns 401."""
        response = await client.get(
            f"/api/v1/organizations/{owned_organization.id}/members"
        )

        assert response.status_code == 401


# =============================================================================
# Add Member Tests
# =============================================================================


class TestAddMember:
    """Tests for POST /api/v1/organizations/{org_id}/members."""

    async def test_add_member_success(
        self,
        authenticated_client: AsyncClient,
        owned_organization: Organization,
        non_member_user: User,
    ):
        """Admin can add a new member."""
        payload = {
            "user_id": str(non_member_user.id),
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{owned_organization.id}/members", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == str(non_member_user.id)
        assert data["role"] == "student"
        assert data["is_active"] is True

    async def test_add_member_as_trainer(
        self,
        authenticated_client: AsyncClient,
        owned_organization: Organization,
        non_member_user: User,
    ):
        """Can add a member with trainer role."""
        payload = {
            "user_id": str(non_member_user.id),
            "role": "trainer",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{owned_organization.id}/members", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "trainer"

    async def test_add_member_not_admin(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        another_user: User,
        non_member_user: User,
    ):
        """Non-admin cannot add members."""
        # Create org where sample_user is only a student
        org = Organization(
            name="Student Org",
            type=OrganizationType.GYM,
            owner_id=another_user.id,
            is_active=True,
        )
        db_session.add(org)
        await db_session.flush()

        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=sample_user["id"],
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(membership)
        await db_session.commit()

        payload = {
            "user_id": str(non_member_user.id),
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{org.id}/members", json=payload
        )

        assert response.status_code == 403

    async def test_add_member_user_not_found(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Returns 404 when user doesn't exist."""
        fake_user_id = uuid.uuid4()
        payload = {
            "user_id": str(fake_user_id),
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{owned_organization.id}/members", json=payload
        )

        assert response.status_code == 404

    async def test_add_member_already_member(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
        another_user: User,
    ):
        """Returns 400 when user is already a member."""
        payload = {
            "user_id": str(another_user.id),
            "role": "trainer",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{organization_with_members.id}/members", json=payload
        )

        assert response.status_code == 400
        assert "already a member" in response.json()["detail"].lower()


# =============================================================================
# Remove Member Tests
# =============================================================================


class TestRemoveMember:
    """Tests for DELETE /api/v1/organizations/{org_id}/members/{user_id}."""

    async def test_remove_member_as_admin(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
        another_user: User,
    ):
        """Admin can remove a member."""
        response = await authenticated_client.delete(
            f"/api/v1/organizations/{organization_with_members.id}/members/{another_user.id}"
        )

        assert response.status_code == 204

    async def test_remove_self_from_organization(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        another_user: User,
    ):
        """User can remove themselves from an organization."""
        # Create org where sample_user is a member but not owner
        org = Organization(
            name="Self Remove Org",
            type=OrganizationType.GYM,
            owner_id=another_user.id,
            is_active=True,
        )
        db_session.add(org)
        await db_session.flush()

        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=sample_user["id"],
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(membership)
        await db_session.commit()

        response = await authenticated_client.delete(
            f"/api/v1/organizations/{org.id}/members/{sample_user['id']}"
        )

        assert response.status_code == 204

    async def test_remove_member_not_admin_not_self(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        another_user: User,
        non_member_user: User,
    ):
        """Non-admin cannot remove other members."""
        # Create org with sample_user as student
        org = Organization(
            name="No Remove Org",
            type=OrganizationType.GYM,
            owner_id=another_user.id,
            is_active=True,
        )
        db_session.add(org)
        await db_session.flush()

        # Add sample_user as student
        membership1 = OrganizationMembership(
            organization_id=org.id,
            user_id=sample_user["id"],
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(membership1)

        # Add another member
        membership2 = OrganizationMembership(
            organization_id=org.id,
            user_id=non_member_user.id,
            role=UserRole.STUDENT,
            is_active=True,
        )
        db_session.add(membership2)
        await db_session.commit()

        # Try to remove the other member as a student
        response = await authenticated_client.delete(
            f"/api/v1/organizations/{org.id}/members/{non_member_user.id}"
        )

        assert response.status_code == 403

    async def test_remove_member_not_found(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Returns 404 when member doesn't exist."""
        fake_user_id = uuid.uuid4()
        response = await authenticated_client.delete(
            f"/api/v1/organizations/{owned_organization.id}/members/{fake_user_id}"
        )

        assert response.status_code == 404

    async def test_remove_member_not_org_member(
        self, authenticated_client: AsyncClient, other_organization: Organization
    ):
        """Returns 403 when not a member of the organization."""
        fake_user_id = uuid.uuid4()
        response = await authenticated_client.delete(
            f"/api/v1/organizations/{other_organization.id}/members/{fake_user_id}"
        )

        assert response.status_code == 403


# =============================================================================
# Delete Organization Tests
# =============================================================================


class TestDeleteOrganization:
    """Tests for DELETE /api/v1/organizations/{org_id}."""

    async def test_delete_organization_as_owner(
        self, authenticated_client: AsyncClient, owned_organization: Organization
    ):
        """Owner can delete their organization."""
        response = await authenticated_client.delete(
            f"/api/v1/organizations/{owned_organization.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted (should return 404)
        get_response = await authenticated_client.get(
            f"/api/v1/organizations/{owned_organization.id}"
        )
        assert get_response.status_code == 404

    async def test_delete_organization_not_owner(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        another_user: User,
    ):
        """Non-owner cannot delete organization even if admin."""
        # Create org owned by another user but where sample_user is admin
        org = Organization(
            name="Not Owner Org",
            type=OrganizationType.GYM,
            owner_id=another_user.id,
            is_active=True,
        )
        db_session.add(org)
        await db_session.flush()

        # Add sample_user as gym_admin (but not owner)
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=sample_user["id"],
            role=UserRole.GYM_ADMIN,
            is_active=True,
        )
        db_session.add(membership)
        await db_session.commit()

        response = await authenticated_client.delete(f"/api/v1/organizations/{org.id}")

        assert response.status_code == 403
        assert "owner" in response.json()["detail"].lower()

    async def test_delete_nonexistent_organization(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent organization."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.delete(f"/api/v1/organizations/{fake_id}")

        assert response.status_code == 404


# =============================================================================
# Invite Validation Tests
# =============================================================================


@pytest.fixture
async def trainer_organization(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Organization:
    """Create an organization where sample_user is a trainer."""
    org = Organization(
        name="Trainer's Gym",
        type=OrganizationType.PERSONAL,
        description="Personal trainer organization",
        owner_id=sample_user["id"],
        is_active=True,
    )
    db_session.add(org)
    await db_session.flush()

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=sample_user["id"],
        role=UserRole.TRAINER,
        is_active=True,
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(org)
    return org


@pytest.fixture
async def inactive_member(
    db_session: AsyncSession, trainer_organization: Organization
) -> User:
    """Create an inactive member in the trainer's organization."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"inactive-{user_id}@example.com",
        name="Inactive Student",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = OrganizationMembership(
        organization_id=trainer_organization.id,
        user_id=user.id,
        role=UserRole.STUDENT,
        is_active=False,  # Inactive
    )
    db_session.add(membership)
    await db_session.commit()
    await db_session.refresh(user)
    return user


class TestInviteValidation:
    """Tests for invite duplicate validation."""

    async def test_create_invite_success(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
    ):
        """Can create invite for new email."""
        payload = {
            "email": "newstudent@example.com",
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{trainer_organization.id}/invite",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newstudent@example.com"
        assert data["role"] == "student"

    async def test_create_invite_already_active_member(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
        another_user: User,
    ):
        """Returns error when inviting someone who is already an active member."""
        payload = {
            "email": another_user.email,
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{organization_with_members.id}/invite",
            json=payload,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "ALREADY_MEMBER"
        assert "já tem esse aluno" in data["detail"]["message"]

    async def test_create_invite_inactive_member(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
        inactive_member: User,
    ):
        """Returns error with reactivation option for inactive member."""
        payload = {
            "email": inactive_member.email,
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{trainer_organization.id}/invite",
            json=payload,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "INACTIVE_MEMBER"
        assert "inativo" in data["detail"]["message"]
        assert "membership_id" in data["detail"]

    async def test_create_invite_pending_invite_exists(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
    ):
        """Returns error when there's already a pending invite for this email."""
        # Create a pending invite first
        existing_invite = OrganizationInvite(
            organization_id=trainer_organization.id,
            email="pending@example.com",
            role=UserRole.STUDENT,
            token="test-token-123",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            invited_by_id=sample_user["id"],
        )
        db_session.add(existing_invite)
        await db_session.commit()

        # Try to create another invite for the same email
        payload = {
            "email": "pending@example.com",
            "role": "student",
        }

        response = await authenticated_client.post(
            f"/api/v1/organizations/{trainer_organization.id}/invite",
            json=payload,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["code"] == "PENDING_INVITE"
        assert "convite pendente" in data["detail"]["message"]
        assert "invite_id" in data["detail"]


class TestReactivateMember:
    """Tests for member reactivation endpoint."""

    async def test_reactivate_member_success(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
        inactive_member: User,
        db_session: AsyncSession,
    ):
        """Trainer can reactivate an inactive member."""
        # Get the membership ID
        from sqlalchemy import select
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.user_id == inactive_member.id,
            )
        )
        membership = result.scalar_one()

        response = await authenticated_client.post(
            f"/api/v1/organizations/{trainer_organization.id}/members/{membership.id}/reactivate"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True
        assert data["user_id"] == str(inactive_member.id)

    async def test_reactivate_member_already_active(
        self,
        authenticated_client: AsyncClient,
        organization_with_members: Organization,
        another_user: User,
        db_session: AsyncSession,
    ):
        """Returns error when trying to reactivate an already active member."""
        # Get the active membership ID
        from sqlalchemy import select
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == organization_with_members.id,
                OrganizationMembership.user_id == another_user.id,
            )
        )
        membership = result.scalar_one()

        response = await authenticated_client.post(
            f"/api/v1/organizations/{organization_with_members.id}/members/{membership.id}/reactivate"
        )

        assert response.status_code == 400
        assert "já está ativo" in response.json()["detail"]

    async def test_reactivate_member_not_found(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
    ):
        """Returns 404 for nonexistent membership."""
        fake_membership_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"/api/v1/organizations/{trainer_organization.id}/members/{fake_membership_id}/reactivate"
        )

        assert response.status_code == 404

    async def test_reactivate_member_wrong_organization(
        self,
        authenticated_client: AsyncClient,
        trainer_organization: Organization,
        owned_organization: Organization,
        inactive_member: User,
        db_session: AsyncSession,
    ):
        """Returns 404 when membership belongs to different organization."""
        # Get the membership from trainer_organization
        from sqlalchemy import select
        result = await db_session.execute(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == trainer_organization.id,
                OrganizationMembership.user_id == inactive_member.id,
            )
        )
        membership = result.scalar_one()

        # Try to reactivate using a different organization ID
        response = await authenticated_client.post(
            f"/api/v1/organizations/{owned_organization.id}/members/{membership.id}/reactivate"
        )

        assert response.status_code == 404
