import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference

from src.config.settings import settings
from src.core.observability import init_observability
from src.domains.auth.router import router as auth_router
from src.domains.billing.router import router as billing_router
from src.domains.chat.router import router as chat_router
from src.domains.checkin.router import router as checkin_router
from src.domains.consultancy.router import router as consultancy_router
from src.domains.gamification.router import router as gamification_router
from src.domains.marketplace.router import router as marketplace_router
from src.domains.notifications.router import router as notifications_router
from src.domains.nutrition.router import router as nutrition_router
from src.domains.organizations.router import router as organizations_router
from src.domains.progress.router import router as progress_router
from src.domains.referrals.router import router as referrals_router
from src.domains.schedule.router import router as schedule_router
from src.domains.subscriptions.router import router as subscriptions_router
from src.domains.trainers.router import router as trainers_router
from src.domains.users.router import router as users_router
from src.domains.workouts.router import router as workouts_router

logger = structlog.get_logger(__name__)


async def run_pending_migrations():
    """Run any pending database migrations."""
    import os

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        logger.info("skipping_migrations", reason="no DATABASE_URL configured")
        return

    # Convert to asyncpg format
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # List of migrations to run in order
    migrations = [
        ("remove_user_type", "src.migrations.remove_user_type"),
        ("add_archived_at", "src.migrations.add_archived_at"),
        ("add_autonomous_org_type", "src.migrations.add_autonomous_org_type"),
        ("backfill_workout_org_id", "src.migrations.backfill_workout_org_id"),
        ("add_checkin_acceptance", "src.migrations.add_checkin_acceptance"),
        ("add_checkin_training_mode", "src.migrations.add_checkin_training_mode"),
        ("add_service_plans", "src.migrations.add_service_plans"),
        ("add_appointment_reminders", "src.migrations.add_appointment_reminders"),
        ("add_late_cancel_policy", "src.migrations.add_late_cancel_policy"),
        ("add_group_sessions", "src.migrations.add_group_sessions"),
        ("add_session_evaluations", "src.migrations.add_session_evaluations"),
        ("add_waitlist_templates", "src.migrations.add_waitlist_templates"),
        ("add_business_model", "src.migrations.add_business_model"),
        ("fix_consultancy_listing_fk", "src.migrations.fix_consultancy_listing_fk"),
    ]

    for name, module_path in migrations:
        try:
            module = __import__(module_path, fromlist=["migrate"])
            await module.migrate(database_url)
            logger.info("migration_completed", name=name)
        except Exception as e:
            logger.warning("migration_error", name=name, error=str(e), type=type(e).__name__, note="may already be applied")


async def seed_exercises_if_empty():
    """Seed exercises if none exist in the database."""
    from sqlalchemy import func, select

    from src.config.database import AsyncSessionLocal
    from src.domains.workouts.models import Exercise

    try:
        async with AsyncSessionLocal() as session:
            # Check if any exercises exist
            result = await session.execute(select(func.count(Exercise.id)))
            count = result.scalar()

            if count == 0:
                logger.info("seeding_exercises", reason="no exercises found in database")
                # Import and run the seed script
                from src.scripts.seed_exercises import seed_exercises
                seeded_count = await seed_exercises(session, clear_existing=False)
                logger.info("exercises_seeded", count=seeded_count)
            else:
                logger.info("exercises_seed_skipped", existing_count=count)
    except Exception as e:
        logger.warning("exercise_seed_error", error=str(e), type=type(e).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    logger.info("app_starting", app_name=settings.APP_NAME, environment=settings.APP_ENV, database_configured=bool(settings.DATABASE_URL))

    # Initialize database tables
    try:
        from src.config.database import init_db
        await init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e), type=type(e).__name__)
        # Re-raise in production to prevent unhealthy startup
        if settings.is_production:
            raise

    # Run pending migrations
    try:
        await run_pending_migrations()
    except Exception as e:
        logger.warning("migrations_failed", error=str(e), type=type(e).__name__)

    # Auto-seed exercises if database is empty
    try:
        await seed_exercises_if_empty()
    except Exception as e:
        logger.warning("exercise_seed_failed", error=str(e), type=type(e).__name__)

    # Start background scheduler
    from src.core.scheduler import scheduler
    try:
        await scheduler.start()
        logger.info("scheduler_started")
    except Exception as e:
        logger.warning("scheduler_start_failed", error=str(e), type=type(e).__name__)

    yield
    # Shutdown
    logger.info("app_shutting_down", app_name=settings.APP_NAME)
    # Stop background scheduler
    try:
        await scheduler.stop()
        logger.info("scheduler_stopped")
    except Exception as e:
        logger.warning("scheduler_stop_failed", error=str(e), type=type(e).__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # Initialize observability (GlitchTip/Sentry)
    init_observability()

    app = FastAPI(
        title=settings.APP_NAME,
        description="MyFit Platform API",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
        # Disable automatic trailing slash redirects - they lose Authorization headers
        redirect_slashes=False,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Organization-Id", "X-Request-Id"],
    )

    # Include routers
    app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Authentication"])
    app.include_router(users_router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["Users"])
    app.include_router(organizations_router, prefix=f"{settings.API_V1_PREFIX}/organizations", tags=["Organizations"])
    app.include_router(workouts_router, prefix=f"{settings.API_V1_PREFIX}/workouts", tags=["Workouts"])
    app.include_router(nutrition_router, prefix=f"{settings.API_V1_PREFIX}/nutrition", tags=["Nutrition"])
    app.include_router(progress_router, prefix=f"{settings.API_V1_PREFIX}/progress", tags=["Progress"])
    app.include_router(checkin_router, prefix=f"{settings.API_V1_PREFIX}/checkins", tags=["Check-ins"])
    app.include_router(gamification_router, prefix=f"{settings.API_V1_PREFIX}/gamification", tags=["Gamification"])
    app.include_router(marketplace_router, prefix=f"{settings.API_V1_PREFIX}/marketplace", tags=["Marketplace"])
    app.include_router(trainers_router, prefix=f"{settings.API_V1_PREFIX}/trainers", tags=["Trainers"])
    app.include_router(schedule_router, prefix=f"{settings.API_V1_PREFIX}", tags=["Schedule"])
    app.include_router(billing_router, prefix=f"{settings.API_V1_PREFIX}/billing", tags=["Billing"])
    app.include_router(chat_router, prefix=f"{settings.API_V1_PREFIX}/chat", tags=["Chat"])
    app.include_router(notifications_router, prefix=f"{settings.API_V1_PREFIX}/notifications", tags=["Notifications"])
    app.include_router(subscriptions_router, prefix=f"{settings.API_V1_PREFIX}/subscriptions", tags=["Subscriptions"])
    app.include_router(consultancy_router, prefix=f"{settings.API_V1_PREFIX}/consultancy", tags=["Consultancy"])
    app.include_router(referrals_router, prefix=f"{settings.API_V1_PREFIX}/referrals", tags=["Referrals"])

    # Legacy routes without /api/v1 prefix (for backwards compatibility)
    app.include_router(organizations_router, prefix="/organizations", tags=["Organizations (Legacy)"])

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
        }

    # Scalar API Reference - Modern API documentation
    @app.get("/reference", include_in_schema=False)
    async def scalar_html():
        return get_scalar_api_reference(
            openapi_url=app.openapi_url,
            title=f"{settings.APP_NAME} - API Reference",
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
