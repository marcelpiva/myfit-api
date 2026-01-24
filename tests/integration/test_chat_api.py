"""Integration tests for chat API endpoints."""
import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.chat.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
    MessageType,
)

# Base URL for chat endpoints (router has /chat prefix, app adds /api/v1/chat prefix)
CHAT_BASE_URL = "/api/v1/chat/chat"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_conversation(
    db_session: AsyncSession, sample_user: dict[str, Any], student_user: dict[str, Any]
) -> Conversation:
    """Create a sample direct conversation between trainer and student."""
    conversation = Conversation(
        title=None,
        conversation_type=ConversationType.DIRECT,
        organization_id=sample_user["organization_id"],
    )
    db_session.add(conversation)
    await db_session.flush()

    # Add trainer as participant
    trainer_participant = ConversationParticipant(
        conversation_id=conversation.id,
        user_id=sample_user["id"],
    )
    db_session.add(trainer_participant)

    # Add student as participant
    student_participant = ConversationParticipant(
        conversation_id=conversation.id,
        user_id=student_user["id"],
    )
    db_session.add(student_participant)

    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


@pytest.fixture
async def sample_message(
    db_session: AsyncSession,
    sample_conversation: Conversation,
    sample_user: dict[str, Any],
) -> Message:
    """Create a sample message in the conversation."""
    message = Message(
        conversation_id=sample_conversation.id,
        sender_id=sample_user["id"],
        message_type=MessageType.TEXT,
        content="Hello! This is a test message.",
    )
    db_session.add(message)

    # Update conversation
    sample_conversation.last_message_preview = message.content[:255]

    await db_session.commit()
    await db_session.refresh(message)
    return message


@pytest.fixture
async def multiple_messages(
    db_session: AsyncSession,
    sample_conversation: Conversation,
    sample_user: dict[str, Any],
    student_user: dict[str, Any],
) -> list[Message]:
    """Create multiple messages for pagination testing."""
    messages = []
    for i in range(15):
        sender_id = sample_user["id"] if i % 2 == 0 else student_user["id"]
        message = Message(
            conversation_id=sample_conversation.id,
            sender_id=sender_id,
            message_type=MessageType.TEXT,
            content=f"Message number {i + 1}",
        )
        db_session.add(message)
        messages.append(message)

    sample_conversation.last_message_preview = messages[-1].content[:255]

    await db_session.commit()
    for msg in messages:
        await db_session.refresh(msg)
    return messages


# =============================================================================
# List Conversations Tests
# =============================================================================


class TestListConversations:
    """Tests for GET /api/v1/chat/chat/conversations."""

    async def test_list_conversations_authenticated(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Authenticated user can list their conversations."""
        response = await authenticated_client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_conversations_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 401

    async def test_list_conversations_empty(self, authenticated_client: AsyncClient):
        """Returns empty list when user has no conversations."""
        response = await authenticated_client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_conversations_with_pagination(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations", params={"limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    async def test_list_conversations_returns_other_participant(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Direct conversation response includes other participant info."""
        response = await authenticated_client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        conv = data[0]
        assert conv["conversation_type"] == "direct"
        assert conv["other_participant"] is not None
        assert "user_id" in conv["other_participant"]
        assert "name" in conv["other_participant"]


# =============================================================================
# Create Conversation Tests
# =============================================================================


class TestCreateConversation:
    """Tests for POST /api/v1/chat/chat/conversations."""

    async def test_create_conversation_success(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Can create a new direct conversation."""
        payload = {
            "participant_ids": [str(student_user["id"])],
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["conversation_type"] == "direct"
        assert "id" in data
        assert len(data["participants"]) == 2

    async def test_create_conversation_with_initial_message(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Can create conversation with initial message."""
        payload = {
            "participant_ids": [str(student_user["id"])],
            "initial_message": "Hey, how are you?",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["last_message_preview"] == "Hey, how are you?"

    async def test_create_conversation_with_title(
        self, authenticated_client: AsyncClient, student_user: dict[str, Any]
    ):
        """Can create conversation with custom title."""
        payload = {
            "participant_ids": [str(student_user["id"])],
            "title": "Training Discussion",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Training Discussion"

    async def test_create_conversation_returns_existing(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        student_user: dict[str, Any],
    ):
        """Creating duplicate direct conversation returns existing one."""
        payload = {
            "participant_ids": [str(student_user["id"])],
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(sample_conversation.id)

    async def test_create_conversation_invalid_participant(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 for non-existent participant."""
        fake_id = uuid.uuid4()
        payload = {
            "participant_ids": [str(fake_id)],
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    async def test_create_conversation_missing_participants(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing participant_ids."""
        payload = {}

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations", json=payload
        )

        assert response.status_code == 422


# =============================================================================
# Get Conversation Tests
# =============================================================================


class TestGetConversation:
    """Tests for GET /api/v1/chat/chat/conversations/{conversation_id}."""

    async def test_get_own_conversation(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Can get a conversation user is participant of."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_conversation.id)
        assert data["conversation_type"] == "direct"
        assert "participants" in data
        assert len(data["participants"]) == 2

    async def test_get_conversation_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent conversation."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{fake_id}"
        )

        assert response.status_code == 404

    async def test_get_conversation_not_participant(
        self,
        db_session: AsyncSession,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 when user is not a participant."""
        # Create a conversation without the authenticated user
        other_user_id = uuid.uuid4()

        # We need to create users that exist
        from src.domains.users.models import User

        user1 = User(
            id=other_user_id,
            email="other1@example.com",
            name="Other User 1",
            password_hash="$2b$12$test",
            is_active=True,
        )
        user2_id = uuid.uuid4()
        user2 = User(
            id=user2_id,
            email="other2@example.com",
            name="Other User 2",
            password_hash="$2b$12$test",
            is_active=True,
        )
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        conversation = Conversation(
            conversation_type=ConversationType.DIRECT,
        )
        db_session.add(conversation)
        await db_session.flush()

        p1 = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=other_user_id,
        )
        p2 = ConversationParticipant(
            conversation_id=conversation.id,
            user_id=user2_id,
        )
        db_session.add(p1)
        db_session.add(p2)
        await db_session.commit()

        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{conversation.id}"
        )

        assert response.status_code == 404

    async def test_get_conversation_includes_unread_count(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Response includes unread_count field."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data


# =============================================================================
# Send Message Tests
# =============================================================================


class TestSendMessage:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/messages."""

    async def test_send_message_success(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Can send a text message."""
        payload = {
            "content": "Hello, this is a test message!",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["content"] == "Hello, this is a test message!"
        assert data["message_type"] == "text"
        assert data["conversation_id"] == str(sample_conversation.id)
        assert "sender_name" in data

    async def test_send_message_with_attachment(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Can send a message with attachment."""
        payload = {
            "content": "Check out this file",
            "message_type": "file",
            "attachment_url": "https://example.com/file.pdf",
            "attachment_name": "document.pdf",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message_type"] == "file"
        assert data["attachment_url"] == "https://example.com/file.pdf"
        assert data["attachment_name"] == "document.pdf"

    async def test_send_message_empty_content(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Returns 422 for empty message content."""
        payload = {
            "content": "",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            json=payload,
        )

        assert response.status_code == 422

    async def test_send_message_content_too_long(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Returns 422 for message content exceeding max length."""
        payload = {
            "content": "x" * 5001,  # Max is 5000
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            json=payload,
        )

        assert response.status_code == 422

    async def test_send_message_not_participant(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when user is not a conversation participant."""
        fake_id = uuid.uuid4()
        payload = {
            "content": "Test message",
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/messages",
            json=payload,
        )

        assert response.status_code == 404

    async def test_send_message_updates_conversation(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Sending message updates conversation's last_message_preview."""
        payload = {
            "content": "This is the latest message",
        }

        await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            json=payload,
        )

        # Get the conversation and check last_message_preview
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}"
        )

        data = response.json()
        assert data["last_message_preview"] == "This is the latest message"


# =============================================================================
# List Messages Tests
# =============================================================================


class TestListMessages:
    """Tests for GET /api/v1/chat/chat/conversations/{conversation_id}/messages."""

    async def test_list_messages_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Can list messages in a conversation."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["content"] == "Hello! This is a test message."

    async def test_list_messages_pagination(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        multiple_messages: list[Message],
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            params={"limit": 5, "offset": 0},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    async def test_list_messages_pagination_offset(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        multiple_messages: list[Message],
    ):
        """Offset parameter returns correct subset."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            params={"limit": 5, "offset": 5},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 5

    async def test_list_messages_not_participant(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when user is not a conversation participant."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/messages"
        )

        assert response.status_code == 404

    async def test_list_messages_empty_conversation(
        self, authenticated_client: AsyncClient, sample_conversation: Conversation
    ):
        """Returns empty list for conversation with no messages."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages"
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_messages_returns_chronological_order(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        multiple_messages: list[Message],
    ):
        """Messages are returned in chronological order (oldest first after reversal)."""
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages",
            params={"limit": 50},  # Get all messages
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 15

        # The router queries in desc order and reverses, so messages should be
        # in chronological order (oldest first). However, due to pagination mechanics,
        # with no offset, we get the newest messages first (in desc), then reversed.
        # So with limit=50 and no offset, we get all 15 messages in chronological order.
        # Verify messages are in ascending created_at order
        for i in range(len(data) - 1):
            assert data[i]["created_at"] <= data[i + 1]["created_at"]


# =============================================================================
# Mark As Read Tests
# =============================================================================


class TestMarkAsRead:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/read."""

    async def test_mark_as_read_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Can mark conversation as read."""
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/read"
        )

        assert response.status_code == 204

    async def test_mark_as_read_with_message_id(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Can mark as read up to specific message."""
        payload = {
            "last_read_message_id": str(sample_message.id),
        }

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/read",
            json=payload,
        )

        assert response.status_code == 204

    async def test_mark_as_read_not_participant(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 when user is not a conversation participant."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/read"
        )

        assert response.status_code == 404

    async def test_mark_as_read_resets_unread_count(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        db_session: AsyncSession,
        student_user: dict[str, Any],
    ):
        """Marking as read resets the unread count."""
        # First, create a message from the student (so trainer has unread)
        student_message = Message(
            conversation_id=sample_conversation.id,
            sender_id=student_user["id"],
            message_type=MessageType.TEXT,
            content="Message from student",
        )
        db_session.add(student_message)
        await db_session.commit()

        # Mark as read
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/read"
        )
        assert response.status_code == 204

        # Get conversation and check unread_count is 0
        conv_response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}"
        )
        data = conv_response.json()
        assert data["unread_count"] == 0


# =============================================================================
# Update Message Tests
# =============================================================================


class TestUpdateMessage:
    """Tests for PUT /api/v1/chat/chat/conversations/{conversation_id}/messages/{message_id}."""

    async def test_update_message_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Sender can update their own message."""
        payload = {
            "content": "Updated message content",
        }

        response = await authenticated_client.put(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{sample_message.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Updated message content"
        assert data["is_edited"] is True
        assert data["edited_at"] is not None

    async def test_update_message_not_found(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
    ):
        """Returns 404 for nonexistent message."""
        fake_message_id = uuid.uuid4()
        payload = {
            "content": "Updated content",
        }

        response = await authenticated_client.put(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{fake_message_id}",
            json=payload,
        )

        assert response.status_code == 404

    async def test_update_message_wrong_conversation(
        self,
        authenticated_client: AsyncClient,
        sample_message: Message,
    ):
        """Returns 404 when message belongs to different conversation."""
        fake_conversation_id = uuid.uuid4()
        payload = {
            "content": "Updated content",
        }

        response = await authenticated_client.put(
            f"{CHAT_BASE_URL}/conversations/{fake_conversation_id}/messages/{sample_message.id}",
            json=payload,
        )

        assert response.status_code == 404

    async def test_update_message_not_sender(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        student_user: dict[str, Any],
    ):
        """Returns 403 when user is not the message sender."""
        # Create a message from the student user
        student_message = Message(
            conversation_id=sample_conversation.id,
            sender_id=student_user["id"],
            message_type=MessageType.TEXT,
            content="Student's message",
        )
        db_session.add(student_message)
        await db_session.commit()
        await db_session.refresh(student_message)

        payload = {
            "content": "Trying to update someone else's message",
        }

        response = await authenticated_client.put(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{student_message.id}",
            json=payload,
        )

        assert response.status_code == 403
        assert "sender" in response.json()["detail"].lower()

    async def test_update_deleted_message(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        sample_user: dict[str, Any],
    ):
        """Returns 400 when trying to update a deleted message."""
        # Create a deleted message
        deleted_message = Message(
            conversation_id=sample_conversation.id,
            sender_id=sample_user["id"],
            message_type=MessageType.TEXT,
            content="This message was deleted",
            is_deleted=True,
        )
        db_session.add(deleted_message)
        await db_session.commit()
        await db_session.refresh(deleted_message)

        payload = {
            "content": "Trying to update deleted message",
        }

        response = await authenticated_client.put(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{deleted_message.id}",
            json=payload,
        )

        assert response.status_code == 400
        assert "deleted" in response.json()["detail"].lower()


# =============================================================================
# Delete Message Tests
# =============================================================================


class TestDeleteMessage:
    """Tests for DELETE /api/v1/chat/chat/conversations/{conversation_id}/messages/{message_id}."""

    async def test_delete_message_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Sender can delete their own message (soft delete)."""
        response = await authenticated_client.delete(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{sample_message.id}"
        )

        assert response.status_code == 204

    async def test_delete_message_not_found(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
    ):
        """Returns 404 for nonexistent message."""
        fake_message_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{fake_message_id}"
        )

        assert response.status_code == 404

    async def test_delete_message_wrong_conversation(
        self,
        authenticated_client: AsyncClient,
        sample_message: Message,
    ):
        """Returns 404 when message belongs to different conversation."""
        fake_conversation_id = uuid.uuid4()

        response = await authenticated_client.delete(
            f"{CHAT_BASE_URL}/conversations/{fake_conversation_id}/messages/{sample_message.id}"
        )

        assert response.status_code == 404

    async def test_delete_message_not_sender(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        student_user: dict[str, Any],
    ):
        """Returns 403 when user is not the message sender."""
        # Create a message from the student user
        student_message = Message(
            conversation_id=sample_conversation.id,
            sender_id=student_user["id"],
            message_type=MessageType.TEXT,
            content="Student's message",
        )
        db_session.add(student_message)
        await db_session.commit()
        await db_session.refresh(student_message)

        response = await authenticated_client.delete(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{student_message.id}"
        )

        assert response.status_code == 403
        assert "sender" in response.json()["detail"].lower()

    async def test_deleted_message_shows_placeholder_content(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        sample_message: Message,
    ):
        """Deleted message shows placeholder content in list."""
        # Delete the message
        await authenticated_client.delete(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages/{sample_message.id}"
        )

        # List messages and check the deleted message shows placeholder
        response = await authenticated_client.get(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/messages"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        deleted_msg = next((m for m in data if m["id"] == str(sample_message.id)), None)
        assert deleted_msg is not None
        assert deleted_msg["is_deleted"] is True
        assert deleted_msg["content"] == "[Message deleted]"


# =============================================================================
# Archive Conversation Tests
# =============================================================================


class TestArchiveConversation:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/archive."""

    async def test_archive_conversation_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
    ):
        """User can archive a conversation."""
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/archive"
        )

        assert response.status_code == 204

    async def test_archive_conversation_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent conversation."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/archive"
        )

        assert response.status_code == 404

    async def test_archive_conversation_not_participant(
        self,
        db_session: AsyncSession,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 when user is not a participant."""
        from src.domains.users.models import User

        # Create a conversation without the authenticated user
        user1 = User(
            id=uuid.uuid4(),
            email="archive_test1@example.com",
            name="Archive Test User 1",
            password_hash="$2b$12$test",
            is_active=True,
        )
        user2 = User(
            id=uuid.uuid4(),
            email="archive_test2@example.com",
            name="Archive Test User 2",
            password_hash="$2b$12$test",
            is_active=True,
        )
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        conversation = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conversation)
        await db_session.flush()

        p1 = ConversationParticipant(conversation_id=conversation.id, user_id=user1.id)
        p2 = ConversationParticipant(conversation_id=conversation.id, user_id=user2.id)
        db_session.add(p1)
        db_session.add(p2)
        await db_session.commit()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{conversation.id}/archive"
        )

        assert response.status_code == 404

    async def test_archived_conversation_not_in_default_list(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
    ):
        """Archived conversation is not returned in default conversation list."""
        # Archive the conversation
        await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/archive"
        )

        # List conversations without include_archived flag
        response = await authenticated_client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 200
        data = response.json()
        conversation_ids = [c["id"] for c in data]
        assert str(sample_conversation.id) not in conversation_ids


# =============================================================================
# Unarchive Conversation Tests
# =============================================================================


class TestUnarchiveConversation:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/unarchive."""

    async def test_unarchive_conversation_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        sample_user: dict[str, Any],
    ):
        """User can unarchive a conversation."""
        # First archive the conversation
        participant_query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == sample_conversation.id,
                ConversationParticipant.user_id == sample_user["id"],
            )
        )
        result = await db_session.execute(participant_query)
        participant = result.scalar_one()
        participant.is_archived = True
        await db_session.commit()

        # Unarchive it
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/unarchive"
        )

        assert response.status_code == 204

    async def test_unarchive_conversation_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent conversation."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/unarchive"
        )

        assert response.status_code == 404

    async def test_unarchive_restores_to_list(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        sample_user: dict[str, Any],
    ):
        """Unarchived conversation appears in the default list."""
        # Archive the conversation first
        participant_query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == sample_conversation.id,
                ConversationParticipant.user_id == sample_user["id"],
            )
        )
        result = await db_session.execute(participant_query)
        participant = result.scalar_one()
        participant.is_archived = True
        await db_session.commit()

        # Unarchive it
        await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/unarchive"
        )

        # List conversations and verify it's there
        response = await authenticated_client.get(f"{CHAT_BASE_URL}/conversations")

        assert response.status_code == 200
        data = response.json()
        conversation_ids = [c["id"] for c in data]
        assert str(sample_conversation.id) in conversation_ids


# =============================================================================
# Mute Conversation Tests
# =============================================================================


class TestMuteConversation:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/mute."""

    async def test_mute_conversation_success(
        self,
        authenticated_client: AsyncClient,
        sample_conversation: Conversation,
    ):
        """User can mute a conversation."""
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/mute"
        )

        assert response.status_code == 204

    async def test_mute_conversation_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent conversation."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/mute"
        )

        assert response.status_code == 404

    async def test_mute_conversation_not_participant(
        self,
        db_session: AsyncSession,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 when user is not a participant."""
        from src.domains.users.models import User

        # Create a conversation without the authenticated user
        user1 = User(
            id=uuid.uuid4(),
            email="mute_test1@example.com",
            name="Mute Test User 1",
            password_hash="$2b$12$test",
            is_active=True,
        )
        user2 = User(
            id=uuid.uuid4(),
            email="mute_test2@example.com",
            name="Mute Test User 2",
            password_hash="$2b$12$test",
            is_active=True,
        )
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        conversation = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conversation)
        await db_session.flush()

        p1 = ConversationParticipant(conversation_id=conversation.id, user_id=user1.id)
        p2 = ConversationParticipant(conversation_id=conversation.id, user_id=user2.id)
        db_session.add(p1)
        db_session.add(p2)
        await db_session.commit()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{conversation.id}/mute"
        )

        assert response.status_code == 404


# =============================================================================
# Unmute Conversation Tests
# =============================================================================


class TestUnmuteConversation:
    """Tests for POST /api/v1/chat/chat/conversations/{conversation_id}/unmute."""

    async def test_unmute_conversation_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_conversation: Conversation,
        sample_user: dict[str, Any],
    ):
        """User can unmute a conversation."""
        # First mute the conversation
        participant_query = select(ConversationParticipant).where(
            and_(
                ConversationParticipant.conversation_id == sample_conversation.id,
                ConversationParticipant.user_id == sample_user["id"],
            )
        )
        result = await db_session.execute(participant_query)
        participant = result.scalar_one()
        participant.is_muted = True
        await db_session.commit()

        # Unmute it
        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{sample_conversation.id}/unmute"
        )

        assert response.status_code == 204

    async def test_unmute_conversation_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent conversation."""
        fake_id = uuid.uuid4()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{fake_id}/unmute"
        )

        assert response.status_code == 404

    async def test_unmute_conversation_not_participant(
        self,
        db_session: AsyncSession,
        authenticated_client: AsyncClient,
    ):
        """Returns 404 when user is not a participant."""
        from src.domains.users.models import User

        # Create a conversation without the authenticated user
        user1 = User(
            id=uuid.uuid4(),
            email="unmute_test1@example.com",
            name="Unmute Test User 1",
            password_hash="$2b$12$test",
            is_active=True,
        )
        user2 = User(
            id=uuid.uuid4(),
            email="unmute_test2@example.com",
            name="Unmute Test User 2",
            password_hash="$2b$12$test",
            is_active=True,
        )
        db_session.add(user1)
        db_session.add(user2)
        await db_session.flush()

        conversation = Conversation(conversation_type=ConversationType.DIRECT)
        db_session.add(conversation)
        await db_session.flush()

        p1 = ConversationParticipant(conversation_id=conversation.id, user_id=user1.id)
        p2 = ConversationParticipant(conversation_id=conversation.id, user_id=user2.id)
        db_session.add(p1)
        db_session.add(p2)
        await db_session.commit()

        response = await authenticated_client.post(
            f"{CHAT_BASE_URL}/conversations/{conversation.id}/unmute"
        )

        assert response.status_code == 404
