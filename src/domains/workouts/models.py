"""Workout models for the MyFit platform."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class Difficulty(str, enum.Enum):
    """Workout difficulty levels."""

    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class WorkoutGoal(str, enum.Enum):
    """Workout program goals."""

    HYPERTROPHY = "hypertrophy"
    STRENGTH = "strength"
    FAT_LOSS = "fat_loss"
    ENDURANCE = "endurance"
    FUNCTIONAL = "functional"
    GENERAL_FITNESS = "general_fitness"


class SplitType(str, enum.Enum):
    """Training split types."""

    ABC = "abc"
    ABCD = "abcd"
    ABCDE = "abcde"
    PUSH_PULL_LEGS = "push_pull_legs"
    UPPER_LOWER = "upper_lower"
    FULL_BODY = "full_body"
    CUSTOM = "custom"


class MuscleGroup(str, enum.Enum):
    """Major muscle groups."""

    CHEST = "chest"
    BACK = "back"
    SHOULDERS = "shoulders"
    BICEPS = "biceps"
    TRICEPS = "triceps"
    FOREARMS = "forearms"
    ABS = "abs"
    QUADRICEPS = "quadriceps"
    HAMSTRINGS = "hamstrings"
    GLUTES = "glutes"
    CALVES = "calves"
    FULL_BODY = "full_body"
    CARDIO = "cardio"


class TechniqueType(str, enum.Enum):
    """Advanced training technique types."""

    NORMAL = "normal"
    SUPERSET = "superset"
    BISET = "biset"
    TRISET = "triset"
    GIANTSET = "giantset"
    DROPSET = "dropset"
    REST_PAUSE = "rest_pause"
    CLUSTER = "cluster"


class SessionStatus(str, enum.Enum):
    """Workout session status for co-training."""

    WAITING = "waiting"  # Session created, waiting to start
    ACTIVE = "active"  # Session in progress
    PAUSED = "paused"  # Temporarily paused
    COMPLETED = "completed"  # Session finished


class Exercise(Base, UUIDMixin, TimestampMixin):
    """Exercise model representing a single exercise."""

    __tablename__ = "exercises"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    muscle_group: Mapped[MuscleGroup] = mapped_column(
        Enum(MuscleGroup, name="muscle_group_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    secondary_muscles: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    equipment: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Exercise {self.name}>"


class Workout(Base, UUIDMixin, TimestampMixin):
    """Workout model representing a complete workout plan."""

    __tablename__ = "workouts"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty_enum", values_callable=lambda x: [e.value for e in x]),
        default=Difficulty.INTERMEDIATE,
        nullable=False,
    )
    estimated_duration_min: Mapped[int] = mapped_column(
        Integer, default=60, nullable=False
    )
    target_muscles: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # NULL for system templates
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship("User")
    organization: Mapped["Organization | None"] = relationship("Organization")
    exercises: Mapped[list["WorkoutExercise"]] = relationship(
        "WorkoutExercise",
        back_populates="workout",
        order_by="WorkoutExercise.order",
        lazy="selectin",
        passive_deletes=True,  # Let DB handle CASCADE DELETE
    )
    assignments: Mapped[list["WorkoutAssignment"]] = relationship(
        "WorkoutAssignment",
        back_populates="workout",
        lazy="selectin",
        passive_deletes=True,  # Let DB handle CASCADE DELETE
    )

    def __repr__(self) -> str:
        return f"<Workout {self.name}>"


class WorkoutExercise(Base, UUIDMixin):
    """Linking table between workouts and exercises with configuration."""

    __tablename__ = "workout_exercises"

    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
    )
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sets: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    reps: Mapped[str] = mapped_column(
        String(50), default="10-12", nullable=False
    )  # Can be "10-12", "15", "AMRAP", etc.
    rest_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    superset_with: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )  # For supersets (legacy)

    # Advanced technique fields
    execution_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    isometric_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    technique_type: Mapped[TechniqueType] = mapped_column(
        Enum(TechniqueType, name="technique_type_enum", values_callable=lambda x: [e.value for e in x]),
        default=TechniqueType.NORMAL,
        nullable=False,
    )
    exercise_group_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    exercise_group_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    workout: Mapped["Workout"] = relationship(
        "Workout",
        back_populates="exercises",
    )
    exercise: Mapped["Exercise"] = relationship("Exercise", lazy="joined")

    def __repr__(self) -> str:
        return f"<WorkoutExercise workout={self.workout_id} exercise={self.exercise_id}>"


class WorkoutAssignment(Base, UUIDMixin, TimestampMixin):
    """Assignment of a workout to a student by a trainer."""

    __tablename__ = "workout_assignments"

    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    workout: Mapped["Workout"] = relationship(
        "Workout",
        back_populates="assignments",
    )
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    trainer: Mapped["User"] = relationship("User", foreign_keys=[trainer_id])
    sessions: Mapped[list["WorkoutSession"]] = relationship(
        "WorkoutSession",
        back_populates="assignment",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<WorkoutAssignment workout={self.workout_id} student={self.student_id}>"


class WorkoutSession(Base, UUIDMixin):
    """A single training session performed by a user."""

    __tablename__ = "workout_sessions"

    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_assignments.id", ondelete="SET NULL"),
        nullable=True,
    )
    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Co-training fields
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum", values_callable=lambda x: [e.value for e in x]),
        default=SessionStatus.WAITING,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    student_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    trainer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    assignment: Mapped["WorkoutAssignment | None"] = relationship(
        "WorkoutAssignment",
        back_populates="sessions",
    )
    workout: Mapped["Workout"] = relationship("Workout")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    trainer: Mapped["User | None"] = relationship("User", foreign_keys=[trainer_id])
    sets: Mapped[list["WorkoutSessionSet"]] = relationship(
        "WorkoutSessionSet",
        back_populates="session",
        lazy="selectin",
    )
    messages: Mapped[list["SessionMessage"]] = relationship(
        "SessionMessage",
        back_populates="session",
        lazy="selectin",
        order_by="SessionMessage.sent_at",
    )

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @property
    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    def __repr__(self) -> str:
        return f"<WorkoutSession id={self.id} workout={self.workout_id} status={self.status.value}>"


class WorkoutSessionSet(Base, UUIDMixin):
    """Individual set performed during a workout session."""

    __tablename__ = "workout_session_sets"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_completed: Mapped[int] = mapped_column(Integer, nullable=False)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # For timed exercises
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["WorkoutSession"] = relationship(
        "WorkoutSession",
        back_populates="sets",
    )
    exercise: Mapped["Exercise"] = relationship("Exercise")

    def __repr__(self) -> str:
        return f"<WorkoutSessionSet session={self.session_id} set={self.set_number}>"


class SessionMessage(Base, UUIDMixin):
    """Quick messages exchanged during a shared workout session (co-training)."""

    __tablename__ = "session_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    session: Mapped["WorkoutSession"] = relationship(
        "WorkoutSession",
        back_populates="messages",
    )
    sender: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        return f"<SessionMessage session={self.session_id} sender={self.sender_id}>"


class TrainerAdjustment(Base, UUIDMixin):
    """Trainer adjustments made during a co-training session."""

    __tablename__ = "trainer_adjustments"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("exercises.id", ondelete="CASCADE"),
        nullable=False,
    )
    set_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggested_reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    session: Mapped["WorkoutSession"] = relationship("WorkoutSession")
    trainer: Mapped["User"] = relationship("User")
    exercise: Mapped["Exercise"] = relationship("Exercise")

    def __repr__(self) -> str:
        return f"<TrainerAdjustment session={self.session_id} exercise={self.exercise_id}>"


class WorkoutProgram(Base, UUIDMixin, TimestampMixin):
    """Workout Program - a structured collection of workouts (e.g., ABC split)."""

    __tablename__ = "workout_programs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[WorkoutGoal] = mapped_column(
        Enum(WorkoutGoal, name="workout_goal_enum", values_callable=lambda x: [e.value for e in x]),
        default=WorkoutGoal.HYPERTROPHY,
        nullable=False,
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        Enum(Difficulty, name="difficulty_enum", values_callable=lambda x: [e.value for e in x]),
        default=Difficulty.INTERMEDIATE,
        nullable=False,
    )
    split_type: Mapped[SplitType] = mapped_column(
        Enum(SplitType, name="split_type_enum", values_callable=lambda x: [e.value for e in x]),
        default=SplitType.ABC,
        nullable=False,
    )
    duration_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Diet configuration
    include_diet: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    diet_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    daily_calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    carbs_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fat_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meals_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    diet_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # NULL for system templates
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Track the original template when program is imported from catalog
    source_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship("User")
    organization: Mapped["Organization | None"] = relationship("Organization")
    program_workouts: Mapped[list["ProgramWorkout"]] = relationship(
        "ProgramWorkout",
        back_populates="program",
        order_by="ProgramWorkout.order",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<WorkoutProgram {self.name}>"


class ProgramWorkout(Base, UUIDMixin):
    """Linking table between programs and workouts with order and metadata."""

    __tablename__ = "program_workouts"

    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    workout_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workouts.id", ondelete="CASCADE"),
        nullable=False,
    )
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    label: Mapped[str] = mapped_column(
        String(50), default="A", nullable=False
    )  # "A", "B", "C", "Push", "Pull", etc.
    day_of_week: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # 0=Monday, 6=Sunday (optional)

    # Relationships
    program: Mapped["WorkoutProgram"] = relationship(
        "WorkoutProgram",
        back_populates="program_workouts",
    )
    workout: Mapped["Workout"] = relationship("Workout", lazy="joined")

    def __repr__(self) -> str:
        return f"<ProgramWorkout program={self.program_id} workout={self.workout_id} label={self.label}>"


class ProgramAssignment(Base, UUIDMixin, TimestampMixin):
    """Assignment of a workout program to a student by a trainer."""

    __tablename__ = "program_assignments"

    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workout_programs.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    trainer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    program: Mapped["WorkoutProgram"] = relationship("WorkoutProgram")
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    trainer: Mapped["User"] = relationship("User", foreign_keys=[trainer_id])

    def __repr__(self) -> str:
        return f"<ProgramAssignment program={self.program_id} student={self.student_id}>"


# Import for type hints
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
