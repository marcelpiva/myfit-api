"""Chat schemas for API validation."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .models import ConversationType, MessageType


class ParticipantInfo(BaseModel):
    """Participant info in conversation."""

    user_id: UUID
    name: str
    avatar_url: str | None = None
    last_read_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ConversationCreate(BaseModel):
    """Schema for creating a conversation."""

    participant_ids: list[UUID] = Field(..., min_length=1, max_length=50)
    title: str | None = None
    organization_id: UUID | None = None
    initial_message: str | None = None


class ConversationResponse(BaseModel):
    """Schema for conversation response."""

    id: UUID
    title: str | None
    conversation_type: ConversationType
    organization_id: UUID | None
    last_message_at: datetime | None
    last_message_preview: str | None
    created_at: datetime
    updated_at: datetime | None
    participants: list[ParticipantInfo] = []
    unread_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Schema for conversation list item."""

    id: UUID
    title: str | None
    conversation_type: ConversationType
    last_message_at: datetime | None
    last_message_preview: str | None
    unread_count: int = 0
    other_participant: ParticipantInfo | None = None  # For direct conversations

    model_config = ConfigDict(from_attributes=True)


class MessageCreate(BaseModel):
    """Schema for creating a message."""

    content: str = Field(..., min_length=1, max_length=5000)
    message_type: MessageType = MessageType.TEXT
    attachment_url: str | None = None
    attachment_name: str | None = None


class MessageResponse(BaseModel):
    """Schema for message response."""

    id: UUID
    conversation_id: UUID
    sender_id: UUID
    sender_name: str
    sender_avatar_url: str | None = None
    message_type: MessageType
    content: str
    attachment_url: str | None
    attachment_name: str | None
    is_edited: bool
    edited_at: datetime | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class MessageUpdate(BaseModel):
    """Schema for updating a message."""

    content: str = Field(..., min_length=1, max_length=5000)


class MarkAsReadRequest(BaseModel):
    """Schema for marking messages as read."""

    last_read_message_id: UUID | None = None
