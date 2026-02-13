"""Real-time functionality for co-training sessions.

This module provides Server-Sent Events (SSE) for real-time updates during
workout sessions, enabling trainers and students to share the same session.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.workouts.models import (
    SessionMessage,
    SessionStatus,
    TrainerAdjustment,
    WorkoutSession,
    WorkoutSessionSet,
)


class SessionEventType:
    """Event types for session updates."""

    # Session lifecycle
    SESSION_STARTED = "session_started"
    SESSION_PAUSED = "session_paused"
    SESSION_RESUMED = "session_resumed"
    SESSION_COMPLETED = "session_completed"

    # Trainer events
    TRAINER_JOINED = "trainer_joined"
    TRAINER_LEFT = "trainer_left"
    TRAINER_ADJUSTMENT = "trainer_adjustment"

    # Co-training request events
    COTRAINING_REQUESTED = "cotraining_requested"
    COTRAINING_CANCELLED = "cotraining_cancelled"

    # Exercise events
    SET_COMPLETED = "set_completed"
    EXERCISE_CHANGED = "exercise_changed"

    # Communication
    MESSAGE_SENT = "message_sent"
    MESSAGE_READ = "message_read"

    # Sync events
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"


class SessionEvent:
    """Represents a session event for real-time updates."""

    def __init__(
        self,
        event_type: str,
        session_id: uuid.UUID,
        data: dict[str, Any],
        sender_id: uuid.UUID | None = None,
    ):
        self.event_type = event_type
        self.session_id = session_id
        self.data = data
        self.sender_id = sender_id
        self.timestamp = datetime.now(timezone.utc)

    def to_sse(self) -> str:
        """Convert to Server-Sent Event format."""
        payload = {
            "event_type": self.event_type,
            "session_id": str(self.session_id),
            "data": self.data,
            "sender_id": str(self.sender_id) if self.sender_id else None,
            "timestamp": self.timestamp.isoformat(),
        }
        return f"data: {json.dumps(payload)}\n\n"


class SessionManager:
    """Manages active sessions and their subscribers."""

    def __init__(self):
        # Map of session_id -> list of subscriber queues
        self._subscribers: dict[uuid.UUID, list[asyncio.Queue]] = {}
        # Map of session_id -> last known state
        self._session_states: dict[uuid.UUID, dict] = {}

    async def subscribe(self, session_id: uuid.UUID) -> asyncio.Queue:
        """Subscribe to session updates."""
        if session_id not in self._subscribers:
            self._subscribers[session_id] = []

        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[session_id].append(queue)
        return queue

    async def unsubscribe(self, session_id: uuid.UUID, queue: asyncio.Queue) -> None:
        """Unsubscribe from session updates."""
        if session_id in self._subscribers:
            try:
                self._subscribers[session_id].remove(queue)
                if not self._subscribers[session_id]:
                    del self._subscribers[session_id]
            except ValueError:
                pass

    async def broadcast(self, event: SessionEvent) -> None:
        """Broadcast event to all session subscribers."""
        session_id = event.session_id
        if session_id in self._subscribers:
            for queue in self._subscribers[session_id]:
                try:
                    await queue.put(event)
                except (asyncio.QueueFull, RuntimeError):
                    pass  # Best-effort broadcast to subscribers

    def update_state(self, session_id: uuid.UUID, state: dict) -> None:
        """Update cached session state."""
        self._session_states[session_id] = state

    def get_state(self, session_id: uuid.UUID) -> dict | None:
        """Get cached session state."""
        return self._session_states.get(session_id)

    def clear_state(self, session_id: uuid.UUID) -> None:
        """Clear session state when session ends."""
        if session_id in self._session_states:
            del self._session_states[session_id]


# Global session manager instance
session_manager = SessionManager()


async def broadcast_session_event(
    session_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
    sender_id: uuid.UUID | None = None,
) -> None:
    """Broadcast an event to all session subscribers.

    Args:
        session_id: The session to broadcast to
        event_type: Type of event (from SessionEventType)
        data: Event payload data
        sender_id: ID of the user who triggered the event
    """
    event = SessionEvent(
        event_type=event_type,
        session_id=session_id,
        data=data,
        sender_id=sender_id,
    )
    await session_manager.broadcast(event)


async def stream_session_events(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AsyncGenerator[str, None]:
    """Stream session events as Server-Sent Events.

    Args:
        session_id: Session to subscribe to
        user_id: User subscribing to events

    Yields:
        SSE formatted strings
    """
    queue = await session_manager.subscribe(session_id)

    try:
        # Send initial sync event
        yield SessionEvent(
            event_type=SessionEventType.SYNC_REQUEST,
            session_id=session_id,
            data={"user_id": str(user_id)},
        ).to_sse()

        # Send cached state if available
        state = session_manager.get_state(session_id)
        if state:
            yield SessionEvent(
                event_type=SessionEventType.SYNC_RESPONSE,
                session_id=session_id,
                data=state,
            ).to_sse()

        # Stream events
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event.to_sse()
            except asyncio.TimeoutError:
                # Send heartbeat to keep connection alive
                yield ": heartbeat\n\n"
    finally:
        await session_manager.unsubscribe(session_id, queue)


async def notify_trainer_joined(
    session_id: uuid.UUID,
    trainer_id: uuid.UUID,
    trainer_name: str,
) -> None:
    """Notify that a trainer has joined the session."""
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.TRAINER_JOINED,
        data={
            "trainer_id": str(trainer_id),
            "trainer_name": trainer_name,
        },
        sender_id=trainer_id,
    )


async def notify_trainer_left(
    session_id: uuid.UUID,
    trainer_id: uuid.UUID,
) -> None:
    """Notify that a trainer has left the session."""
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.TRAINER_LEFT,
        data={"trainer_id": str(trainer_id)},
        sender_id=trainer_id,
    )


async def notify_set_completed(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    exercise_id: uuid.UUID,
    set_number: int,
    reps: int,
    weight_kg: float | None,
) -> None:
    """Notify that a set was completed."""
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.SET_COMPLETED,
        data={
            "exercise_id": str(exercise_id),
            "set_number": set_number,
            "reps": reps,
            "weight_kg": weight_kg,
        },
        sender_id=user_id,
    )


async def notify_trainer_adjustment(
    session_id: uuid.UUID,
    trainer_id: uuid.UUID,
    exercise_id: uuid.UUID,
    set_number: int | None,
    suggested_weight_kg: float | None,
    suggested_reps: int | None,
    note: str | None,
) -> None:
    """Notify that trainer made an adjustment."""
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.TRAINER_ADJUSTMENT,
        data={
            "exercise_id": str(exercise_id),
            "set_number": set_number,
            "suggested_weight_kg": suggested_weight_kg,
            "suggested_reps": suggested_reps,
            "note": note,
        },
        sender_id=trainer_id,
    )


async def notify_message_sent(
    session_id: uuid.UUID,
    sender_id: uuid.UUID,
    sender_name: str,
    message: str,
    message_id: uuid.UUID,
) -> None:
    """Notify that a message was sent."""
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.MESSAGE_SENT,
        data={
            "message_id": str(message_id),
            "sender_name": sender_name,
            "message": message,
        },
        sender_id=sender_id,
    )


async def notify_session_status_change(
    session_id: uuid.UUID,
    status: SessionStatus,
    changed_by: uuid.UUID,
) -> None:
    """Notify session status change."""
    event_type = {
        SessionStatus.ACTIVE: SessionEventType.SESSION_STARTED,
        SessionStatus.PAUSED: SessionEventType.SESSION_PAUSED,
        SessionStatus.COMPLETED: SessionEventType.SESSION_COMPLETED,
    }.get(status, SessionEventType.SESSION_RESUMED)

    await broadcast_session_event(
        session_id=session_id,
        event_type=event_type,
        data={"status": status.value},
        sender_id=changed_by,
    )

    # Clear state when session completes
    if status == SessionStatus.COMPLETED:
        session_manager.clear_state(session_id)


async def get_session_snapshot(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> dict:
    """Get current session state for sync."""
    # Get session
    session = await db.get(WorkoutSession, session_id)
    if not session:
        return {}

    # Get completed sets
    sets_query = select(WorkoutSessionSet).where(
        WorkoutSessionSet.session_id == session_id
    ).order_by(WorkoutSessionSet.performed_at)
    sets_result = await db.execute(sets_query)
    sets = sets_result.scalars().all()

    # Get recent messages
    messages_query = select(SessionMessage).where(
        SessionMessage.session_id == session_id
    ).order_by(SessionMessage.sent_at.desc()).limit(50)
    messages_result = await db.execute(messages_query)
    messages = messages_result.scalars().all()

    # Get trainer adjustments
    adjustments_query = select(TrainerAdjustment).where(
        TrainerAdjustment.session_id == session_id
    ).order_by(TrainerAdjustment.created_at.desc())
    adjustments_result = await db.execute(adjustments_query)
    adjustments = adjustments_result.scalars().all()

    state = {
        "session_id": str(session.id),
        "workout_id": str(session.workout_id),
        "user_id": str(session.user_id),
        "trainer_id": str(session.trainer_id) if session.trainer_id else None,
        "status": session.status.value,
        "is_shared": session.is_shared,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_sets": [
            {
                "id": str(s.id),
                "exercise_id": str(s.exercise_id),
                "set_number": s.set_number,
                "reps_completed": s.reps_completed,
                "weight_kg": s.weight_kg,
                "performed_at": s.performed_at.isoformat(),
            }
            for s in sets
        ],
        "messages": [
            {
                "id": str(m.id),
                "sender_id": str(m.sender_id),
                "message": m.message,
                "sent_at": m.sent_at.isoformat(),
            }
            for m in reversed(list(messages))
        ],
        "adjustments": [
            {
                "id": str(a.id),
                "exercise_id": str(a.exercise_id),
                "set_number": a.set_number,
                "suggested_weight_kg": a.suggested_weight_kg,
                "suggested_reps": a.suggested_reps,
                "note": a.note,
            }
            for a in adjustments
        ],
    }

    # Cache the state
    session_manager.update_state(session_id, state)

    return state


async def notify_cotraining_request(
    session: WorkoutSession,
    student_name: str,
    workout_name: str,
    trainer_id: uuid.UUID,
) -> None:
    """Notify trainer that a student has requested co-training.

    This function should be called when a student creates a shared session
    with is_shared=True and status=WAITING.

    Args:
        session: The workout session that was created
        student_name: Name of the student requesting co-training
        workout_name: Name of the workout
        trainer_id: ID of the trainer to notify
    """
    # Broadcast to the session (in case trainer is already subscribed)
    await broadcast_session_event(
        session_id=session.id,
        event_type=SessionEventType.COTRAINING_REQUESTED,
        data={
            "session_id": str(session.id),
            "workout_id": str(session.workout_id),
            "student_id": str(session.user_id),
            "student_name": student_name,
            "workout_name": workout_name,
            "trainer_id": str(trainer_id),
            "started_at": session.started_at.isoformat() if session.started_at else None,
        },
        sender_id=session.user_id,
    )


async def notify_cotraining_cancelled(
    session_id: uuid.UUID,
    student_id: uuid.UUID,
    trainer_id: uuid.UUID,
    reason: str = "student_cancelled",
) -> None:
    """Notify trainer that a co-training request was cancelled.

    Args:
        session_id: The session ID that was cancelled
        student_id: ID of the student who cancelled
        trainer_id: ID of the trainer to notify
        reason: Reason for cancellation (student_cancelled, timeout, etc.)
    """
    await broadcast_session_event(
        session_id=session_id,
        event_type=SessionEventType.COTRAINING_CANCELLED,
        data={
            "session_id": str(session_id),
            "student_id": str(student_id),
            "trainer_id": str(trainer_id),
            "reason": reason,
        },
        sender_id=student_id,
    )
