"""Session-related service operations (sessions, co-training, auto-expiration)."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.domains.workouts.models import (
    SessionMessage,
    SessionStatus,
    TrainerAdjustment,
    Workout,
    WorkoutExercise,
    WorkoutSession,
    WorkoutSessionSet,
)
from src.domains.workouts.schemas import ActiveSessionResponse


class SessionServiceMixin:
    """Mixin providing session-related operations for WorkoutService."""

    db: AsyncSession

    # Session operations

    async def get_session_by_id(
        self,
        session_id: uuid.UUID,
    ) -> WorkoutSession | None:
        """Get a session by ID."""
        result = await self.db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.id == session_id)
            .options(
                selectinload(WorkoutSession.sets),
                selectinload(WorkoutSession.workout),
            )
        )
        return result.scalar_one_or_none()

    async def list_user_sessions(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WorkoutSession]:
        """List sessions for a user."""
        result = await self.db.execute(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == user_id)
            .options(selectinload(WorkoutSession.workout))
            .order_by(WorkoutSession.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def start_session(
        self,
        user_id: uuid.UUID,
        workout_id: uuid.UUID,
        assignment_id: uuid.UUID | None = None,
        is_shared: bool = False,
    ) -> WorkoutSession:
        """Start a new workout session.

        Args:
            user_id: The ID of the user starting the session.
            workout_id: The ID of the workout.
            assignment_id: Optional assignment ID.
            is_shared: If True, creates a co-training session in 'waiting' status.
        """
        session = WorkoutSession(
            workout_id=workout_id,
            user_id=user_id,
            assignment_id=assignment_id,
            is_shared=is_shared,
            status=SessionStatus.WAITING if is_shared else SessionStatus.ACTIVE,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def complete_session(
        self,
        session: WorkoutSession,
        notes: str | None = None,
        rating: int | None = None,
    ) -> WorkoutSession:
        """Complete a workout session."""
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        if session.started_at:
            # Normalize datetimes for SQLite compatibility (naive datetime)
            completed = session.completed_at.replace(tzinfo=None)
            started = session.started_at.replace(tzinfo=None) if session.started_at.tzinfo else session.started_at
            delta = completed - started
            session.duration_minutes = int(delta.total_seconds() / 60)
        if notes is not None:
            session.notes = notes
        if rating is not None:
            session.rating = rating

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def add_session_set(
        self,
        session_id: uuid.UUID,
        exercise_id: uuid.UUID,
        set_number: int,
        reps_completed: int,
        weight_kg: float | None = None,
        duration_seconds: int | None = None,
        notes: str | None = None,
    ) -> WorkoutSessionSet:
        """Record a set during a session."""
        session_set = WorkoutSessionSet(
            session_id=session_id,
            exercise_id=exercise_id,
            set_number=set_number,
            reps_completed=reps_completed,
            weight_kg=weight_kg,
            duration_seconds=duration_seconds,
            notes=notes,
        )
        self.db.add(session_set)
        await self.db.commit()
        await self.db.refresh(session_set)
        return session_set

    # Co-Training operations

    async def trainer_join_session(
        self,
        session: WorkoutSession,
        trainer_id: uuid.UUID,
    ) -> WorkoutSession:
        """Trainer joins a session for co-training."""
        session.trainer_id = trainer_id
        session.is_shared = True
        if session.status == SessionStatus.WAITING:
            session.status = SessionStatus.ACTIVE

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def trainer_leave_session(
        self,
        session: WorkoutSession,
    ) -> WorkoutSession:
        """Trainer leaves a co-training session."""
        session.trainer_id = None
        session.is_shared = False

        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def update_session_status(
        self,
        session: WorkoutSession,
        status: SessionStatus,
    ) -> WorkoutSession:
        """Update session status."""
        logger = logging.getLogger(__name__)
        logger.info(f"[SESSION] Updating session {session.id} from {session.status} to {status}")

        session.status = status

        if status == SessionStatus.PAUSED:
            session.paused_at = datetime.now(timezone.utc)
        elif status == SessionStatus.ACTIVE:
            session.paused_at = None  # Clear when resumed
        elif status == SessionStatus.COMPLETED:
            session.paused_at = None
            session.completed_at = datetime.now(timezone.utc)
            if session.started_at:
                delta = session.completed_at - session.started_at
                session.duration_minutes = int(delta.total_seconds() / 60)

        await self.db.commit()
        await self.db.refresh(session)
        logger.info(f"[SESSION] Session {session.id} now status={session.status}, completed_at={session.completed_at}")
        return session

    async def create_trainer_adjustment(
        self,
        session_id: uuid.UUID,
        trainer_id: uuid.UUID,
        exercise_id: uuid.UUID,
        set_number: int | None = None,
        suggested_weight_kg: float | None = None,
        suggested_reps: int | None = None,
        note: str | None = None,
    ) -> TrainerAdjustment:
        """Create a trainer adjustment during co-training."""
        adjustment = TrainerAdjustment(
            session_id=session_id,
            trainer_id=trainer_id,
            exercise_id=exercise_id,
            set_number=set_number,
            suggested_weight_kg=suggested_weight_kg,
            suggested_reps=suggested_reps,
            note=note,
        )
        self.db.add(adjustment)
        await self.db.commit()
        await self.db.refresh(adjustment)
        return adjustment

    async def create_session_message(
        self,
        session_id: uuid.UUID,
        sender_id: uuid.UUID,
        message: str,
    ) -> SessionMessage:
        """Create a message during co-training session."""
        session_message = SessionMessage(
            session_id=session_id,
            sender_id=sender_id,
            message=message,
        )
        self.db.add(session_message)
        await self.db.commit()
        await self.db.refresh(session_message)
        return session_message

    async def list_session_messages(
        self,
        session_id: uuid.UUID,
        limit: int = 50,
    ) -> list[SessionMessage]:
        """List messages from a session."""
        query = (
            select(SessionMessage)
            .where(SessionMessage.session_id == session_id)
            .options(selectinload(SessionMessage.sender))
            .order_by(SessionMessage.sent_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(query)
        messages = list(result.scalars().all())
        return list(reversed(messages))  # Return oldest first

    async def list_active_sessions(
        self,
        trainer_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> list[ActiveSessionResponse]:
        """List active sessions for students (trainer view)."""
        from src.domains.organizations.models import OrganizationMembership, UserRole
        from src.domains.users.models import User
        from src.domains.workouts.models import PlanAssignment

        # Get students assigned to this trainer
        students_query = (
            select(User.id, User.name, User.avatar_url)
            .join(
                PlanAssignment,
                PlanAssignment.student_id == User.id,
            )
            .where(
                and_(
                    PlanAssignment.trainer_id == trainer_id,
                    PlanAssignment.is_active == True,  # noqa: E712
                )
            )
            .distinct()
        )

        if organization_id:
            students_query = students_query.where(
                PlanAssignment.organization_id == organization_id
            )

        students_result = await self.db.execute(students_query)
        student_data = {row[0]: {"name": row[1], "avatar_url": row[2]} for row in students_result.all()}

        if not student_data:
            return []

        # Get active sessions for these students (started within last 90 min, matching auto_expire)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=90)
        sessions_query = (
            select(WorkoutSession)
            .where(
                and_(
                    WorkoutSession.user_id.in_(student_data.keys()),
                    WorkoutSession.status.in_([SessionStatus.WAITING, SessionStatus.ACTIVE, SessionStatus.PAUSED]),
                    WorkoutSession.completed_at.is_(None),
                    WorkoutSession.started_at > cutoff,
                )
            )
            .options(
                selectinload(WorkoutSession.workout).selectinload(Workout.exercises),
                selectinload(WorkoutSession.sets),
            )
            .order_by(WorkoutSession.started_at.desc())
        )

        sessions_result = await self.db.execute(sessions_query)
        sessions = sessions_result.scalars().all()

        logger = logging.getLogger(__name__)
        logger.info(f"[ACTIVE_SESSIONS] Found {len(list(sessions))} raw sessions for trainer {trainer_id}")
        for s in sessions:
            logger.info(f"[ACTIVE_SESSIONS]   - {s.id}: user={s.user_id}, status={s.status}, started={s.started_at}, completed={s.completed_at}")

        # Keep only the most recent session per student (sessions are ordered by started_at desc)
        seen_users: set[uuid.UUID] = set()
        unique_sessions = []
        for s in sessions:
            if s.user_id not in seen_users:
                seen_users.add(s.user_id)
                unique_sessions.append(s)

        return [
            ActiveSessionResponse(
                id=s.id,
                workout_id=s.workout_id,
                workout_name=s.workout.name if s.workout else "",
                user_id=s.user_id,
                student_name=student_data.get(s.user_id, {}).get("name", ""),
                student_avatar=student_data.get(s.user_id, {}).get("avatar_url"),
                trainer_id=s.trainer_id,
                is_shared=s.is_shared,
                status=s.status,
                started_at=s.started_at,
                total_exercises=len(s.workout.exercises) if s.workout else 0,
                completed_sets=len(s.sets) if s.sets else 0,
            )
            for s in unique_sessions
        ]

    # Session Resume

    async def get_user_active_session(
        self,
        user_id: uuid.UUID,
    ) -> WorkoutSession | None:
        """Get the user's most recent active or paused shared session.

        Used to offer session resumption after app restart.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=90)

        result = await self.db.execute(
            select(WorkoutSession)
            .where(
                WorkoutSession.user_id == user_id,
                WorkoutSession.is_shared == True,  # noqa: E712
                WorkoutSession.status.in_([
                    SessionStatus.ACTIVE,
                    SessionStatus.PAUSED,
                ]),
                WorkoutSession.completed_at.is_(None),
                WorkoutSession.started_at > cutoff,
            )
            .order_by(WorkoutSession.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # Session Auto-Expiration

    async def auto_expire_sessions(
        self,
        active_timeout_minutes: int = 90,
        waiting_timeout_minutes: int = 5,
        paused_timeout_minutes: int = 5,
    ) -> int:
        """Auto-expire stale workout sessions.

        WAITING sessions expire after 5 minutes.
        PAUSED sessions expire after 5 minutes (from paused_at).
        ACTIVE sessions expire after 90 minutes (from started_at).

        Returns:
            Number of sessions expired
        """
        now = datetime.now(timezone.utc)
        active_cutoff = now - timedelta(minutes=active_timeout_minutes)
        waiting_cutoff = now - timedelta(minutes=waiting_timeout_minutes)
        paused_cutoff = now - timedelta(minutes=paused_timeout_minutes)

        # Expire WAITING sessions after 5 minutes
        waiting_query = (
            select(WorkoutSession)
            .where(
                WorkoutSession.status == SessionStatus.WAITING,
                WorkoutSession.started_at < waiting_cutoff,
            )
        )
        # Expire ACTIVE sessions after 90 minutes
        active_query = (
            select(WorkoutSession)
            .where(
                WorkoutSession.status == SessionStatus.ACTIVE,
                WorkoutSession.started_at < active_cutoff,
            )
        )
        # Expire PAUSED sessions after 5 minutes from paused_at
        paused_query = (
            select(WorkoutSession)
            .where(
                WorkoutSession.status == SessionStatus.PAUSED,
                or_(
                    # Use paused_at if available
                    and_(
                        WorkoutSession.paused_at.isnot(None),
                        WorkoutSession.paused_at < paused_cutoff,
                    ),
                    # Fallback: paused_at not set, use started_at with active timeout
                    and_(
                        WorkoutSession.paused_at.is_(None),
                        WorkoutSession.started_at < active_cutoff,
                    ),
                ),
            )
        )

        waiting_result = await self.db.execute(waiting_query)
        active_result = await self.db.execute(active_query)
        paused_result = await self.db.execute(paused_query)
        stale_sessions = (
            list(waiting_result.scalars().all())
            + list(active_result.scalars().all())
            + list(paused_result.scalars().all())
        )

        expired_count = 0
        for session in stale_sessions:
            session.status = SessionStatus.COMPLETED
            session.completed_at = now
            session.paused_at = None
            expired_count += 1

        if expired_count > 0:
            await self.db.commit()

        return expired_count

    async def force_expire_all_sessions(self) -> int:
        """Force-expire ALL non-completed sessions. Used for cleanup."""
        now = datetime.now(timezone.utc)

        query = (
            select(WorkoutSession)
            .where(
                WorkoutSession.status.in_([
                    SessionStatus.WAITING,
                    SessionStatus.ACTIVE,
                    SessionStatus.PAUSED,
                ]),
            )
        )
        result = await self.db.execute(query)
        sessions = result.scalars().all()

        count = 0
        for session in sessions:
            session.status = SessionStatus.COMPLETED
            session.completed_at = now
            count += 1

        if count > 0:
            await self.db.commit()

        return count
