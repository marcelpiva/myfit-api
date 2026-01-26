"""Celery application configuration for background tasks and scheduled jobs.

Usage:
    # Start worker with beat scheduler (for development):
    celery -A src.core.celery_app worker -B -l info

    # Production (separate worker and beat):
    celery -A src.core.celery_app worker -l info
    celery -A src.core.celery_app beat -l info

Railway deployment:
    Create a separate service with start command:
    celery -A src.core.celery_app worker -B -l info --concurrency=2
"""
import os
from datetime import timedelta

from celery import Celery
from celery.schedules import crontab

# Load environment variables
from dotenv import load_dotenv

load_dotenv()

# Redis URL for broker and backend
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "myfit",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.tasks.reminders",
        "src.tasks.notifications",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Sao_Paulo",
    enable_utc=True,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Reject task if worker dies
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # Soft limit at 4 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour

    # Beat scheduler settings
    beat_scheduler="celery.beat:PersistentScheduler",
    beat_schedule_filename="celerybeat-schedule",
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Workout reminders - every hour from 6am to 10pm
    "send-workout-reminders-hourly": {
        "task": "src.tasks.reminders.send_workout_reminders",
        "schedule": crontab(minute=0, hour="6-22"),
    },

    # Check inactive students - daily at 10am
    "check-inactive-students-daily": {
        "task": "src.tasks.notifications.check_inactive_students",
        "schedule": crontab(minute=0, hour=10),
    },

    # Send invite reminders - daily at 9am
    "send-invite-reminders-daily": {
        "task": "src.tasks.notifications.send_invite_reminders",
        "schedule": crontab(minute=0, hour=9),
    },

    # Plan expiration warnings - daily at 8am
    "check-expiring-plans-daily": {
        "task": "src.tasks.notifications.check_expiring_plans",
        "schedule": crontab(minute=0, hour=8),
    },

    # Cleanup old notifications - weekly on Sunday at 3am
    "cleanup-old-notifications-weekly": {
        "task": "src.tasks.notifications.cleanup_old_notifications",
        "schedule": crontab(minute=0, hour=3, day_of_week=0),
    },
}


# Optional: Configure for Railway
if os.getenv("RAILWAY_ENVIRONMENT"):
    # Railway-specific settings
    celery_app.conf.update(
        # Use fewer resources on Railway
        worker_concurrency=2,
        # Store beat schedule in Redis instead of file
        beat_scheduler="celery.beat:PersistentScheduler",
    )
