"""Nutrition router with food, diet plan, and meal log endpoints."""
from datetime import date, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import get_db
from src.domains.auth.dependencies import CurrentUser
from src.domains.nutrition.models import FoodCategory, MealType
from src.domains.nutrition.schemas import (
    DailySummary,
    DietAssignmentCreate,
    DietAssignmentResponse,
    DietAssignmentUpdate,
    DietPlanCreate,
    DietPlanListResponse,
    DietPlanMealInput,
    DietPlanResponse,
    DietPlanUpdate,
    FoodCreate,
    FoodListResponse,
    FoodResponse,
    FoodUpdate,
    MealLogCreate,
    MealLogFoodInput,
    MealLogFoodResponse,
    MealLogResponse,
    PatientNoteCreate,
    PatientNoteResponse,
    WeeklySummary,
)
from src.domains.nutrition.service import NutritionService
from src.domains.users.service import UserService

router = APIRouter()


# Food endpoints

@router.get("/foods", response_model=list[FoodListResponse])
async def search_foods(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    search: Annotated[str | None, Query(max_length=100)] = None,
    category: Annotated[FoodCategory | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[FoodListResponse]:
    """Search foods in the database."""
    nutrition_service = NutritionService(db)
    foods = await nutrition_service.search_foods(
        user_id=current_user.id,
        search=search,
        category=category,
        limit=limit,
        offset=offset,
    )
    return [FoodListResponse.model_validate(f) for f in foods]


@router.get("/foods/barcode/{barcode}", response_model=FoodResponse)
async def get_food_by_barcode(
    barcode: str,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FoodResponse:
    """Get food by barcode."""
    nutrition_service = NutritionService(db)
    food = await nutrition_service.get_food_by_barcode(barcode)

    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Food not found",
        )

    return FoodResponse.model_validate(food)


@router.get("/foods/{food_id}", response_model=FoodResponse)
async def get_food(
    food_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FoodResponse:
    """Get food details."""
    nutrition_service = NutritionService(db)
    food = await nutrition_service.get_food_by_id(food_id)

    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Food not found",
        )

    return FoodResponse.model_validate(food)


@router.post("/foods", response_model=FoodResponse, status_code=status.HTTP_201_CREATED)
async def create_food(
    request: FoodCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FoodResponse:
    """Create a new food item."""
    nutrition_service = NutritionService(db)

    # Check barcode uniqueness
    if request.barcode:
        existing = await nutrition_service.get_food_by_barcode(request.barcode)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Food with this barcode already exists",
            )

    food = await nutrition_service.create_food(
        created_by_id=current_user.id,
        **request.model_dump(),
    )

    return FoodResponse.model_validate(food)


@router.put("/foods/{food_id}", response_model=FoodResponse)
async def update_food(
    food_id: UUID,
    request: FoodUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FoodResponse:
    """Update a food item (owner only)."""
    nutrition_service = NutritionService(db)
    food = await nutrition_service.get_food_by_id(food_id)

    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Food not found",
        )

    if food.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit foods you created",
        )

    updated = await nutrition_service.update_food(
        food=food,
        **request.model_dump(exclude_unset=True),
    )

    return FoodResponse.model_validate(updated)


# Favorites

@router.get("/foods/favorites", response_model=list[FoodResponse])
async def get_favorite_foods(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FoodResponse]:
    """Get user's favorite foods."""
    nutrition_service = NutritionService(db)
    foods = await nutrition_service.get_user_favorites(current_user.id)
    return [FoodResponse.model_validate(f) for f in foods]


@router.post("/foods/{food_id}/favorite", status_code=status.HTTP_201_CREATED)
async def add_favorite(
    food_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Add food to favorites."""
    nutrition_service = NutritionService(db)

    food = await nutrition_service.get_food_by_id(food_id)
    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Food not found",
        )

    await nutrition_service.add_to_favorites(current_user.id, food_id)
    return {"message": "Added to favorites"}


@router.delete("/foods/{food_id}/favorite", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    food_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove food from favorites."""
    nutrition_service = NutritionService(db)
    await nutrition_service.remove_from_favorites(current_user.id, food_id)


# Diet plan endpoints

@router.get("/diet-plans", response_model=list[DietPlanListResponse])
async def list_diet_plans(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    organization_id: Annotated[UUID | None, Query()] = None,
    templates_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[DietPlanListResponse]:
    """List diet plans."""
    nutrition_service = NutritionService(db)
    plans = await nutrition_service.list_diet_plans(
        user_id=current_user.id,
        organization_id=organization_id,
        templates_only=templates_only,
        limit=limit,
        offset=offset,
    )

    return [
        DietPlanListResponse(
            id=p.id,
            name=p.name,
            target_calories=p.target_calories,
            is_template=p.is_template,
            meal_count=len(p.meals),
        )
        for p in plans
    ]


@router.get("/diet-plans/{plan_id}", response_model=DietPlanResponse)
async def get_diet_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DietPlanResponse:
    """Get diet plan details."""
    nutrition_service = NutritionService(db)
    plan = await nutrition_service.get_diet_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet plan not found",
        )

    return DietPlanResponse.model_validate(plan)


@router.post("/diet-plans", response_model=DietPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_diet_plan(
    request: DietPlanCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DietPlanResponse:
    """Create a new diet plan."""
    nutrition_service = NutritionService(db)

    plan = await nutrition_service.create_diet_plan(
        created_by_id=current_user.id,
        name=request.name,
        description=request.description,
        target_calories=request.target_calories,
        target_protein=request.target_protein,
        target_carbs=request.target_carbs,
        target_fat=request.target_fat,
        tags=request.tags,
        is_template=request.is_template,
        is_public=request.is_public,
        organization_id=request.organization_id,
    )

    # Add meals if provided
    if request.meals:
        for meal_input in request.meals:
            meal = await nutrition_service.add_meal_to_plan(
                plan_id=plan.id,
                name=meal_input.name,
                meal_time=meal_input.meal_time,
                order=meal_input.order,
                notes=meal_input.notes,
            )
            for food_input in meal_input.foods:
                await nutrition_service.add_food_to_meal(
                    meal_id=meal.id,
                    food_id=food_input.food_id,
                    servings=food_input.servings,
                    portion_description=food_input.portion_description,
                    notes=food_input.notes,
                )

        # Refresh to get full data
        plan = await nutrition_service.get_diet_plan_by_id(plan.id)

    return DietPlanResponse.model_validate(plan)


@router.put("/diet-plans/{plan_id}", response_model=DietPlanResponse)
async def update_diet_plan(
    plan_id: UUID,
    request: DietPlanUpdate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DietPlanResponse:
    """Update a diet plan."""
    nutrition_service = NutritionService(db)
    plan = await nutrition_service.get_diet_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own diet plans",
        )

    updated = await nutrition_service.update_diet_plan(
        plan=plan,
        **request.model_dump(exclude_unset=True),
    )

    return DietPlanResponse.model_validate(updated)


@router.delete("/diet-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diet_plan(
    plan_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a diet plan."""
    nutrition_service = NutritionService(db)
    plan = await nutrition_service.get_diet_plan_by_id(plan_id)

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet plan not found",
        )

    if plan.created_by_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own diet plans",
        )

    await nutrition_service.delete_diet_plan(plan)


# Diet assignment endpoints

@router.get("/assignments", response_model=list[DietAssignmentResponse])
async def list_diet_assignments(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    active_only: Annotated[bool, Query()] = True,
) -> list[DietAssignmentResponse]:
    """List diet assignments for the current user (as patient)."""
    nutrition_service = NutritionService(db)
    user_service = UserService(db)

    assignments = await nutrition_service.list_student_assignments(
        student_id=current_user.id,
        active_only=active_only,
    )

    result = []
    for a in assignments:
        student = await user_service.get_user_by_id(a.student_id)
        result.append(
            DietAssignmentResponse(
                id=a.id,
                plan_id=a.plan_id,
                student_id=a.student_id,
                nutritionist_id=a.nutritionist_id,
                organization_id=a.organization_id,
                start_date=a.start_date,
                end_date=a.end_date,
                is_active=a.is_active,
                notes=a.notes,
                created_at=a.created_at,
                plan_name=a.plan.name if a.plan else "",
                student_name=student.name if student else "",
            )
        )

    return result


@router.post("/assignments", response_model=DietAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_diet_assignment(
    request: DietAssignmentCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DietAssignmentResponse:
    """Assign a diet plan to a patient."""
    nutrition_service = NutritionService(db)
    user_service = UserService(db)

    # Verify plan exists
    plan = await nutrition_service.get_diet_plan_by_id(request.plan_id)
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diet plan not found",
        )

    # Verify student exists
    student = await user_service.get_user_by_id(request.student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    assignment = await nutrition_service.create_assignment(
        plan_id=request.plan_id,
        student_id=request.student_id,
        nutritionist_id=current_user.id,
        start_date=request.start_date,
        end_date=request.end_date,
        notes=request.notes,
        organization_id=request.organization_id,
    )

    return DietAssignmentResponse(
        id=assignment.id,
        plan_id=assignment.plan_id,
        student_id=assignment.student_id,
        nutritionist_id=assignment.nutritionist_id,
        organization_id=assignment.organization_id,
        start_date=assignment.start_date,
        end_date=assignment.end_date,
        is_active=assignment.is_active,
        notes=assignment.notes,
        created_at=assignment.created_at,
        plan_name=plan.name,
        student_name=student.name,
    )


# Meal log endpoints

@router.get("/meals", response_model=list[MealLogResponse])
async def list_meal_logs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: Annotated[date | None, Query()] = None,
    to_date: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MealLogResponse]:
    """List meal logs for the current user."""
    nutrition_service = NutritionService(db)
    logs = await nutrition_service.list_meal_logs(
        user_id=current_user.id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )

    return [
        MealLogResponse(
            id=log.id,
            user_id=log.user_id,
            meal_type=log.meal_type,
            logged_at=log.logged_at,
            notes=log.notes,
            foods=[
                MealLogFoodResponse(
                    id=f.id,
                    food_id=f.food_id,
                    servings=f.servings,
                    portion_description=f.portion_description,
                    food=FoodResponse.model_validate(f.food),
                    calories=f.calories,
                    protein=f.protein,
                    carbs=f.carbs,
                    fat=f.fat,
                )
                for f in log.foods
            ],
            total_calories=log.total_calories,
            total_protein=log.total_protein,
            total_carbs=log.total_carbs,
            total_fat=log.total_fat,
        )
        for log in logs
    ]


@router.post("/meals", response_model=MealLogResponse, status_code=status.HTTP_201_CREATED)
async def create_meal_log(
    request: MealLogCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MealLogResponse:
    """Log a meal."""
    nutrition_service = NutritionService(db)

    log = await nutrition_service.create_meal_log(
        user_id=current_user.id,
        meal_type=request.meal_type,
        logged_at=request.logged_at,
        notes=request.notes,
    )

    # Add foods
    for food_input in request.foods:
        await nutrition_service.add_food_to_log(
            meal_log_id=log.id,
            food_id=food_input.food_id,
            servings=food_input.servings,
            portion_description=food_input.portion_description,
        )

    # Refresh to get full data
    log = await nutrition_service.get_meal_log_by_id(log.id)

    return MealLogResponse(
        id=log.id,
        user_id=log.user_id,
        meal_type=log.meal_type,
        logged_at=log.logged_at,
        notes=log.notes,
        foods=[
            MealLogFoodResponse(
                id=f.id,
                food_id=f.food_id,
                servings=f.servings,
                portion_description=f.portion_description,
                food=FoodResponse.model_validate(f.food),
                calories=f.calories,
                protein=f.protein,
                carbs=f.carbs,
                fat=f.fat,
            )
            for f in log.foods
        ],
        total_calories=log.total_calories,
        total_protein=log.total_protein,
        total_carbs=log.total_carbs,
        total_fat=log.total_fat,
    )


@router.delete("/meals/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal_log(
    log_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a meal log."""
    nutrition_service = NutritionService(db)
    log = await nutrition_service.get_meal_log_by_id(log_id)

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Meal log not found",
        )

    if log.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own meal logs",
        )

    await nutrition_service.delete_meal_log(log)


# Summary endpoints

@router.get("/summary/daily", response_model=DailySummary)
async def get_daily_summary(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    target_date: Annotated[date | None, Query()] = None,
) -> DailySummary:
    """Get daily nutrition summary."""
    nutrition_service = NutritionService(db)
    summary = await nutrition_service.get_daily_summary(
        user_id=current_user.id,
        target_date=target_date or date.today(),
    )
    return DailySummary(**summary)


@router.get("/summary/weekly", response_model=WeeklySummary)
async def get_weekly_summary(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    start_date: Annotated[date | None, Query()] = None,
) -> WeeklySummary:
    """Get weekly nutrition summary."""
    nutrition_service = NutritionService(db)

    if not start_date:
        # Start from beginning of current week (Monday)
        today = date.today()
        start_date = today - timedelta(days=today.weekday())

    summary = await nutrition_service.get_weekly_summary(
        user_id=current_user.id,
        start_date=start_date,
    )
    return WeeklySummary(**summary)


# Patient notes

@router.post("/patients/{patient_id}/notes", response_model=PatientNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_note(
    patient_id: UUID,
    request: PatientNoteCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PatientNoteResponse:
    """Create a note for a patient."""
    nutrition_service = NutritionService(db)
    user_service = UserService(db)

    # Verify patient exists
    patient = await user_service.get_user_by_id(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    note = await nutrition_service.create_patient_note(
        patient_id=patient_id,
        nutritionist_id=current_user.id,
        content=request.content,
        category=request.category,
        is_private=request.is_private,
    )

    return PatientNoteResponse.model_validate(note)


@router.get("/patients/{patient_id}/notes", response_model=list[PatientNoteResponse])
async def list_patient_notes(
    patient_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PatientNoteResponse]:
    """List notes for a patient."""
    nutrition_service = NutritionService(db)

    # If viewing own notes, include private; otherwise only public
    include_private = patient_id == current_user.id

    notes = await nutrition_service.list_patient_notes(
        patient_id=patient_id,
        include_private=include_private,
    )

    return [PatientNoteResponse.model_validate(n) for n in notes]
