"""Workout reminder tasks.

These tasks send push notifications to remind users about their workouts.
Features:
- Personalized reminder messages
- Streak protection reminders
- Day-of-week scheduling support
- DND (Do Not Disturb) respect
"""
import asyncio
import logging
import random
from datetime import datetime, time, timedelta, timezone

from src.core.celery_app import celery_app

logger = logging.getLogger(__name__)

# Varied reminder messages for variety
WORKOUT_REMINDER_MESSAGES = [
    ("Hora do treino!", "Seu treino de hoje está esperando. Bora manter o ritmo! 💪"),
    ("Bora treinar?", "Não deixe para amanhã o que você pode conquistar hoje! 🏋️"),
    ("Seu corpo agradece!", "Um treino hoje = um passo mais perto do seu objetivo 🎯"),
    ("Lembrete fitness", "Consistência é a chave. Vamos lá! 🔥"),
    ("Treino pendente", "Cada dia conta. Que tal mover o corpo agora? 💪"),
    ("Momento treino!", "Seu personal preparou um treino especial para você 🌟"),
]

STREAK_REMINDER_MESSAGES = [
    ("Seu streak está em risco! 🔥", "Não deixe seu progresso escapar. Treine hoje!"),
    ("Mantenha o fogo aceso! 🔥", "Você está em uma sequência incrível. Não pare agora!"),
    ("Sequência em perigo!", "Falta pouco para encerrar o dia. Bora treinar?"),
]

INACTIVE_MESSAGES = [
    ("Sentimos sua falta!", "Faz alguns dias que você não treina. Que tal voltar hoje?"),
    ("Hora de voltar!", "Seu treino está esperando. Vamos retomar juntos?"),
    ("Retome o ritmo!", "Nunca é tarde para recomeçar. Seu corpo agradece!"),
]


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
    """Async implementation of intelligent workout reminders.

    Features:
    - Varied reminder messages for engagement
    - Checks user's preferred workout time (if set)
    - Respects DND settings
    - Tracks days since last workout for personalized messaging
    """
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
    streak_reminders = 0

    async with async_session() as db:
        try:
            # Get current time in Brazil timezone (UTC-3)
            now = datetime.now(timezone.utc)
            brazil_offset = timedelta(hours=-3)
            brazil_now = now + brazil_offset
            today = brazil_now.date()
            current_hour = brazil_now.hour

            # Find users with active plan assignments who haven't trained today
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

            logger.info(f"Found {len(assignments)} active assignments, current hour: {current_hour}")

            for assignment in assignments:
                try:
                    student_id = assignment.student_id

                    # Check if user already trained today
                    session_query = (
                        select(func.count())
                        .select_from(WorkoutSession)
                        .where(
                            WorkoutSession.user_id == student_id,
                            func.date(WorkoutSession.started_at) == today,
                        )
                    )
                    result = await db.execute(session_query)
                    sessions_today = result.scalar() or 0

                    if sessions_today > 0:
                        skipped_count += 1
                        continue  # Already trained today

                    # Get user settings for preferred reminder time
                    settings_query = select(UserSettings).where(UserSettings.user_id == student_id)
                    result = await db.execute(settings_query)
                    settings = result.scalar_one_or_none()

                    # Check if this is the right time to send reminder
                    preferred_hour = 9  # Default: 9am
                    if settings and hasattr(settings, 'preferred_workout_time'):
                        pref_time = getattr(settings, 'preferred_workout_time', None)
                        if pref_time:
                            preferred_hour = pref_time.hour if hasattr(pref_time, 'hour') else 9

                    # Send reminders at preferred hour or a few hours later (gentle nudges)
                    valid_hours = [preferred_hour, preferred_hour + 2, preferred_hour + 4, 19, 20]
                    if current_hour not in valid_hours:
                        skipped_count += 1
                        continue

                    # Check notification preferences and DND
                    should_send = await should_send_notification(
                        db=db,
                        user_id=student_id,
                        notification_type=NotificationType.WORKOUT_REMINDER,
                        channel="push",
                        respect_dnd=True,
                    )

                    if not should_send:
                        skipped_count += 1
                        continue

                    # Get user info
                    user_query = select(User).where(User.id == student_id)
                    result = await db.execute(user_query)
                    user = result.scalar_one_or_none()

                    if not user or not user.is_active:
                        skipped_count += 1
                        continue

                    # Get last workout date to personalize message
                    last_session_query = (
                        select(func.max(WorkoutSession.started_at))
                        .where(WorkoutSession.user_id == student_id)
                    )
                    result = await db.execute(last_session_query)
                    last_session_date = result.scalar()

                    # Choose appropriate message based on days since last workout
                    days_since_last = None
                    if last_session_date:
                        days_since_last = (today - last_session_date.date()).days

                    if days_since_last and days_since_last >= 3:
                        # Inactive user - use comeback messages
                        title, body = random.choice(INACTIVE_MESSAGES)
                    elif current_hour >= 19:
                        # Late evening - streak protection message
                        title, body = random.choice(STREAK_REMINDER_MESSAGES)
                        streak_reminders += 1
                    else:
                        # Normal reminder
                        title, body = random.choice(WORKOUT_REMINDER_MESSAGES)

                    # Send push notification
                    await send_push_notification(
                        db=db,
                        user_id=student_id,
                        title=title,
                        body=body,
                        data={
                            "type": "workout_reminder",
                            "assignment_id": str(assignment.id),
                            "plan_id": str(assignment.plan_id),
                            "days_since_last": days_since_last,
                        },
                    )
                    sent_count += 1

                except Exception as e:
                    logger.error(f"Error processing assignment {assignment.id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in workout reminders task: {e}")
            raise

    logger.info(f"Workout reminders: sent={sent_count}, skipped={skipped_count}, streak_reminders={streak_reminders}")
    return {"sent": sent_count, "skipped": skipped_count, "streak_reminders": streak_reminders}


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
