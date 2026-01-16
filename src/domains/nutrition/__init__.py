"""Nutrition domain package."""
from src.domains.nutrition.models import (
    DietAssignment,
    DietPlan,
    DietPlanMeal,
    DietPlanMealFood,
    Food,
    FoodCategory,
    MealLog,
    MealLogFood,
    MealType,
    PatientNote,
    UserFavoriteFood,
)
from src.domains.nutrition.router import router
from src.domains.nutrition.service import NutritionService

__all__ = [
    "router",
    "Food",
    "FoodCategory",
    "MealType",
    "UserFavoriteFood",
    "DietPlan",
    "DietPlanMeal",
    "DietPlanMealFood",
    "DietAssignment",
    "MealLog",
    "MealLogFood",
    "PatientNote",
    "NutritionService",
]
