from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from scalar_fastapi import get_scalar_api_reference

from src.config.settings import settings
from src.domains.auth.router import router as auth_router
from src.domains.checkin.router import router as checkin_router
from src.domains.gamification.router import router as gamification_router
from src.domains.marketplace.router import router as marketplace_router
from src.domains.nutrition.router import router as nutrition_router
from src.domains.organizations.router import router as organizations_router
from src.domains.progress.router import router as progress_router
from src.domains.trainers.router import router as trainers_router
from src.domains.users.router import router as users_router
from src.domains.workouts.router import router as workouts_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events."""
    # Startup
    print(f"Starting {settings.APP_NAME}...")

    # Initialize database tables
    from src.config.database import init_db
    await init_db()
    print("Database tables initialized")

    yield
    # Shutdown
    print(f"Shutting down {settings.APP_NAME}...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        description="White-label fitness platform API",
        version="1.0.0",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
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

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy", "app": settings.APP_NAME}

    # Admin seed endpoint (protected by secret token)
    @app.post("/admin/seed-exercises")
    async def seed_exercises_endpoint(token: str) -> dict[str, str | int]:
        """Seed exercises database. Requires admin token."""
        import os
        admin_token = os.environ.get("JWT_SECRET", "")[:16]  # Use first 16 chars of JWT_SECRET
        if token != admin_token:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Invalid admin token")

        from src.config.database import AsyncSessionLocal
        from src.scripts.seed_exercises import seed_exercises

        async with AsyncSessionLocal() as session:
            count = await seed_exercises(session, clear_existing=True)
            return {"status": "success", "exercises_seeded": count}

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
