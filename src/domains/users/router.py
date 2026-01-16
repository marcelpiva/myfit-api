"""User router with profile and settings endpoints."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.core.redis import TokenBlacklist
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.schemas import (
    AvatarUploadResponse,
    PasswordChangeRequest,
    UserListResponse,
    UserProfileResponse,
    UserProfileUpdate,
    UserSettingsResponse,
    UserSettingsUpdate,
)
from src.domains.users.service import UserService
from src.domains.organizations.service import OrganizationService
from src.domains.organizations.schemas import UserMembershipResponse, OrganizationInMembership

router = APIRouter()


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: CurrentUser,
) -> UserProfileResponse:
    """Get current user's profile."""
    return UserProfileResponse.model_validate(current_user)


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    request: UserProfileUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfileResponse:
    """Update current user's profile."""
    user_service = UserService(db)

    updated_user = await user_service.update_profile(
        user=current_user,
        name=request.name,
        phone=request.phone,
        birth_date=request.birth_date,
        gender=request.gender,
        height_cm=request.height_cm,
        bio=request.bio,
    )

    return UserProfileResponse.model_validate(updated_user)


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AvatarUploadResponse:
    """Upload user avatar image.

    TODO: Implement S3 upload when AWS credentials are configured.
    Currently returns a placeholder URL.
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: JPEG, PNG, WebP",
        )

    # Validate file size (max 5MB)
    max_size = 5 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size: 5MB",
        )

    # TODO: Upload to S3 and get URL
    # For now, return a placeholder
    avatar_url = f"https://placeholder.com/avatars/{current_user.id}.jpg"

    user_service = UserService(db)
    await user_service.update_avatar(current_user, avatar_url)

    return AvatarUploadResponse(avatar_url=avatar_url)


@router.get("/settings", response_model=UserSettingsResponse)
async def get_settings(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSettingsResponse:
    """Get current user's settings."""
    user_service = UserService(db)
    settings = await user_service.get_settings(current_user.id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    return UserSettingsResponse.model_validate(settings)


@router.put("/settings", response_model=UserSettingsResponse)
async def update_settings(
    request: UserSettingsUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSettingsResponse:
    """Update current user's settings."""
    user_service = UserService(db)
    settings = await user_service.get_settings(current_user.id)

    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found",
        )

    updated_settings = await user_service.update_settings(
        settings=settings,
        theme=request.theme,
        language=request.language,
        units=request.units,
        notifications_enabled=request.notifications_enabled,
        goal_weight=request.goal_weight,
        target_calories=request.target_calories,
    )

    return UserSettingsResponse.model_validate(updated_settings)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: PasswordChangeRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Change current user's password.

    This also invalidates all existing tokens for security.
    """
    user_service = UserService(db)

    success = await user_service.change_password(
        user=current_user,
        current_password=request.current_password,
        new_password=request.new_password,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    # Invalidate all user tokens
    await TokenBlacklist.invalidate_all_user_tokens(str(current_user.id))


@router.get("/search", response_model=list[UserListResponse])
async def search_users(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[UserListResponse]:
    """Search for users by name or email."""
    user_service = UserService(db)
    users = await user_service.search_users(q, limit, offset)
    return [UserListResponse.model_validate(u) for u in users]


@router.get("/me/memberships", response_model=list[UserMembershipResponse])
async def get_my_memberships(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserMembershipResponse]:
    """Get all memberships for the current user with organization details."""
    org_service = OrganizationService(db)
    memberships = await org_service.get_user_memberships_with_orgs(current_user.id)

    result = []
    for membership in memberships:
        org = membership.organization
        result.append(
            UserMembershipResponse(
                id=membership.id,
                organization=OrganizationInMembership(
                    id=org.id,
                    name=org.name,
                    type=org.type,
                    logo_url=org.logo_url,
                    member_count=org.member_count,
                    created_at=org.created_at,
                ),
                role=membership.role,
                joined_at=membership.joined_at,
                is_active=membership.is_active,
                invited_by=None,  # TODO: Get inviter name if needed
            )
        )

    return result
