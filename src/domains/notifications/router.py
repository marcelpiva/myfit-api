"""Notifications router for user notifications."""
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser

from .models import Notification, NotificationPriority, NotificationType
from .schemas import (
    MarkReadRequest,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _notification_to_response(notification: Notification) -> NotificationResponse:
    """Convert notification model to response schema."""
    return NotificationResponse(
        id=notification.id,
        notification_type=notification.notification_type,
        priority=notification.priority,
        title=notification.title,
        body=notification.body,
        icon=notification.icon,
        action_type=notification.action_type,
        action_data=notification.action_data,
        reference_type=notification.reference_type,
        reference_id=notification.reference_id,
        organization_id=notification.organization_id,
        sender_id=notification.sender_id,
        sender_name=notification.sender.name if notification.sender else None,
        sender_avatar_url=notification.sender.avatar_url if notification.sender else None,
        is_read=notification.is_read,
        read_at=notification.read_at,
        is_archived=notification.is_archived,
        created_at=notification.created_at,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    unread_only: Annotated[bool, Query()] = False,
    notification_type: Annotated[NotificationType | None, Query()] = None,
    include_archived: Annotated[bool, Query()] = False,
) -> NotificationListResponse:
    """List notifications for current user."""
    # Base query
    base_filter = [Notification.user_id == current_user.id]

    if not include_archived:
        base_filter.append(Notification.is_archived == False)

    if unread_only:
        base_filter.append(Notification.is_read == False)

    if notification_type:
        base_filter.append(Notification.notification_type == notification_type)

    # Get total count
    count_query = select(func.count(Notification.id)).where(and_(*base_filter))
    result = await db.execute(count_query)
    total = result.scalar() or 0

    # Get unread count
    unread_query = select(func.count(Notification.id)).where(
        and_(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
            Notification.is_archived == False,
        )
    )
    result = await db.execute(unread_query)
    unread_count = result.scalar() or 0

    # Get notifications
    query = (
        select(Notification)
        .where(and_(*base_filter))
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(query)
    notifications = list(result.scalars().all())

    return NotificationListResponse(
        notifications=[_notification_to_response(n) for n in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UnreadCountResponse:
    """Get count of unread notifications."""
    query = select(func.count(Notification.id)).where(
        and_(
            Notification.user_id == current_user.id,
            Notification.is_read == False,
            Notification.is_archived == False,
        )
    )

    result = await db.execute(query)
    unread_count = result.scalar() or 0

    return UnreadCountResponse(unread_count=unread_count)


@router.get("/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationResponse:
    """Get a specific notification."""
    notification = await db.get(Notification, notification_id)

    if not notification or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return _notification_to_response(notification)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Mark a notification as read."""
    notification = await db.get(Notification, notification_id)

    if not notification or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: MarkReadRequest | None = None,
) -> None:
    """Mark all notifications as read (or specific ones if IDs provided)."""
    now = datetime.now(timezone.utc)

    if request and request.notification_ids:
        # Mark specific notifications as read
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == current_user.id,
                    Notification.id.in_(request.notification_ids),
                    Notification.is_read == False,
                )
            )
            .values(is_read=True, read_at=now)
        )
    else:
        # Mark all notifications as read
        stmt = (
            update(Notification)
            .where(
                and_(
                    Notification.user_id == current_user.id,
                    Notification.is_read == False,
                )
            )
            .values(is_read=True, read_at=now)
        )

    await db.execute(stmt)
    await db.commit()


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete (archive) a notification."""
    notification = await db.get(Notification, notification_id)

    if not notification or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    # Soft delete by archiving
    notification.is_archived = True
    await db.commit()


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_all_notifications(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    read_only: Annotated[bool, Query()] = True,
) -> None:
    """Delete (archive) all notifications. By default only read ones."""
    conditions = [
        Notification.user_id == current_user.id,
        Notification.is_archived == False,
    ]

    if read_only:
        conditions.append(Notification.is_read == True)

    stmt = update(Notification).where(and_(*conditions)).values(is_archived=True)

    await db.execute(stmt)
    await db.commit()


# --- Internal service functions for creating notifications ---


async def create_notification(
    db: AsyncSession,
    notification_data: NotificationCreate,
) -> Notification:
    """Create a new notification (internal use by other services)."""
    notification = Notification(
        user_id=notification_data.user_id,
        notification_type=notification_data.notification_type,
        priority=notification_data.priority,
        title=notification_data.title,
        body=notification_data.body,
        icon=notification_data.icon,
        action_type=notification_data.action_type,
        action_data=notification_data.action_data,
        reference_type=notification_data.reference_type,
        reference_id=notification_data.reference_id,
        organization_id=notification_data.organization_id,
        sender_id=notification_data.sender_id,
    )

    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    return notification


async def create_bulk_notifications(
    db: AsyncSession,
    notifications_data: list[NotificationCreate],
) -> list[Notification]:
    """Create multiple notifications at once (internal use)."""
    notifications = []

    for data in notifications_data:
        notification = Notification(
            user_id=data.user_id,
            notification_type=data.notification_type,
            priority=data.priority,
            title=data.title,
            body=data.body,
            icon=data.icon,
            action_type=data.action_type,
            action_data=data.action_data,
            reference_type=data.reference_type,
            reference_id=data.reference_id,
            organization_id=data.organization_id,
            sender_id=data.sender_id,
        )
        db.add(notification)
        notifications.append(notification)

    await db.commit()

    for n in notifications:
        await db.refresh(n)

    return notifications


# Helper functions for common notification types


async def notify_workout_assigned(
    db: AsyncSession,
    user_id: UUID,
    workout_name: str,
    trainer_id: UUID,
    trainer_name: str,
    workout_id: UUID,
    organization_id: UUID | None = None,
) -> Notification:
    """Create notification for workout assignment."""
    return await create_notification(
        db,
        NotificationCreate(
            user_id=user_id,
            notification_type=NotificationType.WORKOUT_ASSIGNED,
            title="Novo treino atribuído",
            body=f"{trainer_name} atribuiu o treino '{workout_name}' para você",
            icon="dumbbell",
            action_type="navigate",
            action_data=f'{{"route": "/workouts/{workout_id}"}}',
            reference_type="workout",
            reference_id=workout_id,
            organization_id=organization_id,
            sender_id=trainer_id,
        ),
    )


async def notify_achievement_unlocked(
    db: AsyncSession,
    user_id: UUID,
    achievement_name: str,
    achievement_id: UUID,
    points_earned: int,
) -> Notification:
    """Create notification for achievement unlocked."""
    return await create_notification(
        db,
        NotificationCreate(
            user_id=user_id,
            notification_type=NotificationType.ACHIEVEMENT_UNLOCKED,
            priority=NotificationPriority.HIGH,
            title="Conquista desbloqueada!",
            body=f"Você desbloqueou '{achievement_name}' e ganhou {points_earned} pontos!",
            icon="trophy",
            action_type="navigate",
            action_data=f'{{"route": "/achievements/{achievement_id}"}}',
            reference_type="achievement",
            reference_id=achievement_id,
        ),
    )


async def notify_new_message(
    db: AsyncSession,
    user_id: UUID,
    sender_id: UUID,
    sender_name: str,
    conversation_id: UUID,
    message_preview: str,
) -> Notification:
    """Create notification for new message."""
    return await create_notification(
        db,
        NotificationCreate(
            user_id=user_id,
            notification_type=NotificationType.NEW_MESSAGE,
            title=f"Nova mensagem de {sender_name}",
            body=message_preview[:100] + ("..." if len(message_preview) > 100 else ""),
            icon="message",
            action_type="navigate",
            action_data=f'{{"route": "/chat/{conversation_id}"}}',
            reference_type="conversation",
            reference_id=conversation_id,
            sender_id=sender_id,
        ),
    )


async def notify_payment_due(
    db: AsyncSession,
    user_id: UUID,
    amount_cents: int,
    due_date: str,
    payment_id: UUID,
    organization_id: UUID | None = None,
) -> Notification:
    """Create notification for payment due."""
    amount_formatted = f"R$ {amount_cents / 100:.2f}"
    return await create_notification(
        db,
        NotificationCreate(
            user_id=user_id,
            notification_type=NotificationType.PAYMENT_DUE,
            priority=NotificationPriority.HIGH,
            title="Pagamento pendente",
            body=f"Você tem um pagamento de {amount_formatted} com vencimento em {due_date}",
            icon="credit-card",
            action_type="navigate",
            action_data=f'{{"route": "/billing/payments/{payment_id}"}}',
            reference_type="payment",
            reference_id=payment_id,
            organization_id=organization_id,
        ),
    )


async def notify_appointment_reminder(
    db: AsyncSession,
    user_id: UUID,
    appointment_id: UUID,
    trainer_name: str,
    appointment_time: str,
    organization_id: UUID | None = None,
) -> Notification:
    """Create notification for appointment reminder."""
    return await create_notification(
        db,
        NotificationCreate(
            user_id=user_id,
            notification_type=NotificationType.APPOINTMENT_REMINDER,
            priority=NotificationPriority.HIGH,
            title="Lembrete de sessão",
            body=f"Sua sessão com {trainer_name} está agendada para {appointment_time}",
            icon="calendar",
            action_type="navigate",
            action_data=f'{{"route": "/schedule/appointments/{appointment_id}"}}',
            reference_type="appointment",
            reference_id=appointment_id,
            organization_id=organization_id,
        ),
    )
