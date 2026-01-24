"""Push notification service using Firebase Admin SDK.

This service sends push notifications to mobile devices via FCM.
Requires firebase-admin package and service account credentials.
"""
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Firebase Admin SDK (lazy import to avoid errors if not installed)
_firebase_app = None


def _init_firebase():
    """Initialize Firebase Admin SDK."""
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials
        import os

        # Check if already initialized
        try:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app
        except ValueError:
            pass

        # Try to load credentials from environment variable
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

        if cred_json:
            # Parse JSON from environment variable
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
        elif cred_path:
            # Load from file
            cred = credentials.Certificate(cred_path)
        else:
            logger.warning("Firebase credentials not configured. Push notifications will be disabled.")
            return None

        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized successfully")
        return _firebase_app

    except ImportError:
        logger.warning("firebase-admin package not installed. Push notifications will be disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
        return None


async def send_push_notification(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
    image_url: str | None = None,
) -> int:
    """Send push notification to all active devices of a user.

    Args:
        db: Database session
        user_id: User ID to send notification to
        title: Notification title
        body: Notification body text
        data: Optional data payload for the notification
        image_url: Optional image URL for rich notifications

    Returns:
        Number of successfully sent notifications
    """
    from .models import DeviceToken

    # Initialize Firebase if needed
    app = _init_firebase()
    if app is None:
        logger.warning(f"Firebase not initialized. Skipping push notification for user {user_id}")
        return 0

    try:
        from firebase_admin import messaging
    except ImportError:
        logger.warning("firebase-admin not installed. Skipping push notification.")
        return 0

    # Get active device tokens for user
    query = select(DeviceToken).where(
        DeviceToken.user_id == user_id,
        DeviceToken.is_active == True,
    )
    result = await db.execute(query)
    tokens = list(result.scalars().all())

    if not tokens:
        logger.debug(f"No active device tokens for user {user_id}")
        return 0

    # Prepare message
    notification = messaging.Notification(
        title=title,
        body=body,
        image=image_url,
    )

    # Convert data values to strings (FCM requirement)
    str_data = {k: str(v) for k, v in (data or {}).items()}

    success_count = 0
    failed_tokens = []

    for device_token in tokens:
        try:
            message = messaging.Message(
                notification=notification,
                data=str_data,
                token=device_token.token,
                # Platform-specific options
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        icon="ic_notification",
                        color="#4F46E5",  # Primary color
                        channel_id="myfit_notifications",
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            badge=1,
                            sound="default",
                        ),
                    ),
                ),
            )

            response = messaging.send(message)
            logger.debug(f"Push notification sent: {response}")
            success_count += 1

        except messaging.UnregisteredError:
            # Token is no longer valid
            logger.info(f"Device token unregistered: {device_token.token[:20]}...")
            failed_tokens.append(device_token)

        except messaging.SenderIdMismatchError:
            # Token belongs to a different Firebase project
            logger.warning(f"Sender ID mismatch for token: {device_token.token[:20]}...")
            failed_tokens.append(device_token)

        except Exception as e:
            logger.error(f"Failed to send push notification: {e}")

    # Deactivate failed tokens
    for token in failed_tokens:
        token.is_active = False

    if failed_tokens:
        await db.commit()

    logger.info(f"Push notifications sent: {success_count}/{len(tokens)} for user {user_id}")
    return success_count


async def send_push_to_multiple_users(
    db: AsyncSession,
    user_ids: list[UUID],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Send push notification to multiple users.

    Returns:
        Dictionary with 'sent' and 'failed' counts
    """
    sent = 0
    failed = 0

    for user_id in user_ids:
        count = await send_push_notification(db, user_id, title, body, data)
        if count > 0:
            sent += count
        else:
            failed += 1

    return {"sent": sent, "failed": failed}


async def send_push_to_topic(
    topic: str,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> bool:
    """Send push notification to a topic.

    Args:
        topic: Topic name (e.g., 'org_123' for organization-wide notifications)
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        True if sent successfully
    """
    app = _init_firebase()
    if app is None:
        return False

    try:
        from firebase_admin import messaging

        notification = messaging.Notification(title=title, body=body)
        str_data = {k: str(v) for k, v in (data or {}).items()}

        message = messaging.Message(
            notification=notification,
            data=str_data,
            topic=topic,
        )

        response = messaging.send(message)
        logger.info(f"Topic notification sent to '{topic}': {response}")
        return True

    except Exception as e:
        logger.error(f"Failed to send topic notification: {e}")
        return False
