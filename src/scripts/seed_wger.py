"""
Seed script for importing exercises from WGER API (free, no API key required).

WGER provides ~400 exercises with images.
API docs: https://wger.de/api/v2/

Run with:
    DATABASE_URL="postgresql+asyncpg://..." python -m src.scripts.seed_wger
"""

import asyncio
import re
import sys
from pathlib import Path

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import Exercise, MuscleGroup

logger = structlog.get_logger(__name__)

WGER_API_URL = "https://wger.de/api/v2"

# WGER muscle IDs to our MuscleGroup
MUSCLE_MAPPING = {
    1: MuscleGroup.BICEPS,       # Biceps brachii
    2: MuscleGroup.SHOULDERS,    # Anterior deltoid
    3: MuscleGroup.SHOULDERS,    # Serratus anterior
    4: MuscleGroup.CHEST,        # Pectoralis major
    5: MuscleGroup.TRICEPS,      # Triceps brachii
    6: MuscleGroup.ABS,          # Rectus abdominis
    7: MuscleGroup.CALVES,       # Gastrocnemius
    8: MuscleGroup.GLUTES,       # Gluteus maximus
    9: MuscleGroup.HAMSTRINGS,   # Biceps femoris
    10: MuscleGroup.QUADRICEPS,  # Quadriceps femoris
    11: MuscleGroup.FOREARMS,    # Brachialis
    12: MuscleGroup.BACK,        # Latissimus dorsi
    13: MuscleGroup.BACK,        # Trapezius
    14: MuscleGroup.ABS,         # Obliquus externus abdominis
    15: MuscleGroup.CALVES,      # Soleus
}

# WGER category IDs to MuscleGroup
CATEGORY_MAPPING = {
    8: MuscleGroup.BICEPS,       # Arms
    9: MuscleGroup.QUADRICEPS,   # Legs
    10: MuscleGroup.ABS,         # Abs
    11: MuscleGroup.CHEST,       # Chest
    12: MuscleGroup.BACK,        # Back
    13: MuscleGroup.SHOULDERS,   # Shoulders
    14: MuscleGroup.CALVES,      # Calves
    15: MuscleGroup.CARDIO,      # Cardio
}

# WGER equipment IDs
EQUIPMENT_MAPPING = {
    1: "barbell",
    2: "ez_bar",
    3: "dumbbell",
    4: "gym_mat",
    5: "swiss_ball",
    6: "pull_up_bar",
    7: "bodyweight",
    8: "bench",
    9: "incline_bench",
    10: "kettlebell",
}


async def fetch_exercise_info() -> list[dict]:
    """Fetch all exercise info from WGER API."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        exercises = []
        next_url = f"{WGER_API_URL}/exerciseinfo/?limit=50"

        while next_url:
            logger.info("fetching_exercises", url=next_url)
            response = await client.get(next_url)

            if response.status_code != 200:
                logger.error("api_request_failed", status_code=response.status_code)
                break

            data = response.json()
            exercises.extend(data.get("results", []))
            next_url = data.get("next")

            # Progress
            logger.info("exercises_fetched_so_far", count=len(exercises))

        logger.info("total_exercises_fetched", count=len(exercises), source="WGER API")
        return exercises


def get_english_translation(exercise_info: dict) -> dict | None:
    """Get English translation from exercise info."""
    translations = exercise_info.get("translations", [])

    # Prefer English (language=2)
    for t in translations:
        if t.get("language") == 2:
            return t

    # Fallback to first translation with a name
    for t in translations:
        if t.get("name"):
            return t

    return None


def get_muscle_group(exercise_info: dict) -> tuple[MuscleGroup, list[str] | None]:
    """Determine muscle group from WGER exercise info."""
    muscles = exercise_info.get("muscles", [])
    secondary = exercise_info.get("muscles_secondary", [])
    category = exercise_info.get("category", {})
    category_id = category.get("id") if isinstance(category, dict) else None

    primary = MuscleGroup.FULL_BODY
    secondary_names = []

    # Get primary from first muscle
    if muscles:
        muscle_id = muscles[0].get("id") if isinstance(muscles[0], dict) else muscles[0]
        primary = MUSCLE_MAPPING.get(muscle_id, MuscleGroup.FULL_BODY)

    # If no muscles, use category
    if primary == MuscleGroup.FULL_BODY and category_id:
        primary = CATEGORY_MAPPING.get(category_id, MuscleGroup.FULL_BODY)

    # Get secondary muscles
    for m in secondary:
        muscle_id = m.get("id") if isinstance(m, dict) else m
        if muscle_id in MUSCLE_MAPPING:
            muscle_name = MUSCLE_MAPPING[muscle_id].value
            if muscle_name not in secondary_names:
                secondary_names.append(muscle_name)

    return primary, secondary_names if secondary_names else None


def get_equipment(exercise_info: dict) -> list[str] | None:
    """Get equipment list from exercise info."""
    equipment_list = exercise_info.get("equipment", [])
    result = []

    for eq in equipment_list:
        eq_id = eq.get("id") if isinstance(eq, dict) else eq
        if eq_id in EQUIPMENT_MAPPING:
            result.append(EQUIPMENT_MAPPING[eq_id])

    return result if result else None


def get_image_url(exercise_info: dict) -> str | None:
    """Get main image URL from exercise info."""
    images = exercise_info.get("images", [])

    # Prefer main image
    for img in images:
        if img.get("is_main") and img.get("image"):
            return img["image"]

    # Fallback to first image
    for img in images:
        if img.get("image"):
            return img["image"]

    return None


def clean_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text).strip()


async def seed_exercises_from_wger(session: AsyncSession, clear_existing: bool = False) -> int:
    """Seed the database with exercises from WGER API."""

    if clear_existing:
        logger.info("clearing_existing_exercises")
        await session.execute(delete(Exercise).where(Exercise.is_custom == False))
        await session.commit()

    # Fetch all exercise info (includes translations, images, muscles)
    exercises = await fetch_exercise_info()

    if not exercises:
        return 0

    count = 0
    seen_names = set()
    errors = 0

    logger.info("processing_exercises", count=len(exercises))
    for ex in exercises:
        try:
            # Get English translation
            translation = get_english_translation(ex)
            if not translation:
                continue

            name = translation.get("name", "").strip()
            if not name or len(name) < 3:
                continue

            # Skip duplicates
            name_lower = name.lower()
            if name_lower in seen_names:
                continue
            seen_names.add(name_lower)

            # Get muscle groups
            muscle_group, secondary_muscles = get_muscle_group(ex)

            # Get equipment
            equipment = get_equipment(ex)

            # Get image - skip exercises without images
            image_url = get_image_url(ex)
            if not image_url:
                continue

            # Get description
            description = translation.get("description", "")
            if description:
                description = clean_html(description)[:500]
            else:
                description = None

            exercise = Exercise(
                name=name.title(),
                description=description,
                muscle_group=muscle_group,
                secondary_muscles=secondary_muscles,
                equipment=equipment,
                image_url=image_url,
                video_url=None,
                instructions=None,
                is_custom=False,
                is_public=True,
            )
            session.add(exercise)
            count += 1

            if count % 50 == 0:
                await session.commit()
                logger.info("batch_inserted", count=count)

        except Exception as e:
            errors += 1
            if errors < 5:
                logger.error("exercise_processing_failed", error=str(e))
            continue

    logger.info("final_commit", exercise_count=count, error_count=errors)
    await session.commit()
    return count


async def main():
    """Main function to run the seed."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed exercises from WGER API")
    parser.add_argument("--clear", action="store_true", help="Clear existing public exercises first")
    args = parser.parse_args()

    logger.info("wger_seed_script_started")

    async with AsyncSessionLocal() as session:
        count = await seed_exercises_from_wger(session, clear_existing=args.clear)

    if count > 0:
        logger.info("wger_seed_script_completed", exercise_count=count)
    else:
        logger.info("no_exercises_seeded")


if __name__ == "__main__":
    asyncio.run(main())
