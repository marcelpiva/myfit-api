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
from src.domains.gamification.router import router as gamification_router
from src.domains.marketplace.router import router as marketplace_router
from src.domains.notifications.router import router as notifications_router
from src.domains.nutrition.router import router as nutrition_router
from src.domains.organizations.router import router as organizations_router
from src.domains.progress.router import router as progress_router
from src.domains.schedule.router import router as schedule_router
from src.domains.trainers.router import router as trainers_router
from src.domains.users.router import router as users_router
from src.domains.workouts.router import router as workouts_router


async def run_pending_migrations():
    """Run any pending database migrations."""
    import os

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("No DATABASE_URL, skipping migrations")
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
    ]

    for name, module_path in migrations:
        try:
            module = __import__(module_path, fromlist=["migrate"])
            await module.migrate(database_url)
            print(f"Migration {name} completed")
        except Exception as e:
            print(f"Migration {name} error (may already be applied): {type(e).__name__}: {e}")


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
                print("No exercises found in database, seeding...")
                # Import and run the seed script
                from src.scripts.seed_exercises import seed_exercises
                seeded_count = await seed_exercises(session, clear_existing=False)
                print(f"Exercises seeded successfully: {seeded_count} exercises added")
            else:
                print(f"Database has {count} exercises, skipping seed")
    except Exception as e:
        print(f"Error checking/seeding exercises: {type(e).__name__}: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.APP_NAME}...")
    print(f"Environment: {settings.APP_ENV}")
    print(f"Database URL configured: {bool(settings.DATABASE_URL)}")

    # Initialize database tables
    try:
        from src.config.database import init_db
        await init_db()
        print("Database tables initialized")
    except Exception as e:
        print(f"ERROR initializing database: {type(e).__name__}: {e}")
        # Re-raise in production to prevent unhealthy startup
        if settings.is_production:
            raise

    # Run pending migrations
    try:
        await run_pending_migrations()
    except Exception as e:
        print(f"Warning: Could not run migrations: {type(e).__name__}: {e}")

    # Auto-seed exercises if database is empty
    try:
        await seed_exercises_if_empty()
    except Exception as e:
        print(f"Warning: Could not seed exercises: {type(e).__name__}: {e}")

    yield
    # Shutdown
    print(f"Shutting down {settings.APP_NAME}...")


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
        allow_methods=["*"],
        allow_headers=["*"],
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

    # Temporary debug endpoint - remove after fixing org isolation
    from fastapi import Request as DebugRequest
    @app.get("/debug/headers")
    async def debug_headers(request: DebugRequest) -> dict:
        return {
            "x_organization_id": request.headers.get("x-organization-id"),
            "all_headers": dict(request.headers),
        }

    # Temporary debug endpoint - query workouts for a user
    @app.get("/debug/workouts")
    async def debug_workouts() -> dict:
        from sqlalchemy import text
        from src.config.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT w.id, w.name, w.organization_id, w.created_by_id, w.is_template, w.is_public
                    FROM workouts w
                    ORDER BY w.created_at DESC
                    LIMIT 20
                """)
            )
            rows = result.fetchall()
            return {
                "workouts": [
                    {
                        "id": str(r[0]),
                        "name": r[1],
                        "organization_id": str(r[2]) if r[2] else None,
                        "created_by_id": str(r[3]),
                        "is_template": r[4],
                        "is_public": r[5],
                    }
                    for r in rows
                ]
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
