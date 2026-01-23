"""Tests for OrganizationService - organizations, memberships, and invites."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.organizations.service import OrganizationService
from src.domains.users.models import User


class TestCreateOrganization:
    """Tests for organization creation."""

    async def test_create_organization_sets_owner(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Organization should have owner_id set."""
        service = OrganizationService(db_session)

        # Get user from database
        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="My Gym",
            org_type=OrganizationType.GYM,
        )

        assert org.owner_id == user.id
        assert org.name == "My Gym"
        assert org.type == OrganizationType.GYM

    async def test_create_organization_creates_owner_membership(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Owner should automatically become a member."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="My Gym",
            org_type=OrganizationType.GYM,
        )

        membership = await service.get_membership(org.id, user.id)

        assert membership is not None
        assert membership.is_active is True

    @pytest.mark.parametrize(
        "org_type,expected_role",
        [
            (OrganizationType.GYM, UserRole.GYM_OWNER),
            (OrganizationType.PERSONAL, UserRole.TRAINER),
            (OrganizationType.NUTRITIONIST, UserRole.NUTRITIONIST),
            (OrganizationType.CLINIC, UserRole.COACH),
        ],
    )
    async def test_create_organization_assigns_correct_role(
        self,
        db_session: AsyncSession,
        sample_user: dict,
        org_type: OrganizationType,
        expected_role: UserRole,
    ):
        """Owner role should match organization type."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name=f"Test {org_type.value}",
            org_type=org_type,
        )

        membership = await service.get_membership(org.id, user.id)

        assert membership.role == expected_role

    async def test_create_organization_is_active_by_default(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """New organization should be active."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Active Org",
            org_type=OrganizationType.PERSONAL,
        )

        assert org.is_active is True


class TestDeleteOrganization:
    """Tests for organization soft delete."""

    async def test_delete_organization_soft_delete(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Deleting should set is_active to False."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Delete Me",
            org_type=OrganizationType.PERSONAL,
        )

        await service.delete_organization(org)

        assert org.is_active is False

    async def test_deleted_org_not_in_user_organizations(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Deleted orgs should not appear in user's organization list."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Hidden Org",
            org_type=OrganizationType.PERSONAL,
        )

        await service.delete_organization(org)

        orgs = await service.get_user_organizations(user.id)
        org_ids = [o.id for o in orgs]

        assert org.id not in org_ids


class TestMembershipOperations:
    """Tests for membership management."""

    async def test_add_member(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should add a new member to organization."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Membership Test",
            org_type=OrganizationType.GYM,
        )

        new_member_id = uuid.uuid4()
        # Create new user
        new_user = User(
            id=new_member_id,
            email="newmember@example.com",
            name="New Member",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(new_user)
        await db_session.commit()

        membership = await service.add_member(
            org_id=org.id,
            user_id=new_member_id,
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        assert membership.user_id == new_member_id
        assert membership.role == UserRole.STUDENT
        assert membership.invited_by_id == user.id
        assert membership.is_active is True

    async def test_get_membership_returns_highest_priority(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """When user has multiple roles, should return highest priority."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Multi Role Test",
            org_type=OrganizationType.GYM,
        )

        # Add same user as student (they're already GYM_OWNER)
        student_membership = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=UserRole.STUDENT,
        )
        db_session.add(student_membership)
        await db_session.commit()

        # Get membership should return GYM_OWNER (higher priority)
        membership = await service.get_membership(org.id, user.id)

        assert membership.role == UserRole.GYM_OWNER

    async def test_update_member_role(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should update member's role."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Role Update Test",
            org_type=OrganizationType.GYM,
        )

        # Add a trainer
        trainer_id = uuid.uuid4()
        trainer = User(
            id=trainer_id,
            email="trainer@example.com",
            name="Trainer",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(trainer)
        await db_session.commit()

        membership = await service.add_member(
            org_id=org.id,
            user_id=trainer_id,
            role=UserRole.TRAINER,
        )

        # Promote to admin
        updated = await service.update_member_role(membership, UserRole.GYM_ADMIN)

        assert updated.role == UserRole.GYM_ADMIN

    async def test_remove_member(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should deactivate membership."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Remove Test",
            org_type=OrganizationType.GYM,
        )

        # Add member
        member_id = uuid.uuid4()
        member = User(
            id=member_id,
            email="removeme@example.com",
            name="Remove Me",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(member)
        await db_session.commit()

        membership = await service.add_member(
            org_id=org.id,
            user_id=member_id,
            role=UserRole.STUDENT,
        )

        await service.remove_member(membership)

        assert membership.is_active is False

    async def test_get_organization_members_active_only(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter by active members."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Members Test",
            org_type=OrganizationType.GYM,
        )

        # Add and remove a member
        member_id = uuid.uuid4()
        member = User(
            id=member_id,
            email="inactive@example.com",
            name="Inactive",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(member)
        await db_session.commit()

        membership = await service.add_member(
            org_id=org.id,
            user_id=member_id,
            role=UserRole.STUDENT,
        )
        await service.remove_member(membership)

        members = await service.get_organization_members(org.id, active_only=True)

        # Only owner should be active
        assert len(members) == 1
        assert members[0].user_id == user.id


class TestInviteOperations:
    """Tests for invitation system."""

    async def test_create_invite(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create invitation with token."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Invite Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="invited@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        assert invite.email == "invited@example.com"
        assert invite.role == UserRole.STUDENT
        assert invite.token is not None
        assert len(invite.token) > 20
        assert invite.accepted_at is None

    async def test_create_invite_normalizes_email(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Email should be lowercased."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Email Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="UPPERCASE@EXAMPLE.COM",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        assert invite.email == "uppercase@example.com"

    async def test_create_invite_expires_in_7_days_by_default(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Default expiration should be 7 days."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Expiry Test",
            org_type=OrganizationType.GYM,
        )

        before = datetime.utcnow()
        invite = await service.create_invite(
            org_id=org.id,
            email="expiry@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        expected_min = before + timedelta(days=7)
        expected_max = datetime.utcnow() + timedelta(days=7, seconds=5)

        # Compare naive datetimes (SQLite returns naive datetimes)
        expires_at = invite.expires_at.replace(tzinfo=None) if invite.expires_at.tzinfo else invite.expires_at
        assert expires_at >= expected_min
        assert expires_at <= expected_max

    async def test_get_invite_by_token(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find invite by token."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Token Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="token@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        found = await service.get_invite_by_token(invite.token)

        assert found is not None
        assert found.id == invite.id

    async def test_accept_invite_creates_membership(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Accepting invite should create membership."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        owner = result.scalar_one()

        org = await service.create_organization(
            owner=owner,
            name="Accept Test",
            org_type=OrganizationType.GYM,
        )

        # Create invited user
        invited_user = User(
            id=uuid.uuid4(),
            email="accept@example.com",
            name="Accepted User",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(invited_user)
        await db_session.commit()

        invite = await service.create_invite(
            org_id=org.id,
            email="accept@example.com",
            role=UserRole.STUDENT,
            invited_by_id=owner.id,
        )

        membership = await service.accept_invite(invite, invited_user)

        assert membership.user_id == invited_user.id
        assert membership.role == UserRole.STUDENT
        assert membership.organization_id == org.id
        assert invite.accepted_at is not None

    async def test_resend_invite_regenerates_token(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Resending should create new token."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Resend Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="resend@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        old_token = invite.token

        updated = await service.resend_invite(invite)

        assert updated.token != old_token
        assert updated.resend_count == 1

    async def test_resend_invite_increments_counter(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Resend counter should increment."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Counter Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="counter@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        await service.resend_invite(invite)
        await service.resend_invite(invite)
        await service.resend_invite(invite)

        assert invite.resend_count == 3

    async def test_delete_invite(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete invite."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Delete Invite Test",
            org_type=OrganizationType.GYM,
        )

        invite = await service.create_invite(
            org_id=org.id,
            email="delete@example.com",
            role=UserRole.STUDENT,
            invited_by_id=user.id,
        )

        invite_id = invite.id
        await service.delete_invite(invite)

        found = await service.get_invite_by_id(invite_id)
        assert found is None


class TestPermissionChecks:
    """Tests for permission checking methods."""

    async def test_is_admin_gym_owner(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """GYM_OWNER should be admin."""
        service = OrganizationService(db_session)

        membership = OrganizationMembership(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=UserRole.GYM_OWNER,
        )

        assert service.is_admin(membership) is True

    async def test_is_admin_gym_admin(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """GYM_ADMIN should be admin."""
        service = OrganizationService(db_session)

        membership = OrganizationMembership(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=UserRole.GYM_ADMIN,
        )

        assert service.is_admin(membership) is True

    async def test_is_admin_trainer_not_admin(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """TRAINER should not be admin."""
        service = OrganizationService(db_session)

        membership = OrganizationMembership(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=UserRole.TRAINER,
        )

        assert service.is_admin(membership) is False

    async def test_is_admin_student_not_admin(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """STUDENT should not be admin."""
        service = OrganizationService(db_session)

        membership = OrganizationMembership(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=UserRole.STUDENT,
        )

        assert service.is_admin(membership) is False

    @pytest.mark.parametrize(
        "role,expected",
        [
            (UserRole.GYM_OWNER, True),
            (UserRole.GYM_ADMIN, True),
            (UserRole.TRAINER, True),
            (UserRole.COACH, True),
            (UserRole.NUTRITIONIST, True),
            (UserRole.STUDENT, False),
        ],
    )
    async def test_is_professional(
        self,
        db_session: AsyncSession,
        role: UserRole,
        expected: bool,
    ):
        """Test professional role check for all roles."""
        service = OrganizationService(db_session)

        membership = OrganizationMembership(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            role=role,
        )

        assert service.is_professional(membership) is expected


class TestGetUserOrganizations:
    """Tests for getting user's organizations."""

    async def test_get_user_organizations(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return all active organizations for user."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        # Create multiple orgs
        org1 = await service.create_organization(
            owner=user,
            name="Org 1",
            org_type=OrganizationType.PERSONAL,
        )

        org2 = await service.create_organization(
            owner=user,
            name="Org 2",
            org_type=OrganizationType.GYM,
        )

        orgs = await service.get_user_organizations(user.id)

        # Note: sample_user fixture already creates an organization
        assert len(orgs) >= 2
        org_names = [o.name for o in orgs]
        assert "Org 1" in org_names
        assert "Org 2" in org_names

    async def test_get_user_organizations_excludes_inactive_memberships(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Inactive memberships should not return orgs."""
        service = OrganizationService(db_session)

        result = await db_session.execute(
            select(User).where(User.id == sample_user["id"])
        )
        user = result.scalar_one()

        org = await service.create_organization(
            owner=user,
            name="Leave Me",
            org_type=OrganizationType.PERSONAL,
        )

        # Deactivate membership
        membership = await service.get_membership(org.id, user.id)
        await service.remove_member(membership)

        orgs = await service.get_user_organizations(user.id)
        org_ids = [o.id for o in orgs]

        assert org.id not in org_ids
