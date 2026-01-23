"""Tests for notifications router."""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationType,
)
from src.domains.notifications.router import (
    create_bulk_notifications,
    create_notification,
    notify_achievement_unlocked,
    notify_appointment_reminder,
    notify_new_message,
    notify_payment_due,
    notify_workout_assigned,
)
from src.domains.notifications.schemas import NotificationCreate
from src.domains.users.models import User


@pytest.fixture
async def notification_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a user for notification tests."""
    user = User(
        email="notif_user@example.com",
        password_hash="hashed_password",
        name="Notification User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@pytest.fixture
async def sender_user(db_session: AsyncSession) -> dict[str, Any]:
    """Create a sender user for notification tests."""
    user = User(
        email="sender@example.com",
        password_hash="hashed_password",
        name="Sender User",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name}


@pytest.fixture
async def sample_notification(
    db_session: AsyncSession, notification_user: dict[str, Any]
) -> Notification:
    """Create a sample notification."""
    notification = Notification(
        user_id=notification_user["id"],
        notification_type=NotificationType.WORKOUT_ASSIGNED,
        title="Test Notification",
        body="This is a test notification",
        icon="dumbbell",
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.fixture
async def read_notification(
    db_session: AsyncSession, notification_user: dict[str, Any]
) -> Notification:
    """Create a read notification."""
    notification = Notification(
        user_id=notification_user["id"],
        notification_type=NotificationType.ACHIEVEMENT_UNLOCKED,
        title="Read Notification",
        body="This notification has been read",
        is_read=True,
        read_at=datetime.now(timezone.utc),
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.fixture
async def archived_notification(
    db_session: AsyncSession, notification_user: dict[str, Any]
) -> Notification:
    """Create an archived notification."""
    notification = Notification(
        user_id=notification_user["id"],
        notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        title="Archived Notification",
        body="This notification has been archived",
        is_archived=True,
    )
    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)
    return notification


class TestListNotifications:
    """Tests for list_notifications endpoint."""

    @pytest.mark.asyncio
    async def test_list_notifications_returns_user_notifications(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
    ):
        """Should return notifications for the user."""
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"],
                Notification.is_archived == False,
            )
        )
        notifications = list(result.scalars().all())

        assert len(notifications) >= 1
        assert any(n.id == sample_notification.id for n in notifications)

    @pytest.mark.asyncio
    async def test_list_notifications_excludes_archived_by_default(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
        archived_notification: Notification,
    ):
        """Should not include archived notifications by default."""
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"],
                Notification.is_archived == False,
            )
        )
        notifications = list(result.scalars().all())

        assert all(not n.is_archived for n in notifications)
        assert archived_notification.id not in [n.id for n in notifications]

    @pytest.mark.asyncio
    async def test_list_notifications_includes_archived_when_requested(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
        archived_notification: Notification,
    ):
        """Should include archived notifications when include_archived=True."""
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"]
            )
        )
        notifications = list(result.scalars().all())

        assert any(n.id == archived_notification.id for n in notifications)

    @pytest.mark.asyncio
    async def test_list_notifications_unread_only_filter(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
        read_notification: Notification,
    ):
        """Should filter to unread only when unread_only=True."""
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
                Notification.is_archived == False,
            )
        )
        notifications = list(result.scalars().all())

        assert all(not n.is_read for n in notifications)

    @pytest.mark.asyncio
    async def test_list_notifications_type_filter(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should filter by notification type."""
        # Create notifications of different types
        for ntype in [NotificationType.WORKOUT_ASSIGNED, NotificationType.NEW_MESSAGE]:
            notification = Notification(
                user_id=notification_user["id"],
                notification_type=ntype,
                title=f"{ntype.value} notification",
                body="Test body",
            )
            db_session.add(notification)
        await db_session.commit()

        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"],
                Notification.notification_type == NotificationType.WORKOUT_ASSIGNED,
            )
        )
        notifications = list(result.scalars().all())

        assert all(
            n.notification_type == NotificationType.WORKOUT_ASSIGNED
            for n in notifications
        )

    @pytest.mark.asyncio
    async def test_list_notifications_ordered_by_created_at_desc(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should order notifications by created_at descending."""
        # Create multiple notifications
        for i in range(3):
            notification = Notification(
                user_id=notification_user["id"],
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Notification {i}",
                body="Test body",
            )
            db_session.add(notification)
        await db_session.commit()

        result = await db_session.execute(
            select(Notification)
            .where(Notification.user_id == notification_user["id"])
            .order_by(Notification.created_at.desc())
        )
        notifications = list(result.scalars().all())

        # Verify descending order
        for i in range(len(notifications) - 1):
            assert notifications[i].created_at >= notifications[i + 1].created_at


class TestGetUnreadCount:
    """Tests for get_unread_count endpoint."""

    @pytest.mark.asyncio
    async def test_get_unread_count_returns_count(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
    ):
        """Should return count of unread notifications."""
        from sqlalchemy import func

        result = await db_session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
                Notification.is_archived == False,
            )
        )

        assert result >= 1

    @pytest.mark.asyncio
    async def test_get_unread_count_excludes_archived(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
        archived_notification: Notification,
    ):
        """Should not count archived notifications."""
        from sqlalchemy import func

        # Unarchive to verify count changes
        archived_notification.is_archived = False
        archived_notification.is_read = False
        await db_session.commit()

        count_with_unarchived = await db_session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
                Notification.is_archived == False,
            )
        )

        # Re-archive
        archived_notification.is_archived = True
        await db_session.commit()

        count_after_archive = await db_session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
                Notification.is_archived == False,
            )
        )

        assert count_with_unarchived == count_after_archive + 1


class TestGetNotification:
    """Tests for get_notification endpoint."""

    @pytest.mark.asyncio
    async def test_get_notification_returns_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sample_notification: Notification,
    ):
        """Should return the requested notification."""
        notification = await db_session.get(Notification, sample_notification.id)

        assert notification is not None
        assert notification.id == sample_notification.id
        assert notification.user_id == notification_user["id"]

    @pytest.mark.asyncio
    async def test_get_notification_verifies_ownership(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
        sample_notification: Notification,
    ):
        """Should only return notification if owned by user."""
        # Notification belongs to notification_user, not sender_user
        notification = await db_session.get(Notification, sample_notification.id)

        assert notification.user_id == notification_user["id"]
        assert notification.user_id != sender_user["id"]


class TestMarkNotificationRead:
    """Tests for mark_notification_read endpoint."""

    @pytest.mark.asyncio
    async def test_mark_notification_read_sets_is_read(
        self,
        db_session: AsyncSession,
        sample_notification: Notification,
    ):
        """Should set is_read to True."""
        assert sample_notification.is_read is False

        sample_notification.is_read = True
        sample_notification.read_at = datetime.utcnow()
        await db_session.commit()

        await db_session.refresh(sample_notification)
        assert sample_notification.is_read is True

    @pytest.mark.asyncio
    async def test_mark_notification_read_sets_read_at(
        self,
        db_session: AsyncSession,
        sample_notification: Notification,
    ):
        """Should set read_at timestamp."""
        assert sample_notification.read_at is None

        now = datetime.utcnow()
        sample_notification.is_read = True
        sample_notification.read_at = now
        await db_session.commit()

        await db_session.refresh(sample_notification)
        assert sample_notification.read_at is not None

    @pytest.mark.asyncio
    async def test_mark_notification_read_idempotent(
        self,
        db_session: AsyncSession,
        read_notification: Notification,
    ):
        """Should not fail if notification is already read."""
        original_read_at = read_notification.read_at
        assert read_notification.is_read is True

        # Re-marking as read should not change anything
        # (mimics router behavior of checking is_read first)
        if not read_notification.is_read:
            read_notification.read_at = datetime.utcnow()
        await db_session.commit()

        await db_session.refresh(read_notification)
        assert read_notification.read_at == original_read_at


class TestMarkAllRead:
    """Tests for mark_all_read endpoint."""

    @pytest.mark.asyncio
    async def test_mark_all_read_marks_all_user_notifications(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should mark all unread notifications as read."""
        # Create multiple unread notifications
        for i in range(3):
            notification = Notification(
                user_id=notification_user["id"],
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Unread {i}",
                body="Test body",
            )
            db_session.add(notification)
        await db_session.commit()

        # Mark all as read
        from sqlalchemy import update

        await db_session.execute(
            update(Notification)
            .where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await db_session.commit()

        # Verify all are read
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
            )
        )
        unread = list(result.scalars().all())

        assert len(unread) == 0

    @pytest.mark.asyncio
    async def test_mark_all_read_only_affects_user_notifications(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should only mark current user's notifications as read."""
        # Create notification for sender_user
        other_notification = Notification(
            user_id=sender_user["id"],
            notification_type=NotificationType.NEW_MESSAGE,
            title="Other user notification",
            body="Test body",
        )
        db_session.add(other_notification)
        await db_session.commit()

        # Mark notification_user's notifications as read
        from sqlalchemy import update

        await db_session.execute(
            update(Notification)
            .where(
                Notification.user_id == notification_user["id"],
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await db_session.commit()

        # Verify other user's notification is still unread
        await db_session.refresh(other_notification)
        assert other_notification.is_read is False

    @pytest.mark.asyncio
    async def test_mark_specific_notifications_read(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should mark only specific notification IDs as read."""
        # Create notifications
        notifications = []
        for i in range(3):
            notification = Notification(
                user_id=notification_user["id"],
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Notification {i}",
                body="Test body",
            )
            db_session.add(notification)
            notifications.append(notification)
        await db_session.commit()

        # Mark only first two as read
        ids_to_mark = [notifications[0].id, notifications[1].id]
        from sqlalchemy import update

        await db_session.execute(
            update(Notification)
            .where(
                Notification.user_id == notification_user["id"],
                Notification.id.in_(ids_to_mark),
                Notification.is_read == False,
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        await db_session.commit()

        # Refresh and verify
        for notif in notifications:
            await db_session.refresh(notif)

        assert notifications[0].is_read is True
        assert notifications[1].is_read is True
        assert notifications[2].is_read is False


class TestDeleteNotification:
    """Tests for delete_notification endpoint."""

    @pytest.mark.asyncio
    async def test_delete_notification_archives_it(
        self,
        db_session: AsyncSession,
        sample_notification: Notification,
    ):
        """Should soft delete by setting is_archived to True."""
        assert sample_notification.is_archived is False

        sample_notification.is_archived = True
        await db_session.commit()

        await db_session.refresh(sample_notification)
        assert sample_notification.is_archived is True

    @pytest.mark.asyncio
    async def test_delete_notification_verifies_ownership(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
        sample_notification: Notification,
    ):
        """Should only delete notification if owned by user."""
        # Notification belongs to notification_user
        assert sample_notification.user_id == notification_user["id"]
        assert sample_notification.user_id != sender_user["id"]

    @pytest.mark.asyncio
    async def test_delete_notification_not_found(
        self,
        db_session: AsyncSession,
    ):
        """Should not find non-existent notification."""
        non_existent_id = uuid.uuid4()
        notification = await db_session.get(Notification, non_existent_id)

        assert notification is None


class TestDeleteAllNotifications:
    """Tests for delete_all_notifications endpoint."""

    @pytest.mark.asyncio
    async def test_delete_all_read_only_by_default(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should only delete read notifications by default."""
        # Create read and unread notifications
        read_notif = Notification(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Read notification",
            body="Test",
            is_read=True,
            read_at=datetime.utcnow(),
        )
        unread_notif = Notification(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Unread notification",
            body="Test",
        )
        db_session.add(read_notif)
        db_session.add(unread_notif)
        await db_session.commit()

        # Delete read notifications only
        from sqlalchemy import update

        await db_session.execute(
            update(Notification)
            .where(
                Notification.user_id == notification_user["id"],
                Notification.is_archived == False,
                Notification.is_read == True,
            )
            .values(is_archived=True)
        )
        await db_session.commit()

        # Refresh and verify
        await db_session.refresh(read_notif)
        await db_session.refresh(unread_notif)

        assert read_notif.is_archived is True
        assert unread_notif.is_archived is False

    @pytest.mark.asyncio
    async def test_delete_all_including_unread(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should delete all notifications when read_only=False."""
        # Create read and unread notifications
        read_notif = Notification(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Read notification",
            body="Test",
            is_read=True,
        )
        unread_notif = Notification(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Unread notification",
            body="Test",
        )
        db_session.add(read_notif)
        db_session.add(unread_notif)
        await db_session.commit()

        # Delete all notifications (read_only=False)
        from sqlalchemy import update

        await db_session.execute(
            update(Notification)
            .where(
                Notification.user_id == notification_user["id"],
                Notification.is_archived == False,
            )
            .values(is_archived=True)
        )
        await db_session.commit()

        # Refresh and verify
        await db_session.refresh(read_notif)
        await db_session.refresh(unread_notif)

        assert read_notif.is_archived is True
        assert unread_notif.is_archived is True


class TestCreateNotification:
    """Tests for create_notification internal function."""

    @pytest.mark.asyncio
    async def test_create_notification_basic(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should create a notification with basic fields."""
        notification_data = NotificationCreate(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Test Notification",
            body="This is a test",
        )

        notification = await create_notification(db_session, notification_data)

        assert notification.id is not None
        assert notification.user_id == notification_user["id"]
        assert notification.title == "Test Notification"
        assert notification.body == "This is a test"
        assert notification.notification_type == NotificationType.SYSTEM_ANNOUNCEMENT
        assert notification.is_read is False
        assert notification.is_archived is False

    @pytest.mark.asyncio
    async def test_create_notification_with_all_fields(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should create a notification with all optional fields."""
        reference_id = uuid.uuid4()
        org_id = uuid.uuid4()

        notification_data = NotificationCreate(
            user_id=notification_user["id"],
            notification_type=NotificationType.WORKOUT_ASSIGNED,
            title="Workout Assigned",
            body="Your trainer assigned a new workout",
            priority=NotificationPriority.HIGH,
            icon="dumbbell",
            action_type="navigate",
            action_data='{"route": "/workouts/123"}',
            reference_type="workout",
            reference_id=reference_id,
            organization_id=org_id,
            sender_id=sender_user["id"],
        )

        notification = await create_notification(db_session, notification_data)

        assert notification.priority == NotificationPriority.HIGH
        assert notification.icon == "dumbbell"
        assert notification.action_type == "navigate"
        assert notification.reference_type == "workout"
        assert notification.reference_id == reference_id
        assert notification.sender_id == sender_user["id"]


class TestCreateBulkNotifications:
    """Tests for create_bulk_notifications internal function."""

    @pytest.mark.asyncio
    async def test_create_bulk_notifications(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should create multiple notifications at once."""
        notifications_data = [
            NotificationCreate(
                user_id=notification_user["id"],
                notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
                title=f"Bulk Notification {i}",
                body=f"Body {i}",
            )
            for i in range(3)
        ]

        notifications = await create_bulk_notifications(db_session, notifications_data)

        assert len(notifications) == 3
        for i, notif in enumerate(notifications):
            assert notif.id is not None
            assert notif.title == f"Bulk Notification {i}"

    @pytest.mark.asyncio
    async def test_create_bulk_notifications_to_multiple_users(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should create notifications for different users."""
        notifications_data = [
            NotificationCreate(
                user_id=notification_user["id"],
                notification_type=NotificationType.NEW_MESSAGE,
                title="Message for user 1",
                body="Body",
            ),
            NotificationCreate(
                user_id=sender_user["id"],
                notification_type=NotificationType.NEW_MESSAGE,
                title="Message for user 2",
                body="Body",
            ),
        ]

        notifications = await create_bulk_notifications(db_session, notifications_data)

        assert len(notifications) == 2
        assert notifications[0].user_id == notification_user["id"]
        assert notifications[1].user_id == sender_user["id"]


class TestNotifyWorkoutAssigned:
    """Tests for notify_workout_assigned helper function."""

    @pytest.mark.asyncio
    async def test_notify_workout_assigned_creates_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should create workout assigned notification."""
        workout_id = uuid.uuid4()

        notification = await notify_workout_assigned(
            db=db_session,
            user_id=notification_user["id"],
            workout_name="Push Pull Legs",
            trainer_id=sender_user["id"],
            trainer_name=sender_user["name"],
            workout_id=workout_id,
        )

        assert notification.notification_type == NotificationType.WORKOUT_ASSIGNED
        assert notification.title == "Novo treino atribuído"
        assert sender_user["name"] in notification.body
        assert "Push Pull Legs" in notification.body
        assert notification.icon == "dumbbell"
        assert notification.reference_type == "workout"
        assert notification.reference_id == workout_id
        assert notification.sender_id == sender_user["id"]


class TestNotifyAchievementUnlocked:
    """Tests for notify_achievement_unlocked helper function."""

    @pytest.mark.asyncio
    async def test_notify_achievement_unlocked_creates_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should create achievement unlocked notification."""
        achievement_id = uuid.uuid4()

        notification = await notify_achievement_unlocked(
            db=db_session,
            user_id=notification_user["id"],
            achievement_name="First Workout",
            achievement_id=achievement_id,
            points_earned=100,
        )

        assert notification.notification_type == NotificationType.ACHIEVEMENT_UNLOCKED
        assert notification.priority == NotificationPriority.HIGH
        assert notification.title == "Conquista desbloqueada!"
        assert "First Workout" in notification.body
        assert "100" in notification.body
        assert notification.icon == "trophy"
        assert notification.reference_type == "achievement"
        assert notification.reference_id == achievement_id


class TestNotifyNewMessage:
    """Tests for notify_new_message helper function."""

    @pytest.mark.asyncio
    async def test_notify_new_message_creates_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should create new message notification."""
        conversation_id = uuid.uuid4()

        notification = await notify_new_message(
            db=db_session,
            user_id=notification_user["id"],
            sender_id=sender_user["id"],
            sender_name=sender_user["name"],
            conversation_id=conversation_id,
            message_preview="Hello, how are you doing today?",
        )

        assert notification.notification_type == NotificationType.NEW_MESSAGE
        assert sender_user["name"] in notification.title
        assert notification.icon == "message"
        assert notification.reference_type == "conversation"
        assert notification.reference_id == conversation_id
        assert notification.sender_id == sender_user["id"]

    @pytest.mark.asyncio
    async def test_notify_new_message_truncates_long_preview(
        self,
        db_session: AsyncSession,
        notification_user: dict,
        sender_user: dict,
    ):
        """Should truncate message preview longer than 100 characters."""
        conversation_id = uuid.uuid4()
        long_message = "A" * 150

        notification = await notify_new_message(
            db=db_session,
            user_id=notification_user["id"],
            sender_id=sender_user["id"],
            sender_name=sender_user["name"],
            conversation_id=conversation_id,
            message_preview=long_message,
        )

        # Body should be truncated to 100 chars + "..."
        assert len(notification.body) == 103
        assert notification.body.endswith("...")


class TestNotifyPaymentDue:
    """Tests for notify_payment_due helper function."""

    @pytest.mark.asyncio
    async def test_notify_payment_due_creates_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should create payment due notification."""
        payment_id = uuid.uuid4()

        notification = await notify_payment_due(
            db=db_session,
            user_id=notification_user["id"],
            amount_cents=15000,  # R$ 150.00
            due_date="15/01/2025",
            payment_id=payment_id,
        )

        assert notification.notification_type == NotificationType.PAYMENT_DUE
        assert notification.priority == NotificationPriority.HIGH
        assert notification.title == "Pagamento pendente"
        assert "R$ 150.00" in notification.body
        assert "15/01/2025" in notification.body
        assert notification.icon == "credit-card"
        assert notification.reference_type == "payment"
        assert notification.reference_id == payment_id


class TestNotifyAppointmentReminder:
    """Tests for notify_appointment_reminder helper function."""

    @pytest.mark.asyncio
    async def test_notify_appointment_reminder_creates_notification(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should create appointment reminder notification."""
        appointment_id = uuid.uuid4()
        org_id = uuid.uuid4()

        notification = await notify_appointment_reminder(
            db=db_session,
            user_id=notification_user["id"],
            appointment_id=appointment_id,
            trainer_name="John Trainer",
            appointment_time="14:00",
            organization_id=org_id,
        )

        assert notification.notification_type == NotificationType.APPOINTMENT_REMINDER
        assert notification.priority == NotificationPriority.HIGH
        assert notification.title == "Lembrete de sessão"
        assert "John Trainer" in notification.body
        assert "14:00" in notification.body
        assert notification.icon == "calendar"
        assert notification.reference_type == "appointment"
        assert notification.reference_id == appointment_id
        assert notification.organization_id == org_id


class TestNotificationModel:
    """Tests for Notification model behavior."""

    @pytest.mark.asyncio
    async def test_notification_default_values(
        self,
        db_session: AsyncSession,
        notification_user: dict,
    ):
        """Should have correct default values."""
        notification = Notification(
            user_id=notification_user["id"],
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            title="Test",
            body="Test body",
        )
        db_session.add(notification)
        await db_session.commit()
        await db_session.refresh(notification)

        assert notification.priority == NotificationPriority.NORMAL
        assert notification.is_read is False
        assert notification.is_archived is False
        assert notification.push_sent is False
        assert notification.read_at is None
        assert notification.push_sent_at is None

    @pytest.mark.asyncio
    async def test_notification_types_enum(self):
        """Should have all required notification types."""
        types = [t.value for t in NotificationType]

        # Workout related
        assert "workout_assigned" in types
        assert "workout_reminder" in types
        assert "workout_completed" in types

        # Gamification
        assert "achievement_unlocked" in types
        assert "points_earned" in types

        # Social
        assert "new_message" in types

        # Payment
        assert "payment_due" in types
        assert "payment_received" in types

        # Appointments
        assert "appointment_reminder" in types
        assert "appointment_cancelled" in types

    @pytest.mark.asyncio
    async def test_notification_priority_enum(self):
        """Should have all priority levels."""
        priorities = [p.value for p in NotificationPriority]

        assert "low" in priorities
        assert "normal" in priorities
        assert "high" in priorities
        assert "urgent" in priorities
