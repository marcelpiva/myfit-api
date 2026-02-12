"""Background scheduler for periodic tasks (reminders, alerts)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


class BackgroundScheduler:
    """Runs periodic background tasks using asyncio."""

    def __init__(self):
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """Start all background tasks."""
        logger.info("BackgroundScheduler starting...")
        self._tasks = [
            asyncio.create_task(self._reminder_loop()),
            asyncio.create_task(self._package_expiry_loop()),
        ]
        logger.info("BackgroundScheduler started with %d tasks", len(self._tasks))

    async def stop(self):
        """Gracefully stop all background tasks."""
        logger.info("BackgroundScheduler stopping...")
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("BackgroundScheduler stopped")

    async def _reminder_loop(self):
        """Check for upcoming appointments every 5 minutes and send reminders."""
        while not self._stop_event.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    await self._send_24h_reminders(db)
                    await self._send_1h_reminders(db)
            except Exception as e:
                logger.error("Reminder loop error: %s", e)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=300)  # 5 min
                break
            except asyncio.TimeoutError:
                pass

    async def _package_expiry_loop(self):
        """Check for expiring packages every hour."""
        while not self._stop_event.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    await self._send_package_expiry_alerts(db)
            except Exception as e:
                logger.error("Package expiry loop error: %s", e)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=3600)  # 1 hour
                break
            except asyncio.TimeoutError:
                pass

    async def _send_24h_reminders(self, db: AsyncSession):
        """Send 24-hour reminders for upcoming appointments."""
        from src.domains.schedule.models import Appointment, AppointmentStatus
        from src.domains.notifications.push_service import send_push_notification

        now = datetime.now(timezone.utc)
        window_start = now + timedelta(hours=23)
        window_end = now + timedelta(hours=25)

        query = select(Appointment).where(
            and_(
                Appointment.date_time >= window_start,
                Appointment.date_time <= window_end,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.reminder_24h_sent == False,
            )
        )
        result = await db.execute(query)
        appointments = list(result.scalars().all())

        for appt in appointments:
            try:
                # Send to student
                dt_str = appt.date_time.strftime("%d/%m às %H:%M")
                await send_push_notification(
                    db, appt.student_id,
                    "Lembrete de Sessão",
                    f"Você tem uma sessão amanhã, {dt_str}",
                    data={"type": "APPOINTMENT_REMINDER", "appointment_id": str(appt.id)},
                )
                # Send to trainer
                await send_push_notification(
                    db, appt.trainer_id,
                    "Lembrete de Sessão",
                    f"Sessão amanhã, {dt_str}",
                    data={"type": "APPOINTMENT_REMINDER", "appointment_id": str(appt.id)},
                )
                appt.reminder_24h_sent = True
                await db.commit()
                logger.info("Sent 24h reminder for appointment %s", appt.id)
            except Exception as e:
                logger.error("Failed to send 24h reminder for %s: %s", appt.id, e)
                await db.rollback()

    async def _send_1h_reminders(self, db: AsyncSession):
        """Send 1-hour reminders for upcoming appointments."""
        from src.domains.schedule.models import Appointment, AppointmentStatus
        from src.domains.notifications.push_service import send_push_notification

        now = datetime.now(timezone.utc)
        window_start = now + timedelta(minutes=55)
        window_end = now + timedelta(minutes=65)

        query = select(Appointment).where(
            and_(
                Appointment.date_time >= window_start,
                Appointment.date_time <= window_end,
                Appointment.status.in_([AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED]),
                Appointment.reminder_1h_sent == False,
            )
        )
        result = await db.execute(query)
        appointments = list(result.scalars().all())

        for appt in appointments:
            try:
                dt_str = appt.date_time.strftime("%H:%M")
                await send_push_notification(
                    db, appt.student_id,
                    "Sessão em 1 hora",
                    f"Sua sessão começa às {dt_str}. Prepare-se!",
                    data={"type": "APPOINTMENT_REMINDER", "appointment_id": str(appt.id)},
                )
                await send_push_notification(
                    db, appt.trainer_id,
                    "Sessão em 1 hora",
                    f"Sessão às {dt_str} se aproximando",
                    data={"type": "APPOINTMENT_REMINDER", "appointment_id": str(appt.id)},
                )
                appt.reminder_1h_sent = True
                await db.commit()
                logger.info("Sent 1h reminder for appointment %s", appt.id)
            except Exception as e:
                logger.error("Failed to send 1h reminder for %s: %s", appt.id, e)
                await db.rollback()

    async def _send_package_expiry_alerts(self, db: AsyncSession):
        """Alert students/trainers when a service plan is running low."""
        from src.domains.billing.models import ServicePlan, ServicePlanType
        from src.domains.notifications.push_service import send_push_notification

        query = select(ServicePlan).where(
            and_(
                ServicePlan.status == "active",
                ServicePlan.plan_type == ServicePlanType.PACKAGE,
                ServicePlan.remaining_sessions.isnot(None),
                ServicePlan.remaining_sessions <= 2,
                ServicePlan.remaining_sessions > 0,
            )
        )
        result = await db.execute(query)
        plans = list(result.scalars().all())

        for plan in plans:
            try:
                remaining = plan.remaining_sessions
                await send_push_notification(
                    db, plan.student_id,
                    "Pacote Acabando",
                    f"Seu pacote '{plan.name}' tem apenas {remaining} sessão(ões) restante(s).",
                    data={"type": "PACKAGE_EXPIRY", "service_plan_id": str(plan.id)},
                )
                if plan.trainer_id:
                    await send_push_notification(
                        db, plan.trainer_id,
                        "Pacote de Aluno Acabando",
                        f"Pacote '{plan.name}' tem apenas {remaining} sessão(ões) restante(s).",
                        data={"type": "PACKAGE_EXPIRY", "service_plan_id": str(plan.id)},
                    )
                logger.info("Sent package expiry alert for plan %s (%d remaining)", plan.id, remaining)
            except Exception as e:
                logger.error("Failed to send package expiry alert for %s: %s", plan.id, e)


# Singleton instance
scheduler = BackgroundScheduler()
