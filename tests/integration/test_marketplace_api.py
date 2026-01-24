"""Integration tests for marketplace API endpoints."""
import uuid
from datetime import datetime, timezone
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.marketplace.models import (
    MarketplaceTemplate,
    PaymentProvider,
    PurchaseStatus,
    TemplateCategory,
    TemplateDifficulty,
    TemplatePurchase,
    TemplateReview,
    TemplateType,
)
from src.domains.workouts.models import Difficulty, Workout


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def sample_workout_for_template(
    db_session: AsyncSession, sample_user: dict[str, Any]
) -> Workout:
    """Create a sample workout for marketplace templates."""
    workout = Workout(
        name="HIIT Cardio Blast",
        description="High intensity interval training for fat loss",
        difficulty=Difficulty.INTERMEDIATE,
        estimated_duration_min=30,
        target_muscles=["full_body"],
        is_template=True,
        is_public=False,
        created_by_id=sample_user["id"],
    )
    db_session.add(workout)
    await db_session.commit()
    await db_session.refresh(workout)
    return workout


@pytest.fixture
async def sample_template(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    sample_workout_for_template: Workout,
) -> MarketplaceTemplate:
    """Create a sample marketplace template."""
    template = MarketplaceTemplate(
        template_type=TemplateType.WORKOUT,
        workout_id=sample_workout_for_template.id,
        creator_id=sample_user["id"],
        price_cents=2990,
        currency="BRL",
        title="HIIT Cardio Program",
        short_description="Intense cardio workout for fat burning",
        full_description="A complete HIIT program designed to maximize calorie burn.",
        category=TemplateCategory.WEIGHT_LOSS,
        difficulty=TemplateDifficulty.INTERMEDIATE,
        tags=["hiit", "cardio", "fat-loss"],
        is_active=True,
        is_featured=False,
        approved_at=datetime.now(timezone.utc),
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def sample_free_template(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    sample_workout_for_template: Workout,
) -> MarketplaceTemplate:
    """Create a free marketplace template."""
    template = MarketplaceTemplate(
        template_type=TemplateType.WORKOUT,
        workout_id=sample_workout_for_template.id,
        creator_id=sample_user["id"],
        price_cents=0,
        currency="BRL",
        title="Free Beginner Workout",
        short_description="A free workout for beginners",
        category=TemplateCategory.GENERAL_FITNESS,
        difficulty=TemplateDifficulty.BEGINNER,
        is_active=True,
        approved_at=datetime.now(timezone.utc),
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def sample_featured_template(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    sample_workout_for_template: Workout,
) -> MarketplaceTemplate:
    """Create a featured marketplace template."""
    template = MarketplaceTemplate(
        template_type=TemplateType.WORKOUT,
        workout_id=sample_workout_for_template.id,
        creator_id=sample_user["id"],
        price_cents=4990,
        currency="BRL",
        title="Featured Strength Program",
        short_description="Our top-rated strength program",
        category=TemplateCategory.STRENGTH,
        difficulty=TemplateDifficulty.ADVANCED,
        is_active=True,
        is_featured=True,
        approved_at=datetime.now(timezone.utc),
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def sample_completed_purchase(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    sample_template: MarketplaceTemplate,
) -> TemplatePurchase:
    """Create a completed purchase for review testing."""
    purchase = TemplatePurchase(
        marketplace_template_id=sample_template.id,
        buyer_id=sample_user["id"],
        price_cents=sample_template.price_cents,
        currency=sample_template.currency,
        payment_provider=PaymentProvider.PIX,
        status=PurchaseStatus.COMPLETED,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


@pytest.fixture
async def sample_review(
    db_session: AsyncSession,
    sample_user: dict[str, Any],
    sample_template: MarketplaceTemplate,
    sample_completed_purchase: TemplatePurchase,
) -> TemplateReview:
    """Create a sample review."""
    review = TemplateReview(
        marketplace_template_id=sample_template.id,
        purchase_id=sample_completed_purchase.id,
        reviewer_id=sample_user["id"],
        rating=5,
        title="Excellent program!",
        comment="This workout really helped me lose weight.",
        is_verified_purchase=True,
    )
    db_session.add(review)

    # Update template rating stats
    sample_template.rating_count = 1
    sample_template.rating_average = 5.0

    await db_session.commit()
    await db_session.refresh(review)
    return review


# =============================================================================
# Template Endpoint Tests
# =============================================================================


class TestListTemplates:
    """Tests for GET /api/v1/marketplace/templates."""

    @pytest.mark.asyncio
    async def test_list_templates_authenticated(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Authenticated user can list templates."""
        response = await authenticated_client.get("/api/v1/marketplace/templates")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_templates_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/v1/marketplace/templates")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_category(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can filter templates by category."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/templates", params={"category": "weight_loss"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["category"] == "weight_loss" for t in data)

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_difficulty(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can filter templates by difficulty."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/templates", params={"difficulty": "intermediate"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["difficulty"] == "intermediate" for t in data)

    @pytest.mark.asyncio
    async def test_list_templates_filter_free_only(
        self,
        authenticated_client: AsyncClient,
        sample_template: MarketplaceTemplate,
        sample_free_template: MarketplaceTemplate,
    ):
        """Can filter to show only free templates."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/templates", params={"free_only": True}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["is_free"] is True for t in data)

    @pytest.mark.asyncio
    async def test_list_templates_search(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can search templates by title."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/templates", params={"search": "HIIT"}
        )

        assert response.status_code == 200
        data = response.json()
        assert any("HIIT" in t["title"] for t in data)

    @pytest.mark.asyncio
    async def test_list_templates_pagination(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Pagination parameters work correctly."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/templates", params={"limit": 1, "offset": 0}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1


class TestListFeaturedTemplates:
    """Tests for GET /api/v1/marketplace/templates/featured."""

    @pytest.mark.asyncio
    async def test_list_featured_templates(
        self, authenticated_client: AsyncClient, sample_featured_template: MarketplaceTemplate
    ):
        """Can list featured templates."""
        response = await authenticated_client.get("/api/v1/marketplace/templates/featured")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert all(t["is_featured"] is True for t in data)


class TestGetTemplate:
    """Tests for GET /api/v1/marketplace/templates/{template_id}."""

    @pytest.mark.asyncio
    async def test_get_template_success(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can get template details."""
        response = await authenticated_client.get(
            f"/api/v1/marketplace/templates/{sample_template.id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_template.id)
        assert data["title"] == "HIIT Cardio Program"
        assert data["price_cents"] == 2990
        assert "creator" in data

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent template."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/marketplace/templates/{fake_id}"
        )

        assert response.status_code == 404


class TestGetTemplatePreview:
    """Tests for GET /api/v1/marketplace/templates/{template_id}/preview."""

    @pytest.mark.asyncio
    async def test_get_template_preview(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can get template preview with limited info."""
        response = await authenticated_client.get(
            f"/api/v1/marketplace/templates/{sample_template.id}/preview"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_template.id)
        assert data["title"] == "HIIT Cardio Program"
        assert "creator" in data


class TestCreateTemplate:
    """Tests for POST /api/v1/marketplace/templates."""

    @pytest.mark.asyncio
    async def test_create_template_success(
        self,
        authenticated_client: AsyncClient,
        sample_workout_for_template: Workout,
    ):
        """Can create a new template."""
        payload = {
            "template_type": "workout",
            "workout_id": str(sample_workout_for_template.id),
            "title": "New Amazing Workout",
            "price_cents": 1990,
            "short_description": "An amazing workout program",
            "category": "muscle_gain",
            "difficulty": "intermediate",
        }

        response = await authenticated_client.post(
            "/api/v1/marketplace/templates", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Amazing Workout"
        assert data["price_cents"] == 1990
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_free_template(
        self,
        authenticated_client: AsyncClient,
        sample_workout_for_template: Workout,
    ):
        """Can create a free template."""
        payload = {
            "template_type": "workout",
            "workout_id": str(sample_workout_for_template.id),
            "title": "Free Community Workout",
            "price_cents": 0,
            "category": "general_fitness",
            "difficulty": "beginner",
        }

        response = await authenticated_client.post(
            "/api/v1/marketplace/templates", json=payload
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_free"] is True
        assert data["price_display"] == "Grátis"

    @pytest.mark.asyncio
    async def test_create_template_missing_workout_id(
        self, authenticated_client: AsyncClient
    ):
        """Returns 400 when workout_id is missing for workout template."""
        payload = {
            "template_type": "workout",
            "title": "Invalid Template",
            "price_cents": 1990,
        }

        response = await authenticated_client.post(
            "/api/v1/marketplace/templates", json=payload
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_create_template_validation_error(
        self, authenticated_client: AsyncClient
    ):
        """Returns 422 for invalid data."""
        payload = {
            "template_type": "workout",
            "title": "AB",  # Too short (min 3 chars)
            "price_cents": -100,  # Negative price
        }

        response = await authenticated_client.post(
            "/api/v1/marketplace/templates", json=payload
        )

        assert response.status_code == 422


class TestUpdateTemplate:
    """Tests for PUT /api/v1/marketplace/templates/{template_id}."""

    @pytest.mark.asyncio
    async def test_update_own_template(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Owner can update their template."""
        payload = {
            "title": "Updated HIIT Program",
            "price_cents": 3990,
        }

        response = await authenticated_client.put(
            f"/api/v1/marketplace/templates/{sample_template.id}",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated HIIT Program"
        assert data["price_cents"] == 3990

    @pytest.mark.asyncio
    async def test_update_template_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent template."""
        fake_id = uuid.uuid4()
        payload = {"title": "New Title"}

        response = await authenticated_client.put(
            f"/api/v1/marketplace/templates/{fake_id}", json=payload
        )

        assert response.status_code == 404


class TestDeleteTemplate:
    """Tests for DELETE /api/v1/marketplace/templates/{template_id}."""

    @pytest.mark.asyncio
    async def test_delete_own_template(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        sample_workout_for_template: Workout,
    ):
        """Owner can delete (deactivate) their template."""
        # Create a template to delete
        template = MarketplaceTemplate(
            template_type=TemplateType.WORKOUT,
            workout_id=sample_workout_for_template.id,
            creator_id=sample_user["id"],
            price_cents=1000,
            title="Template to Delete",
            is_active=True,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)

        response = await authenticated_client.delete(
            f"/api/v1/marketplace/templates/{template.id}"
        )

        assert response.status_code == 204


# =============================================================================
# Purchase Endpoint Tests
# =============================================================================


class TestCheckoutTemplate:
    """Tests for POST /api/v1/marketplace/templates/{template_id}/checkout."""

    @pytest.mark.asyncio
    async def test_checkout_free_template(
        self, authenticated_client: AsyncClient, sample_free_template: MarketplaceTemplate
    ):
        """Can checkout a free template immediately."""
        payload = {"payment_provider": "pix"}

        response = await authenticated_client.post(
            f"/api/v1/marketplace/templates/{sample_free_template.id}/checkout",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["price_cents"] == 0

    @pytest.mark.asyncio
    async def test_checkout_paid_template(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can start checkout for a paid template."""
        payload = {"payment_provider": "pix"}

        response = await authenticated_client.post(
            f"/api/v1/marketplace/templates/{sample_template.id}/checkout",
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "pix_copy_paste" in data

    @pytest.mark.asyncio
    async def test_checkout_template_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent template."""
        fake_id = uuid.uuid4()
        payload = {"payment_provider": "pix"}

        response = await authenticated_client.post(
            f"/api/v1/marketplace/templates/{fake_id}/checkout",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_checkout_already_purchased(
        self,
        authenticated_client: AsyncClient,
        sample_template: MarketplaceTemplate,
        sample_completed_purchase: TemplatePurchase,
    ):
        """Returns 400 if user already owns the template."""
        payload = {"payment_provider": "pix"}

        response = await authenticated_client.post(
            f"/api/v1/marketplace/templates/{sample_template.id}/checkout",
            json=payload,
        )

        assert response.status_code == 400
        assert "already own" in response.json()["detail"].lower()


class TestListMyPurchases:
    """Tests for GET /api/v1/marketplace/my-purchases."""

    @pytest.mark.asyncio
    async def test_list_my_purchases(
        self,
        authenticated_client: AsyncClient,
        sample_completed_purchase: TemplatePurchase,
    ):
        """Can list user's purchases."""
        response = await authenticated_client.get("/api/v1/marketplace/my-purchases")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_my_purchases_filter_by_status(
        self,
        authenticated_client: AsyncClient,
        sample_completed_purchase: TemplatePurchase,
    ):
        """Can filter purchases by status."""
        response = await authenticated_client.get(
            "/api/v1/marketplace/my-purchases", params={"status": "completed"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["status"] == "completed" for p in data)


class TestGetPurchaseStatus:
    """Tests for GET /api/v1/marketplace/purchases/{purchase_id}/status."""

    @pytest.mark.asyncio
    async def test_get_purchase_status(
        self,
        authenticated_client: AsyncClient,
        sample_completed_purchase: TemplatePurchase,
    ):
        """Can get purchase status."""
        response = await authenticated_client.get(
            f"/api/v1/marketplace/purchases/{sample_completed_purchase.id}/status"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_get_purchase_status_not_found(self, authenticated_client: AsyncClient):
        """Returns 404 for nonexistent purchase."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/marketplace/purchases/{fake_id}/status"
        )

        assert response.status_code == 404


# =============================================================================
# Review Endpoint Tests
# =============================================================================


class TestCreateReview:
    """Tests for POST /api/v1/marketplace/purchases/{purchase_id}/review."""

    @pytest.mark.asyncio
    async def test_create_review_success(
        self,
        authenticated_client: AsyncClient,
        db_session: AsyncSession,
        sample_user: dict[str, Any],
        sample_template: MarketplaceTemplate,
    ):
        """Can create a review for a completed purchase."""
        # Create a new purchase without review
        purchase = TemplatePurchase(
            marketplace_template_id=sample_template.id,
            buyer_id=sample_user["id"],
            price_cents=sample_template.price_cents,
            currency=sample_template.currency,
            status=PurchaseStatus.COMPLETED,
        )
        db_session.add(purchase)
        await db_session.commit()
        await db_session.refresh(purchase)

        payload = {
            "rating": 5,
            "title": "Great workout!",
            "comment": "Really enjoyed this program.",
        }

        response = await authenticated_client.post(
            f"/api/v1/marketplace/purchases/{purchase.id}/review",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == 5
        assert data["title"] == "Great workout!"
        assert data["is_verified_purchase"] is True

    @pytest.mark.asyncio
    async def test_create_review_purchase_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent purchase."""
        fake_id = uuid.uuid4()
        payload = {"rating": 5}

        response = await authenticated_client.post(
            f"/api/v1/marketplace/purchases/{fake_id}/review",
            json=payload,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_review_invalid_rating(
        self,
        authenticated_client: AsyncClient,
        sample_completed_purchase: TemplatePurchase,
    ):
        """Returns 422 for invalid rating."""
        payload = {"rating": 10}  # Max is 5

        response = await authenticated_client.post(
            f"/api/v1/marketplace/purchases/{sample_completed_purchase.id}/review",
            json=payload,
        )

        assert response.status_code == 422


class TestListTemplateReviews:
    """Tests for GET /api/v1/marketplace/templates/{template_id}/reviews."""

    @pytest.mark.asyncio
    async def test_list_template_reviews(
        self,
        authenticated_client: AsyncClient,
        sample_template: MarketplaceTemplate,
        sample_review: TemplateReview,
    ):
        """Can list reviews for a template."""
        response = await authenticated_client.get(
            f"/api/v1/marketplace/templates/{sample_template.id}/reviews"
        )

        assert response.status_code == 200
        data = response.json()
        assert "reviews" in data
        assert "rating_average" in data
        assert "rating_distribution" in data

    @pytest.mark.asyncio
    async def test_list_template_reviews_not_found(
        self, authenticated_client: AsyncClient
    ):
        """Returns 404 for nonexistent template."""
        fake_id = uuid.uuid4()
        response = await authenticated_client.get(
            f"/api/v1/marketplace/templates/{fake_id}/reviews"
        )

        assert response.status_code == 404


# =============================================================================
# Creator Dashboard Tests
# =============================================================================


class TestCreatorDashboard:
    """Tests for creator dashboard endpoints."""

    @pytest.mark.asyncio
    async def test_get_creator_dashboard(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can get creator dashboard stats."""
        response = await authenticated_client.get("/api/v1/marketplace/creator/dashboard")

        assert response.status_code == 200
        data = response.json()
        assert "total_templates" in data
        assert "total_sales" in data
        assert "total_earnings_cents" in data

    @pytest.mark.asyncio
    async def test_list_my_templates(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can list creator's own templates."""
        response = await authenticated_client.get("/api/v1/marketplace/my-templates")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1


# =============================================================================
# Categories Tests
# =============================================================================


class TestCategories:
    """Tests for category endpoints."""

    @pytest.mark.asyncio
    async def test_list_categories(
        self, authenticated_client: AsyncClient, sample_template: MarketplaceTemplate
    ):
        """Can list categories with template counts."""
        response = await authenticated_client.get("/api/v1/marketplace/categories")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have category info
        if data:
            assert "category" in data[0]
            assert "name" in data[0]
            assert "template_count" in data[0]
