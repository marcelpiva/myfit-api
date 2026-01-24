# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-01-24

### Added
- **Push Notifications for Workout Updates** - Students receive notifications when trainer edits their workout
  - Triggered on workout update (`PUT /{workout_id}`)
  - Triggered on exercise added (`POST /{workout_id}/exercises`)
  - Triggered on exercise removed (`DELETE /{workout_id}/exercises/{id}`)
  - Notifies all students with active assignments for the workout

- **Push Notification when Student Starts Workout** - Trainer receives notification
  - Message: "[Student name] iniciou o treino '[workout name]'"
  - Includes session_id, student_id, workout_id in data payload
  - Works for both regular and co-training sessions

- **Push Notification when Student Views Plan** - Trainer receives notification
  - Triggered on `POST /plans/assignments/{id}/acknowledge`
  - Message: "[Student name] visualizou o plano '[plan name]'"
  - Helps trainers know when students have seen their assigned plans

### Fixed
- **Organization Context Filtering** - Students with multiple trainers now see only data from selected trainer
  - `GET /plans/assignments` filters by `X-Organization-ID` header
  - `GET /users/me/trainer-notes` filters by `X-Organization-ID` header
  - Backward compatible: includes records with NULL organization_id

## [0.4.9] - 2026-01-24

### Added
- **GlitchTip Observability** - Error tracking and performance monitoring
  - New `src/core/observability.py` module with Sentry SDK integration
  - `init_observability()` - initializes GlitchTip with FastAPI/SQLAlchemy integrations
  - `set_user_context()` / `clear_user_context()` - user context for error reports
  - `capture_exception()` / `capture_message()` - manual error capture
  - Configurable via `GLITCHTIP_DSN`, `GLITCHTIP_TRACES_SAMPLE_RATE`, `GLITCHTIP_PROFILES_SAMPLE_RATE`

### Changed
- Removed "white-label" terminology from project description

## [0.4.8] - 2026-01-23

### Added
- **E2E Test Suite** - Comprehensive end-to-end tests covering user journeys (SAGAs)
  - SAGA 1: Complete onboarding flow (registration → first workout)
  - SAGA 2: Co-training with real-time supervision
  - SAGA 3: Plan evolution and progress tracking
  - SAGA 4-5: Student recovery and plan rejection flows
  - SAGA 6-7: Physical assessments and weekly training
  - SAGA 8-10: Scheduling, multi-client management, and feedback handling
  - Uses SQLite in-memory database for fast, isolated test execution
  - Includes safety checks to prevent running against production

### Fixed
- **DateTime Timezone Handling** - `OrganizationInvite.is_expired` now handles both naive and aware datetimes
  - SQLite doesn't preserve timezone info, causing comparison errors
  - Property now normalizes datetimes to UTC before comparison

## [0.4.7] - 2026-01-23

### Added
- **Full Plan Data in Assignments** - Plan assignment responses now include complete plan object
  - Includes `plan_workouts` with nested workout details
  - Enables proper workout count display in app
  - Loads workout exercises for accurate exercise counts

### Fixed
- **Organization Context Filtering** - Dashboard now includes records with NULL organization_id
  - Backward compatibility for existing plan assignments without organization
  - Uses `X-Organization-ID` header for filtering when provided

- **Student Access to Plans/Workouts** - Students can now access plans and workouts via assignments
  - `GET /plans/{id}` - Checks if user has active plan assignment
  - `GET /workouts/{id}` - Checks if workout is in assigned plan
  - `GET /workouts/{id}/exercises` - Same permission check
  - Allows both PENDING and ACCEPTED assignment status

- **Pending Assignments Visible** - Students can see plans before accepting
  - `list_student_plan_assignments` includes PENDING status
  - Enables viewing plan details to make accept/decline decision

## [0.4.6] - 2026-01-23

### Fixed
- **Migration URL Handling** - Fixed migration scripts to handle `postgresql://` URL format
  - Previously only converted `postgres://` to `postgresql+asyncpg://`
  - Now also converts `postgresql://` for Railway compatibility

## [0.4.5] - 2026-01-23

### Added
- **Multiple Roles per User** - Users can now have multiple roles in same organization
  - `get_membership_by_role()` method for checking specific role membership
  - Example: User can be both TRAINER and STUDENT in same organization

### Fixed
- **Accept Invite Multiple Roles** - Now checks by role instead of any membership
  - Allows accepting invite for different role in same organization
  - Only blocks if user already has that specific role

- **Multiple Memberships Query** - `get_membership()` now handles multiple results
  - Returns highest priority role when user has multiple memberships
  - Priority: GYM_OWNER > GYM_ADMIN > TRAINER/COACH/NUTRITIONIST > STUDENT

- **Co-Training Session Start** - Fixed AttributeError in session creation
  - Changed `current_user.full_name` to `current_user.name`
  - Changed `session.created_at` to `session.started_at`

## [0.4.4] - 2026-01-22

### Fixed
- **Co-Training Session Start** - Fixed AttributeError when student starts workout session
  - Changed from non-existent `OrganizationMembership.trainer_id` to `invited_by_id`
  - Trainers now correctly receive co-training notifications when students start workouts

## [0.4.3] - 2026-01-22

### Added
- **Invite Tracking Improvements**
  - `student_info` JSONB column - stores name, phone, goal, notes from registration
  - `resend_count` column - tracks how many times invite was resent
  - `last_resent_at` column - timestamp of last resend
  - Unique partial index `ix_unique_pending_invite` - prevents duplicate pending invites
  - `cleanup_expired_invites()` method - removes invites older than specified days

### Fixed
- **Inactive Member Reactivation** - Accept invite now reactivates inactive members
  - Previously returned error when member was inactive
  - Now sets `is_active=True` and updates role from invite
- **Race Condition on Duplicate Invites** - IntegrityError handling for concurrent requests
  - Returns user-friendly message when duplicate invite attempted

### Changed
- **Resend Invite** - Now tracks resend_count and last_resent_at
- **Create Invite** - Accepts student_info parameter for metadata storage

## [0.4.2] - 2026-01-21

### Changed
- **Student Registration Flow** - Now uses invite system instead of direct membership
  - `POST /trainers/students/register` creates `OrganizationInvite` instead of direct membership
  - Students must accept invite to join trainer's organization
  - Prevents duplicate user creation when student registers separately
  - Sends invite email via Resend

### Added
- **Trainer Pending Invites Endpoint**
  - `GET /trainers/students/pending-invites` - List pending student invites for trainer

### Fixed
- **Case-Insensitive Email Matching** - Pending invites query now lowercases email for comparison

## [0.4.1] - 2026-01-21

### Added
- **Student Status Management** - New student status workflow
  - `status` field on OrganizationMembership (pending, active, inactive, blocked)
  - `PUT /organizations/{org_id}/members/{user_id}/status` - Update member status
  - Students must accept invitation before accessing organization features

- **Plan Assignment Acceptance** - Student must accept plan assignments
  - `status` field on PlanAssignment (pending, accepted, declined)
  - `POST /workouts/plans/assignments/{id}/accept` - Accept assignment
  - `POST /workouts/plans/assignments/{id}/decline` - Decline assignment

- **Clear Duration for Continuous Plans**
  - `clear_duration_weeks` parameter in PlanUpdate schema
  - Allows setting duration to null (continuous plan) via explicit flag

### Fixed
- **Route Ordering** - Fixed 422 error on `/plans/assignments` endpoint
  - Moved assignment routes before dynamic `{plan_id}` route in FastAPI
- **Duplicate Plan Validation** - Returns 409 Conflict when same plan already assigned to student

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
