"""Nutrition models for the MyFit platform."""
import enum
import uuid
from datetime import date, datetime, time

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
    Time,
    func,
)
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.config.database import Base
from src.core.models import TimestampMixin, UUIDMixin


class FoodCategory(str, enum.Enum):
    """Food categories."""

    PROTEINS = "proteins"
    CARBS = "carbs"
    VEGETABLES = "vegetables"
    FRUITS = "fruits"
    DAIRY = "dairy"
    FATS = "fats"
    BEVERAGES = "beverages"
    SUPPLEMENTS = "supplements"
    SNACKS = "snacks"
    OTHER = "other"


class MealType(str, enum.Enum):
    """Types of meals."""

    BREAKFAST = "breakfast"
    MORNING_SNACK = "morning_snack"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon_snack"
    DINNER = "dinner"
    EVENING_SNACK = "evening_snack"
    PRE_WORKOUT = "pre_workout"
    POST_WORKOUT = "post_workout"


class Food(Base, UUIDMixin, TimestampMixin):
    """Food item with nutritional information."""

    __tablename__ = "foods"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(
        String(100), unique=True, nullable=True, index=True
    )

    # Nutritional info per portion
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein: Mapped[float] = mapped_column(Float, nullable=False)
    carbs: Mapped[float] = mapped_column(Float, nullable=False)
    fat: Mapped[float] = mapped_column(Float, nullable=False)
    fiber: Mapped[float | None] = mapped_column(Float, nullable=True)
    sodium: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugar: Mapped[float | None] = mapped_column(Float, nullable=True)

    portion_size: Mapped[str] = mapped_column(
        String(100), default="100g", nullable=False
    )
    portion_weight_g: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)

    category: Mapped[FoodCategory] = mapped_column(
        Enum(FoodCategory, name="food_category_enum", values_callable=lambda x: [e.value for e in x]),
        default=FoodCategory.OTHER,
        nullable=False,
    )
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User | None"] = relationship("User")

    def __repr__(self) -> str:
        return f"<Food {self.name}>"


class UserFavoriteFood(Base, UUIDMixin):
    """User's favorite foods for quick access."""

    __tablename__ = "user_favorite_foods"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    food_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("foods.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User")
    food: Mapped["Food"] = relationship("Food")


class DietPlan(Base, UUIDMixin, TimestampMixin):
    """Diet plan with nutritional targets."""

    __tablename__ = "diet_plans"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Macro targets
    target_calories: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    target_protein: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    target_carbs: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    target_fat: Mapped[int] = mapped_column(Integer, default=70, nullable=False)

    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    created_by: Mapped["User"] = relationship("User")
    organization: Mapped["Organization | None"] = relationship("Organization")
    meals: Mapped[list["DietPlanMeal"]] = relationship(
        "DietPlanMeal",
        back_populates="plan",
        order_by="DietPlanMeal.order",
        lazy="selectin",
    )
    assignments: Mapped[list["DietAssignment"]] = relationship(
        "DietAssignment",
        back_populates="plan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<DietPlan {self.name}>"


class DietPlanMeal(Base, UUIDMixin):
    """A meal within a diet plan."""

    __tablename__ = "diet_plan_meals"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    meal_time: Mapped[time] = mapped_column(Time, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    plan: Mapped["DietPlan"] = relationship("DietPlan", back_populates="meals")
    foods: Mapped[list["DietPlanMealFood"]] = relationship(
        "DietPlanMealFood",
        back_populates="meal",
        lazy="selectin",
    )

    @property
    def total_calories(self) -> float:
        return sum(
            f.food.calories * f.servings * (f.food.portion_weight_g / 100)
            for f in self.foods
        )

    def __repr__(self) -> str:
        return f"<DietPlanMeal {self.name}>"


class DietPlanMealFood(Base, UUIDMixin):
    """Foods included in a diet plan meal."""

    __tablename__ = "diet_plan_meal_foods"

    meal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plan_meals.id", ondelete="CASCADE"),
        nullable=False,
    )
    food_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("foods.id", ondelete="CASCADE"),
        nullable=False,
    )
    servings: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    portion_description: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    meal: Mapped["DietPlanMeal"] = relationship("DietPlanMeal", back_populates="foods")
    food: Mapped["Food"] = relationship("Food", lazy="joined")


class DietAssignment(Base, UUIDMixin, TimestampMixin):
    """Assignment of a diet plan to a patient/student."""

    __tablename__ = "diet_assignments"

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diet_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    nutritionist_id: Mapped[uuid.UUID] = mapped_column(
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
    plan: Mapped["DietPlan"] = relationship("DietPlan", back_populates="assignments")
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])
    nutritionist: Mapped["User"] = relationship("User", foreign_keys=[nutritionist_id])

    def __repr__(self) -> str:
        return f"<DietAssignment plan={self.plan_id} student={self.student_id}>"


class MealLog(Base, UUIDMixin):
    """User's logged meal."""

    __tablename__ = "meal_logs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meal_type: Mapped[MealType] = mapped_column(
        Enum(MealType, name="meal_type_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User")
    foods: Mapped[list["MealLogFood"]] = relationship(
        "MealLogFood",
        back_populates="meal_log",
        lazy="selectin",
    )

    @property
    def total_calories(self) -> float:
        return sum(f.calories for f in self.foods)

    @property
    def total_protein(self) -> float:
        return sum(f.protein for f in self.foods)

    @property
    def total_carbs(self) -> float:
        return sum(f.carbs for f in self.foods)

    @property
    def total_fat(self) -> float:
        return sum(f.fat for f in self.foods)

    def __repr__(self) -> str:
        return f"<MealLog {self.meal_type} at {self.logged_at}>"


class MealLogFood(Base, UUIDMixin):
    """Foods in a logged meal."""

    __tablename__ = "meal_log_foods"

    meal_log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("meal_logs.id", ondelete="CASCADE"),
        nullable=False,
    )
    food_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("foods.id", ondelete="CASCADE"),
        nullable=False,
    )
    servings: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    portion_description: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    meal_log: Mapped["MealLog"] = relationship("MealLog", back_populates="foods")
    food: Mapped["Food"] = relationship("Food", lazy="joined")

    @property
    def calories(self) -> float:
        return self.food.calories * self.servings

    @property
    def protein(self) -> float:
        return self.food.protein * self.servings

    @property
    def carbs(self) -> float:
        return self.food.carbs * self.servings

    @property
    def fat(self) -> float:
        return self.food.fat * self.servings


class PatientNote(Base, UUIDMixin, TimestampMixin):
    """Notes about a patient from nutritionist."""

    __tablename__ = "patient_notes"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    nutritionist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), default="general", nullable=False
    )  # adjustment, alert, feedback, restriction
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    patient: Mapped["User"] = relationship("User", foreign_keys=[patient_id])
    nutritionist: Mapped["User"] = relationship("User", foreign_keys=[nutritionist_id])


# Import for type hints
from src.domains.organizations.models import Organization  # noqa: E402, F401
from src.domains.users.models import User  # noqa: E402, F401
