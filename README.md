# MyFit API

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](../CHANGELOG.md)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi)](https://fastapi.tiangolo.com)

FastAPI backend for the MyFit white-label fitness platform.

## Requirements

- Python 3.11+
- PostgreSQL 16
- Redis 7

## Setup

### 1. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate  # Windows
```

### 2. Install dependencies

```bash
pip install -e ".[dev]"
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Start database

```bash
docker-compose up -d postgres redis
```

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Seed exercises database

Populate the database with common exercises (required for AI suggestions and exercise catalog):

```bash
PYTHONPATH=. python src/scripts/seed_exercises.py
```

This will add 60+ exercises covering all major muscle groups. The seed is idempotent - it won't duplicate exercises if run multiple times.

### 7. Start server

```bash
uvicorn src.main:app --reload
```

## API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
src/
├── config/           # Configuration (settings, database)
├── core/             # Core utilities (security, middleware)
├── models/           # SQLAlchemy models
├── schemas/          # Pydantic schemas (shared)
├── services/         # Shared services (email, storage, AI)
├── domains/          # Domain modules
│   ├── auth/         # Authentication
│   ├── organizations/# Organization management
│   ├── users/        # User management
│   ├── workouts/     # Workout plans
│   ├── nutrition/    # Diet plans
│   ├── progress/     # Progress tracking
│   ├── chat/         # Real-time chat
│   ├── payments/     # Payment processing
│   └── ...
└── main.py           # Application entry point
```

## Running Tests

```bash
pytest tests/ -v
```

## Code Quality

```bash
# Lint
ruff check src/

# Format
ruff format src/

# Type check
mypy src/
```
