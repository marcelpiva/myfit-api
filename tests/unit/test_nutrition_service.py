"""Tests for Nutrition service business logic."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from src.domains.nutrition.service import NutritionService


@pytest.fixture
async def sample_food(db_session: AsyncSession, sample_user: dict) -> Food:
    """Create a sample food for testing."""
    food = Food(
        name="Chicken Breast",
        brand="Fresh Farm",
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        fiber=0.0,
        portion_size="100g",
        portion_weight_g=100.0,
        category=FoodCategory.PROTEINS,
        is_public=True,
        created_by_id=sample_user["id"],
    )
    db_session.add(food)
    await db_session.commit()
    await db_session.refresh(food)
    return food


@pytest.fixture
async def sample_diet_plan(db_session: AsyncSession, sample_user: dict) -> DietPlan:
    """Create a sample diet plan for testing."""
    plan = DietPlan(
        name="Weight Loss Plan",
        description="A balanced plan for weight loss",
        target_calories=1800,
        target_protein=150,
        target_carbs=150,
        target_fat=60,
        is_template=True,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


class TestFoodOperations:
    """Tests for food CRUD operations."""

    async def test_get_food_by_id(
        self, db_session: AsyncSession, sample_food: Food
    ):
        """Should find food by ID."""
        service = NutritionService(db_session)

        food = await service.get_food_by_id(sample_food.id)

        assert food is not None
        assert food.name == "Chicken Breast"
        assert food.calories == 165.0

    async def test_get_food_by_id_not_found(self, db_session: AsyncSession):
        """Should return None for nonexistent food."""
        service = NutritionService(db_session)

        food = await service.get_food_by_id(uuid.uuid4())

        assert food is None

    async def test_get_food_by_barcode(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should find food by barcode."""
        service = NutritionService(db_session)

        # Create food with barcode
        food = Food(
            name="Protein Bar",
            barcode="7891234567890",
            calories=200.0,
            protein=20.0,
            carbs=25.0,
            fat=8.0,
            portion_size="1 bar",
            portion_weight_g=50.0,
            is_public=True,
            created_by_id=sample_user["id"],
        )
        db_session.add(food)
        await db_session.commit()

        found = await service.get_food_by_barcode("7891234567890")

        assert found is not None
        assert found.name == "Protein Bar"

    async def test_get_food_by_barcode_not_found(self, db_session: AsyncSession):
        """Should return None for nonexistent barcode."""
        service = NutritionService(db_session)

        food = await service.get_food_by_barcode("0000000000000")

        assert food is None

    async def test_create_food(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a new food."""
        service = NutritionService(db_session)

        food = await service.create_food(
            created_by_id=sample_user["id"],
            name="Brown Rice",
            calories=111.0,
            protein=2.6,
            carbs=23.0,
            fat=0.9,
            fiber=1.8,
            category=FoodCategory.CARBS,
        )

        assert food.id is not None
        assert food.name == "Brown Rice"
        assert food.category == FoodCategory.CARBS

    async def test_create_food_with_all_fields(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create food with all optional fields."""
        service = NutritionService(db_session)

        food = await service.create_food(
            created_by_id=sample_user["id"],
            name="Energy Drink",
            calories=120.0,
            protein=0.0,
            carbs=30.0,
            fat=0.0,
            brand="PowerBoost",
            barcode="1234567890123",
            fiber=0.0,
            sodium=100.0,
            sugar=28.0,
            portion_size="1 can",
            portion_weight_g=250.0,
            category=FoodCategory.BEVERAGES,
            image_url="https://example.com/drink.jpg",
            is_public=False,
        )

        assert food.brand == "PowerBoost"
        assert food.barcode == "1234567890123"
        assert food.sodium == 100.0
        assert food.is_public is False

    async def test_search_foods_by_name(
        self, db_session: AsyncSession, sample_food: Food, sample_user: dict
    ):
        """Should search foods by name."""
        service = NutritionService(db_session)

        foods = await service.search_foods(
            user_id=sample_user["id"],
            search="Chicken",
        )

        assert len(foods) >= 1
        assert any(f.id == sample_food.id for f in foods)

    async def test_search_foods_by_brand(
        self, db_session: AsyncSession, sample_food: Food, sample_user: dict
    ):
        """Should search foods by brand."""
        service = NutritionService(db_session)

        foods = await service.search_foods(
            user_id=sample_user["id"],
            search="Fresh Farm",
        )

        assert len(foods) >= 1
        assert any(f.id == sample_food.id for f in foods)

    async def test_search_foods_by_category(
        self, db_session: AsyncSession, sample_food: Food, sample_user: dict
    ):
        """Should filter foods by category."""
        service = NutritionService(db_session)

        foods = await service.search_foods(
            user_id=sample_user["id"],
            category=FoodCategory.PROTEINS,
        )

        assert len(foods) >= 1
        assert all(f.category == FoodCategory.PROTEINS for f in foods)

    async def test_search_foods_includes_user_private_foods(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should include user's private foods in search."""
        service = NutritionService(db_session)

        # Create private food
        private_food = Food(
            name="My Secret Recipe",
            calories=300.0,
            protein=15.0,
            carbs=30.0,
            fat=12.0,
            is_public=False,
            created_by_id=sample_user["id"],
        )
        db_session.add(private_food)
        await db_session.commit()

        foods = await service.search_foods(
            user_id=sample_user["id"],
            search="Secret Recipe",
        )

        assert len(foods) == 1
        assert foods[0].name == "My Secret Recipe"

    async def test_update_food(
        self, db_session: AsyncSession, sample_food: Food
    ):
        """Should update food fields."""
        service = NutritionService(db_session)

        updated = await service.update_food(
            sample_food,
            name="Grilled Chicken Breast",
            calories=170.0,
        )

        assert updated.name == "Grilled Chicken Breast"
        assert updated.calories == 170.0


class TestFavorites:
    """Tests for food favorites operations."""

    async def test_add_to_favorites(
        self, db_session: AsyncSession, sample_user: dict, sample_food: Food
    ):
        """Should add food to favorites."""
        service = NutritionService(db_session)

        await service.add_to_favorites(sample_user["id"], sample_food.id)

        # Verify in database
        result = await db_session.execute(
            select(UserFavoriteFood).where(
                UserFavoriteFood.user_id == sample_user["id"],
                UserFavoriteFood.food_id == sample_food.id,
            )
        )
        favorite = result.scalar_one_or_none()
        assert favorite is not None

    async def test_get_user_favorites(
        self, db_session: AsyncSession, sample_user: dict, sample_food: Food
    ):
        """Should get user's favorite foods."""
        service = NutritionService(db_session)

        # Add to favorites
        await service.add_to_favorites(sample_user["id"], sample_food.id)

        favorites = await service.get_user_favorites(sample_user["id"])

        assert len(favorites) >= 1
        assert any(f.id == sample_food.id for f in favorites)

    async def test_remove_from_favorites(
        self, db_session: AsyncSession, sample_user: dict, sample_food: Food
    ):
        """Should remove food from favorites."""
        service = NutritionService(db_session)

        # Add then remove
        await service.add_to_favorites(sample_user["id"], sample_food.id)
        await service.remove_from_favorites(sample_user["id"], sample_food.id)

        # Verify removed
        result = await db_session.execute(
            select(UserFavoriteFood).where(
                UserFavoriteFood.user_id == sample_user["id"],
                UserFavoriteFood.food_id == sample_food.id,
            )
        )
        favorite = result.scalar_one_or_none()
        assert favorite is None


class TestDietPlanOperations:
    """Tests for diet plan operations."""

    async def test_get_diet_plan_by_id(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan
    ):
        """Should get diet plan by ID."""
        service = NutritionService(db_session)

        plan = await service.get_diet_plan_by_id(sample_diet_plan.id)

        assert plan is not None
        assert plan.name == "Weight Loss Plan"
        assert plan.target_calories == 1800

    async def test_create_diet_plan(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a new diet plan."""
        service = NutritionService(db_session)

        plan = await service.create_diet_plan(
            created_by_id=sample_user["id"],
            name="Muscle Gain Plan",
            target_calories=2500,
            target_protein=200,
            target_carbs=300,
            target_fat=80,
            description="High protein diet for muscle building",
            is_template=True,
        )

        assert plan.id is not None
        assert plan.name == "Muscle Gain Plan"
        assert plan.target_protein == 200

    async def test_update_diet_plan(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan
    ):
        """Should update diet plan fields."""
        service = NutritionService(db_session)

        updated = await service.update_diet_plan(
            sample_diet_plan,
            name="Updated Weight Loss Plan",
            target_calories=1600,
        )

        assert updated.name == "Updated Weight Loss Plan"
        assert updated.target_calories == 1600

    async def test_delete_diet_plan(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan
    ):
        """Should delete diet plan."""
        service = NutritionService(db_session)
        plan_id = sample_diet_plan.id

        await service.delete_diet_plan(sample_diet_plan)

        # Verify deleted
        result = await db_session.execute(
            select(DietPlan).where(DietPlan.id == plan_id)
        )
        assert result.scalar_one_or_none() is None

    async def test_add_meal_to_plan(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan
    ):
        """Should add meal to diet plan."""
        service = NutritionService(db_session)

        meal = await service.add_meal_to_plan(
            plan_id=sample_diet_plan.id,
            name="Breakfast",
            meal_time=time(7, 0),
            order=1,
            notes="Start the day with protein",
        )

        assert meal.id is not None
        assert meal.name == "Breakfast"
        assert meal.meal_time == time(7, 0)

    async def test_add_food_to_meal(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan, sample_food: Food
    ):
        """Should add food to a meal."""
        service = NutritionService(db_session)

        # Create meal first
        meal = await service.add_meal_to_plan(
            plan_id=sample_diet_plan.id,
            name="Lunch",
            meal_time=time(12, 0),
        )

        meal_food = await service.add_food_to_meal(
            meal_id=meal.id,
            food_id=sample_food.id,
            servings=1.5,
            portion_description="150g grilled",
        )

        assert meal_food.id is not None
        assert meal_food.servings == 1.5


class TestDietAssignment:
    """Tests for diet assignment operations."""

    async def test_create_assignment(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan, sample_user: dict
    ):
        """Should create diet assignment."""
        service = NutritionService(db_session)

        # Create another user as student
        from src.domains.users.models import User
        student = User(
            email="student@example.com",
            name="Test Student",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(student)
        await db_session.commit()

        assignment = await service.create_assignment(
            plan_id=sample_diet_plan.id,
            student_id=student.id,
            nutritionist_id=sample_user["id"],
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            notes="Follow strictly",
        )

        assert assignment.id is not None
        assert assignment.student_id == student.id
        assert assignment.notes == "Follow strictly"

    async def test_list_student_assignments(
        self, db_session: AsyncSession, sample_diet_plan: DietPlan, sample_user: dict
    ):
        """Should list assignments for a student."""
        service = NutritionService(db_session)

        # Create student and assignment
        from src.domains.users.models import User
        student = User(
            email="student2@example.com",
            name="Another Student",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(student)
        await db_session.commit()

        await service.create_assignment(
            plan_id=sample_diet_plan.id,
            student_id=student.id,
            nutritionist_id=sample_user["id"],
            start_date=date.today(),
        )

        assignments = await service.list_student_assignments(student.id)

        assert len(assignments) >= 1


class TestMealLog:
    """Tests for meal logging operations."""

    async def test_create_meal_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a meal log."""
        service = NutritionService(db_session)

        log = await service.create_meal_log(
            user_id=sample_user["id"],
            meal_type=MealType.BREAKFAST,
            notes="Morning meal",
        )

        assert log.id is not None
        assert log.meal_type == MealType.BREAKFAST
        assert log.logged_at is not None

    async def test_create_meal_log_with_timestamp(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create meal log with specific timestamp."""
        service = NutritionService(db_session)

        specific_time = datetime(2024, 1, 15, 8, 30, tzinfo=timezone.utc)
        log = await service.create_meal_log(
            user_id=sample_user["id"],
            meal_type=MealType.BREAKFAST,
            logged_at=specific_time,
        )

        # Compare without timezone
        assert log.logged_at.replace(tzinfo=None) == specific_time.replace(tzinfo=None)

    async def test_add_food_to_log(
        self, db_session: AsyncSession, sample_user: dict, sample_food: Food
    ):
        """Should add food to meal log."""
        service = NutritionService(db_session)

        log = await service.create_meal_log(
            user_id=sample_user["id"],
            meal_type=MealType.LUNCH,
        )

        log_food = await service.add_food_to_log(
            meal_log_id=log.id,
            food_id=sample_food.id,
            servings=2.0,
            portion_description="Double portion",
        )

        assert log_food.id is not None
        assert log_food.servings == 2.0

    async def test_list_meal_logs_date_filter(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should filter meal logs by date."""
        service = NutritionService(db_session)

        # Create log for today
        await service.create_meal_log(
            user_id=sample_user["id"],
            meal_type=MealType.DINNER,
        )

        today = date.today()
        logs = await service.list_meal_logs(
            user_id=sample_user["id"],
            from_date=today,
            to_date=today,
        )

        assert len(logs) >= 1

    async def test_delete_meal_log(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should delete meal log."""
        service = NutritionService(db_session)

        log = await service.create_meal_log(
            user_id=sample_user["id"],
            meal_type=MealType.MORNING_SNACK,
        )
        log_id = log.id

        await service.delete_meal_log(log)

        # Verify deleted
        result = await db_session.execute(
            select(MealLog).where(MealLog.id == log_id)
        )
        assert result.scalar_one_or_none() is None


class TestNutritionSummary:
    """Tests for nutrition summary calculations."""

    async def test_daily_summary_no_meals(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return zero totals when no meals."""
        service = NutritionService(db_session)

        summary = await service.get_daily_summary(
            user_id=sample_user["id"],
            target_date=date.today() - timedelta(days=100),  # Date with no meals
        )

        assert summary["meal_count"] == 0
        assert summary["total_calories"] == 0.0

    async def test_weekly_summary_no_meals(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should return zero averages when no meals logged."""
        service = NutritionService(db_session)

        summary = await service.get_weekly_summary(
            user_id=sample_user["id"],
            start_date=date.today() - timedelta(days=200),  # Date range with no meals
        )

        assert summary["days_logged"] == 0
        assert summary["avg_calories"] == 0


class TestPatientNotes:
    """Tests for patient notes operations."""

    async def test_create_patient_note(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a patient note."""
        service = NutritionService(db_session)

        # Create patient
        from src.domains.users.models import User
        patient = User(
            email="patient@example.com",
            name="Patient User",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(patient)
        await db_session.commit()

        note = await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Patient is making good progress",
            category="progress",
            is_private=False,
        )

        assert note.id is not None
        assert note.content == "Patient is making good progress"
        assert note.category == "progress"

    async def test_create_private_note(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should create a private note."""
        service = NutritionService(db_session)

        from src.domains.users.models import User
        patient = User(
            email="patient3@example.com",
            name="Patient 3",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(patient)
        await db_session.commit()

        note = await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Internal observation",
            is_private=True,
        )

        assert note.is_private is True

    async def test_list_patient_notes_excludes_private(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should exclude private notes by default."""
        service = NutritionService(db_session)

        from src.domains.users.models import User
        patient = User(
            email="patient4@example.com",
            name="Patient 4",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(patient)
        await db_session.commit()

        # Create public note
        await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Public note",
            is_private=False,
        )

        # Create private note
        await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Private note",
            is_private=True,
        )

        notes = await service.list_patient_notes(
            patient_id=patient.id,
            include_private=False,
        )

        assert len(notes) == 1
        assert notes[0].content == "Public note"

    async def test_list_patient_notes_includes_private(
        self, db_session: AsyncSession, sample_user: dict
    ):
        """Should include private notes when requested."""
        service = NutritionService(db_session)

        from src.domains.users.models import User
        patient = User(
            email="patient5@example.com",
            name="Patient 5",
            password_hash="hash",
            is_active=True,
        )
        db_session.add(patient)
        await db_session.commit()

        await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Public",
            is_private=False,
        )

        await service.create_patient_note(
            patient_id=patient.id,
            nutritionist_id=sample_user["id"],
            content="Private",
            is_private=True,
        )

        notes = await service.list_patient_notes(
            patient_id=patient.id,
            include_private=True,
        )

        assert len(notes) == 2
