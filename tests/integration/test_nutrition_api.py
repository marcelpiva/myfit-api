"""Integration tests for nutrition API endpoints."""
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.nutrition.models import (
    DietPlan,
    Food,
    FoodCategory,
    MealLog,
    MealLogFood,
    MealType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_food(db_session: AsyncSession, sample_user: dict[str, Any]) -> Food:
    """Create a sample food item."""
    food = Food(
        name="Chicken Breast",
        brand="Generic",
        calories=165.0,
        protein=31.0,
        carbs=0.0,
        fat=3.6,
        fiber=0.0,
        portion_size="100g",
        portion_weight_g=100.0,
        category=FoodCategory.PROTEINS,
        is_verified=True,
        is_public=True,
        created_by_id=sample_user["id"],
    )
    db_session.add(food)
    await db_session.commit()
    await db_session.refresh(food)
    return food


@pytest.fixture
async def sample_food_with_barcode(db_session: AsyncSession, sample_user: dict[str, Any]) -> Food:
    """Create a sample food with a barcode."""
    food = Food(
        name="Oatmeal",
        brand="Quaker",
        barcode="012345678901",
        calories=389.0,
        protein=16.9,
        carbs=66.3,
        fat=6.9,
        fiber=10.6,
        portion_size="100g",
        portion_weight_g=100.0,
        category=FoodCategory.CARBS,
        is_verified=True,
        is_public=True,
        created_by_id=sample_user["id"],
    )
    db_session.add(food)
    await db_session.commit()
    await db_session.refresh(food)
    return food


@pytest.fixture
async def sample_private_food(db_session: AsyncSession, sample_user: dict[str, Any]) -> Food:
    """Create a private food item owned by sample_user."""
    food = Food(
        name="My Custom Protein Shake",
        brand="Homemade",
        calories=250.0,
        protein=40.0,
        carbs=10.0,
        fat=5.0,
        portion_size="1 shake",
        portion_weight_g=300.0,
        category=FoodCategory.SUPPLEMENTS,
        is_verified=False,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(food)
    await db_session.commit()
    await db_session.refresh(food)
    return food


@pytest.fixture
async def sample_diet_plan(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> DietPlan:
    """Create a sample diet plan."""
    plan = DietPlan(
        name="Weight Loss Plan",
        description="A calorie-deficit diet plan",
        target_calories=1800,
        target_protein=150,
        target_carbs=150,
        target_fat=60,
        tags=["weight-loss", "high-protein"],
        is_template=True,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(plan)
    await db_session.commit()
    await db_session.refresh(plan)
    return plan


@pytest.fixture
async def sample_meal_log(
    db_session: AsyncSession, sample_user: dict[str, Any], sample_food: Food
) -> MealLog:
    """Create a sample meal log with food."""
    meal_log = MealLog(
        user_id=sample_user["id"],
        meal_type=MealType.BREAKFAST,
        logged_at=datetime.now(timezone.utc),
        notes="Morning meal",
    )
    db_session.add(meal_log)
    await db_session.flush()

    # Add food to meal log
    meal_log_food = MealLogFood(
        meal_log_id=meal_log.id,
        food_id=sample_food.id,
        servings=1.5,
        portion_description="1.5 portions",
    )
    db_session.add(meal_log_food)
    await db_session.commit()
    await db_session.refresh(meal_log)
    return meal_log


# =============================================================================
# Food Endpoint Tests
# =============================================================================


class TestListFoods:
    """Tests for GET /api/v1/nutrition/foods."""

    async def test_list_foods_authenticated(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Authenticated user can list foods."""
        response = await authenticated_client.get("/api/v1/nutrition/foods")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_foods_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/nutrition/foods")

        assert response.status_code == 401

    async def test_list_foods_filter_by_category(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can filter foods by category."""
        response = await authenticated_client.get(
            "/api/v1/nutrition/foods", params={"category": "proteins"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(f["category"] == "proteins" for f in data)

    async def test_list_foods_search(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can search foods by name."""
        response = await authenticated_client.get(
            "/api/v1/nutrition/foods", params={"search": "Chicken"}
        )

        assert response.status_code == 200
        data = response.json()
        assert any("Chicken" in f["name"] for f in data)

    async def test_list_foods_pagination(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/nutrition/foods", params={"limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1


class TestGetFood:
    """Tests for GET /api/v1/nutrition/foods/{food_id}."""

    async def test_get_food_by_id(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can get a food by ID."""
        response = await authenticated_client.get(
            f"/api/v1/nutrition/foods/{sample_food.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Chicken Breast"
        assert data["calories"] == 165.0
        assert data["protein"] == 31.0

    async def test_get_food_by_barcode(
        self, authenticated_client: AsyncClient, sample_food_with_barcode: Food
    ):
        """Can get a food by barcode."""
        response = await authenticated_client.get(
            f"/api/v1/nutrition/foods/barcode/{sample_food_with_barcode.barcode}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Oatmeal"
        assert data["barcode"] == "012345678901"

    async def test_get_nonexistent_food(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent food."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/nutrition/foods/{fake_id}"
        )

        assert response.status_code == 404

    async def test_get_nonexistent_barcode(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent barcode."""
        response = await authenticated_client.get(
            "/api/v1/nutrition/foods/barcode/nonexistent_barcode"
        )

        assert response.status_code == 404


class TestCreateFood:
    """Tests for POST /api/v1/nutrition/foods."""

    async def test_create_food_success(self, authenticated_client: AsyncClient):
        """Can create a new food item."""
        payload = {
            "name": "Brown Rice",
            "calories": 112.0,
            "protein": 2.6,
            "carbs": 23.5,
            "fat": 0.9,
            "category": "carbs",
            "portion_size": "100g",
            "portion_weight_g": 100.0,
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/foods", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Brown Rice"
        assert data["category"] == "carbs"
        assert "id" in data

    async def test_create_food_with_barcode(self, authenticated_client: AsyncClient):
        """Can create food with barcode."""
        payload = {
            "name": "Protein Bar",
            "brand": "Quest",
            "barcode": "unique_barcode_123",
            "calories": 200.0,
            "protein": 21.0,
            "carbs": 22.0,
            "fat": 8.0,
            "category": "snacks",
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/foods", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["barcode"] == "unique_barcode_123"

    async def test_create_food_duplicate_barcode(
        self, authenticated_client: AsyncClient, sample_food_with_barcode: Food
    ):
        """Returns 400 for duplicate barcode."""
        payload = {
            "name": "Another Food",
            "barcode": sample_food_with_barcode.barcode,
            "calories": 100.0,
            "protein": 10.0,
            "carbs": 10.0,
            "fat": 5.0,
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/foods", json=payload
        )

        assert response.status_code == 400
        assert "barcode" in response.json()["detail"].lower()

    async def test_create_food_missing_required_fields(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for missing required fields."""
        payload = {"name": "Incomplete Food"}

        response = await authenticated_client.post(
            "/api/v1/nutrition/foods", json=payload
        )

        assert response.status_code == 422


class TestUpdateFood:
    """Tests for PUT /api/v1/nutrition/foods/{food_id}."""

    async def test_update_own_food(
        self, authenticated_client: AsyncClient, sample_private_food: Food
    ):
        """Owner can update their food."""
        payload = {
            "name": "Updated Protein Shake",
            "calories": 280.0,
        }

        response = await authenticated_client.put(
            f"/api/v1/nutrition/foods/{sample_private_food.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Protein Shake"
        assert data["calories"] == 280.0

    async def test_update_nonexistent_food(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent food."""
        fake_id = uuid.uuid4()
        payload = {"name": "New Name"}

        response = await authenticated_client.put(
            f"/api/v1/nutrition/foods/{fake_id}", json=payload
        )

        assert response.status_code == 404


# =============================================================================
# Diet Plan Endpoint Tests
# =============================================================================


class TestListDietPlans:
    """Tests for GET /api/v1/nutrition/diet-plans."""

    async def test_list_diet_plans_authenticated(
        self, authenticated_client: AsyncClient, sample_diet_plan: DietPlan
    ):
        """Authenticated user can list diet plans."""
        response = await authenticated_client.get("/api/v1/nutrition/diet-plans")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_list_diet_plans_templates_only(
        self, authenticated_client: AsyncClient, sample_diet_plan: DietPlan
    ):
        """Can filter for templates only."""
        response = await authenticated_client.get(
            "/api/v1/nutrition/diet-plans", params={"templates_only": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["is_template"] for p in data)


class TestGetDietPlan:
    """Tests for GET /api/v1/nutrition/diet-plans/{plan_id}."""

    async def test_get_diet_plan(
        self, authenticated_client: AsyncClient, sample_diet_plan: DietPlan
    ):
        """Can get a diet plan by ID."""
        response = await authenticated_client.get(
            f"/api/v1/nutrition/diet-plans/{sample_diet_plan.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Weight Loss Plan"
        assert data["target_calories"] == 1800

    async def test_get_nonexistent_diet_plan(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent diet plan."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/nutrition/diet-plans/{fake_id}"
        )

        assert response.status_code == 404


class TestCreateDietPlan:
    """Tests for POST /api/v1/nutrition/diet-plans."""

    async def test_create_diet_plan_success(self, authenticated_client: AsyncClient):
        """Can create a new diet plan."""
        payload = {
            "name": "Muscle Building Plan",
            "target_calories": 2500,
            "target_protein": 200,
            "target_carbs": 300,
            "target_fat": 80,
            "is_template": True,
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/diet-plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Muscle Building Plan"
        assert data["target_calories"] == 2500
        assert "id" in data

    async def test_create_diet_plan_with_description(
        self, authenticated_client: AsyncClient
    ):
        """Can create diet plan with description and tags."""
        payload = {
            "name": "Keto Diet",
            "description": "Low carb, high fat diet",
            "target_calories": 2000,
            "target_protein": 150,
            "target_carbs": 50,
            "target_fat": 150,
            "tags": ["keto", "low-carb"],
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/diet-plans", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "Low carb, high fat diet"
        assert "keto" in data["tags"]


class TestUpdateDietPlan:
    """Tests for PUT /api/v1/nutrition/diet-plans/{plan_id}."""

    async def test_update_own_diet_plan(
        self, authenticated_client: AsyncClient, sample_diet_plan: DietPlan
    ):
        """Owner can update their diet plan."""
        payload = {
            "name": "Updated Weight Loss Plan",
            "target_calories": 1600,
        }

        response = await authenticated_client.put(
            f"/api/v1/nutrition/diet-plans/{sample_diet_plan.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Weight Loss Plan"
        assert data["target_calories"] == 1600


class TestDeleteDietPlan:
    """Tests for DELETE /api/v1/nutrition/diet-plans/{plan_id}."""

    async def test_delete_own_diet_plan(
        self, authenticated_client: AsyncClient, sample_diet_plan: DietPlan
    ):
        """Owner can delete their diet plan."""
        response = await authenticated_client.delete(
            f"/api/v1/nutrition/diet-plans/{sample_diet_plan.id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await authenticated_client.get(
            f"/api/v1/nutrition/diet-plans/{sample_diet_plan.id}"
        )
        assert get_response.status_code == 404


# =============================================================================
# Meal Log Endpoint Tests
# =============================================================================


class TestListMealLogs:
    """Tests for GET /api/v1/nutrition/meals."""

    async def test_list_meal_logs_authenticated(
        self, authenticated_client: AsyncClient, sample_meal_log: MealLog
    ):
        """Authenticated user can list their meal logs."""
        response = await authenticated_client.get("/api/v1/nutrition/meals")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_list_meal_logs_with_date_filter(
        self, authenticated_client: AsyncClient, sample_meal_log: MealLog
    ):
        """Can filter meal logs by date range."""
        today = date.today()
        response = await authenticated_client.get(
            "/api/v1/nutrition/meals",
            params={
                "from_date": today.isoformat(),
                "to_date": today.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCreateMealLog:
    """Tests for POST /api/v1/nutrition/meals."""

    async def test_create_meal_log_success(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can create a new meal log."""
        payload = {
            "meal_type": "lunch",
            "notes": "Post-workout meal",
            "foods": [
                {
                    "food_id": str(sample_food.id),
                    "servings": 2.0,
                    "portion_description": "2 chicken breasts",
                }
            ],
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/meals", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["meal_type"] == "lunch"
        assert data["notes"] == "Post-workout meal"
        # Verify meal log was created with an ID
        assert "id" in data

        # Verify the food was added by fetching the meal logs list
        list_response = await authenticated_client.get("/api/v1/nutrition/meals")
        assert list_response.status_code == 200
        logs = list_response.json()
        created_log = next((l for l in logs if l["id"] == data["id"]), None)
        assert created_log is not None
        assert len(created_log["foods"]) == 1
        assert created_log["total_calories"] == 165.0 * 2  # 2 servings

    async def test_create_meal_log_multiple_foods(
        self,
        authenticated_client: AsyncClient,
        sample_food: Food,
        sample_food_with_barcode: Food,
    ):
        """Can create meal log with multiple foods."""
        payload = {
            "meal_type": "breakfast",
            "foods": [
                {"food_id": str(sample_food.id), "servings": 1.0},
                {"food_id": str(sample_food_with_barcode.id), "servings": 0.5},
            ],
        }

        response = await authenticated_client.post(
            "/api/v1/nutrition/meals", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

        # Verify foods were added by fetching the meal logs list
        list_response = await authenticated_client.get("/api/v1/nutrition/meals")
        assert list_response.status_code == 200
        logs = list_response.json()
        created_log = next((l for l in logs if l["id"] == data["id"]), None)
        assert created_log is not None
        assert len(created_log["foods"]) == 2


class TestDeleteMealLog:
    """Tests for DELETE /api/v1/nutrition/meals/{log_id}."""

    async def test_delete_own_meal_log(
        self, authenticated_client: AsyncClient
    ):
        """Owner can delete their meal log."""
        # Create a meal log via API (without foods to avoid SQLite cascade issues)
        payload = {
            "meal_type": "dinner",
            "notes": "Test meal to delete",
            "foods": [],
        }
        create_response = await authenticated_client.post(
            "/api/v1/nutrition/meals", json=payload
        )
        assert create_response.status_code == 201
        meal_log_id = create_response.json()["id"]

        # Delete the meal log
        response = await authenticated_client.delete(
            f"/api/v1/nutrition/meals/{meal_log_id}"
        )

        assert response.status_code == 204

        # Verify it's deleted
        list_response = await authenticated_client.get("/api/v1/nutrition/meals")
        assert list_response.status_code == 200
        logs = list_response.json()
        assert not any(l["id"] == meal_log_id for l in logs)

    async def test_delete_nonexistent_meal_log(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent meal log."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.delete(
            f"/api/v1/nutrition/meals/{fake_id}"
        )

        assert response.status_code == 404


# =============================================================================
# Summary Endpoint Tests
# =============================================================================


class TestDailySummary:
    """Tests for GET /api/v1/nutrition/summary/daily."""

    async def test_get_daily_summary(
        self, authenticated_client: AsyncClient, sample_meal_log: MealLog
    ):
        """Can get daily nutrition summary."""
        response = await authenticated_client.get("/api/v1/nutrition/summary/daily")

        assert response.status_code == 200
        data = response.json()
        assert "date" in data
        assert "total_calories" in data
        assert "total_protein" in data
        assert "total_carbs" in data
        assert "total_fat" in data
        assert "meal_count" in data

    async def test_get_daily_summary_specific_date(
        self, authenticated_client: AsyncClient
    ):
        """Can get daily summary for specific date."""
        target_date = date.today()
        response = await authenticated_client.get(
            "/api/v1/nutrition/summary/daily",
            params={"target_date": target_date.isoformat()},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["date"] == target_date.isoformat()


class TestWeeklySummary:
    """Tests for GET /api/v1/nutrition/summary/weekly."""

    async def test_get_weekly_summary(
        self, authenticated_client: AsyncClient, sample_meal_log: MealLog
    ):
        """Can get weekly nutrition summary."""
        response = await authenticated_client.get("/api/v1/nutrition/summary/weekly")

        assert response.status_code == 200
        data = response.json()
        assert "start_date" in data
        assert "end_date" in data
        assert "avg_calories" in data
        assert "avg_protein" in data
        assert "avg_carbs" in data
        assert "avg_fat" in data
        assert "days_logged" in data


# =============================================================================
# Favorites Endpoint Tests
# =============================================================================


class TestFavorites:
    """Tests for food favorites endpoints."""

    async def test_add_favorite(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can add food to favorites."""
        response = await authenticated_client.post(
            f"/api/v1/nutrition/foods/{sample_food.id}/favorite"
        )

        assert response.status_code == 201
        data = response.json()
        assert "message" in data

    async def test_add_favorite_nonexistent_food(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent food."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.post(
            f"/api/v1/nutrition/foods/{fake_id}/favorite"
        )

        assert response.status_code == 404

    async def test_remove_favorite(
        self, authenticated_client: AsyncClient, sample_food: Food
    ):
        """Can remove food from favorites."""
        # First add to favorites
        await authenticated_client.post(
            f"/api/v1/nutrition/foods/{sample_food.id}/favorite"
        )

        # Then remove
        response = await authenticated_client.delete(
            f"/api/v1/nutrition/foods/{sample_food.id}/favorite"
        )

        assert response.status_code == 204
