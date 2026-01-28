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
from src.domains.workouts.models import WorkoutAssignment, WorkoutSession


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
                selectinload(OrganizationMembership.organization)
                .selectinload(Organization.memberships),
                selectinload(OrganizationMembership.organization)
                .selectinload(Organization.owner),
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

    async def create_autonomous_organization(
        self,
        user: User,
        name: str = "Meus Treinos",
    ) -> Organization:
        """Create an autonomous organization for self-training.

        The user becomes both owner and student member of this organization.
        This allows students to create and manage their own workouts independently.

        Args:
            user: The User who will own and be member of this organization
            name: Organization name (default: "Meus Treinos")

        Returns:
            The created Organization object
        """
        org = Organization(
            name=name,
            type=OrganizationType.AUTONOMOUS,
            owner_id=user.id,
        )
        self.db.add(org)
        await self.db.flush()

        # User joins as student (owner of their own training)
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=user.id,
            role=UserRole.STUDENT,
            is_active=True,
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

        Also deactivates all memberships and cleanup related data.

        Args:
            org: The Organization object to delete
        """
        org.is_active = False

        # Deactivate all memberships in this organization
        memberships = await self.get_organization_members(org.id, active_only=True)
        for membership in memberships:
            membership.is_active = False

        # Deactivate all workout assignments in this organization
        result = await self.db.execute(
            select(WorkoutAssignment).where(
                and_(
                    WorkoutAssignment.organization_id == org.id,
                    WorkoutAssignment.is_active == True,
                )
            )
        )
        assignments = result.scalars().all()
        for assignment in assignments:
            assignment.is_active = False

        await self.db.commit()

    # Membership operations

    async def get_membership(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        """Get a user's membership in an organization.

        If user has multiple memberships (e.g., trainer + student),
        returns the one with highest privilege (admin > trainer > student).

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
        memberships = result.scalars().all()

        if not memberships:
            return None

        if len(memberships) == 1:
            return memberships[0]

        # Prioritize by role: owner/admin > trainer/coach > student
        role_priority = {
            UserRole.GYM_OWNER: 0,
            UserRole.GYM_ADMIN: 1,
            UserRole.TRAINER: 2,
            UserRole.COACH: 2,
            UserRole.NUTRITIONIST: 2,
            UserRole.STUDENT: 3,
        }
        return min(memberships, key=lambda m: role_priority.get(m.role, 99))

    async def get_membership_by_id(
        self,
        membership_id: uuid.UUID,
    ) -> OrganizationMembership | None:
        """Get a membership by its ID.

        Args:
            membership_id: The membership UUID

        Returns:
            The membership if found, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationMembership)
            .where(OrganizationMembership.id == membership_id)
        )
        return result.scalar_one_or_none()

    async def get_membership_by_role(
        self,
        org_id: uuid.UUID,
        user_id: uuid.UUID,
        role: UserRole,
    ) -> OrganizationMembership | None:
        """Get a user's membership in an organization with a specific role.

        Args:
            org_id: Organization UUID
            user_id: User UUID
            role: The specific role to check

        Returns:
            The membership if found with that role, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationMembership)
            .where(
                and_(
                    OrganizationMembership.organization_id == org_id,
                    OrganizationMembership.user_id == user_id,
                    OrganizationMembership.role == role,
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

        Also cleans up related data:
        - Deactivates workout assignments if member is a trainer
        - Clears trainer_id from workout sessions (co-training)
        - If owner of a PERSONAL organization leaves, archives org but keeps owner active

        Args:
            membership: The membership to deactivate
        """
        # Check if this is the owner of a PERSONAL organization BEFORE deactivating
        is_personal_owner = False
        if membership.role in [UserRole.TRAINER, UserRole.COACH, UserRole.GYM_OWNER]:
            org = await self.get_organization_by_id(membership.organization_id)
            if org and org.owner_id == membership.user_id and org.type == OrganizationType.PERSONAL:
                is_personal_owner = True

        # Only deactivate membership if NOT the owner of a PERSONAL org
        # Owner keeps active membership so they can see archived profile and reactivate
        if not is_personal_owner:
            membership.is_active = False

        # If removing a trainer/coach, clean up their assignments and sessions
        if membership.role in [UserRole.TRAINER, UserRole.COACH, UserRole.GYM_OWNER]:
            # Deactivate workout assignments
            result = await self.db.execute(
                select(WorkoutAssignment).where(
                    and_(
                        WorkoutAssignment.trainer_id == membership.user_id,
                        WorkoutAssignment.organization_id == membership.organization_id,
                        WorkoutAssignment.is_active == True,
                    )
                )
            )
            assignments = result.scalars().all()
            for assignment in assignments:
                assignment.is_active = False

            # Clear trainer_id from workout sessions (co-training)
            session_result = await self.db.execute(
                select(WorkoutSession).where(
                    WorkoutSession.trainer_id == membership.user_id,
                )
            )
            sessions = session_result.scalars().all()
            for session in sessions:
                session.trainer_id = None
                session.is_shared = False

            # If this is the owner of a PERSONAL organization, archive it
            if is_personal_owner and org:
                # Archive the organization - students can still see it but in read-only mode
                org.archived_at = datetime.now(timezone.utc)
                # Keep org.is_active = True so students can still see the organization
                # Keep owner membership active so they can reactivate
                # Keep student memberships active so they can access their workout history

        await self.db.commit()

    # Invitation operations

    def _generate_short_code(self) -> str:
        """Generate a short code in format MFP-XXXXX where X is hex.

        Returns:
            Short code like MFP-A1B2C
        """
        hex_part = secrets.token_hex(3)[:5].upper()  # 5 hex characters
        return f"MFP-{hex_part}"

    async def _get_unique_short_code(self) -> str:
        """Generate a unique short code that doesn't exist in the database.

        Returns:
            Unique short code
        """
        max_attempts = 10
        for _ in range(max_attempts):
            short_code = self._generate_short_code()
            # Check if it already exists
            existing = await self.get_invite_by_short_code(short_code)
            if existing is None:
                return short_code
        # Fallback: use more entropy if collisions happen
        hex_part = secrets.token_hex(4)[:5].upper()
        return f"MFP-{hex_part}"

    async def create_invite(
        self,
        org_id: uuid.UUID,
        email: str,
        role: UserRole,
        invited_by_id: uuid.UUID,
        expires_in_days: int = 7,
        student_info: dict | None = None,
    ) -> OrganizationInvite:
        """Create an invitation to join an organization.

        Args:
            org_id: Organization UUID
            email: Email to invite
            role: Role to assign
            invited_by_id: ID of inviting user
            expires_in_days: Days until expiration
            student_info: Optional student info (name, phone, goal, notes)

        Returns:
            The created invite
        """
        token = secrets.token_urlsafe(32)
        short_code = await self._get_unique_short_code()
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        invite = OrganizationInvite(
            organization_id=org_id,
            email=email.lower(),
            role=role,
            token=token,
            short_code=short_code,
            expires_at=expires_at,
            invited_by_id=invited_by_id,
            student_info=student_info,
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

    async def get_invite_by_short_code(
        self,
        short_code: str,
    ) -> OrganizationInvite | None:
        """Get an invite by its short code.

        Args:
            short_code: The invite short code (e.g., MFP-A1B2C)

        Returns:
            The invite if found, None otherwise
        """
        # Normalize short code to uppercase
        normalized = short_code.upper().strip()
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(OrganizationInvite.short_code == normalized)
            .options(
                selectinload(OrganizationInvite.organization),
                selectinload(OrganizationInvite.invited_by),
            )
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

    async def get_pending_invites_for_email(
        self,
        email: str,
    ) -> list[OrganizationInvite]:
        """Get all pending invites for a specific email.

        Args:
            email: User email to find invites for

        Returns:
            List of pending invites
        """
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(
                and_(
                    OrganizationInvite.email == email.lower(),
                    OrganizationInvite.accepted_at == None,
                )
            )
            .options(
                selectinload(OrganizationInvite.organization),
                selectinload(OrganizationInvite.invited_by),
            )
        )
        return list(result.scalars().all())

    async def get_pending_invite_by_email(
        self,
        org_id: uuid.UUID,
        email: str,
    ) -> OrganizationInvite | None:
        """Get a pending invite for a specific email in an organization.

        Args:
            org_id: Organization UUID
            email: Email to check for pending invite

        Returns:
            The pending invite if found, None otherwise
        """
        result = await self.db.execute(
            select(OrganizationInvite)
            .where(
                and_(
                    OrganizationInvite.organization_id == org_id,
                    OrganizationInvite.email == email.lower(),
                    OrganizationInvite.accepted_at == None,
                )
            )
        )
        return result.scalar_one_or_none()

    async def reactivate_membership(
        self,
        membership: OrganizationMembership,
    ) -> OrganizationMembership:
        """Reactivate an inactive membership.

        Args:
            membership: The membership to reactivate

        Returns:
            The reactivated membership
        """
        membership.is_active = True
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

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
        invite.resend_count += 1
        invite.last_resent_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(invite)
        return invite

    async def cleanup_expired_invites(
        self,
        older_than_days: int = 30,
    ) -> int:
        """Delete expired invites older than specified days.

        Args:
            older_than_days: Only delete invites that expired more than this many days ago

        Returns:
            Number of deleted invites
        """
        from sqlalchemy import delete

        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        result = await self.db.execute(
            delete(OrganizationInvite)
            .where(
                and_(
                    OrganizationInvite.expires_at < datetime.now(timezone.utc),
                    OrganizationInvite.expires_at < cutoff,
                    OrganizationInvite.accepted_at == None,
                )
            )
        )
        await self.db.commit()
        return result.rowcount

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

    async def reactivate_organization(self, org: Organization) -> Organization:
        """Reactivate an archived organization.

        Clears the archived_at timestamp to restore the organization.

        Args:
            org: The organization to reactivate

        Returns:
            The reactivated organization
        """
        org.archived_at = None
        await self.db.commit()
        await self.db.refresh(org)
        return org
