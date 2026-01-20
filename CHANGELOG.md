# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-20

### Added
- **Chat Domain** - Real-time messaging system
  - `Conversation`, `ConversationParticipant`, `Message` models
  - `GET /chat/conversations` - List user conversations
  - `GET /chat/conversations/{id}/messages` - Get conversation messages
  - `POST /chat/conversations/{id}/messages` - Send message
  - `POST /chat/conversations` - Create/get direct conversation
  - `POST /chat/conversations/{id}/read` - Mark messages as read

- **Notifications Domain** - User notification system
  - `Notification` model with 25+ notification types
  - `GET /notifications` - List user notifications
  - `GET /notifications/unread-count` - Get unread count
  - `POST /notifications/{id}/read` - Mark as read
  - `POST /notifications/read-all` - Mark all as read
  - `DELETE /notifications/{id}` - Delete notification

- **Billing Domain** - Payment management for trainers
  - `Payment`, `PaymentPlan` models
  - `GET /billing/payments` - List payments (as payer or payee)
  - `GET /billing/payments/{id}` - Get payment details
  - `POST /billing/payments` - Create payment
  - `POST /billing/payments/{id}/mark-paid` - Mark as paid
  - `POST /billing/payments/{id}/reminder` - Send payment reminder
  - `GET /billing/summary` - Get billing summary
  - `GET /billing/revenue/current-month` - Monthly revenue for trainers
  - `GET /billing/revenue/month/{year}/{month}` - Specific month revenue
  - `GET /billing/revenue/history` - Revenue history (12 months)
  - `GET /billing/plans` - List payment plans
  - `POST /billing/plans` - Create payment plan

- **Email Service** - Resend integration
  - Welcome email for new users
  - Organization invite email
  - Workout reminder email
  - Payment reminder email

- **Rate Limiting** - Redis-based rate limiting
  - 50 workout assignments per hour per trainer
  - 20 plan assignments per hour per trainer

- **Student Trainer Notes Endpoint**
  - `GET /users/me/trainer-notes` - Students can read notes written about them

### Security Fixes
- **VULN-1**: Trainer can now GET sessions they joined (was blocked before)
- **VULN-2**: Prescription notes now validate user has access to context (plan/workout/session)
- **VULN-3**: Workout assignments now validate trainer and student share organization
- **VULN-4**: `organization_id` is now required for listing active sessions
- **VULN-5**: Students can now read trainer notes about them
- **VULN-6**: `list_notes_for_student` now properly filters by student_id

### Removed
- Debug/migration endpoints from workouts router (809 lines removed)

### Changed
- User model now includes `birth_date`, `gender`, `height_cm`, `bio` fields
- Streak calculation now uses GamificationService for accuracy

## [0.3.0] - 2026-01-20

### Added
- **Schedule Domain** - Trainer-student appointment management
  - `Appointment` model with status (pending, confirmed, cancelled, completed)
  - `AppointmentType` enum (strength, cardio, functional, hiit, assessment, other)
  - CRUD endpoints for appointments
  - Day view: `GET /schedule/day/{date}`
  - Week view: `GET /schedule/week/{date}`
  - Cancel endpoint: `POST /schedule/appointments/{id}/cancel`
  - Confirm endpoint: `POST /schedule/appointments/{id}/confirm`

- **Student Progress Notes** - Trainer notes system
  - `StudentNote` model for trainer observations about students
  - `POST /trainers/students/{id}/progress/notes` - Add note
  - `GET /trainers/students/{id}/progress/notes` - List notes
  - Notes included in `GET /trainers/students/{id}/progress` response

- **Plan Assignments Filter**
  - `GET /plans/assignments?student_id=X` now supports filtering by specific student

### Changed
- Student progress endpoint now returns recent notes
- Database auto-creates `appointments` and `student_notes` tables on startup

## [0.2.2] - 2026-01-20

### Added
- **LEGS Muscle Group**
  - New `legs` enum value for generic leg exercises
  - `get_leg_groups()` method returns all leg-related muscle groups
  - Filter by `legs` expands to include quadriceps, hamstrings, calves, and legs
  - 10 new generic leg exercises in seed (bodyweight squats, lunges, pistol squat, etc.)

- **Pexels Video Integration**
  - New `add_pexels_videos.py` script to fetch exercise videos from Pexels API
  - Muscle group-specific search terms for better video matching
  - Exercise-specific search overrides for accurate video results
  - Automatic video assignment to exercises without videos

### Changed
- Exercise seed now includes 121 exercises (was 111)
- Updated `.env.example` with `PEXELS_API_KEY` configuration

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
