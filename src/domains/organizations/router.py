"""Organization router with CRUD and member management endpoints."""
import structlog
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.organizations.schemas import (
    AcceptInviteByCodeRequest,
    AcceptInviteRequest,
    InviteCreate,
    InvitePreviewResponse,
    InviteResponse,
    InviteShareLinksResponse,
    MemberCreate,
    MemberResponse,
    MemberUpdate,
    OrganizationCreate,
    OrganizationListResponse,
    OrganizationResponse,
    OrganizationUpdate,
)
from src.domains.organizations.models import UserRole
from src.domains.organizations.service import OrganizationService
from src.domains.users.service import UserService
from src.domains.notifications.push_service import send_push_notification
from src.domains.notifications.router import create_notification
from src.domains.subscriptions.service import SubscriptionService
from src.domains.subscriptions.models import PlatformTier
from src.domains.notifications.schemas import NotificationCreate
from src.domains.notifications.models import NotificationType

logger = structlog.get_logger(__name__)

router = APIRouter()


# Public invite preview (no auth required)

@router.get("/invite/preview/{token}", response_model=InvitePreviewResponse)
async def preview_invite(
    token: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitePreviewResponse:
    """Get invite details by token (public, no auth required).

    This endpoint allows users to preview invite details before
    logging in or creating an account.
    """
    org_service = OrganizationService(db)
    user_service = UserService(db)

    invite = await org_service.get_invite_by_token(token)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invite not found",
        )

    if invite.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite has expired",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invite already accepted",
        )

    # Get organization and inviter details
    org = await org_service.get_organization_by_id(invite.organization_id)
    inviter = await user_service.get_user_by_id(invite.invited_by_id)

    return InvitePreviewResponse(
        organization_id=invite.organization_id,
        organization_name=org.name if org else "Unknown",
        invited_by_name=inviter.name if inviter else "Unknown",
        role=invite.role,
        email=invite.email,
    )


@router.get("/invite/code/{short_code}", response_model=InvitePreviewResponse)
async def preview_invite_by_code(
    short_code: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitePreviewResponse:
    """Get invite details by short code (public, no auth required).

    This endpoint allows users to preview invite details using the short code
    (e.g., MFP-A1B2C) before logging in or creating an account.
    """
    org_service = OrganizationService(db)
    user_service = UserService(db)

    invite = await org_service.get_invite_by_short_code(short_code)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código de convite não encontrado",
        )

    if invite.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Convite expirado",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Convite já aceito",
        )

    # Get organization and inviter details
    org = await org_service.get_organization_by_id(invite.organization_id)
    inviter = await user_service.get_user_by_id(invite.invited_by_id)

    return InvitePreviewResponse(
        organization_id=invite.organization_id,
        organization_name=org.name if org else "Unknown",
        invited_by_name=inviter.name if inviter else "Unknown",
        role=invite.role,
        email=invite.email,
    )


# Organization CRUD

@router.get("", response_model=list[OrganizationListResponse])
async def list_organizations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[OrganizationListResponse]:
    """Get all organizations the current user belongs to."""
    org_service = OrganizationService(db)
    organizations = await org_service.get_user_organizations(current_user.id)
    return [OrganizationListResponse.model_validate(org) for org in organizations]


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    request: OrganizationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Create a new organization."""
    from src.domains.organizations.schemas import MembershipInOrganization, OrganizationInMembershipCreate
    try:
        logger.info("create_org_request", name=request.name, org_type=str(request.type), user_id=str(current_user.id), email=current_user.email)

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

        # Get the owner's membership to include in response
        membership = await org_service.get_membership(org.id, current_user.id)
        logger.info("create_org_success", org_id=str(org.id), membership_role=str(membership.role) if membership else None)

        response = OrganizationResponse.model_validate(org)
        if membership:
            # Build membership with organization included (Flutter expects this structure)
            response.membership = MembershipInOrganization(
                id=membership.id,
                organization=OrganizationInMembershipCreate.model_validate(org),
                role=membership.role,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
                invited_by=None,
            )
        return response
    except (SQLAlchemyError, ValueError) as e:
        logger.error("create_org_failed", error=str(e), type=type(e).__name__, exc_info=True)
        raise


@router.post("/autonomous", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_autonomous_organization(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: str = "Meus Treinos",
) -> OrganizationResponse:
    """Create an autonomous organization for self-training.

    This creates a personal training profile where the user is both owner and student.
    The user can create and manage their own workouts independently, without a trainer.
    """
    from src.domains.organizations.schemas import MembershipInOrganization, OrganizationInMembershipCreate

    try:
        logger.info("create_autonomous_request", name=name, user_id=str(current_user.id))

        org_service = OrganizationService(db)

        org = await org_service.create_autonomous_organization(
            user=current_user,
            name=name,
        )
        logger.info("create_autonomous_org_created", org_id=str(org.id))

        # Get the user's membership to include in response
        membership = await org_service.get_membership(org.id, current_user.id)
        logger.info("create_autonomous_membership", membership_id=str(membership.id) if membership else None)

        response = OrganizationResponse.model_validate(org)
        if membership:
            response.membership = MembershipInOrganization(
                id=membership.id,
                organization=OrganizationInMembershipCreate.model_validate(org),
                role=membership.role,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
                invited_by=None,
            )
        return response
    except (SQLAlchemyError, ValueError) as e:
        logger.error("create_autonomous_failed", error=str(e), type=type(e).__name__, exc_info=True)
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


@router.post("/{org_id}/reactivate", response_model=OrganizationResponse)
async def reactivate_organization(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Reactivate an archived organization (owner only).

    When a personal trainer who previously removed their profile wants to
    return, this endpoint clears the archived_at timestamp and sends
    notifications to all members.
    """
    org_service = OrganizationService(db)
    user_service = UserService(db)

    org = await org_service.get_organization_by_id(org_id)
    if not org or not org.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Only owner can reactivate
    if org.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can reactivate the organization",
        )

    # Check if organization is archived
    if not org.is_archived:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is not archived",
        )

    # Reactivate the organization
    reactivated_org = await org_service.reactivate_organization(org)

    # Send push notifications to all active members (except owner)
    members = await org_service.get_organization_members(org_id, active_only=True)
    for member in members:
        if member.user_id != current_user.id:
            user = await user_service.get_user_by_id(member.user_id)
            if user:
                # Create in-app notification
                await create_notification(
                    db=db,
                    notification=NotificationCreate(
                        user_id=member.user_id,
                        type=NotificationType.GENERAL,
                        title="Personal de volta!",
                        message=f"{org.name} retomou as atividades.",
                        data={"organization_id": str(org_id), "type": "organization_reactivated"},
                    ),
                )
                # Send push notification
                try:
                    await send_push_notification(
                        db=db,
                        user_id=member.user_id,
                        title="Personal de volta!",
                        body=f"{org.name} retomou as atividades.",
                        data={"organization_id": str(org_id), "type": "organization_reactivated"},
                    )
                except (ConnectionError, OSError, RuntimeError):
                    # Don't fail if push notification fails
                    pass

    return OrganizationResponse.model_validate(reactivated_org)


# Member management

@router.get("/{org_id}/members", response_model=list[MemberResponse])
async def list_members(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    role: str | None = None,
    active_only: bool = True,
) -> list[MemberResponse]:
    """Get all members of an organization.

    Args:
        org_id: Organization UUID
        role: Optional role filter (e.g., 'student', 'trainer')
        active_only: If True, only return active members (default: True)
    """
    org_service = OrganizationService(db)

    # Verify membership
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization",
        )

    members = await org_service.get_organization_members(org_id, role=role, active_only=active_only)

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

    # Check student limit if adding a student
    if request.role == UserRole.student:
        sub_service = SubscriptionService(db)
        can_add, current_count, limit = await sub_service.can_add_student(current_user.id)
        if not can_add:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "student_limit_reached",
                    "message": f"Você atingiu o limite de {limit} alunos no plano gratuito. Faça upgrade para Pro para alunos ilimitados.",
                    "current_count": current_count,
                    "limit": limit,
                    "current_tier": PlatformTier.FREE.value,
                    "upgrade_required": True,
                },
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


@router.post("/{org_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_organization(
    org_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Leave an organization as a student.

    This specifically removes the student membership, even if the user
    has other roles (like trainer) in the same organization.
    Use this endpoint for students leaving, not for owners archiving.
    """
    org_service = OrganizationService(db)

    # Get specifically the STUDENT membership
    membership = await org_service.get_membership_by_role(
        org_id, current_user.id, UserRole.STUDENT
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Você não é aluno desta organização",
        )

    # Deactivate only the student membership
    membership.is_active = False
    await db.commit()


@router.post("/{org_id}/members/{membership_id}/reactivate", response_model=MemberResponse)
async def reactivate_member(
    org_id: UUID,
    membership_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    """Reactivate an inactive member (professionals only)."""
    org_service = OrganizationService(db)
    user_service = UserService(db)

    # Check professional permission
    my_membership = await org_service.get_membership(org_id, current_user.id)
    if not my_membership or not org_service.is_professional(my_membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    # Get the membership to reactivate
    membership = await org_service.get_membership_by_id(membership_id)
    if not membership or membership.organization_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membro não encontrado",
        )

    if membership.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Membro já está ativo",
        )

    # Reactivate the membership
    reactivated = await org_service.reactivate_membership(membership)

    user = await user_service.get_user_by_id(reactivated.user_id)

    return MemberResponse(
        id=reactivated.id,
        user_id=reactivated.user_id,
        organization_id=reactivated.organization_id,
        role=reactivated.role,
        joined_at=reactivated.joined_at,
        is_active=reactivated.is_active,
        user_name=user.name if user else "",
        user_email=user.email if user else "",
        user_avatar=user.avatar_url if user else None,
    )


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
    user_service = UserService(db)

    # Check professional permission (trainers, coaches, nutritionists, admins)
    membership = await org_service.get_membership(org_id, current_user.id)
    if not membership or not org_service.is_professional(membership):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professional permission required",
        )

    # Check student limit if inviting a student
    if request.role == UserRole.student:
        sub_service = SubscriptionService(db)
        can_add, current_count, limit = await sub_service.can_add_student(current_user.id)
        if not can_add:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "student_limit_reached",
                    "message": f"Você atingiu o limite de {limit} alunos no plano gratuito. Faça upgrade para Pro para alunos ilimitados.",
                    "current_count": current_count,
                    "limit": limit,
                    "current_tier": PlatformTier.FREE.value,
                    "upgrade_required": True,
                },
            )

    # Self-invite is allowed - trainer can add themselves as a student
    # to follow their own training plans

    org = await org_service.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    # Check if user with this email already exists and has the SAME role
    user_by_email = await user_service.get_user_by_email(request.email)
    if user_by_email:
        # Only check for membership with the specific role being invited
        # This allows users to have multiple roles (e.g., owner + student)
        existing_with_role = await org_service.get_membership_by_role(
            org_id, user_by_email.id, request.role
        )
        if existing_with_role:
            if existing_with_role.is_active:
                role_names = {
                    "student": "aluno",
                    "trainer": "personal trainer",
                    "coach": "coach",
                    "nutritionist": "nutricionista",
                    "gym_admin": "administrador",
                    "gym_owner": "proprietário",
                }
                role_name = role_names.get(request.role.value, request.role.value)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "ALREADY_MEMBER",
                        "message": f"Este usuário já é {role_name} nesta organização",
                    },
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "code": "INACTIVE_MEMBER",
                        "message": "Este aluno já está em seus alunos, inativo. Deseja enviar um convite de reativação?",
                        "membership_id": str(existing_with_role.id),
                        "user_id": str(user_by_email.id),
                    },
                )

    # Check if there's already a pending invite for this email
    existing_invite = await org_service.get_pending_invite_by_email(org_id, request.email)
    if existing_invite:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PENDING_INVITE",
                "message": "Este aluno já possui um convite pendente",
                "invite_id": str(existing_invite.id),
            },
        )

    invite = await org_service.create_invite(
        org_id=org_id,
        email=request.email,
        role=request.role,
        invited_by_id=current_user.id,
    )

    # Send notifications if user exists
    if user_by_email:
        # Create in-app notification
        await create_notification(
            db=db,
            notification_data=NotificationCreate(
                user_id=user_by_email.id,
                notification_type=NotificationType.INVITE_RECEIVED,
                title="Novo Convite",
                body=f"{current_user.name} convidou você para {org.name}",
                icon="mail",
                action_type="navigate",
                action_data=f'{{"route": "/invites"}}',
                reference_type="invite",
                reference_id=invite.id,
                organization_id=org_id,
                sender_id=current_user.id,
            ),
        )

        # Send push notification
        await send_push_notification(
            db=db,
            user_id=user_by_email.id,
            title="Novo Convite",
            body=f"{current_user.name} convidou você para {org.name}",
            data={
                "type": "invite",
                "invite_id": str(invite.id),
                "organization_id": str(org_id),
            },
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
        short_code=invite.short_code,
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
                short_code=invite.short_code,
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

    # Check if already a member with the same role
    existing_with_role = await org_service.get_membership_by_role(
        invite.organization_id, current_user.id, invite.role
    )
    if existing_with_role:
        if existing_with_role.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"You are already a {invite.role.value} in this organization",
            )
        else:
            # Reactivate inactive membership with same role
            existing_with_role.is_active = True
            invite.accepted_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing_with_role)
            membership = existing_with_role
    else:
        # Create new membership (allows multiple roles for same user)
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


@router.post("/accept-invite-by-code", response_model=MemberResponse)
async def accept_invite_by_code(
    request: AcceptInviteByCodeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MemberResponse:
    """Accept an invitation using the short code (e.g., MFP-A1B2C)."""
    org_service = OrganizationService(db)

    invite = await org_service.get_invite_by_short_code(request.short_code)
    if not invite:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Código de convite não encontrado",
        )

    if invite.is_expired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Convite expirado",
        )

    if invite.is_accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Convite já aceito",
        )

    # Validate email matches the invite
    if invite.email.lower() != current_user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Este convite foi enviado para outro email",
        )

    # Check if already a member with the same role
    existing_with_role = await org_service.get_membership_by_role(
        invite.organization_id, current_user.id, invite.role
    )
    if existing_with_role:
        if existing_with_role.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Você já é {invite.role.value} nesta organização",
            )
        else:
            # Reactivate inactive membership with same role
            existing_with_role.is_active = True
            invite.accepted_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(existing_with_role)
            membership = existing_with_role
    else:
        # Create new membership (allows multiple roles for same user)
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
        short_code=renewed.short_code,
    )


@router.get("/{org_id}/invites/{invite_id}/share-links", response_model=InviteShareLinksResponse)
async def get_invite_share_links(
    org_id: UUID,
    invite_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_qr: bool = True,
) -> InviteShareLinksResponse:
    """Get shareable links for an invitation (WhatsApp, direct link, QR code).

    Returns URLs that can be shared with the invited person to accept the invite.

    Args:
        org_id: Organization UUID
        invite_id: Invite UUID
        include_qr: If True, includes base64 QR code data URL (default: True)
    """
    from urllib.parse import quote

    from src.config.settings import settings
    from src.core.qrcode import generate_invite_qr_code

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
            detail="Invite already accepted",
        )

    # Get organization details
    org = await org_service.get_organization_by_id(org_id)
    org_name = org.name if org else "MyFit"

    # Generate invite URL
    invite_url = f"{settings.APP_URL}/invite/{invite.token}"

    # Generate WhatsApp share message
    whatsapp_message = (
        f"Olá! Você foi convidado(a) para treinar com {current_user.name} "
        f"na {org_name} pelo MyFit! 💪\n\n"
        f"Clique no link para aceitar o convite:\n{invite_url}"
    )
    whatsapp_url = f"https://wa.me/?text={quote(whatsapp_message)}"

    # Generate QR code if requested
    qr_code_url = None
    if include_qr:
        qr_code_url = generate_invite_qr_code(invite_url)

    return InviteShareLinksResponse(
        invite_url=invite_url,
        whatsapp_url=whatsapp_url,
        qr_code_url=qr_code_url,
        short_code=invite.short_code,
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
    memberships = await org_service.get_user_memberships_with_orgs(current_user.id)

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
