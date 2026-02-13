# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-02-13

### Added
- **Subscription PIX Checkout** - PIX payment flow for Pro upgrades
  - `POST /subscriptions/upgrade` now returns `SubscriptionCheckoutResponse` with PIX data when `payment_provider=pix`
  - Subscription created with `PENDING` status until payment confirmed
  - `GET /subscriptions/{id}/status` endpoint for payment status polling
  - PIX placeholder BRCODE generation (gateway integration TBD)
  - `PENDING` added to `SubscriptionStatus` enum
- **Consultancy PIX Checkout** - PIX payment flow for consultancy purchases
  - `POST /consultancy/purchase` now returns `ConsultancyCheckoutResponse` with PIX data
  - `GET /consultancy/transactions/{id}/status` endpoint for payment status polling
  - PIX placeholder BRCODE generation matching marketplace pattern

### Changed
- `SubscriptionCheckoutResponse` schema added with `pix_qr_code`, `pix_copy_paste`, `subscription_id`, `amount_cents`, `price_display`
- `ConsultancyCheckoutResponse` schema extends `ConsultancyTransactionResponse` with PIX fields
- `_sync_enum_values()` now includes `subscription_status_enum` with `pending` value

---

## [0.8.0] - 2026-02-11

### Added
- **Self-Service Booking API** - Students can book sessions directly with their trainer
  - `GET /schedule/available-slots` - Returns available time slots for a trainer on a given date
  - `POST /schedule/book` - Student books a session (validates availability, decrements package sessions)
  - Slot calculation: generates slots from trainer settings, subtracts blocked slots and existing appointments
  - Conflict detection returns 409 if slot is already taken
  - Push notification (`SESSION_BOOKED_BY_STUDENT`) sent to trainer on booking
- **Trainer Availability Management** - Full CRUD for trainer schedule configuration
  - `GET /schedule/trainer-availability` - Returns trainer's blocked slots and settings
  - `POST /schedule/trainer-availability/block` - Create blocked time slot (recurring or specific date)
  - `DELETE /schedule/trainer-availability/block/{id}` - Remove blocked slot
  - `PUT /schedule/trainer-availability/settings` - Update default hours, session duration, slot interval
- **Attendance Tracking** - Trainer marks session attendance
  - `PATCH /schedule/appointments/{id}/attendance` - Mark attended/missed/late_cancelled
  - Optional makeup session creation for missed appointments
  - Push notification (`ATTENDANCE_MARKED`) sent to student
- **New Models** - `TrainerBlockedSlot` and `TrainerSettings` database tables
- **New Notification Types** - `SESSION_BOOKED_BY_STUDENT`, `ATTENDANCE_MARKED`

---

## [0.7.2] - 2026-02-05

### Added
- **Session Auto-Expiration** - Automatically complete stale workout sessions
  - New `auto_expire_sessions()` method in `WorkoutService`
  - Sessions in WAITING/ACTIVE/PAUSED status for > 4 hours are auto-completed
  - Prevents duplicate students appearing in trainer dashboard
  - New `auto_expire_old_sessions` Celery task runs hourly at :30

### Fixed
- **`users.user_type` Column Error** - Removed stale migration reference
  - Removed `user_type` from `database.py` migrations list
  - Fixes Celery task errors "column users.user_type does not exist"
  - The `remove_user_type` migration already handles cleanup

### Changed
- **Active Sessions Deduplication** - Show only most recent session per student
  - Fixed trainer seeing 8x same student in "Alunos Agora" list

---

## [0.7.1] - 2026-02-05

### Added
- **GPS Proximity Verification on Accept** - `POST /checkins/{id}/accept` validates distance
  - Accepts optional `latitude`/`longitude` in request body (`CheckInAcceptRequest`)
  - For in-person check-ins: calculates distance between student and trainer (max 200m)
  - Uses existing `calculate_distance()` (Haversine) and `get_trainer_location()`
  - Graceful fallback: if trainer location unavailable, allows accept without GPS check
  - Returns error with actual distance when student is too far
- **Unilateral Check-in** - Trainer registers check-in without student acceptance
  - New `unilateral: bool` field in `ManualCheckinForStudentRequest`
  - When `unilateral=True`: creates CONFIRMED check-in directly, no expiration, skips push notification
  - Auto-activates trainer session immediately
- **Student Retroactive Confirmation** - `POST /checkins/{id}/student-confirm`
  - Student confirms presence after unilateral check-in (optional)
  - Sets `accepted_at` on the check-in record
  - Validates student is the check-in's user and status is CONFIRMED

---

## [0.7.0] - 2026-02-05

### Added
- **Trainer-Initiated Student Checkout** - `POST /checkins/{id}/checkout` endpoint
  - Trainer can end a specific student's check-in by ID
  - Permission check: only trainer (initiated_by/approved_by) or student can checkout
  - Push notification sent to student on checkout
- **Auto-Activate Trainer Session on Accept** - When student accepts check-in, trainer's `TrainerLocation` is auto-activated with `session_started_at = checked_in_at` for timer sync
- **Auto-Deactivate Trainer Session** - When last student checks out, trainer session auto-ends (`session_active = False`)

### Fixed
- **UTC Timezone in Session Data** - All datetime fields in `get_active_session()` now include UTC timezone info via `_to_utc_iso()` helper
  - Prevents Dart from interpreting naive timestamps as local time (caused negative timer values in UTC-3)
- **Naive vs Aware Datetime Comparison** - Fixed `TypeError` in `get_pending_acceptance_for_user()` and accept/reject expiration checks
  - Added `.replace(tzinfo=timezone.utc)` for naive TIMESTAMP values before comparison with aware datetimes

---

## [0.6.9] - 2026-02-04

### Added
- **Training Sessions** - Start/end/active training sessions with 20-minute auto-expiration
  - Trainer-initiated sessions with student acceptance flow
  - `pending_acceptance` status for check-in requests
- **Push Notifications for Sessions** - Notifications on checkout and end_training_session events
- **Code-Based Check-in** - Re-enabled code-based check-in endpoint for QR/manual code entry
- **Training Mode** - Added `training_mode` field to check-in for trainer-only initiation

### Fixed
- **Trainer Role Validation** - Fixed trainer role check to validate in own org, not gym's org for manual-for-student check-in
- **Proximity Radius** - Increased trainer proximity radius from 200m to 500m
- **UTC Validation** - Fixed UTC consistency in `CheckInCode.is_valid` validation
- **Multi-Membership Check-in** - Handle multiple memberships correctly in manual check-in for student
- **Gym Fallback** - Auto-create gym fallback + translate check-in errors to Portuguese

---

## [0.6.8] - 2026-01-28

### Fixed
- **Workout Organization Isolation** - Critical security fixes for multi-organization access
  - `create_workout` now uses `X-Organization-ID` header as fallback when `organization_id` not in request body
  - Ensures workouts are created in the correct organization context when header is set

- **Workout Access Control** - Fixed unauthorized cross-organization workout access
  - `get_workout` and `get_workout_exercises` now verify organization membership
  - Previously allowed access to any workout if `organization_id` was set (security vulnerability)
  - Users can now only access workouts they created, public workouts, or workouts in organizations they belong to

### Added
- **Workout Isolation Tests** - 13 integration tests covering organization isolation
  - Solo student sees only their own workouts
  - Student with trainer sees only assigned plans
  - Multiple trainers context switching
  - Trainer workout isolation
  - Cross-organization access control

## [0.6.7] - 2026-01-28

### Fixed
- **307 Redirect Losing Authorization Header** - Critical fix for API authentication
  - Added `redirect_slashes=False` to FastAPI app initialization
  - Prevents automatic 307 redirects that strip the Authorization header
  - Fixes authentication failures when client requests URLs without trailing slash

- **404 Error on Root Endpoints** - Fixed endpoints returning 404 after redirect_slashes fix
  - Changed `"/"` to `""` for root endpoints in checkin router
  - Changed `"/"` to `""` for root endpoints in workouts router
  - Changed `"/"` to `""` for root endpoints in organizations router
  - Autonomous student "Meus Treinos" screen now works correctly

## [0.6.6] - 2026-01-27

### Added
- **Autonomous Organization Support** - Users can now create personal training profiles
  - New endpoint `POST /organizations/autonomous` for self-training mode
  - User becomes both owner and student of their own organization
  - Enables independent workout management without a trainer

- **Organization Reactivation** - Archived organizations can be restored
  - New endpoint `POST /organizations/{org_id}/reactivate`
  - Sends push notifications to all members when organization is reactivated
  - Owner-only operation

### Fixed
- **Former Student Reinvite Flow** - Fixed critical bug in student reactivation
  - `INACTIVE_MEMBER` error now includes `user_id` for proper reinvite flow
  - Students must now accept reinvite before membership is reactivated
  - Previously, membership was reactivated immediately bypassing invite system
  - Updated error message to indicate invite will be sent

- **Student Endpoints 404 Error** - Fixed endpoints accepting both membership_id and user_id
  - Added `_find_student_member` helper that searches by membership_id first, then user_id
  - Affects: `/students/{id}`, `/students/{id}/stats`, `/students/{id}/workouts`, `/students/{id}/progress`, `/students/{id}/progress/notes`
  - Provides flexibility for clients that may have either ID available

## [0.6.5] - 2026-01-27

### Added
- **Membership in Organization Creation Response** - Organization creation now returns membership data
  - Enables proper client-side context setup immediately after organization creation

### Changed
- **Self-Invite Allowed** - Trainers can now invite themselves as students
  - Enables trainers to follow their own training plans
  - Previously blocked with "Cannot invite yourself" error

### Fixed
- **Portuguese Role Translations** - Fixed role names in error messages
  - `student` → `aluno`
  - `trainer` → `personal trainer`
  - Improved localization for Portuguese-speaking users

## [0.6.4] - 2026-01-26

### Added
- **Onboarding Profile Fields** - New fields for storing onboarding data
  - Trainer fields: `specialties` (JSON), `years_of_experience`
  - Student fields: `fitness_goal`, `fitness_goal_other`, `experience_level`, `weight_kg`, `age`, `weekly_frequency`, `injuries` (JSON), `injuries_other`
  - Tracking flag: `onboarding_completed`
  - Migration: `add_onboarding_fields.py`

- **Profile Endpoint Updates** - GET/PUT `/users/profile` now handle onboarding data
  - `UserProfileResponse` includes all onboarding fields
  - `UserProfileUpdate` accepts all onboarding fields
  - JSON fields (specialties, injuries) automatically serialized/deserialized

### Changed
- `UserService.update_profile()` handles all new onboarding fields
- Added `_user_to_response()` helper for JSON field parsing in router

## [0.6.3] - 2026-01-26

### Fixed
- **Celery Tasks Not Executing** - Tasks were being scheduled but never consumed
  - Removed custom queue routing (`reminders`, `notifications`, `maintenance`)
  - All tasks now use the default queue
  - Worker was only listening to `default` queue, causing tasks to pile up

## [0.6.2] - 2026-01-25

### Fixed
- **Stretching Exercises** - Added missing stretching exercises to database seed
  - Added `stretching` value to PostgreSQL `muscle_group_enum`
  - Seeded 18 stretching/flexibility exercises

## [0.6.1] - 2026-01-25

### Added
- **Smart Workout Reminders** - Intelligent reminder system with personalization
  - Varied reminder messages for better engagement
  - Time-based reminder selection (preferred hour, gentle nudges, evening streak protection)
  - Personalized messages based on days since last workout
  - Three message categories: regular, streak protection, and comeback messages

### Fixed
- **Invite Reminders Task** - Fixed query using non-existent `InviteStatus.PENDING`
  - Changed to use `accepted_at IS NULL` for pending invites
  - Added email reminders at 3-day and 14-day marks
  - Added expiration notifications to trainers when invites expire
  - Improved logging with expired invite count

### Changed
- Added `send_invite_reminder_email()` function for automated invite reminders
- Enhanced `send_workout_reminders` task with streak protection logic

## [0.6.0] - 2026-01-25

### Added
- **Celery Scheduler for Automated Notifications** - Background task processing with Redis
  - Workout reminders (hourly 6am-10pm) for users with active plans who haven't trained
  - Inactive student notifications (daily) alerts trainers when students miss training
  - Invite reminders (3, 7, 14 days) for pending organization invites
  - Plan expiration warnings (7, 3, 1 day) before plan end dates
  - Weekly cleanup of old notifications (90+ days)
  - Configurable via `docker-compose.yml` with celery-worker and celery-beat services
  - Railway deployment support via Procfile worker process

- **Plan Version History** - Track changes to prescribed plans over time
  - `PlanVersion` model stores snapshots when plans are modified
  - `GET /plans/assignments/{id}/versions` - List all versions
  - `GET /plans/assignments/{id}/versions/{version}` - Get specific version
  - `PUT /plans/assignments/{id}/versions/{version}` - Update version description
  - `POST /plans/assignments/{id}/versions/mark-viewed` - Mark version as viewed
  - Automatic version creation on plan updates
  - `PLAN_UPDATED` notification type for students

- **S3/R2 Media Upload** - Cloud storage for avatars and exercise media
  - `StorageService` supporting AWS S3, Cloudflare R2, and local filesystem
  - Avatar upload endpoint with automatic resizing
  - Exercise media upload endpoint with validation
  - Presigned URL generation for direct uploads
  - Configurable via `STORAGE_PROVIDER`, `S3_*`, `CDN_BASE_URL` settings

- **Plan Assignment Response** - Students can accept or decline plan assignments
  - `PUT /plans/assignments/{id}/respond` endpoint
  - `requires_acceptance` field on assignments
  - `declined_reason` field for rejection feedback
  - Notifications to trainer on accept/decline

### Changed
- Updated `requirements.txt` with `celery[redis]`, `aioboto3`, `aiofiles`
- Added `REDIS_URL` configuration for Celery broker

## [0.5.3] - 2026-01-25

### Added
- **Auto-seed exercises on startup** - Exercises automatically populated if database is empty
  - On startup, checks if exercises table has data
  - If empty, seeds 100+ exercises automatically
  - Ensures production database always has exercises available
  - Prevents "no exercises" issues in production

## [0.5.2] - 2026-01-25

### Fixed
- **APNs Payload** - Fixed iOS push notifications not arriving
  - Added explicit `ApsAlert` with title/body in APNs payload
  - Notifications now display correctly on iOS devices

- **Test Push Endpoint** - Test notifications now also create in-app notification
  - `POST /notifications/debug/test-push` creates notification in database
  - Test notifications appear in the notifications screen (bell icon)

### Added
- **Enhanced Push Logging** - Better debugging for push notification issues
  - Logs Firebase message ID for delivery tracking
  - Logs token and platform details

## [0.5.1] - 2026-01-24

### Added
- **Version in Health Endpoint** - `/health` now returns version and environment info
  - `version`: Current API version (e.g., "0.5.1")
  - `environment`: Current environment (development, staging, production)

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

- **Push Notification Debug Endpoints** - Endpoints for troubleshooting push notifications
  - `GET /notifications/debug/push-status` - Check Firebase config and device tokens
  - `POST /notifications/debug/test-push` - Send test notification to current user

### Fixed
- **Organization Context Filtering** - Students with multiple trainers now see only data from selected trainer
  - `GET /plans/assignments` filters by `X-Organization-ID` header
  - `GET /users/me/trainer-notes` filters by `X-Organization-ID` header
  - Backward compatible: includes records with NULL organization_id

### Changed
- **Environment Documentation** - Added Firebase credentials to `.env.example`
  - `FIREBASE_CREDENTIALS_PATH` or `FIREBASE_CREDENTIALS_JSON` for FCM

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
