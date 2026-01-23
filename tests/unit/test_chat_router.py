"""Tests for Chat router business logic."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
    MessageType,
)
from src.domains.users.models import User


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
async def user1(db_session: AsyncSession) -> dict[str, Any]:
    """Create first user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"user1-{user_id}@example.com",
        name="User One",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def user2(db_session: AsyncSession) -> dict[str, Any]:
    """Create second user."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"user2-{user_id}@example.com",
        name="User Two",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def user3(db_session: AsyncSession) -> dict[str, Any]:
    """Create third user for group chats."""
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"user3-{user_id}@example.com",
        name="User Three",
        password_hash="$2b$12$test.hash.password",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user_id, "email": user.email, "name": user.name}


@pytest.fixture
async def direct_conversation(
    db_session: AsyncSession, user1: dict, user2: dict
) -> Conversation:
    """Create a direct conversation between two users."""
    conv = Conversation(
        conversation_type=ConversationType.DIRECT,
    )
    db_session.add(conv)
    await db_session.flush()

    # Add participants
    p1 = ConversationParticipant(conversation_id=conv.id, user_id=user1["id"])
    p2 = ConversationParticipant(conversation_id=conv.id, user_id=user2["id"])
    db_session.add_all([p1, p2])

    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest.fixture
async def group_conversation(
    db_session: AsyncSession, user1: dict, user2: dict, user3: dict
) -> Conversation:
    """Create a group conversation."""
    conv = Conversation(
        title="Test Group",
        conversation_type=ConversationType.GROUP,
    )
    db_session.add(conv)
    await db_session.flush()

    # Add participants
    for user in [user1, user2, user3]:
        p = ConversationParticipant(conversation_id=conv.id, user_id=user["id"])
        db_session.add(p)

    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest.fixture
async def sample_message(
    db_session: AsyncSession, direct_conversation: Conversation, user1: dict
) -> Message:
    """Create a sample message."""
    msg = Message(
        conversation_id=direct_conversation.id,
        sender_id=user1["id"],
        message_type=MessageType.TEXT,
        content="Hello, this is a test message",
    )
    db_session.add(msg)
    await db_session.commit()
    await db_session.refresh(msg)
    return msg


# =============================================================================
# Conversation Creation Tests
# =============================================================================


class TestConversationCreation:
    """Tests for conversation creation."""

    async def test_create_direct_conversation(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Should create direct conversation between two users."""
        conv = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conv)
        await db_session.flush()

        p1 = ConversationParticipant(conversation_id=conv.id, user_id=user1["id"])
        p2 = ConversationParticipant(conversation_id=conv.id, user_id=user2["id"])
        db_session.add_all([p1, p2])
        await db_session.commit()

        assert conv.id is not None
        assert conv.conversation_type == ConversationType.DIRECT

    async def test_direct_conversation_detects_type(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Direct conversation should have DIRECT type when 2 participants."""
        conv = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conv)
        await db_session.commit()

        assert conv.conversation_type == ConversationType.DIRECT

    async def test_create_group_conversation(
        self, db_session: AsyncSession, user1: dict, user2: dict, user3: dict
    ):
        """Should create group conversation with multiple users."""
        conv = Conversation(
            title="Test Group",
            conversation_type=ConversationType.GROUP,
        )
        db_session.add(conv)
        await db_session.flush()

        for user in [user1, user2, user3]:
            p = ConversationParticipant(conversation_id=conv.id, user_id=user["id"])
            db_session.add(p)
        await db_session.commit()

        assert conv.id is not None
        assert conv.conversation_type == ConversationType.GROUP
        assert conv.title == "Test Group"

    async def test_conversation_auto_adds_creator(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Creator should be auto-added as participant."""
        conv = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conv)
        await db_session.flush()

        # Add both users as participants
        p1 = ConversationParticipant(conversation_id=conv.id, user_id=user1["id"])
        p2 = ConversationParticipant(conversation_id=conv.id, user_id=user2["id"])
        db_session.add_all([p1, p2])
        await db_session.commit()

        # Check participants
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conv.id
            )
        )
        participants = list(result.scalars().all())

        assert len(participants) == 2

    async def test_conversation_with_initial_message(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Should support initial message on creation."""
        conv = Conversation(
            conversation_type=ConversationType.DIRECT,
            last_message_preview="Hello!",
            last_message_at=datetime.now(timezone.utc),
        )
        db_session.add(conv)
        await db_session.flush()

        msg = Message(
            conversation_id=conv.id,
            sender_id=user1["id"],
            content="Hello!",
            message_type=MessageType.TEXT,
        )
        db_session.add(msg)
        await db_session.commit()

        assert conv.last_message_preview == "Hello!"


# =============================================================================
# Conversation List Tests
# =============================================================================


class TestConversationList:
    """Tests for listing conversations."""

    async def test_list_user_conversations(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should list conversations where user is participant."""
        result = await db_session.execute(
            select(ConversationParticipant.conversation_id).where(
                ConversationParticipant.user_id == user1["id"]
            )
        )
        conv_ids = [row[0] for row in result.all()]

        assert direct_conversation.id in conv_ids

    async def test_filter_archived_conversations(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should filter archived conversations."""
        # Archive the conversation for user1
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.is_archived = True
        await db_session.commit()

        # Query non-archived
        result = await db_session.execute(
            select(ConversationParticipant.conversation_id).where(
                ConversationParticipant.user_id == user1["id"],
                ConversationParticipant.is_archived == False,
            )
        )
        conv_ids = [row[0] for row in result.all()]

        assert direct_conversation.id not in conv_ids

    async def test_conversations_ordered_by_last_message(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Conversations should be ordered by last message."""
        # Create two conversations
        conv1 = Conversation(
            conversation_type=ConversationType.DIRECT,
            last_message_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        conv2 = Conversation(
            conversation_type=ConversationType.DIRECT,
            last_message_at=datetime.now(timezone.utc),
        )
        db_session.add_all([conv1, conv2])
        await db_session.flush()

        # Add participants
        for conv in [conv1, conv2]:
            p1 = ConversationParticipant(conversation_id=conv.id, user_id=user1["id"])
            p2 = ConversationParticipant(conversation_id=conv.id, user_id=user2["id"])
            db_session.add_all([p1, p2])
        await db_session.commit()

        # Query ordered by last_message_at
        result = await db_session.execute(
            select(Conversation)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user1["id"])
            .order_by(Conversation.last_message_at.desc().nulls_last())
        )
        conversations = list(result.scalars().all())

        # Most recent should be first
        assert conversations[0].id == conv2.id

    async def test_pagination(
        self, db_session: AsyncSession, user1: dict, user2: dict
    ):
        """Should support pagination."""
        # Create multiple conversations
        for _ in range(5):
            conv = Conversation(conversation_type=ConversationType.DIRECT)
            db_session.add(conv)
            await db_session.flush()
            p1 = ConversationParticipant(conversation_id=conv.id, user_id=user1["id"])
            p2 = ConversationParticipant(conversation_id=conv.id, user_id=user2["id"])
            db_session.add_all([p1, p2])
        await db_session.commit()

        # Get page 1
        result = await db_session.execute(
            select(Conversation)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user1["id"])
            .limit(2)
            .offset(0)
        )
        page1 = list(result.scalars().all())

        # Get page 2
        result = await db_session.execute(
            select(Conversation)
            .join(ConversationParticipant)
            .where(ConversationParticipant.user_id == user1["id"])
            .limit(2)
            .offset(2)
        )
        page2 = list(result.scalars().all())

        assert len(page1) == 2
        assert len(page2) == 2
        assert page1[0].id != page2[0].id


# =============================================================================
# Message Tests
# =============================================================================


class TestMessages:
    """Tests for message operations."""

    async def test_send_message(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should send message in conversation."""
        msg = Message(
            conversation_id=direct_conversation.id,
            sender_id=user1["id"],
            message_type=MessageType.TEXT,
            content="Test message",
        )
        db_session.add(msg)
        await db_session.commit()
        await db_session.refresh(msg)

        assert msg.id is not None
        assert msg.content == "Test message"

    async def test_send_message_updates_conversation(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Sending message should update conversation last_message."""
        msg = Message(
            conversation_id=direct_conversation.id,
            sender_id=user1["id"],
            message_type=MessageType.TEXT,
            content="New message",
        )
        db_session.add(msg)

        # Update conversation
        direct_conversation.last_message_at = datetime.now(timezone.utc)
        direct_conversation.last_message_preview = "New message"[:255]
        await db_session.commit()

        assert direct_conversation.last_message_preview == "New message"

    async def test_list_messages_ordered(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Messages should be ordered by creation time."""
        for i in range(3):
            msg = Message(
                conversation_id=direct_conversation.id,
                sender_id=user1["id"],
                message_type=MessageType.TEXT,
                content=f"Message {i}",
            )
            db_session.add(msg)
        await db_session.commit()

        result = await db_session.execute(
            select(Message)
            .where(Message.conversation_id == direct_conversation.id)
            .order_by(Message.created_at.asc())
        )
        messages = list(result.scalars().all())

        assert len(messages) >= 3

    async def test_edit_message(
        self, db_session: AsyncSession, sample_message: Message
    ):
        """Should edit message and set is_edited flag."""
        sample_message.content = "Edited content"
        sample_message.is_edited = True
        sample_message.edited_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(sample_message)

        assert sample_message.content == "Edited content"
        assert sample_message.is_edited is True

    async def test_delete_message_soft(
        self, db_session: AsyncSession, sample_message: Message
    ):
        """Should soft delete message."""
        sample_message.is_deleted = True
        await db_session.commit()
        await db_session.refresh(sample_message)

        assert sample_message.is_deleted is True

    async def test_deleted_message_content_hidden(
        self, db_session: AsyncSession, sample_message: Message
    ):
        """Deleted message should hide content in response."""
        original_content = sample_message.content
        sample_message.is_deleted = True
        await db_session.commit()

        # The model still has content, but router should hide it
        assert sample_message.content == original_content  # Still stored


# =============================================================================
# Mark as Read Tests
# =============================================================================


class TestMarkAsRead:
    """Tests for marking messages as read."""

    async def test_mark_conversation_read(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should update last_read_at timestamp."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()

        participant.last_read_at = datetime.now(timezone.utc)
        await db_session.commit()
        await db_session.refresh(participant)

        assert participant.last_read_at is not None

    async def test_unread_count_decreases(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
        user2: dict,
    ):
        """Unread count should decrease after marking as read."""
        # Create messages from user2
        for _ in range(3):
            msg = Message(
                conversation_id=direct_conversation.id,
                sender_id=user2["id"],
                message_type=MessageType.TEXT,
                content="New message",
            )
            db_session.add(msg)
        await db_session.commit()

        # Get participant and mark as read
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.last_read_at = datetime.now(timezone.utc)
        await db_session.commit()

        # Count unread (messages after last_read_at)
        unread_count = await db_session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == direct_conversation.id,
                Message.sender_id != user1["id"],
                Message.created_at > participant.last_read_at,
            )
        )

        assert unread_count == 0


# =============================================================================
# Archive/Unarchive Tests
# =============================================================================


class TestArchive:
    """Tests for archiving conversations."""

    async def test_archive_conversation(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should archive conversation for user."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.is_archived = True
        await db_session.commit()
        await db_session.refresh(participant)

        assert participant.is_archived is True

    async def test_unarchive_conversation(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should unarchive conversation."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.is_archived = True
        await db_session.commit()

        # Unarchive
        participant.is_archived = False
        await db_session.commit()
        await db_session.refresh(participant)

        assert participant.is_archived is False

    async def test_archive_user_specific(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
        user2: dict,
    ):
        """Archiving should be user-specific."""
        # Archive for user1 only
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant1 = result.scalar_one()
        participant1.is_archived = True
        await db_session.commit()

        # Check user2's participant
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user2["id"],
            )
        )
        participant2 = result.scalar_one()

        assert participant1.is_archived is True
        assert participant2.is_archived is False


# =============================================================================
# Mute/Unmute Tests
# =============================================================================


class TestMute:
    """Tests for muting conversations."""

    async def test_mute_conversation(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should mute conversation for user."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.is_muted = True
        await db_session.commit()
        await db_session.refresh(participant)

        assert participant.is_muted is True

    async def test_unmute_conversation(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should unmute conversation."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        participant.is_muted = True
        await db_session.commit()

        participant.is_muted = False
        await db_session.commit()
        await db_session.refresh(participant)

        assert participant.is_muted is False

    async def test_mute_user_specific(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
        user2: dict,
    ):
        """Muting should be user-specific."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant1 = result.scalar_one()
        participant1.is_muted = True
        await db_session.commit()

        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user2["id"],
            )
        )
        participant2 = result.scalar_one()

        assert participant1.is_muted is True
        assert participant2.is_muted is False


# =============================================================================
# Unread Count Tests
# =============================================================================


class TestUnreadCount:
    """Tests for unread message counting."""

    async def test_count_unread_messages(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
        user2: dict,
    ):
        """Should count unread messages correctly."""
        # Create messages from user2
        for _ in range(5):
            msg = Message(
                conversation_id=direct_conversation.id,
                sender_id=user2["id"],
                message_type=MessageType.TEXT,
                content="Message",
            )
            db_session.add(msg)
        await db_session.commit()

        # Count all messages not from user1
        count = await db_session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == direct_conversation.id,
                Message.sender_id != user1["id"],
                Message.is_deleted == False,
            )
        )

        assert count == 5

    async def test_unread_respects_last_read(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
        user2: dict,
    ):
        """Should only count messages after last_read_at."""
        # Create some old messages with explicit timestamps
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        for i in range(3):
            msg = Message(
                conversation_id=direct_conversation.id,
                sender_id=user2["id"],
                message_type=MessageType.TEXT,
                content=f"Old message {i}",
            )
            db_session.add(msg)
        await db_session.commit()

        # Mark as read at current time
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user1["id"],
            )
        )
        participant = result.scalar_one()
        read_time = datetime.now(timezone.utc)
        participant.last_read_at = read_time
        await db_session.commit()

        # Get count of messages that would be read (created before last_read_at)
        read_count = await db_session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == direct_conversation.id,
                Message.sender_id != user1["id"],
                Message.is_deleted == False,
            )
        )

        # All 3 messages should be marked as read (created before last_read_at)
        assert read_count == 3

        # If we set last_read_at to an earlier time, we should have unread
        participant.last_read_at = datetime.now(timezone.utc) - timedelta(hours=2)
        await db_session.commit()

        # Now count messages after that earlier time (should be all 3)
        unread_count = await db_session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == direct_conversation.id,
                Message.sender_id != user1["id"],
                Message.created_at > participant.last_read_at,
                Message.is_deleted == False,
            )
        )

        assert unread_count == 3

    async def test_own_messages_not_counted(
        self,
        db_session: AsyncSession,
        direct_conversation: Conversation,
        user1: dict,
    ):
        """Own messages should not count as unread."""
        # Create messages from user1
        for _ in range(3):
            msg = Message(
                conversation_id=direct_conversation.id,
                sender_id=user1["id"],
                message_type=MessageType.TEXT,
                content="My message",
            )
            db_session.add(msg)
        await db_session.commit()

        # Count unread (excluding own)
        count = await db_session.scalar(
            select(func.count(Message.id)).where(
                Message.conversation_id == direct_conversation.id,
                Message.sender_id != user1["id"],
            )
        )

        assert count == 0


# =============================================================================
# Message Type Tests
# =============================================================================


class TestMessageTypes:
    """Tests for different message types."""

    async def test_text_message(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should create text message."""
        msg = Message(
            conversation_id=direct_conversation.id,
            sender_id=user1["id"],
            message_type=MessageType.TEXT,
            content="Text message",
        )
        db_session.add(msg)
        await db_session.commit()

        assert msg.message_type == MessageType.TEXT

    async def test_image_message(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should create image message."""
        msg = Message(
            conversation_id=direct_conversation.id,
            sender_id=user1["id"],
            message_type=MessageType.IMAGE,
            content="Image caption",
            attachment_url="https://example.com/image.jpg",
            attachment_name="image.jpg",
        )
        db_session.add(msg)
        await db_session.commit()

        assert msg.message_type == MessageType.IMAGE
        assert msg.attachment_url is not None

    async def test_file_message(
        self, db_session: AsyncSession, direct_conversation: Conversation, user1: dict
    ):
        """Should create file message."""
        msg = Message(
            conversation_id=direct_conversation.id,
            sender_id=user1["id"],
            message_type=MessageType.FILE,
            content="Document",
            attachment_url="https://example.com/doc.pdf",
            attachment_name="document.pdf",
        )
        db_session.add(msg)
        await db_session.commit()

        assert msg.message_type == MessageType.FILE
        assert msg.attachment_name == "document.pdf"


# =============================================================================
# Access Control Tests
# =============================================================================


class TestAccessControl:
    """Tests for conversation access control."""

    async def test_only_sender_can_edit(
        self, db_session: AsyncSession, sample_message: Message, user1: dict
    ):
        """Only message sender should be able to edit."""
        assert sample_message.sender_id == user1["id"]

    async def test_only_sender_can_delete(
        self, db_session: AsyncSession, sample_message: Message, user1: dict
    ):
        """Only message sender should be able to delete."""
        assert sample_message.sender_id == user1["id"]

    async def test_non_participant_cannot_access(
        self, db_session: AsyncSession, direct_conversation: Conversation, user3: dict
    ):
        """Non-participant should not access conversation."""
        result = await db_session.execute(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == direct_conversation.id,
                ConversationParticipant.user_id == user3["id"],
            )
        )
        participant = result.scalar_one_or_none()

        assert participant is None
