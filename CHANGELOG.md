# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2026-01-19

### Added
- **Structured Technique Parameters**
  - New database columns: `drop_count`, `rest_between_drops`, `pause_duration`, `mini_set_count`
  - Dropset: stores number of drops (2-5) and rest between drops (0-30s)
  - Rest-Pause: stores pause duration (5-60s)
  - Cluster: stores mini-set count (2-10) and pause duration
  - Migration script: `python -m src.migrations.add_technique_params`

### Changed
- `WorkoutExerciseInput` and `WorkoutExerciseResponse` schemas include technique parameters
- `add_exercise_to_workout` service method accepts structured technique parameters
- Workout copy function preserves technique parameters

## [0.2.0] - 2026-01-19

### Added
- **Exercise Time Estimation**
  - New `estimated_seconds` computed property on `WorkoutExercise` model
  - Technique-aware calculation (Drop Set: 90s, Rest-Pause: 60s, etc.)
  - Considers sets, rest periods, and isometric holds

- **AI Exercise Ordering**
  - Compound exercises sorted first, isolation exercises last
  - Preserves exercise group integrity (bi-set, tri-set, etc.)
  - Keyword-based classification for Portuguese and English exercise names

- **AI Suggestion Improvements**
  - `allowed_techniques` parameter strictly enforced
  - Both AI-powered and rule-based fallback respect technique restrictions

### Changed
- `WorkoutExerciseResponse` schema now includes `estimated_seconds` field

## [0.1.0] - 2026-01-01

### Added
- Initial release
- User authentication with JWT
- Organization and membership management
- Workout and exercise CRUD operations
- AI-powered exercise suggestions via OpenAI
- Training plan management
- PostgreSQL database with Alembic migrations
