"""
E2E Test Server.

Standalone FastAPI server for external E2E tests (Playwright, Patrol, etc).
Runs with SQLite in-memory database and exposes endpoints for:
- /test/setup/{scenario} - Load scenario fixtures
- /test/reset - Clear all data
- All regular API endpoints

Usage:
    # From myfit-api directory
    python -m tests.e2e.server

    # Or with custom port
    E2E_PORT=8001 python -m tests.e2e.server

IMPORTANT: Never run against production! This server is for local testing only.
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Environment safety check
ALLOWED_ENVIRONMENTS = {"local", "development", "test", "testing"}


def validate_environment():
    """Ensure we're not running in production."""
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env not in ALLOWED_ENVIRONMENTS:
        print(f"ERROR: E2E server can only run in {ALLOWED_ENVIRONMENTS}")
        print(f"Current environment: {env}")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL", "")
    if "prod" in db_url.lower():
        print("ERROR: E2E server cannot use production database!")
        sys.exit(1)


validate_environment()

# In-memory SQLite for E2E tests
E2E_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# SQLite compatibility - map PostgreSQL JSONB to JSON
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    def visit_JSONB(self, type_, **kw):
        return self.visit_JSON(type_, **kw)
    SQLiteTypeCompiler.visit_JSONB = visit_JSONB


# Global engine and session factory
_engine = None
_async_session = None


async def init_database():
    """Initialize in-memory database with all tables."""
    global _engine, _async_session

    _engine = create_async_engine(
        E2E_DATABASE_URL,
        echo=os.getenv("SQL_ECHO", "false").lower() == "true",
        connect_args={"check_same_thread": False},
    )

    # Enable foreign keys for SQLite
    @event.listens_for(_engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    _async_session = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    # Import all models and create tables
    from src.config.database import Base
    from src.domains import models  # noqa: F401

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("E2E Database initialized with in-memory SQLite")


async def close_database():
    """Close database connections."""
    global _engine
    if _engine:
        await _engine.dispose()


async def get_e2e_db():
    """Database session dependency for E2E server."""
    async with _async_session() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await init_database()
    yield
    await close_database()


# Create the E2E test server app
def create_e2e_app() -> FastAPI:
    """Create FastAPI app for E2E testing."""
    from src.main import create_app
    from src.config.database import get_db

    # Create main app
    app = create_app()

    # Override database dependency to use in-memory SQLite
    app.dependency_overrides[get_db] = get_e2e_db

    # Add test endpoints
    @app.post("/test/setup/{scenario_name}")
    async def setup_scenario(
        scenario_name: str,
        db: AsyncSession = Depends(get_e2e_db),
    ):
        """
        Load a test scenario into the database.

        Args:
            scenario_name: Name of scenario (cotraining, plan_assignment, etc.)

        Returns:
            Credentials and IDs for test clients
        """
        from tests.e2e.scenarios import SCENARIOS

        if scenario_name not in SCENARIOS:
            raise HTTPException(
                status_code=404,
                detail=f"Scenario '{scenario_name}' not found. Available: {list(SCENARIOS.keys())}",
            )

        # Clear existing data first
        await _reset_database(db)

        # Setup scenario
        setup_fn = SCENARIOS[scenario_name]
        data = await setup_fn(db)

        return {
            "status": "ok",
            "scenario": scenario_name,
            "data": data,
        }

    @app.post("/test/reset")
    async def reset_database(db: AsyncSession = Depends(get_e2e_db)):
        """Clear all data from the database."""
        await _reset_database(db)
        return {"status": "ok", "message": "Database reset"}

    @app.get("/test/health")
    async def health_check():
        """Health check for E2E server."""
        return {
            "status": "ok",
            "database": "sqlite_in_memory",
            "environment": os.getenv("ENVIRONMENT", "development"),
        }

    return app


async def _reset_database(db: AsyncSession):
    """Reset database by deleting all data from tables."""
    from src.config.database import Base

    # Get all tables in reverse order (respects foreign keys)
    tables = reversed(Base.metadata.sorted_tables)

    for table in tables:
        await db.execute(text(f"DELETE FROM {table.name}"))

    await db.commit()


# Create app with lifespan
app = create_e2e_app()


def main():
    """Run the E2E test server."""
    port = int(os.getenv("E2E_PORT", "8001"))
    host = os.getenv("E2E_HOST", "127.0.0.1")

    print(f"""
    ========================================
    E2E Test Server Starting
    ========================================
    Host: {host}
    Port: {port}
    Database: SQLite In-Memory
    Environment: {os.getenv("ENVIRONMENT", "development")}

    Endpoints:
    - POST /test/setup/{{scenario}} - Load test scenario
    - POST /test/reset - Clear all data
    - GET /test/health - Health check
    - All regular API endpoints under /api/v1/

    Available scenarios:
    - cotraining: Trainer + Student + Plan + Assignment
    - plan_assignment: Trainer + 3 Students + Plan

    Press Ctrl+C to stop.
    ========================================
    """)

    uvicorn.run(
        "tests.e2e.server:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
