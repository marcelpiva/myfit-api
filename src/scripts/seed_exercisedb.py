"""
Seed script for importing exercises from ExerciseDB API.

ExerciseDB provides 1300+ exercises with GIF animations.

Run with:
    DATABASE_URL="postgresql+asyncpg://..." python -m src.scripts.seed_exercisedb

Requires: EXERCISEDB_API_KEY environment variable (get from RapidAPI)
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import Exercise, MuscleGroup

logger = structlog.get_logger(__name__)

# ExerciseDB API configuration
EXERCISEDB_API_URL = "https://exercisedb.p.rapidapi.com"
EXERCISEDB_API_KEY = os.getenv("EXERCISEDB_API_KEY", "")

# Mapping from ExerciseDB bodyPart/target to our MuscleGroup enum
BODY_PART_MAPPING = {
    "back": MuscleGroup.BACK,
    "cardio": MuscleGroup.CARDIO,
    "chest": MuscleGroup.CHEST,
    "lower arms": MuscleGroup.FOREARMS,
    "lower legs": MuscleGroup.CALVES,
    "neck": MuscleGroup.SHOULDERS,  # Map to shoulders
    "shoulders": MuscleGroup.SHOULDERS,
    "upper arms": MuscleGroup.BICEPS,  # Will be refined by target
    "upper legs": MuscleGroup.QUADRICEPS,  # Will be refined by target
    "waist": MuscleGroup.ABS,
}

TARGET_MAPPING = {
    # Back
    "lats": MuscleGroup.BACK,
    "traps": MuscleGroup.BACK,
    "upper back": MuscleGroup.BACK,
    "spine": MuscleGroup.BACK,
    # Chest
    "pectorals": MuscleGroup.CHEST,
    # Shoulders
    "delts": MuscleGroup.SHOULDERS,
    "serratus anterior": MuscleGroup.SHOULDERS,
    "levator scapulae": MuscleGroup.SHOULDERS,
    # Arms
    "biceps": MuscleGroup.BICEPS,
    "triceps": MuscleGroup.TRICEPS,
    "forearms": MuscleGroup.FOREARMS,
    # Core
    "abs": MuscleGroup.ABS,
    "abductors": MuscleGroup.GLUTES,
    "adductors": MuscleGroup.QUADRICEPS,
    # Legs
    "glutes": MuscleGroup.GLUTES,
    "hamstrings": MuscleGroup.HAMSTRINGS,
    "quads": MuscleGroup.QUADRICEPS,
    "calves": MuscleGroup.CALVES,
    # Cardio
    "cardiovascular system": MuscleGroup.CARDIO,
}


def get_muscle_group(body_part: str, target: str) -> MuscleGroup:
    """Map ExerciseDB body part and target to our MuscleGroup enum."""
    # First try target (more specific)
    target_lower = target.lower()
    if target_lower in TARGET_MAPPING:
        return TARGET_MAPPING[target_lower]

    # Then try body part
    body_part_lower = body_part.lower()
    if body_part_lower in BODY_PART_MAPPING:
        return BODY_PART_MAPPING[body_part_lower]

    # Default to full body
    return MuscleGroup.FULL_BODY


async def fetch_all_exercises() -> list[dict]:
    """Fetch all exercises from ExerciseDB API."""
    if not EXERCISEDB_API_KEY:
        logger.error("api_key_not_set", variable="EXERCISEDB_API_KEY",
                     help_url="https://rapidapi.com/justin-WFnsXH_t6/api/exercisedb")
        return []

    headers = {
        "X-RapidAPI-Key": EXERCISEDB_API_KEY,
        "X-RapidAPI-Host": "exercisedb.p.rapidapi.com"
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        logger.info("fetching_exercises", source="ExerciseDB")
        response = await client.get(
            f"{EXERCISEDB_API_URL}/exercises",
            headers=headers,
            params={"limit": 2000}  # Get all exercises
        )

        if response.status_code != 200:
            logger.error("api_request_failed", status_code=response.status_code, response=response.text)
            return []

        exercises = response.json()
        logger.info("exercises_fetched", count=len(exercises))
        return exercises


async def seed_exercises_from_api(session: AsyncSession, clear_existing: bool = False) -> int:
    """Seed the database with exercises from ExerciseDB API."""

    if clear_existing:
        logger.info("clearing_existing_exercises")
        await session.execute(delete(Exercise).where(Exercise.is_custom == False))
        await session.commit()
    else:
        # Check if exercises already exist
        result = await session.execute(
            select(Exercise).where(Exercise.is_custom == False).limit(1)
        )
        if result.scalar_one_or_none():
            logger.info("exercises_already_exist", hint="use clear_existing=True to replace")
            return 0

    exercises_data = await fetch_all_exercises()
    if not exercises_data:
        return 0

    count = 0
    batch_size = 100

    for i, ex_data in enumerate(exercises_data):
        try:
            muscle_group = get_muscle_group(
                ex_data.get("bodyPart", ""),
                ex_data.get("target", "")
            )

            # Build secondary muscles list
            secondary = ex_data.get("secondaryMuscles", [])
            if isinstance(secondary, list):
                secondary_muscles = secondary
            else:
                secondary_muscles = None

            # Equipment as list
            equipment = ex_data.get("equipment")
            equipment_list = [equipment] if equipment else None

            # Instructions - ExerciseDB returns as list
            instructions_list = ex_data.get("instructions", [])
            if isinstance(instructions_list, list):
                instructions = "\n".join(f"{j+1}. {step}" for j, step in enumerate(instructions_list))
            else:
                instructions = None

            exercise = Exercise(
                name=ex_data.get("name", "").title(),
                description=f"Target: {ex_data.get('target', 'N/A').title()}",
                muscle_group=muscle_group,
                secondary_muscles=secondary_muscles,
                equipment=equipment_list,
                image_url=ex_data.get("gifUrl"),  # GIF URL
                video_url=None,
                instructions=instructions,
                is_custom=False,
                is_public=True,
            )
            session.add(exercise)
            count += 1

            # Commit in batches
            if count % batch_size == 0:
                await session.commit()
                logger.info("batch_inserted", count=count)

        except Exception as e:
            logger.error("exercise_processing_failed", exercise_name=ex_data.get('name'), error=str(e))
            continue

    # Final commit
    await session.commit()
    return count


async def main():
    """Main function to run the seed."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed exercises from ExerciseDB")
    parser.add_argument("--clear", action="store_true", help="Clear existing public exercises first")
    args = parser.parse_args()

    logger.info("exercisedb_seed_script_started")

    async with AsyncSessionLocal() as session:
        count = await seed_exercises_from_api(session, clear_existing=args.clear)

    if count > 0:
        logger.info("exercisedb_seed_script_completed", exercise_count=count)
    else:
        logger.info("no_exercises_seeded")


if __name__ == "__main__":
    asyncio.run(main())
