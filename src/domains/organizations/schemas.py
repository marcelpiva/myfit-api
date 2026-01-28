"""Organization schemas for request/response validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.domains.organizations.models import OrganizationType, UserRole


class OrganizationCreate(BaseModel):
    """Create organization request."""

    name: str = Field(min_length=2, max_length=255)
    type: OrganizationType
    description: str | None = Field(None, max_length=1000)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=50)
    email: EmailStr | None = None
    website: str | None = Field(None, max_length=255)


class OrganizationUpdate(BaseModel):
    """Update organization request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = Field(None, max_length=1000)
    address: str | None = Field(None, max_length=500)
    phone: str | None = Field(None, max_length=50)
    email: EmailStr | None = None
    website: str | None = Field(None, max_length=255)


class OrganizationInMembershipCreate(BaseModel):
    """Organization data for membership in create response."""

    id: UUID
    name: str
    type: OrganizationType
    logo_url: str | None = None
    member_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None
    is_archived: bool = False

    model_config = ConfigDict(from_attributes=True)


class MembershipInOrganization(BaseModel):
    """Membership data included in organization creation response."""

    id: UUID
    organization: OrganizationInMembershipCreate
    role: UserRole
    joined_at: datetime
    is_active: bool
    invited_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class OrganizationResponse(BaseModel):
    """Organization response."""

    id: UUID
    name: str
    type: OrganizationType
    logo_url: str | None = None
    description: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    owner_id: UUID | None = None
    is_active: bool
    archived_at: datetime | None = None
    is_archived: bool = False
    created_at: datetime
    member_count: int = 0
    trainer_count: int = 0
    membership: MembershipInOrganization | None = None  # Owner's membership when creating

    model_config = ConfigDict(from_attributes=True)


class OrganizationListResponse(BaseModel):
    """Organization list item response."""

    id: UUID
    name: str
    type: OrganizationType
    logo_url: str | None = None
    member_count: int = 0
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class OrganizationInMembership(BaseModel):
    """Organization data for membership response."""

    id: UUID
    name: str
    type: OrganizationType
    logo_url: str | None = None
    member_count: int = 0
    created_at: datetime
    archived_at: datetime | None = None
    is_archived: bool = False

    model_config = ConfigDict(from_attributes=True)


class UserMembershipResponse(BaseModel):
    """User membership with organization details."""

    id: UUID
    organization: OrganizationInMembership
    role: UserRole
    joined_at: datetime
    is_active: bool
    invited_by: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MemberResponse(BaseModel):
    """Organization member response."""

    id: UUID
    user_id: UUID
    organization_id: UUID
    role: UserRole
    joined_at: datetime
    is_active: bool
    user_name: str
    user_email: str
    user_avatar: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    """Add member to organization request."""

    user_id: UUID
    role: UserRole


class MemberUpdate(BaseModel):
    """Update member role request."""

    role: UserRole


class InviteCreate(BaseModel):
    """Create invitation request."""

    email: EmailStr
    role: UserRole


class InviteResponse(BaseModel):
    """Invitation response."""

    id: UUID
    email: str
    role: UserRole
    organization_id: UUID
    organization_name: str
    invited_by_name: str
    expires_at: datetime
    is_expired: bool
    is_accepted: bool
    created_at: datetime
    token: str | None = None  # Token for invite link (only returned to admins)
    short_code: str | None = None  # Short code for manual entry (e.g., MFP-A1B2C)

    model_config = ConfigDict(from_attributes=True)


class AcceptInviteRequest(BaseModel):
    """Accept invitation request."""

    token: str


class AcceptInviteByCodeRequest(BaseModel):
    """Accept invitation by short code request."""

    short_code: str = Field(min_length=9, max_length=9, pattern=r"^MFP-[A-Fa-f0-9]{5}$")


class InvitePreviewResponse(BaseModel):
    """Public invite preview response (no auth required)."""

    organization_id: UUID
    organization_name: str
    invited_by_name: str
    role: UserRole
    email: str


class InviteShareLinksResponse(BaseModel):
    """Shareable links for an invitation."""

    invite_url: str  # Direct invite URL
    whatsapp_url: str  # WhatsApp share URL
    qr_code_url: str | None = None  # QR code image URL (if generated)
    short_code: str | None = None  # Short code for manual entry (e.g., MFP-A1B2C)
