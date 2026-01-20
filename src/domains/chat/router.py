"""Chat router for messaging between users."""
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.users.models import User

from .models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
    MessageType,
)
from .schemas import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    MarkAsReadRequest,
    MessageCreate,
    MessageResponse,
    MessageUpdate,
    ParticipantInfo,
)

router = APIRouter(prefix="/chat", tags=["chat"])


def _participant_to_info(participant: ConversationParticipant) -> ParticipantInfo:
    """Convert participant to info schema."""
    return ParticipantInfo(
        user_id=participant.user_id,
        name=participant.user.name if participant.user else "Unknown",
        avatar_url=participant.user.avatar_url if participant.user else None,
        last_read_at=participant.last_read_at,
    )


def _conversation_to_response(
    conversation: Conversation,
    current_user_id: UUID,
    unread_count: int = 0,
) -> ConversationResponse:
    """Convert conversation to response schema."""
    participants = [_participant_to_info(p) for p in conversation.participants]

    return ConversationResponse(
        id=conversation.id,
        title=conversation.title,
        conversation_type=conversation.conversation_type,
        organization_id=conversation.organization_id,
        last_message_at=conversation.last_message_at,
        last_message_preview=conversation.last_message_preview,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        participants=participants,
        unread_count=unread_count,
    )


def _conversation_to_list_response(
    conversation: Conversation,
    current_user_id: UUID,
    unread_count: int = 0,
) -> ConversationListResponse:
    """Convert conversation to list response schema."""
    # For direct conversations, find the other participant
    other_participant = None
    if conversation.conversation_type == ConversationType.DIRECT:
        for p in conversation.participants:
            if p.user_id != current_user_id:
                other_participant = _participant_to_info(p)
                break

    return ConversationListResponse(
        id=conversation.id,
        title=conversation.title,
        conversation_type=conversation.conversation_type,
        last_message_at=conversation.last_message_at,
        last_message_preview=conversation.last_message_preview,
        unread_count=unread_count,
        other_participant=other_participant,
    )


def _message_to_response(message: Message) -> MessageResponse:
    """Convert message to response schema."""
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        sender_name=message.sender.name if message.sender else "Unknown",
        sender_avatar_url=message.sender.avatar_url if message.sender else None,
        message_type=message.message_type,
        content=message.content if not message.is_deleted else "[Message deleted]",
        attachment_url=message.attachment_url if not message.is_deleted else None,
        attachment_name=message.attachment_name if not message.is_deleted else None,
        is_edited=message.is_edited,
        edited_at=message.edited_at,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


async def _get_unread_count(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    last_read_at: datetime | None,
) -> int:
    """Get unread message count for a user in a conversation."""
    query = select(func.count(Message.id)).where(
        and_(
            Message.conversation_id == conversation_id,
            Message.sender_id != user_id,
            Message.is_deleted == False,
        )
    )

    if last_read_at:
        query = query.where(Message.created_at > last_read_at)

    result = await db.execute(query)
    return result.scalar() or 0


@router.get("/conversations", response_model=list[ConversationListResponse])
async def list_conversations(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_archived: Annotated[bool, Query()] = False,
) -> list[ConversationListResponse]:
    """List conversations for current user."""
    # Get conversation IDs where user is a participant
    participant_query = select(ConversationParticipant.conversation_id).where(
        and_(
            ConversationParticipant.user_id == current_user.id,
            ConversationParticipant.is_archived == include_archived
            if not include_archived
            else True,
        )
    )

    # Get conversations with participants loaded
    query = (
        select(Conversation)
        .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
        .where(Conversation.id.in_(participant_query))
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    conversations = list(result.scalars().all())

    # Build response with unread counts
    responses = []
    for conv in conversations:
        # Find current user's participant record to get last_read_at
        user_participant = next(
            (p for p in conv.participants if p.user_id == current_user.id), None
        )
        last_read_at = user_participant.last_read_at if user_participant else None

        unread_count = await _get_unread_count(db, conv.id, current_user.id, last_read_at)
        responses.append(_conversation_to_list_response(conv, current_user.id, unread_count))

    return responses


@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: ConversationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationResponse:
    """Create a new conversation."""
    # Ensure current user is in participants
    participant_ids = set(request.participant_ids)
    participant_ids.add(current_user.id)

    # Verify all participants exist
    users_query = select(User).where(User.id.in_(participant_ids))
    result = await db.execute(users_query)
    users = {u.id: u for u in result.scalars().all()}

    if len(users) != len(participant_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more participants not found",
        )

    # For direct conversations with 2 participants, check if one already exists
    if len(participant_ids) == 2:
        other_user_id = next(uid for uid in participant_ids if uid != current_user.id)

        # Check for existing direct conversation
        existing_query = (
            select(Conversation)
            .join(ConversationParticipant)
            .where(
                and_(
                    Conversation.conversation_type == ConversationType.DIRECT,
                    ConversationParticipant.user_id.in_([current_user.id, other_user_id]),
                )
            )
            .group_by(Conversation.id)
            .having(func.count(ConversationParticipant.id) == 2)
        )

        result = await db.execute(existing_query)
        existing = result.scalar_one_or_none()

        if existing:
            # Load participants for response
            conv_query = (
                select(Conversation)
                .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
                .where(Conversation.id == existing.id)
            )
            result = await db.execute(conv_query)
            existing = result.scalar_one()
            return _conversation_to_response(existing, current_user.id)

    # Create new conversation
    conversation_type = (
        ConversationType.DIRECT if len(participant_ids) == 2 else ConversationType.GROUP
    )

    conversation = Conversation(
        title=request.title,
        conversation_type=conversation_type,
        organization_id=request.organization_id,
    )
    db.add(conversation)
    await db.flush()

    # Add participants
    for user_id in participant_ids:
        participant = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=user_id,
        )
        db.add(participant)

    # Add initial message if provided
    if request.initial_message:
        message = Message(
            conversation_id=conversation.id,
            sender_id=current_user.id,
            message_type=MessageType.TEXT,
            content=request.initial_message,
        )
        db.add(message)

        conversation.last_message_at = datetime.utcnow()
        conversation.last_message_preview = request.initial_message[:255]

    await db.commit()

    # Reload with relationships
    conv_query = (
        select(Conversation)
        .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
        .where(Conversation.id == conversation.id)
    )
    result = await db.execute(conv_query)
    conversation = result.scalar_one()

    return _conversation_to_response(conversation, current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConversationResponse:
    """Get a specific conversation."""
    # Verify user is a participant
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    user_participant = result.scalar_one_or_none()

    if not user_participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Get conversation with participants
    query = (
        select(Conversation)
        .options(selectinload(Conversation.participants).selectinload(ConversationParticipant.user))
        .where(Conversation.id == conversation_id)
    )
    result = await db.execute(query)
    conversation = result.scalar_one_or_none()

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    unread_count = await _get_unread_count(
        db, conversation_id, current_user.id, user_participant.last_read_at
    )

    return _conversation_to_response(conversation, current_user.id, unread_count)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    before_id: Annotated[UUID | None, Query()] = None,
) -> list[MessageResponse]:
    """List messages in a conversation."""
    # Verify user is a participant
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Build query
    query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    # Pagination by message ID (for infinite scroll)
    if before_id:
        before_msg = await db.get(Message, before_id)
        if before_msg:
            query = query.where(Message.created_at < before_msg.created_at)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    # Return in chronological order
    messages.reverse()

    return [_message_to_response(m) for m in messages]


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    conversation_id: UUID,
    request: MessageCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Send a message in a conversation."""
    # Verify user is a participant
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # Create message
    message = Message(
        conversation_id=conversation_id,
        sender_id=current_user.id,
        message_type=request.message_type,
        content=request.content,
        attachment_url=request.attachment_url,
        attachment_name=request.attachment_name,
    )
    db.add(message)

    # Update conversation
    conversation = await db.get(Conversation, conversation_id)
    if conversation:
        conversation.last_message_at = datetime.utcnow()
        conversation.last_message_preview = request.content[:255]

    # Update sender's last_read_at
    participant.last_read_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)

    # Load sender for response
    message_query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.id == message.id)
    )
    result = await db.execute(message_query)
    message = result.scalar_one()

    return _message_to_response(message)


@router.put("/conversations/{conversation_id}/messages/{message_id}", response_model=MessageResponse)
async def update_message(
    conversation_id: UUID,
    message_id: UUID,
    request: MessageUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Update a message (only sender can update)."""
    message = await db.get(Message, message_id)

    if not message or message.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can edit this message",
        )

    if message.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit a deleted message",
        )

    message.content = request.content
    message.is_edited = True
    message.edited_at = datetime.utcnow()

    await db.commit()
    await db.refresh(message)

    # Load sender for response
    message_query = (
        select(Message)
        .options(selectinload(Message.sender))
        .where(Message.id == message.id)
    )
    result = await db.execute(message_query)
    message = result.scalar_one()

    return _message_to_response(message)


@router.delete("/conversations/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: UUID,
    message_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a message (soft delete, only sender can delete)."""
    message = await db.get(Message, message_id)

    if not message or message.conversation_id != conversation_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the sender can delete this message",
        )

    message.is_deleted = True

    await db.commit()


@router.post("/conversations/{conversation_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_as_read(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: MarkAsReadRequest | None = None,
) -> None:
    """Mark conversation as read up to current time or specific message."""
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    # If specific message ID provided, use its timestamp
    if request and request.last_read_message_id:
        message = await db.get(Message, request.last_read_message_id)
        if message and message.conversation_id == conversation_id:
            participant.last_read_at = message.created_at
    else:
        participant.last_read_at = datetime.utcnow()

    await db.commit()


@router.post("/conversations/{conversation_id}/archive", status_code=status.HTTP_204_NO_CONTENT)
async def archive_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Archive a conversation for current user."""
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant.is_archived = True
    await db.commit()


@router.post("/conversations/{conversation_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
async def unarchive_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Unarchive a conversation for current user."""
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant.is_archived = False
    await db.commit()


@router.post("/conversations/{conversation_id}/mute", status_code=status.HTTP_204_NO_CONTENT)
async def mute_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mute notifications for a conversation."""
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant.is_muted = True
    await db.commit()


@router.post("/conversations/{conversation_id}/unmute", status_code=status.HTTP_204_NO_CONTENT)
async def unmute_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Unmute notifications for a conversation."""
    participant_query = select(ConversationParticipant).where(
        and_(
            ConversationParticipant.conversation_id == conversation_id,
            ConversationParticipant.user_id == current_user.id,
        )
    )
    result = await db.execute(participant_query)
    participant = result.scalar_one_or_none()

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    participant.is_muted = False
    await db.commit()
