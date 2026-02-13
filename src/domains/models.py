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
    NoteAuthorRole,
    NoteContextType,
    PlanAssignment,
    PlanWorkout,
    PrescriptionNote,
    SplitType,
    TrainingPlan,
    Workout,
    WorkoutAssignment,
    WorkoutExercise,
    WorkoutGoal,
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
    TrainerLocation,
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

# Schedule domain
from src.domains.schedule.models import (
    Appointment,
    AppointmentParticipant,
    AppointmentStatus,
    AppointmentType,
    AttendanceStatus,
    DifficultyLevel,
    EvaluatorRole,
    SessionEvaluation,
    SessionTemplate,
    SessionType,
    WaitlistEntry,
    WaitlistStatus,
)

# Trainers domain
from src.domains.trainers.models import (
    StudentNote,
)

# Chat domain
from src.domains.chat.models import (
    Conversation,
    ConversationParticipant,
    ConversationType,
    Message,
    MessageType,
)

# Notifications domain
from src.domains.notifications.models import (
    Notification,
    NotificationPriority,
    NotificationType,
)

# Billing domain
from src.domains.billing.models import (
    Payment,
    PaymentMethod,
    PaymentPlan,
    PaymentStatus,
    PaymentType,
    RecurrenceType,
    ServicePlan,
    ServicePlanType,
)

# Subscriptions domain
from src.domains.subscriptions.models import (
    FeatureDefinition,
    PlatformSubscription,
    PlatformTier,
    SubscriptionSource,
    SubscriptionStatus,
)

# Consultancy domain
from src.domains.consultancy.models import (
    ConsultancyCategory,
    ConsultancyFormat,
    ConsultancyListing,
    ConsultancyReview,
    ConsultancyTransaction,
    ProfessionalProfile,
    TransactionStatus,
)

# Referrals domain
from src.domains.referrals.models import (
    Referral,
    ReferralCode,
    ReferralReward,
    RewardStatus,
    RewardType,
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
    "TrainingPlan",
    "PlanWorkout",
    "PlanAssignment",
    "PrescriptionNote",
    "Difficulty",
    "MuscleGroup",
    "WorkoutGoal",
    "SplitType",
    "NoteContextType",
    "NoteAuthorRole",
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
    "TrainerLocation",
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
    # Schedule
    "Appointment",
    "AppointmentParticipant",
    "AppointmentStatus",
    "AppointmentType",
    "AttendanceStatus",
    "DifficultyLevel",
    "EvaluatorRole",
    "SessionEvaluation",
    "SessionTemplate",
    "SessionType",
    "WaitlistEntry",
    "WaitlistStatus",
    # Trainers
    "StudentNote",
    # Chat
    "Conversation",
    "ConversationParticipant",
    "ConversationType",
    "Message",
    "MessageType",
    # Notifications
    "Notification",
    "NotificationPriority",
    "NotificationType",
    # Billing
    "Payment",
    "PaymentMethod",
    "PaymentPlan",
    "PaymentStatus",
    "PaymentType",
    "RecurrenceType",
    "ServicePlan",
    "ServicePlanType",
    # Subscriptions
    "PlatformSubscription",
    "FeatureDefinition",
    "PlatformTier",
    "SubscriptionStatus",
    "SubscriptionSource",
    # Consultancy
    "ProfessionalProfile",
    "ConsultancyListing",
    "ConsultancyTransaction",
    "ConsultancyReview",
    "ConsultancyCategory",
    "ConsultancyFormat",
    "TransactionStatus",
    # Referrals
    "ReferralCode",
    "Referral",
    "ReferralReward",
    "RewardType",
    "RewardStatus",
]
