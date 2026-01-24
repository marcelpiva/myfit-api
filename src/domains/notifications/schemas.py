"""Notification schemas for API validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import NotificationPriority, NotificationType


class NotificationCreate(BaseModel):
    """Schema for creating a notification (internal use)."""

    user_id: UUID
    notification_type: NotificationType
    title: str = Field(..., max_length=255)
    body: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    icon: str | None = None
    action_type: str | None = None
    action_data: str | None = None
    reference_type: str | None = None
    reference_id: UUID | None = None
    organization_id: UUID | None = None
    sender_id: UUID | None = None


class NotificationResponse(BaseModel):
    """Schema for notification response."""

    id: UUID
    notification_type: NotificationType
    priority: NotificationPriority
    title: str
    body: str
    icon: str | None
    action_type: str | None
    action_data: str | None
    reference_type: str | None
    reference_id: UUID | None
    organization_id: UUID | None
    sender_id: UUID | None
    sender_name: str | None = None
    sender_avatar_url: str | None = None
    is_read: bool
    read_at: datetime | None
    is_archived: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationListResponse(BaseModel):
    """Schema for notification list response."""

    notifications: list[NotificationResponse]
    total: int
    unread_count: int


class UnreadCountResponse(BaseModel):
    """Schema for unread count response."""

    unread_count: int


class MarkReadRequest(BaseModel):
    """Schema for marking notifications as read."""

    notification_ids: list[UUID] | None = None  # If None, mark all as read
