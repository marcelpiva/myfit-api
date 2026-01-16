"""Organization service with database operations."""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)
from src.domains.users.models import User


class OrganizationService:
    """Service for handling organization operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Organization CRUD

    async def get_organization_by_id(
        self,
        org_id: uuid.UUID,
    ) -> Organization | None:
        """Get an organization by ID.

        Args:
            org_id: The organization's UUID

        Returns:
            The Organization object if found, None otherwise
        """
        result = await self.db.execute(
            select(Organization)
            .where(Organization.id == org_id)
            .options(selectinload(Organization.memberships))
        )
        return result.scalar_one_or_none()

    async def get_user_organizations(
        self,
        user_id: uuid.UUID,
    ) -> list[Organization]:
        """Get all organizations a user belongs to.

        Args:
            user_id: The user's UUID

        Returns:
            List of organizations
        """
        result = await self.db.execute(
            select(Organization)
            .join(OrganizationMembership)
            .where(
                and_(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.is_active == True,
                    Organization.is_active == True,
                )
            )
            .options(selectinload(Organization.memberships))
        )
        return list(result.scalars().all())

    async def get_user_memberships_with_orgs(
        self,
        user_id: uuid.UUID,
    ) -> list[OrganizationMembership]:
        """Get all memberships for a user with organization details loaded.

        Args:
            user_id: The user's UUID

        Returns:
            List of memberships with organization details
        """
        result = await self.db.execute(
            select(OrganizationMembership)
            .where(
                and_(
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.is_active == True,
                )
            )
            .options(
                selectinload(OrganizationMembership.organization).selectinload(Organization.memberships)
            )
        )
        memberships = list(result.scalars().all())
        # Filter out memberships where organization is inactive
        return [m for m in memberships if m.organization and m.organization.is_active]

    async def create_organization(
        self,
        owner: User,
        name: str,
        org_type: OrganizationType,
        description: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        website: str | None = None,
    ) -> Organization:
        """Create a new organization.

        Args:
            owner: The owner User object
            name: Organization name
            org_type: Organization type
            description: Optional description
            address: Optional address
            phone: Optional phone
            email: Optional email
            website: Optional website

        Returns:
            The created Organization object
        """
        org = Organization(
            name=name,
            type=org_type,
            description=description,
            address=address,
            phone=phone,
            email=email,
            website=website,
            owner_id=owner.id,
        )
        self.db.add(org)
        await self.db.flush()

        # Add owner as a member with appropriate role based on organization type
        role_map = {
            OrganizationType.GYM: UserRole.GYM_OWNER,
            OrganizationType.PERSONAL: UserRole.TRAINER,
            OrganizationType.NUTRITIONIST: UserRole.NUTRITIONIST,
            OrganizationType.CLINIC: UserRole.COACH,
        }
        role = role_map.get(org_type, UserRole.TRAINER)
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=owner.id,
            role=role,
        )
        self.db.add(membership)

        await self.db.commit()
        await self.db.refresh(org)
        return org

    async def update_organization(
        self,
        org: Organization,
        name: str | None = None,
        description: str | None = None,
        address: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        website: str | None = None,
    ) -> Organization:
        """Update an organization.

        Args:
            org: The Organization object to update
            name: New name (optional)
            description: New description (optional)
            address: New address (optional)
            phone: New phone (optional)
            email: New email (optional)
            website: New website (optional)

        Returns:
            The updated Organization object
        """
        if name is not None:
            org.name = name
        if description is not None:
            org.description = description
        if address is not None:
            org.address = address
        if phone is not None:
            org.phone = phone
        if email is not None:
            org.email = email
        if website is not None:
            org.website = website

        await self.db.commit()
        await self.db.refresh(org)
        return org

    async def delete_organization(self, org: Organization) -> None:
        """Soft delete an organization.

        Args:
            org: The Organization object to delete
        """
        org.is_active = False
        await self.db.commit()

    # Membership operations

    async def get_membership(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        """Get a user's membership in an organization.

        Args:
            org_id: Organization UUID
            user_id: User UUID

        Returns:
            The membership if found, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationMembership)
            .where(
                and_(
                    OrganizationMembership.organization_id == org_id,
                    OrganizationMembership.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_organization_members(
        self,
        org_id: uuid.UUID,
        active_only: bool = True,
        role: str | None = None,
    ) -> list[OrganizationMembership]:
        """Get all members of an organization.

        Args:
            org_id: Organization UUID
            active_only: If True, only return active members
            role: Filter by specific role (e.g., 'student', 'trainer')

        Returns:
            List of memberships
        """
        query = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id
        )
        if active_only:
            query = query.where(OrganizationMembership.is_active == True)
        if role:
            query = query.where(OrganizationMembership.role == role)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_member(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        role: UserRole,
        invited_by_id: uuid.UUID | None = None,
    ) -> OrganizationMembership:
        """Add a member to an organization.

        Args:
            org_id: Organization UUID
            user_id: User UUID
            role: User role
            invited_by_id: ID of user who invited them

        Returns:
            The created membership
        """
        membership = OrganizationMembership(
            organization_id=org_id,
            user_id=user_id,
            role=role,
            invited_by_id=invited_by_id,
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def update_member_role(
        self,
        membership: OrganizationMembership,
        role: UserRole,
    ) -> OrganizationMembership:
        """Update a member's role.

        Args:
            membership: The membership to update
            role: New role

        Returns:
            The updated membership
        """
        membership.role = role
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def remove_member(
        self,
        membership: OrganizationMembership,
    ) -> None:
        """Remove a member from an organization.

        Args:
            membership: The membership to deactivate
        """
        membership.is_active = False
        await self.db.commit()

    # Invitation operations

    async def create_invite(
        self,
        org_id: uuid.UUID,
        email: str,
        role: UserRole,
        invited_by_id: uuid.UUID,
        expires_in_days: int = 7,
    ) -> OrganizationInvite:
        """Create an invitation to join an organization.

        Args:
            org_id: Organization UUID
            email: Email to invite
            role: Role to assign
            invited_by_id: ID of inviting user
            expires_in_days: Days until expiration

        Returns:
            The created invite
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        invite = OrganizationInvite(
            organization_id=org_id,
            email=email.lower(),
            role=role,
            token=token,
            expires_at=expires_at,
            invited_by_id=invited_by_id,
        )
        self.db.add(invite)
        await self.db.commit()
        await self.db.refresh(invite)
        return invite

    async def get_invite_by_token(
        self,
        token: str,
    ) -> OrganizationInvite | None:
        """Get an invite by its token.

        Args:
            token: The invite token

        Returns:
            The invite if found, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.token == token)
            .options(selectinload(OrganizationInvite.organization))
        )
        return result.scalar_one_or_none()

    async def get_pending_invites(
        self,
        org_id: uuid.UUID,
    ) -> list[OrganizationInvite]:
        """Get all pending invites for an organization.

        Args:
            org_id: Organization UUID

        Returns:
            List of pending invites
        """
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(
                and_(
                    OrganizationInvite.organization_id == org_id,
                    OrganizationInvite.accepted_at == None,
                )
            )
        )
        return list(result.scalars().all())

    async def accept_invite(
        self,
        invite: OrganizationInvite,
        user: User,
    ) -> OrganizationMembership:
        """Accept an invitation and create membership.

        Args:
            invite: The invite to accept
            user: The user accepting

        Returns:
            The created membership
        """
        invite.accepted_at = datetime.now(timezone.utc)

        membership = OrganizationMembership(
            organization_id=invite.organization_id,
            user_id=user.id,
            role=invite.role,
            invited_by_id=invite.invited_by_id,
        )
        self.db.add(membership)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def get_invite_by_id(
        self,
        invite_id: uuid.UUID,
    ) -> OrganizationInvite | None:
        """Get an invite by its ID.

        Args:
            invite_id: The invite UUID

        Returns:
            The invite if found, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.id == invite_id)
            .options(selectinload(OrganizationInvite.organization))
        )
        return result.scalar_one_or_none()

    async def delete_invite(
        self,
        invite: OrganizationInvite,
    ) -> None:
        """Delete a pending invitation.

        Args:
            invite: The invite to delete
        """
        await self.db.delete(invite)
        await self.db.commit()

    async def resend_invite(
        self,
        invite: OrganizationInvite,
        expires_in_days: int = 7,
    ) -> OrganizationInvite:
        """Resend an invitation by regenerating the token and extending expiration.

        Args:
            invite: The invite to resend
            expires_in_days: Days until new expiration

        Returns:
            The updated invite
        """
        invite.token = secrets.token_urlsafe(32)
        invite.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        await self.db.commit()
        await self.db.refresh(invite)
        return invite

    # Permission checks

    def is_admin(self, membership: OrganizationMembership) -> bool:
        """Check if membership has admin privileges.

        Args:
            membership: The membership to check

        Returns:
            True if admin, False otherwise
        """
        return membership.role in [UserRole.GYM_ADMIN, UserRole.GYM_OWNER]

    def is_professional(self, membership: OrganizationMembership) -> bool:
        """Check if membership is a professional (trainer/nutritionist).

        Args:
            membership: The membership to check

        Returns:
            True if professional, False otherwise
        """
        return membership.role in [
            UserRole.TRAINER,
            UserRole.COACH,
            UserRole.NUTRITIONIST,
            UserRole.GYM_ADMIN,
            UserRole.GYM_OWNER,
        ]
