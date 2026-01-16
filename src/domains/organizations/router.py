"""Organization router with CRUD and member management endpoints."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.organizations.schemas import (
    AcceptInviteRequest,
    InviteCreate,
    InviteResponse,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from src.domains.organizations.service import OrganizationService
from src.domains.users.service import UserService

router = APIRouter()


# Organization CRUD

@router.get("/", response_model=list[OrganizationListResponse])
async def list_organizations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationListResponse]:
    """Get all organizations the current user belongs to."""
    org_service = OrganizationService(db)
    organizations = await org_service.get_user_organizations(current_user.id)
    return [OrganizationListResponse.model_validate(org) for org in organizations]


@router.post("/", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Create a new organization."""
    import traceback
    try:
        print(f"[CREATE_ORG] Request: name={request.name}, type={request.type}")
        print(f"[CREATE_ORG] User: {current_user.id}, {current_user.email}")

        org_service = OrganizationService(db)

        org = await org_service.create_organization(
            owner=current_user,
            name=request.name,
            org_type=request.type,
            description=request.description,
            address=request.address,
            phone=request.phone,
            email=request.email,
            website=request.website,
        )

        print(f"[CREATE_ORG] Success! org_id={org.id}")
        return OrganizationResponse.model_validate(org)
    except Exception as e:
        print(f"[CREATE_ORG] ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise


@router.get("/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Get organization details."""
    org_service = OrganizationService(db)

    org = await org_service.get_organization_by_id(org_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Check if user is a member
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    return OrganizationResponse.model_validate(org)


@router.put("/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: UUID,
    request: OrganizationUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Update organization details (admin only)."""
    org_service = OrganizationService(db)

    org = await org_service.get_organization_by_id(org_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Check admin permission
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_admin(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    updated_org = await org_service.update_organization(
        org=org,
        name=request.name,
        description=request.description,
        address=request.address,
        phone=request.phone,
        email=request.email,
        website=request.website,
    )

    return OrganizationResponse.model_validate(updated_org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete an organization (owner only)."""
    org_service = OrganizationService(db)

    org = await org_service.get_organization_by_id(org_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Only owner can delete
    if org.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can delete the organization",
        )

    await org_service.delete_organization(org)


# Member management

@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    role: str | None = None,
) -> list[MemberResponse]:
    """Get all members of an organization.

    Args:
        org_id: Organization UUID
        role: Optional role filter (e.g., 'student', 'trainer')
    """
    org_service = OrganizationService(db)

    # Verify membership
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    members = await org_service.get_organization_members(org_id, role=role)

    # Build response with user details
    result = []
    user_service = UserService(db)
    for m in members:
        user = await user_service.get_user_by_id(m.user_id)
        if user:
            result.append(
                MemberResponse(
                    id=m.id,
                    user_id=m.user_id,
                    organization_id=m.organization_id,
                    role=m.role,
                    joined_at=m.joined_at,
                    is_active=m.is_active,
                    user_name=user.name,
                    user_email=user.email,
                    user_avatar=user.avatar_url,
                )
            )

    return result


@router.post("/{org_id}/members", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def add_member(
    org_id: UUID,
    request: MemberCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    """Add a member to the organization (admin only)."""
    org_service = OrganizationService(db)

    # Check admin permission
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_admin(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    # Check if user exists
    user_service = UserService(db)
    user = await user_service.get_user_by_id(request.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already a member
    existing = await org_service.get_membership(org_id, request.user_id)
    if existing and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member",
        )

    new_membership = await org_service.add_member(
        org_id=org_id,
        user_id=request.user_id,
        role=request.role,
        invited_by_id=current_user.id,
    )

    return MemberResponse(
        id=new_membership.id,
        user_id=new_membership.user_id,
        organization_id=new_membership.organization_id,
        role=new_membership.role,
        joined_at=new_membership.joined_at,
        is_active=new_membership.is_active,
        user_name=user.name,
        user_email=user.email,
        user_avatar=user.avatar_url,
    )


@router.put("/{org_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    org_id: UUID,
    user_id: UUID,
    request: MemberUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    """Update a member's role (admin only)."""
    org_service = OrganizationService(db)

    # Check admin permission
    my_membership = await org_service.get_membership(org_id, current_user.id)
    if not my_membership or not org_service.is_admin(my_membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    # Get target membership
    membership = await org_service.get_membership(org_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    updated = await org_service.update_member_role(membership, request.role)

    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)

    return MemberResponse(
        id=updated.id,
        user_id=updated.user_id,
        organization_id=updated.organization_id,
        role=updated.role,
        joined_at=updated.joined_at,
        is_active=updated.is_active,
        user_name=user.name if user else "",
        user_email=user.email if user else "",
        user_avatar=user.avatar_url if user else None,
    )


@router.delete("/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove a member from the organization (admin only or self)."""
    org_service = OrganizationService(db)

    my_membership = await org_service.get_membership(org_id, current_user.id)
    if not my_membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    # Can remove self or if admin
    if user_id != current_user.id and not org_service.is_admin(my_membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )

    membership = await org_service.get_membership(org_id, user_id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await org_service.remove_member(membership)


# Invitations

@router.post("/{org_id}/invite", response_model=InviteResponse, status_code=status.HTTP_201_CREATED)
async def create_invite(
    org_id: UUID,
    request: InviteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteResponse:
    """Create an invitation to join the organization (professionals and admins)."""
    org_service = OrganizationService(db)

    # Check professional permission (trainers, coaches, nutritionists, admins)
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_professional(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    org = await org_service.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    invite = await org_service.create_invite(
        org_id=org_id,
        email=request.email,
        role=request.role,
        invited_by_id=current_user.id,
    )

    return InviteResponse(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        organization_id=invite.organization_id,
        organization_name=org.name,
        invited_by_name=current_user.name,
        expires_at=invite.expires_at,
        is_expired=invite.is_expired,
        is_accepted=invite.is_accepted,
        created_at=invite.created_at,
        token=invite.token,
    )


@router.get("/{org_id}/invites", response_model=list[InviteResponse])
async def list_invites(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[InviteResponse]:
    """List pending invitations (professionals and admins)."""
    org_service = OrganizationService(db)

    # Check professional permission
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_professional(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    org = await org_service.get_organization_by_id(org_id)
    invites = await org_service.get_pending_invites(org_id)

    user_service = UserService(db)
    result = []
    for invite in invites:
        inviter = await user_service.get_user_by_id(invite.invited_by_id)
        result.append(
            InviteResponse(
                id=invite.id,
                email=invite.email,
                role=invite.role,
                organization_id=invite.organization_id,
                organization_name=org.name if org else "",
                invited_by_name=inviter.name if inviter else "",
                expires_at=invite.expires_at,
                is_expired=invite.is_expired,
                is_accepted=invite.is_accepted,
                created_at=invite.created_at,
                token=invite.token,
            )
        )

    return result


@router.post("/accept-invite", response_model=MemberResponse)
async def accept_invite(
    request: AcceptInviteRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    """Accept an invitation to join an organization."""
    org_service = OrganizationService(db)

    invite = await org_service.get_invite_by_token(request.token)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    if invite.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has expired",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already accepted",
        )

    # Check if email matches
    if invite.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email",
        )

    # Check if already a member
    existing = await org_service.get_membership(invite.organization_id, current_user.id)
    if existing and existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this organization",
        )

    membership = await org_service.accept_invite(invite, current_user)

    return MemberResponse(
        id=membership.id,
        user_id=membership.user_id,
        organization_id=membership.organization_id,
        role=membership.role,
        joined_at=membership.joined_at,
        is_active=membership.is_active,
        user_name=current_user.name,
        user_email=current_user.email,
        user_avatar=current_user.avatar_url,
    )


@router.delete("/{org_id}/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invite(
    org_id: UUID,
    invite_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Cancel a pending invitation."""
    org_service = OrganizationService(db)

    # Check professional permission
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_professional(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    # Find and delete invite
    invite = await org_service.get_invite_by_id(invite_id)
    if not invite or invite.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel an already accepted invite",
        )

    await org_service.delete_invite(invite)


@router.post("/{org_id}/invites/{invite_id}/resend", response_model=InviteResponse)
async def resend_invite(
    org_id: UUID,
    invite_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InviteResponse:
    """Resend an invitation (regenerates token and extends expiration)."""
    org_service = OrganizationService(db)

    # Check professional permission
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_professional(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    invite = await org_service.get_invite_by_id(invite_id)
    if not invite or invite.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot resend an already accepted invite",
        )

    # Resend invite (regenerates token and extends expiration)
    renewed = await org_service.resend_invite(invite)

    org = await org_service.get_organization_by_id(org_id)
    user_service = UserService(db)
    inviter = await user_service.get_user_by_id(renewed.invited_by_id)

    return InviteResponse(
        id=renewed.id,
        email=renewed.email,
        role=renewed.role,
        organization_id=renewed.organization_id,
        organization_name=org.name if org else "",
        invited_by_name=inviter.name if inviter else "",
        expires_at=renewed.expires_at,
        is_expired=renewed.is_expired,
        is_accepted=renewed.is_accepted,
        created_at=renewed.created_at,
        token=renewed.token,
    )


# Join code (simple shareable code for students)

@router.get("/my-invite-code")
async def get_my_invite_code(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """
    Get a shareable invite code for the trainer's organization.
    This is for trainers/professionals to share with students.
    """
    from datetime import datetime

    org_service = OrganizationService(db)

    # Get user's organizations where they are a trainer/coach/nutritionist/admin
    memberships = await org_service.get_user_memberships(current_user.id)

    # Find first organization where user has professional/admin role
    professional_membership = None
    for m in memberships:
        if m.role.value in ['trainer', 'coach', 'nutritionist', 'gym_admin', 'gym_owner']:
            professional_membership = m
            break

    if not professional_membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No professional organization found for this user",
        )

    org = await org_service.get_organization_by_id(professional_membership.organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Generate a simple invite code based on org name and year
    year = datetime.now().year
    org_prefix = ''.join(word[0].upper() for word in org.name.split()[:2]) if org.name else 'MF'
    code = f"MYFIT-{org_prefix}{year}"

    return {
        "code": code,
        "organization_id": str(org.id),
        "organization_name": org.name,
    }
