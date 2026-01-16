"""Central import of all domain models.

This file imports all models to ensure they are registered with SQLAlchemy's
metadata before any database operations (like creating tables or migrations).
"""

# Users domain
from src.domains.users.models import (
    Gender,
    Theme,
    Units,
    User,
    UserSettings,
)

# Organizations domain
from src.domains.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMembership,
    OrganizationType,
    UserRole,
)

# Workouts domain
from src.domains.workouts.models import (
    Difficulty,
    Exercise,
    MuscleGroup,
    ProgramAssignment,
    ProgramWorkout,
    SplitType,
    Workout,
    WorkoutAssignment,
    WorkoutExercise,
    WorkoutGoal,
    WorkoutProgram,
    WorkoutSession,
    WorkoutSessionSet,
)

# Nutrition domain
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

# Progress domain
from src.domains.progress.models import (
    MeasurementLog,
    PhotoAngle,
    ProgressPhoto,
    WeightGoal,
    WeightLog,
)

# Check-in domain
from src.domains.checkin.models import (
    CheckIn,
    CheckInCode,
    CheckInMethod,
    CheckInRequest,
    CheckInStatus,
    Gym,
)

# Gamification domain
from src.domains.gamification.models import (
    Achievement,
    LeaderboardEntry,
    PointTransaction,
    UserAchievement,
    UserPoints,
)

# Marketplace domain
from src.domains.marketplace.models import (
    CreatorEarnings,
    CreatorPayout,
    MarketplaceTemplate,
    OrganizationTemplateAccess,
    PaymentProvider,
    PayoutMethod,
    PayoutStatus,
    PurchaseStatus,
    TemplateCategory,
    TemplateDifficulty,
    TemplatePurchase,
    TemplateReview,
    TemplateType,
)

__all__ = [
    # Users
    "User",
    "UserSettings",
    "Gender",
    "Theme",
    "Units",
    # Organizations
    "Organization",
    "OrganizationMembership",
    "OrganizationInvite",
    "OrganizationType",
    "UserRole",
    # Workouts
    "Exercise",
    "Workout",
    "WorkoutExercise",
    "WorkoutAssignment",
    "WorkoutSession",
    "WorkoutSessionSet",
    "WorkoutProgram",
    "ProgramWorkout",
    "ProgramAssignment",
    "Difficulty",
    "MuscleGroup",
    "WorkoutGoal",
    "SplitType",
    # Nutrition
    "Food",
    "UserFavoriteFood",
    "DietPlan",
    "DietPlanMeal",
    "DietPlanMealFood",
    "DietAssignment",
    "MealLog",
    "MealLogFood",
    "PatientNote",
    "FoodCategory",
    "MealType",
    # Progress
    "WeightLog",
    "MeasurementLog",
    "ProgressPhoto",
    "WeightGoal",
    "PhotoAngle",
    # Check-in
    "Gym",
    "CheckIn",
    "CheckInCode",
    "CheckInRequest",
    "CheckInMethod",
    "CheckInStatus",
    # Gamification
    "UserPoints",
    "PointTransaction",
    "Achievement",
    "UserAchievement",
    "LeaderboardEntry",
    # Marketplace
    "MarketplaceTemplate",
    "TemplatePurchase",
    "TemplateReview",
    "CreatorEarnings",
    "CreatorPayout",
    "OrganizationTemplateAccess",
    "TemplateType",
    "TemplateCategory",
    "TemplateDifficulty",
    "PurchaseStatus",
    "PayoutStatus",
    "PaymentProvider",
    "PayoutMethod",
]
