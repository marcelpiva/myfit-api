"""Workout reminder tasks.

These tasks send push notifications to remind users about their workouts.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from src.core.celery_app import celery_app

logger = logging.getLogger(__name__)


def run_async(coro):
    """Run async function in sync context."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_workout_reminders(self):
    """Send workout reminders to users who haven't trained today.

    This task:
    1. Finds users with active plan assignments
    2. Checks if they have a workout scheduled for today
    3. Checks if they've already trained today
    4. Checks their notification preferences and DND settings
    5. Sends push notification if appropriate

    Runs hourly from 6am to 10pm.
    """
    logger.info("Starting workout reminders task")
    return run_async(_send_workout_reminders_async())


async def _send_workout_reminders_async():
    """Async implementation of workout reminders."""
    from sqlalchemy import select, func, and_
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.workouts.models import PlanAssignment, WorkoutSession, AssignmentStatus
    from src.domains.users.models import User, UserSettings
    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.router import should_send_notification
    from src.domains.notifications.push_service import send_push_notification

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")

    # Convert postgres:// to postgresql+asyncpg://
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sent_count = 0
    skipped_count = 0

    async with async_session() as db:
        try:
            # Get current time in Brazil timezone
            now = datetime.now(timezone.utc)
            today = now.date()
            current_hour = (now.hour - 3) % 24  # Convert UTC to Brazil time (approximate)

            # Find users with active plan assignments who haven't trained today
            # Get all active assignments
            assignments_query = (
                select(PlanAssignment)
                .where(
                    PlanAssignment.is_active == True,
                    PlanAssignment.status == AssignmentStatus.ACCEPTED,
                    PlanAssignment.start_date <= today,
                )
            )
            result = await db.execute(assignments_query)
            assignments = result.scalars().all()

            logger.info(f"Found {len(assignments)} active assignments")

            for assignment in assignments:
                try:
                    # Check if user already trained today
                    session_query = (
                        select(func.count())
                        .select_from(WorkoutSession)
                        .where(
                            WorkoutSession.user_id == assignment.student_id,
                            func.date(WorkoutSession.started_at) == today,
                        )
                    )
                    result = await db.execute(session_query)
                    sessions_today = result.scalar() or 0

                    if sessions_today > 0:
                        skipped_count += 1
                        continue  # Already trained today

                    # Check notification preferences
                    should_send = await should_send_notification(
                        db=db,
                        user_id=assignment.student_id,
                        notification_type=NotificationType.WORKOUT_REMINDER,
                        channel="push",
                        respect_dnd=True,
                    )

                    if not should_send:
                        skipped_count += 1
                        continue

                    # Get user info
                    user_query = select(User).where(User.id == assignment.student_id)
                    result = await db.execute(user_query)
                    user = result.scalar_one_or_none()

                    if not user or not user.is_active:
                        skipped_count += 1
                        continue

                    # Send push notification
                    await send_push_notification(
                        db=db,
                        user_id=assignment.student_id,
                        title="Hora do treino!",
                        body="Seu treino de hoje está esperando. Bora manter o ritmo! 💪",
                        data={
                            "type": "workout_reminder",
                            "assignment_id": str(assignment.id),
                            "plan_id": str(assignment.plan_id),
                        },
                    )
                    sent_count += 1

                except Exception as e:
                    logger.error(f"Error processing assignment {assignment.id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in workout reminders task: {e}")
            raise

    logger.info(f"Workout reminders: sent={sent_count}, skipped={skipped_count}")
    return {"sent": sent_count, "skipped": skipped_count}


@celery_app.task(bind=True, max_retries=3)
def send_streak_reminder(self, user_id: str):
    """Send reminder to user about maintaining their streak.

    Called when a user is at risk of losing their streak.
    """
    logger.info(f"Sending streak reminder to user {user_id}")
    return run_async(_send_streak_reminder_async(user_id))


async def _send_streak_reminder_async(user_id: str):
    """Async implementation of streak reminder."""
    from uuid import UUID
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.users.models import User
    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.router import should_send_notification
    from src.domains.notifications.push_service import send_push_notification

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        user_uuid = UUID(user_id)

        # Check notification preferences
        should_send = await should_send_notification(
            db=db,
            user_id=user_uuid,
            notification_type=NotificationType.CHECKIN_STREAK,
            channel="push",
            respect_dnd=True,
        )

        if not should_send:
            return {"sent": False, "reason": "notification_disabled"}

        # Send push notification
        await send_push_notification(
            db=db,
            user_id=user_uuid,
            title="Seu streak está em risco! 🔥",
            body="Não deixe seu progresso escapar. Treine hoje para manter a sequência!",
            data={
                "type": "streak_reminder",
                "user_id": user_id,
            },
        )

        return {"sent": True}
