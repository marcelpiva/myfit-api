"""Notification tasks for trainers and system maintenance.

These tasks handle:
- Inactive student alerts
- Invite reminders
- Plan expiration warnings
- Notification cleanup
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

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
def check_inactive_students(self):
    """Check for inactive students and notify their trainers.

    Finds students who haven't trained in X days and notifies their trainer.
    Default threshold: 5 days of inactivity.

    Runs daily at 10am.
    """
    logger.info("Starting inactive students check")
    return run_async(_check_inactive_students_async())


async def _check_inactive_students_async(inactivity_days: int = 5):
    """Async implementation of inactive students check."""
    from sqlalchemy import select, func, and_
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.workouts.models import PlanAssignment, WorkoutSession, AssignmentStatus
    from src.domains.users.models import User
    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.schemas import NotificationCreate
    from src.domains.notifications.router import create_notification, should_send_notification
    from src.domains.notifications.push_service import send_push_notification

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    notified_count = 0
    skipped_count = 0

    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()
            threshold_date = today - timedelta(days=inactivity_days)

            # Get active assignments
            assignments_query = (
                select(PlanAssignment)
                .where(
                    PlanAssignment.is_active == True,
                    PlanAssignment.status == AssignmentStatus.ACCEPTED,
                )
            )
            result = await db.execute(assignments_query)
            assignments = result.scalars().all()

            # Group by trainer to avoid duplicate notifications
            trainer_students = {}

            for assignment in assignments:
                # Get last workout date for this student
                last_session_query = (
                    select(func.max(WorkoutSession.started_at))
                    .where(WorkoutSession.user_id == assignment.student_id)
                )
                result = await db.execute(last_session_query)
                last_session_date = result.scalar()

                # Check if inactive
                is_inactive = False
                days_inactive = 0

                if last_session_date is None:
                    # Never trained - check assignment start date
                    if assignment.start_date <= threshold_date:
                        is_inactive = True
                        days_inactive = (today - assignment.start_date).days
                elif last_session_date.date() <= threshold_date:
                    is_inactive = True
                    days_inactive = (today - last_session_date.date()).days

                if is_inactive:
                    trainer_id = assignment.trainer_id
                    if trainer_id not in trainer_students:
                        trainer_students[trainer_id] = []
                    trainer_students[trainer_id].append({
                        "student_id": assignment.student_id,
                        "days_inactive": days_inactive,
                    })

            # Notify trainers
            for trainer_id, students in trainer_students.items():
                try:
                    # Check if trainer wants these notifications
                    should_send = await should_send_notification(
                        db=db,
                        user_id=trainer_id,
                        notification_type=NotificationType.STUDENT_INACTIVE,
                        channel="push",
                        respect_dnd=True,
                    )

                    if not should_send:
                        skipped_count += len(students)
                        continue

                    # Get student names
                    student_names = []
                    for s in students[:3]:  # Show first 3 names
                        user_query = select(User.name).where(User.id == s["student_id"])
                        result = await db.execute(user_query)
                        name = result.scalar()
                        if name:
                            student_names.append(name)

                    if len(students) == 1:
                        body = f"{student_names[0]} está há {students[0]['days_inactive']} dias sem treinar"
                    elif len(students) <= 3:
                        body = f"{', '.join(student_names)} estão inativos"
                    else:
                        body = f"{', '.join(student_names)} e mais {len(students) - 3} alunos estão inativos"

                    # Create in-app notification
                    await create_notification(
                        db=db,
                        notification_data=NotificationCreate(
                            user_id=trainer_id,
                            notification_type=NotificationType.STUDENT_INACTIVE,
                            title="Alunos inativos",
                            body=body,
                            icon="user-x",
                            action_type="navigate",
                            action_data='{"route": "/students"}',
                        ),
                    )

                    # Send push notification
                    await send_push_notification(
                        db=db,
                        user_id=trainer_id,
                        title="Alunos inativos",
                        body=body,
                        data={
                            "type": "student_inactive",
                            "student_count": len(students),
                        },
                    )

                    notified_count += len(students)

                except Exception as e:
                    logger.error(f"Error notifying trainer {trainer_id}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in inactive students check: {e}")
            raise

    logger.info(f"Inactive students check: notified={notified_count}, skipped={skipped_count}")
    return {"notified": notified_count, "skipped": skipped_count}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def send_invite_reminders(self):
    """Send reminders for pending invites.

    Sends reminders at:
    - 3 days: First reminder to invitee
    - 7 days: Reminder to inviter that invite wasn't accepted
    - 14 days: Final reminder to invitee

    Runs daily at 9am.
    """
    logger.info("Starting invite reminders task")
    return run_async(_send_invite_reminders_async())


async def _send_invite_reminders_async():
    """Async implementation of invite reminders."""
    from sqlalchemy import select, and_
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.organizations.models import OrganizationInvite
    from src.domains.users.models import User
    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.schemas import NotificationCreate
    from src.domains.notifications.router import create_notification
    from src.domains.notifications.push_service import send_push_notification
    from src.core.email import send_invite_reminder_email

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    sent_count = 0
    expired_count = 0

    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            # Get pending invites (accepted_at is NULL and not expired)
            invites_query = (
                select(OrganizationInvite)
                .where(
                    OrganizationInvite.accepted_at.is_(None),
                    OrganizationInvite.expires_at > now,
                )
            )
            result = await db.execute(invites_query)
            invites = result.scalars().all()

            for invite in invites:
                try:
                    days_pending = (now - invite.created_at).days

                    # Get inviter name
                    inviter_query = select(User.name).where(User.id == invite.invited_by_id)
                    result = await db.execute(inviter_query)
                    inviter_name = result.scalar() or "Um personal"

                    # 3-day reminder to invitee
                    if days_pending == 3 and invite.email:
                        # Check if user exists with this email
                        user_query = select(User).where(User.email == invite.email)
                        result = await db.execute(user_query)
                        user = result.scalar_one_or_none()

                        # Send push if user exists
                        if user:
                            await send_push_notification(
                                db=db,
                                user_id=user.id,
                                title="Convite pendente",
                                body=f"{inviter_name} está esperando sua resposta!",
                                data={
                                    "type": "invite_reminder",
                                    "invite_id": str(invite.id),
                                },
                            )

                        # Always send email reminder
                        try:
                            await send_invite_reminder_email(
                                to_email=invite.email,
                                inviter_name=inviter_name,
                                org_name=invite.organization.name if invite.organization else "MyFit",
                                invite_token=invite.token,
                                is_final=False,
                            )
                        except Exception as email_error:
                            logger.warning(f"Failed to send reminder email to {invite.email}: {email_error}")

                        sent_count += 1

                    # 7-day reminder to inviter
                    elif days_pending == 7:
                        await create_notification(
                            db=db,
                            notification_data=NotificationCreate(
                                user_id=invite.invited_by_id,
                                notification_type=NotificationType.INVITE_RECEIVED,
                                title="Convite não respondido",
                                body=f"O convite para {invite.email} não foi aceito ainda (7 dias)",
                                icon="mail",
                                action_type="navigate",
                                action_data=f'{{"route": "/invites/{invite.id}"}}',
                                reference_type="invite",
                                reference_id=invite.id,
                            ),
                        )

                        await send_push_notification(
                            db=db,
                            user_id=invite.invited_by_id,
                            title="Convite pendente há 7 dias",
                            body=f"O convite para {invite.email} não foi aceito",
                            data={
                                "type": "invite_pending",
                                "invite_id": str(invite.id),
                            },
                        )
                        sent_count += 1

                    # 14-day final reminder to invitee
                    elif days_pending == 14 and invite.email:
                        user_query = select(User).where(User.email == invite.email)
                        result = await db.execute(user_query)
                        user = result.scalar_one_or_none()

                        if user:
                            await send_push_notification(
                                db=db,
                                user_id=user.id,
                                title="Último lembrete!",
                                body=f"Seu convite de {inviter_name} expira em breve",
                                data={
                                    "type": "invite_expiring",
                                    "invite_id": str(invite.id),
                                },
                            )
                            sent_count += 1

                        # Also send email reminder
                        try:
                            await send_invite_reminder_email(
                                to_email=invite.email,
                                inviter_name=inviter_name,
                                org_name=invite.organization.name if invite.organization else "MyFit",
                                invite_token=invite.token,
                                is_final=True,
                            )
                        except Exception as email_error:
                            logger.warning(f"Failed to send reminder email to {invite.email}: {email_error}")

                except Exception as e:
                    logger.error(f"Error processing invite {invite.id}: {e}")
                    continue

            # Also check for expired invites and notify inviters
            expired_query = (
                select(OrganizationInvite)
                .where(
                    OrganizationInvite.accepted_at.is_(None),
                    OrganizationInvite.expires_at <= now,
                )
            )
            result = await db.execute(expired_query)
            expired_invites = result.scalars().all()

            for invite in expired_invites:
                try:
                    # Notify inviter that invite expired
                    await create_notification(
                        db=db,
                        notification_data=NotificationCreate(
                            user_id=invite.invited_by_id,
                            notification_type=NotificationType.INVITE_RECEIVED,
                            title="Convite expirado",
                            body=f"O convite para {invite.email} expirou",
                            icon="mail-x",
                            action_type="navigate",
                            action_data='{"route": "/students"}',
                            reference_type="invite",
                            reference_id=invite.id,
                        ),
                    )
                    expired_count += 1
                except Exception as e:
                    logger.error(f"Error notifying about expired invite {invite.id}: {e}")

            await db.commit()

        except Exception as e:
            logger.error(f"Error in invite reminders task: {e}")
            raise

    logger.info(f"Invite reminders: sent={sent_count}, expired_notified={expired_count}")
    return {"sent": sent_count, "expired_notified": expired_count}


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def check_expiring_plans(self):
    """Check for plans that are about to expire and notify users.

    Sends warnings at:
    - 7 days before expiration
    - 3 days before expiration
    - 1 day before expiration

    Runs daily at 8am.
    """
    logger.info("Starting expiring plans check")
    return run_async(_check_expiring_plans_async())


async def _check_expiring_plans_async():
    """Async implementation of expiring plans check."""
    from sqlalchemy import select, and_
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.workouts.models import PlanAssignment, TrainingPlan, AssignmentStatus
    from src.domains.users.models import User
    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.schemas import NotificationCreate
    from src.domains.notifications.router import create_notification, should_send_notification
    from src.domains.notifications.push_service import send_push_notification

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    notified_count = 0

    async with async_session() as db:
        try:
            now = datetime.now(timezone.utc)
            today = now.date()

            # Warning thresholds
            warning_days = [7, 3, 1]

            for days in warning_days:
                expiring_date = today + timedelta(days=days)

                # Find assignments expiring on this date
                assignments_query = (
                    select(PlanAssignment)
                    .where(
                        PlanAssignment.is_active == True,
                        PlanAssignment.status == AssignmentStatus.ACCEPTED,
                        PlanAssignment.end_date == expiring_date,
                    )
                )
                result = await db.execute(assignments_query)
                assignments = result.scalars().all()

                for assignment in assignments:
                    try:
                        # Get plan name
                        plan_query = select(TrainingPlan.name).where(TrainingPlan.id == assignment.plan_id)
                        result = await db.execute(plan_query)
                        plan_name = result.scalar() or "Seu plano"

                        # Notify student
                        should_send = await should_send_notification(
                            db=db,
                            user_id=assignment.student_id,
                            notification_type=NotificationType.PLAN_ASSIGNED,
                            channel="push",
                            respect_dnd=True,
                        )

                        if should_send:
                            if days == 1:
                                body = f"'{plan_name}' expira amanhã!"
                            else:
                                body = f"'{plan_name}' expira em {days} dias"

                            await send_push_notification(
                                db=db,
                                user_id=assignment.student_id,
                                title="Plano expirando",
                                body=body,
                                data={
                                    "type": "plan_expiring",
                                    "assignment_id": str(assignment.id),
                                    "days_left": days,
                                },
                            )
                            notified_count += 1

                        # Also notify trainer
                        student_query = select(User.name).where(User.id == assignment.student_id)
                        result = await db.execute(student_query)
                        student_name = result.scalar() or "Aluno"

                        await create_notification(
                            db=db,
                            notification_data=NotificationCreate(
                                user_id=assignment.trainer_id,
                                notification_type=NotificationType.STUDENT_PROGRESS,
                                title="Plano expirando",
                                body=f"O plano de {student_name} expira em {days} dia(s)",
                                icon="calendar",
                                action_type="navigate",
                                action_data=f'{{"route": "/students/{assignment.student_id}"}}',
                                reference_type="plan_assignment",
                                reference_id=assignment.id,
                            ),
                        )

                    except Exception as e:
                        logger.error(f"Error processing assignment {assignment.id}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Error in expiring plans check: {e}")
            raise

    logger.info(f"Expiring plans check: notified={notified_count}")
    return {"notified": notified_count}


@celery_app.task(bind=True, max_retries=1)
def cleanup_old_notifications(self, days_old: int = 90):
    """Clean up old notifications to save database space.

    Deletes read notifications older than specified days.
    Keeps unread notifications indefinitely.

    Runs weekly on Sunday at 3am.
    """
    logger.info(f"Starting notification cleanup (older than {days_old} days)")
    return run_async(_cleanup_old_notifications_async(days_old))


async def _cleanup_old_notifications_async(days_old: int = 90):
    """Async implementation of notification cleanup."""
    from sqlalchemy import delete, and_
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.notifications.models import Notification

    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./myfit.db")
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://") and "+asyncpg" not in database_url:
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_old)

            # Delete old read notifications
            delete_query = (
                delete(Notification)
                .where(
                    and_(
                        Notification.is_read == True,
                        Notification.created_at < cutoff_date,
                    )
                )
            )
            result = await db.execute(delete_query)
            await db.commit()

            deleted_count = result.rowcount

            logger.info(f"Cleaned up {deleted_count} old notifications")
            return {"deleted": deleted_count}

        except Exception as e:
            logger.error(f"Error in notification cleanup: {e}")
            await db.rollback()
            raise


@celery_app.task
def send_notification_async(user_id: str, notification_type: str, title: str, body: str, data: dict = None):
    """Generic task to send a notification asynchronously.

    Can be called from anywhere in the app to send notifications
    without blocking the request.

    Usage:
        send_notification_async.delay(
            user_id=str(user.id),
            notification_type="workout_completed",
            title="Treino concluído!",
            body="Parabéns pelo treino de hoje",
            data={"workout_id": str(workout.id)}
        )
    """
    logger.info(f"Sending async notification to user {user_id}")
    return run_async(_send_notification_async_impl(user_id, notification_type, title, body, data))


async def _send_notification_async_impl(user_id: str, notification_type: str, title: str, body: str, data: dict = None):
    """Async implementation of generic notification sender."""
    from uuid import UUID
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    import os

    from src.domains.notifications.models import NotificationType
    from src.domains.notifications.schemas import NotificationCreate
    from src.domains.notifications.router import create_notification, should_send_notification
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

        # Try to get NotificationType enum value
        try:
            notif_type = NotificationType(notification_type)
        except ValueError:
            notif_type = NotificationType.SYSTEM_ANNOUNCEMENT

        # Check if should send
        should_send = await should_send_notification(
            db=db,
            user_id=user_uuid,
            notification_type=notif_type,
            channel="push",
            respect_dnd=True,
        )

        if not should_send:
            return {"sent": False, "reason": "notification_disabled"}

        # Create in-app notification
        await create_notification(
            db=db,
            notification_data=NotificationCreate(
                user_id=user_uuid,
                notification_type=notif_type,
                title=title,
                body=body,
            ),
        )

        # Send push notification
        await send_push_notification(
            db=db,
            user_id=user_uuid,
            title=title,
            body=body,
            data=data or {},
        )

        return {"sent": True}
