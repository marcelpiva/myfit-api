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
        logger.debug("🔔 Firebase already initialized, reusing existing app")
        return _firebase_app

    try:
        import firebase_admin
        from firebase_admin import credentials
        import os

        # Check if already initialized
        try:
            _firebase_app = firebase_admin.get_app()
            logger.debug("🔔 Firebase app already exists, reusing")
            return _firebase_app
        except ValueError:
            pass

        # Try to load credentials from environment variable
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
        cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

        logger.info(f"🔔 Firebase config - FIREBASE_CREDENTIALS_PATH: {'SET' if cred_path else 'NOT SET'}")
        logger.info(f"🔔 Firebase config - FIREBASE_CREDENTIALS_JSON: {'SET' if cred_json else 'NOT SET'}")

        if cred_json:
            # Parse JSON from environment variable
            logger.info("🔔 Loading Firebase credentials from FIREBASE_CREDENTIALS_JSON")
            cred_dict = json.loads(cred_json)
            cred = credentials.Certificate(cred_dict)
            logger.info(f"🔔 Firebase project_id: {cred_dict.get('project_id', 'unknown')}")
        elif cred_path:
            # Load from file
            logger.info(f"🔔 Loading Firebase credentials from file: {cred_path}")
            cred = credentials.Certificate(cred_path)
        else:
            logger.warning("🔔 ❌ Firebase credentials not configured. Push notifications will be disabled.")
            logger.warning("🔔 Set FIREBASE_CREDENTIALS_PATH or FIREBASE_CREDENTIALS_JSON in .env")
            return None

        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("🔔 ✅ Firebase Admin SDK initialized successfully")
        return _firebase_app

    except ImportError as e:
        logger.warning(f"🔔 ❌ firebase-admin package not installed: {e}")
        logger.warning("🔔 Run: pip install firebase-admin")
        return None
    except Exception as e:
        logger.error(f"🔔 ❌ Failed to initialize Firebase Admin SDK: {e}")
        import traceback
        logger.error(f"🔔 Traceback: {traceback.format_exc()}")
        return None


def get_firebase_status() -> dict:
    """Get Firebase initialization status for debugging."""
    import os

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")

    status = {
        "firebase_configured": False,
        "firebase_initialized": _firebase_app is not None,
        "credentials_path_set": bool(cred_path),
        "credentials_json_set": bool(cred_json),
        "firebase_admin_installed": False,
    }

    try:
        import firebase_admin
        status["firebase_admin_installed"] = True
        status["firebase_admin_version"] = firebase_admin.__version__
    except ImportError:
        pass

    if cred_path or cred_json:
        status["firebase_configured"] = True

    # Try to init and get project info
    app = _init_firebase()
    if app:
        status["firebase_initialized"] = True
        try:
            status["project_id"] = app.project_id
        except Exception:
            pass

    return status


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

    logger.info(f"🔔 [PUSH] Starting send_push_notification for user {user_id}")
    logger.info(f"🔔 [PUSH] Title: {title}")
    logger.info(f"🔔 [PUSH] Body: {body[:50]}...")

    # Initialize Firebase if needed
    app = _init_firebase()
    if app is None:
        logger.warning(f"🔔 [PUSH] ❌ Firebase not initialized. Skipping push notification for user {user_id}")
        return 0

    try:
        from firebase_admin import messaging
    except ImportError:
        logger.warning("🔔 [PUSH] ❌ firebase-admin not installed. Skipping push notification.")
        return 0

    # Get active device tokens for user
    query = select(DeviceToken).where(
        DeviceToken.user_id == user_id,
        DeviceToken.is_active == True,
    )
    result = await db.execute(query)
    tokens = list(result.scalars().all())

    if not tokens:
        logger.warning(f"🔔 [PUSH] ❌ No active device tokens for user {user_id}")
        return 0

    logger.info(f"🔔 [PUSH] Found {len(tokens)} active device token(s)")

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

    for i, device_token in enumerate(tokens):
        logger.info(f"🔔 [PUSH] Sending to device {i+1}/{len(tokens)} ({device_token.platform.value})")
        logger.debug(f"🔔 [PUSH] Token prefix: {device_token.token[:30]}...")

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
                    headers={
                        "apns-priority": "10",  # High priority
                        "apns-push-type": "alert",
                    },
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            badge=1,
                            sound="default",
                            content_available=True,
                        ),
                    ),
                ),
            )

            response = messaging.send(message)
            logger.info(f"🔔 [PUSH] ✅ Push notification sent successfully: {response}")
            success_count += 1

        except messaging.UnregisteredError:
            # Token is no longer valid
            logger.warning(f"🔔 [PUSH] ❌ Device token unregistered (expired): {device_token.token[:30]}...")
            failed_tokens.append(device_token)

        except messaging.SenderIdMismatchError:
            # Token belongs to a different Firebase project
            logger.error(f"🔔 [PUSH] ❌ Sender ID mismatch - token from different Firebase project: {device_token.token[:30]}...")
            logger.error("🔔 [PUSH] This usually means the app was built with different Firebase config than the server")
            failed_tokens.append(device_token)

        except messaging.InvalidArgumentError as e:
            logger.error(f"🔔 [PUSH] ❌ Invalid argument error: {e}")
            logger.error("🔔 [PUSH] This might indicate an invalid token format")

        except Exception as e:
            logger.error(f"🔔 [PUSH] ❌ Failed to send push notification: {e}")
            import traceback
            logger.error(f"🔔 [PUSH] Traceback: {traceback.format_exc()}")

    # Deactivate failed tokens
    for token in failed_tokens:
        token.is_active = False
        logger.info(f"🔔 [PUSH] Deactivating failed token: {token.token[:30]}...")

    if failed_tokens:
        await db.commit()

    logger.info(f"🔔 [PUSH] Push notifications completed: {success_count}/{len(tokens)} sent for user {user_id}")
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
