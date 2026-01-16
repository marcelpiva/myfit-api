"""Nutrition schemas for request/response validation."""
from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.nutrition.models import FoodCategory, MealType


# Food schemas

class FoodCreate(BaseModel):
    """Create food request."""

    name: str = Field(min_length=2, max_length=255)
    brand: str | None = Field(None, max_length=255)
    barcode: str | None = Field(None, max_length=100)
    calories: float = Field(ge=0)
    protein: float = Field(ge=0)
    carbs: float = Field(ge=0)
    fat: float = Field(ge=0)
    fiber: float | None = Field(None, ge=0)
    sodium: float | None = Field(None, ge=0)
    sugar: float | None = Field(None, ge=0)
    portion_size: str = Field(default="100g", max_length=100)
    portion_weight_g: float = Field(default=100.0, ge=0)
    category: FoodCategory = FoodCategory.OTHER
    image_url: str | None = Field(None, max_length=500)


class FoodUpdate(BaseModel):
    """Update food request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    brand: str | None = Field(None, max_length=255)
    calories: float | None = Field(None, ge=0)
    protein: float | None = Field(None, ge=0)
    carbs: float | None = Field(None, ge=0)
    fat: float | None = Field(None, ge=0)
    fiber: float | None = Field(None, ge=0)
    sodium: float | None = Field(None, ge=0)
    sugar: float | None = Field(None, ge=0)
    portion_size: str | None = Field(None, max_length=100)
    portion_weight_g: float | None = Field(None, ge=0)
    category: FoodCategory | None = None
    image_url: str | None = Field(None, max_length=500)


class FoodResponse(BaseModel):
    """Food response."""

    id: UUID
    name: str
    brand: str | None = None
    barcode: str | None = None
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: float | None = None
    sodium: float | None = None
    sugar: float | None = None
    portion_size: str
    portion_weight_g: float
    category: FoodCategory
    image_url: str | None = None
    is_verified: bool
    is_public: bool
    created_by_id: UUID | None = None

    class Config:
        from_attributes = True


class FoodListResponse(BaseModel):
    """Food list item response."""

    id: UUID
    name: str
    brand: str | None = None
    calories: float
    protein: float
    category: FoodCategory

    class Config:
        from_attributes = True


# Diet plan schemas

class DietPlanMealFoodInput(BaseModel):
    """Input for food in a diet plan meal."""

    food_id: UUID
    servings: float = Field(default=1.0, ge=0.1)
    portion_description: str | None = Field(None, max_length=100)
    notes: str | None = Field(None, max_length=500)


class DietPlanMealInput(BaseModel):
    """Input for meal in a diet plan."""

    name: str = Field(min_length=2, max_length=100)
    meal_time: time
    order: int = 0
    notes: str | None = None
    foods: list[DietPlanMealFoodInput] = []


class DietPlanCreate(BaseModel):
    """Create diet plan request."""

    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    target_calories: int = Field(default=2000, ge=500, le=10000)
    target_protein: int = Field(default=150, ge=0)
    target_carbs: int = Field(default=200, ge=0)
    target_fat: int = Field(default=70, ge=0)
    tags: list[str] | None = None
    is_template: bool = False
    is_public: bool = False
    organization_id: UUID | None = None
    meals: list[DietPlanMealInput] | None = None


class DietPlanUpdate(BaseModel):
    """Update diet plan request."""

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    target_calories: int | None = Field(None, ge=500, le=10000)
    target_protein: int | None = Field(None, ge=0)
    target_carbs: int | None = Field(None, ge=0)
    target_fat: int | None = Field(None, ge=0)
    tags: list[str] | None = None
    is_template: bool | None = None
    is_public: bool | None = None


class DietPlanMealFoodResponse(BaseModel):
    """Diet plan meal food response."""

    id: UUID
    food_id: UUID
    servings: float
    portion_description: str | None = None
    notes: str | None = None
    food: FoodResponse

    class Config:
        from_attributes = True


class DietPlanMealResponse(BaseModel):
    """Diet plan meal response."""

    id: UUID
    name: str
    meal_time: time
    order: int
    notes: str | None = None
    foods: list[DietPlanMealFoodResponse] = []
    total_calories: float = 0

    class Config:
        from_attributes = True


class DietPlanResponse(BaseModel):
    """Diet plan response."""

    id: UUID
    name: str
    description: str | None = None
    target_calories: int
    target_protein: int
    target_carbs: int
    target_fat: int
    tags: list[str] | None = None
    is_template: bool
    is_public: bool
    created_by_id: UUID
    organization_id: UUID | None = None
    created_at: datetime
    meals: list[DietPlanMealResponse] = []

    class Config:
        from_attributes = True


class DietPlanListResponse(BaseModel):
    """Diet plan list item response."""

    id: UUID
    name: str
    target_calories: int
    is_template: bool
    meal_count: int = 0

    class Config:
        from_attributes = True


# Assignment schemas

class DietAssignmentCreate(BaseModel):
    """Create diet assignment request."""

    plan_id: UUID
    student_id: UUID
    start_date: date
    end_date: date | None = None
    notes: str | None = None
    organization_id: UUID | None = None


class DietAssignmentUpdate(BaseModel):
    """Update diet assignment request."""

    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None
    notes: str | None = None


class DietAssignmentResponse(BaseModel):
    """Diet assignment response."""

    id: UUID
    plan_id: UUID
    student_id: UUID
    nutritionist_id: UUID
    organization_id: UUID | None = None
    start_date: date
    end_date: date | None = None
    is_active: bool
    notes: str | None = None
    created_at: datetime
    plan_name: str
    student_name: str

    class Config:
        from_attributes = True


# Meal log schemas

class MealLogFoodInput(BaseModel):
    """Input for food in a meal log."""

    food_id: UUID
    servings: float = Field(default=1.0, ge=0.1)
    portion_description: str | None = Field(None, max_length=100)


class MealLogCreate(BaseModel):
    """Create meal log request."""

    meal_type: MealType
    logged_at: datetime | None = None
    notes: str | None = None
    foods: list[MealLogFoodInput] = []


class MealLogFoodResponse(BaseModel):
    """Meal log food response."""

    id: UUID
    food_id: UUID
    servings: float
    portion_description: str | None = None
    food: FoodResponse
    calories: float
    protein: float
    carbs: float
    fat: float

    class Config:
        from_attributes = True


class MealLogResponse(BaseModel):
    """Meal log response."""

    id: UUID
    user_id: UUID
    meal_type: MealType
    logged_at: datetime
    notes: str | None = None
    foods: list[MealLogFoodResponse] = []
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float

    class Config:
        from_attributes = True


class DailySummary(BaseModel):
    """Daily nutrition summary."""

    date: date
    total_calories: float
    total_protein: float
    total_carbs: float
    total_fat: float
    meal_count: int


class WeeklySummary(BaseModel):
    """Weekly nutrition summary."""

    start_date: date
    end_date: date
    avg_calories: float
    avg_protein: float
    avg_carbs: float
    avg_fat: float
    days_logged: int


# Patient note schemas

class PatientNoteCreate(BaseModel):
    """Create patient note request."""

    patient_id: UUID
    content: str = Field(min_length=1)
    category: str = Field(default="general", max_length=50)
    is_private: bool = False


class PatientNoteResponse(BaseModel):
    """Patient note response."""

    id: UUID
    patient_id: UUID
    nutritionist_id: UUID
    content: str
    category: str
    is_private: bool
    created_at: datetime

    class Config:
        from_attributes = True
