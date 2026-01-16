"""Nutrition service with database operations."""
import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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


class NutritionService:
    """Service for handling nutrition operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # Food operations

    async def get_food_by_id(self, food_id: uuid.UUID) -> Food | None:
        """Get a food by ID."""
        result = await self.db.execute(
            select(Food).where(Food.id == food_id)
        )
        return result.scalar_one_or_none()

    async def get_food_by_barcode(self, barcode: str) -> Food | None:
        """Get a food by barcode."""
        result = await self.db.execute(
            select(Food).where(Food.barcode == barcode)
        )
        return result.scalar_one_or_none()

    async def search_foods(
        self,
        user_id: uuid.UUID | None = None,
        search: str | None = None,
        category: FoodCategory | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Food]:
        """Search foods with filters."""
        query = select(Food)

        # Filter by public or user's custom foods
        if user_id:
            query = query.where(
                or_(
                    Food.is_public == True,
                    Food.created_by_id == user_id,
                )
            )
        else:
            query = query.where(Food.is_public == True)

        if search:
            query = query.where(
                or_(
                    Food.name.ilike(f"%{search}%"),
                    Food.brand.ilike(f"%{search}%"),
                )
            )

        if category:
            query = query.where(Food.category == category)

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_food(
        self,
        created_by_id: uuid.UUID,
        name: str,
        calories: float,
        protein: float,
        carbs: float,
        fat: float,
        brand: str | None = None,
        barcode: str | None = None,
        fiber: float | None = None,
        sodium: float | None = None,
        sugar: float | None = None,
        portion_size: str = "100g",
        portion_weight_g: float = 100.0,
        category: FoodCategory = FoodCategory.OTHER,
        image_url: str | None = None,
        is_public: bool = True,
    ) -> Food:
        """Create a new food."""
        food = Food(
            name=name,
            brand=brand,
            barcode=barcode,
            calories=calories,
            protein=protein,
            carbs=carbs,
            fat=fat,
            fiber=fiber,
            sodium=sodium,
            sugar=sugar,
            portion_size=portion_size,
            portion_weight_g=portion_weight_g,
            category=category,
            image_url=image_url,
            is_public=is_public,
            created_by_id=created_by_id,
        )
        self.db.add(food)
        await self.db.commit()
        await self.db.refresh(food)
        return food

    async def update_food(
        self,
        food: Food,
        **kwargs,
    ) -> Food:
        """Update a food."""
        for key, value in kwargs.items():
            if value is not None and hasattr(food, key):
                setattr(food, key, value)

        await self.db.commit()
        await self.db.refresh(food)
        return food

    # Favorites

    async def get_user_favorites(
        self,
        user_id: uuid.UUID,
    ) -> list[Food]:
        """Get user's favorite foods."""
        result = await self.db.execute(
            select(Food)
            .join(UserFavoriteFood)
            .where(UserFavoriteFood.user_id == user_id)
            .order_by(UserFavoriteFood.added_at.desc())
        )
        return list(result.scalars().all())

    async def add_to_favorites(
        self,
        user_id: uuid.UUID,
        food_id: uuid.UUID,
    ) -> None:
        """Add food to user's favorites."""
        favorite = UserFavoriteFood(
            user_id=user_id,
            food_id=food_id,
        )
        self.db.add(favorite)
        await self.db.commit()

    async def remove_from_favorites(
        self,
        user_id: uuid.UUID,
        food_id: uuid.UUID,
    ) -> None:
        """Remove food from user's favorites."""
        result = await self.db.execute(
            select(UserFavoriteFood).where(
                and_(
                    UserFavoriteFood.user_id == user_id,
                    UserFavoriteFood.food_id == food_id,
                )
            )
        )
        favorite = result.scalar_one_or_none()
        if favorite:
            await self.db.delete(favorite)
            await self.db.commit()

    # Diet plan operations

    async def get_diet_plan_by_id(
        self,
        plan_id: uuid.UUID,
    ) -> DietPlan | None:
        """Get a diet plan by ID with meals."""
        result = await self.db.execute(
            select(DietPlan)
            .where(DietPlan.id == plan_id)
            .options(
                selectinload(DietPlan.meals).selectinload(DietPlanMeal.foods).selectinload(DietPlanMealFood.food)
            )
        )
        return result.scalar_one_or_none()

    async def list_diet_plans(
        self,
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        templates_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DietPlan]:
        """List diet plans for a user."""
        query = select(DietPlan).options(
            selectinload(DietPlan.meals)
        )

        conditions = [DietPlan.created_by_id == user_id]
        if organization_id:
            conditions.append(DietPlan.organization_id == organization_id)
        conditions.append(and_(DietPlan.is_template == True, DietPlan.is_public == True))

        query = query.where(or_(*conditions))

        if templates_only:
            query = query.where(DietPlan.is_template == True)

        query = query.order_by(DietPlan.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_diet_plan(
        self,
        created_by_id: uuid.UUID,
        name: str,
        target_calories: int = 2000,
        target_protein: int = 150,
        target_carbs: int = 200,
        target_fat: int = 70,
        description: str | None = None,
        tags: list[str] | None = None,
        is_template: bool = False,
        is_public: bool = False,
        organization_id: uuid.UUID | None = None,
    ) -> DietPlan:
        """Create a new diet plan."""
        plan = DietPlan(
            name=name,
            description=description,
            target_calories=target_calories,
            target_protein=target_protein,
            target_carbs=target_carbs,
            target_fat=target_fat,
            tags=tags,
            is_template=is_template,
            is_public=is_public,
            created_by_id=created_by_id,
            organization_id=organization_id,
        )
        self.db.add(plan)
        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def update_diet_plan(
        self,
        plan: DietPlan,
        **kwargs,
    ) -> DietPlan:
        """Update a diet plan."""
        for key, value in kwargs.items():
            if value is not None and hasattr(plan, key):
                setattr(plan, key, value)

        await self.db.commit()
        await self.db.refresh(plan)
        return plan

    async def delete_diet_plan(self, plan: DietPlan) -> None:
        """Delete a diet plan."""
        await self.db.delete(plan)
        await self.db.commit()

    async def add_meal_to_plan(
        self,
        plan_id: uuid.UUID,
        name: str,
        meal_time: time,
        order: int = 0,
        notes: str | None = None,
    ) -> DietPlanMeal:
        """Add a meal to a diet plan."""
        meal = DietPlanMeal(
            plan_id=plan_id,
            name=name,
            meal_time=meal_time,
            order=order,
            notes=notes,
        )
        self.db.add(meal)
        await self.db.commit()
        await self.db.refresh(meal)
        return meal

    async def add_food_to_meal(
        self,
        meal_id: uuid.UUID,
        food_id: uuid.UUID,
        servings: float = 1.0,
        portion_description: str | None = None,
        notes: str | None = None,
    ) -> DietPlanMealFood:
        """Add a food to a diet plan meal."""
        meal_food = DietPlanMealFood(
            meal_id=meal_id,
            food_id=food_id,
            servings=servings,
            portion_description=portion_description,
            notes=notes,
        )
        self.db.add(meal_food)
        await self.db.commit()
        await self.db.refresh(meal_food)
        return meal_food

    # Assignment operations

    async def get_assignment_by_id(
        self,
        assignment_id: uuid.UUID,
    ) -> DietAssignment | None:
        """Get a diet assignment by ID."""
        result = await self.db.execute(
            select(DietAssignment)
            .where(DietAssignment.id == assignment_id)
            .options(selectinload(DietAssignment.plan))
        )
        return result.scalar_one_or_none()

    async def list_student_assignments(
        self,
        student_id: uuid.UUID,
        active_only: bool = True,
    ) -> list[DietAssignment]:
        """List diet assignments for a student."""
        query = select(DietAssignment).where(
            DietAssignment.student_id == student_id
        ).options(selectinload(DietAssignment.plan))

        if active_only:
            query = query.where(DietAssignment.is_active == True)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_assignment(
        self,
        plan_id: uuid.UUID,
        student_id: uuid.UUID,
        nutritionist_id: uuid.UUID,
        start_date: date,
        end_date: date | None = None,
        notes: str | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> DietAssignment:
        """Create a diet assignment."""
        assignment = DietAssignment(
            plan_id=plan_id,
            student_id=student_id,
            nutritionist_id=nutritionist_id,
            start_date=start_date,
            end_date=end_date,
            notes=notes,
            organization_id=organization_id,
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    async def update_assignment(
        self,
        assignment: DietAssignment,
        **kwargs,
    ) -> DietAssignment:
        """Update a diet assignment."""
        for key, value in kwargs.items():
            if value is not None and hasattr(assignment, key):
                setattr(assignment, key, value)

        await self.db.commit()
        await self.db.refresh(assignment)
        return assignment

    # Meal log operations

    async def get_meal_log_by_id(
        self,
        log_id: uuid.UUID,
    ) -> MealLog | None:
        """Get a meal log by ID."""
        result = await self.db.execute(
            select(MealLog)
            .where(MealLog.id == log_id)
            .options(selectinload(MealLog.foods).selectinload(MealLogFood.food))
        )
        return result.scalar_one_or_none()

    async def list_meal_logs(
        self,
        user_id: uuid.UUID,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MealLog]:
        """List meal logs for a user."""
        query = select(MealLog).where(
            MealLog.user_id == user_id
        ).options(selectinload(MealLog.foods).selectinload(MealLogFood.food))

        if from_date:
            query = query.where(MealLog.logged_at >= datetime.combine(from_date, time.min))
        if to_date:
            query = query.where(MealLog.logged_at <= datetime.combine(to_date, time.max))

        query = query.order_by(MealLog.logged_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create_meal_log(
        self,
        user_id: uuid.UUID,
        meal_type: MealType,
        logged_at: datetime | None = None,
        notes: str | None = None,
    ) -> MealLog:
        """Create a meal log."""
        log = MealLog(
            user_id=user_id,
            meal_type=meal_type,
            logged_at=logged_at or datetime.now(timezone.utc),
            notes=notes,
        )
        self.db.add(log)
        await self.db.commit()
        await self.db.refresh(log)
        return log

    async def add_food_to_log(
        self,
        meal_log_id: uuid.UUID,
        food_id: uuid.UUID,
        servings: float = 1.0,
        portion_description: str | None = None,
    ) -> MealLogFood:
        """Add a food to a meal log."""
        log_food = MealLogFood(
            meal_log_id=meal_log_id,
            food_id=food_id,
            servings=servings,
            portion_description=portion_description,
        )
        self.db.add(log_food)
        await self.db.commit()
        await self.db.refresh(log_food)
        return log_food

    async def delete_meal_log(self, log: MealLog) -> None:
        """Delete a meal log."""
        await self.db.delete(log)
        await self.db.commit()

    async def get_daily_summary(
        self,
        user_id: uuid.UUID,
        target_date: date,
    ) -> dict:
        """Get daily nutrition summary."""
        start = datetime.combine(target_date, time.min)
        end = datetime.combine(target_date, time.max)

        logs = await self.list_meal_logs(
            user_id=user_id,
            from_date=target_date,
            to_date=target_date,
        )

        total_calories = 0.0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0

        for log in logs:
            total_calories += log.total_calories
            total_protein += log.total_protein
            total_carbs += log.total_carbs
            total_fat += log.total_fat

        return {
            "date": target_date,
            "total_calories": total_calories,
            "total_protein": total_protein,
            "total_carbs": total_carbs,
            "total_fat": total_fat,
            "meal_count": len(logs),
        }

    async def get_weekly_summary(
        self,
        user_id: uuid.UUID,
        start_date: date,
    ) -> dict:
        """Get weekly nutrition summary."""
        end_date = start_date + timedelta(days=6)

        daily_totals = []
        for i in range(7):
            day = start_date + timedelta(days=i)
            summary = await self.get_daily_summary(user_id, day)
            if summary["meal_count"] > 0:
                daily_totals.append(summary)

        days_logged = len(daily_totals)
        if days_logged == 0:
            return {
                "start_date": start_date,
                "end_date": end_date,
                "avg_calories": 0,
                "avg_protein": 0,
                "avg_carbs": 0,
                "avg_fat": 0,
                "days_logged": 0,
            }

        return {
            "start_date": start_date,
            "end_date": end_date,
            "avg_calories": sum(d["total_calories"] for d in daily_totals) / days_logged,
            "avg_protein": sum(d["total_protein"] for d in daily_totals) / days_logged,
            "avg_carbs": sum(d["total_carbs"] for d in daily_totals) / days_logged,
            "avg_fat": sum(d["total_fat"] for d in daily_totals) / days_logged,
            "days_logged": days_logged,
        }

    # Patient notes

    async def create_patient_note(
        self,
        patient_id: uuid.UUID,
        nutritionist_id: uuid.UUID,
        content: str,
        category: str = "general",
        is_private: bool = False,
    ) -> PatientNote:
        """Create a patient note."""
        note = PatientNote(
            patient_id=patient_id,
            nutritionist_id=nutritionist_id,
            content=content,
            category=category,
            is_private=is_private,
        )
        self.db.add(note)
        await self.db.commit()
        await self.db.refresh(note)
        return note

    async def list_patient_notes(
        self,
        patient_id: uuid.UUID,
        nutritionist_id: uuid.UUID | None = None,
        include_private: bool = False,
    ) -> list[PatientNote]:
        """List notes for a patient."""
        query = select(PatientNote).where(PatientNote.patient_id == patient_id)

        if nutritionist_id:
            query = query.where(PatientNote.nutritionist_id == nutritionist_id)

        if not include_private:
            query = query.where(PatientNote.is_private == False)

        query = query.order_by(PatientNote.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
