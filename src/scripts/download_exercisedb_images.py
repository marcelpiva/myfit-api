"""
Download exercise GIFs from ExerciseDB API and save locally.

Run with:
    EXERCISEDB_API_KEY="..." python -m src.scripts.download_exercisedb_images

This script:
1. Fetches all exercises from ExerciseDB
2. Downloads each GIF image
3. Saves to static/exercises/ directory
4. Updates database with local URLs
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import Exercise, MuscleGroup

logger = structlog.get_logger(__name__)

EXERCISEDB_API_URL = "https://exercisedb.p.rapidapi.com"
EXERCISEDB_API_KEY = os.getenv("EXERCISEDB_API_KEY", "")

# Output directory for GIFs
OUTPUT_DIR = Path(__file__).parent.parent.parent / "static" / "exercises"

# Mapping from ExerciseDB bodyPart/target to our MuscleGroup enum
BODY_PART_MAPPING = {
    "back": MuscleGroup.BACK,
    "cardio": MuscleGroup.CARDIO,
    "chest": MuscleGroup.CHEST,
    "lower arms": MuscleGroup.FOREARMS,
    "lower legs": MuscleGroup.CALVES,
    "neck": MuscleGroup.SHOULDERS,
    "shoulders": MuscleGroup.SHOULDERS,
    "upper arms": MuscleGroup.BICEPS,
    "upper legs": MuscleGroup.QUADRICEPS,
    "waist": MuscleGroup.ABS,
}

TARGET_MAPPING = {
    "lats": MuscleGroup.BACK,
    "traps": MuscleGroup.BACK,
    "upper back": MuscleGroup.BACK,
    "spine": MuscleGroup.BACK,
    "pectorals": MuscleGroup.CHEST,
    "delts": MuscleGroup.SHOULDERS,
    "serratus anterior": MuscleGroup.SHOULDERS,
    "biceps": MuscleGroup.BICEPS,
    "triceps": MuscleGroup.TRICEPS,
    "forearms": MuscleGroup.FOREARMS,
    "abs": MuscleGroup.ABS,
    "abductors": MuscleGroup.GLUTES,
    "adductors": MuscleGroup.QUADRICEPS,
    "glutes": MuscleGroup.GLUTES,
    "hamstrings": MuscleGroup.HAMSTRINGS,
    "quads": MuscleGroup.QUADRICEPS,
    "calves": MuscleGroup.CALVES,
    "cardiovascular system": MuscleGroup.CARDIO,
}


def get_muscle_group(body_part: str, target: str) -> MuscleGroup:
    """Map ExerciseDB body part and target to our MuscleGroup enum."""
    target_lower = target.lower()
    if target_lower in TARGET_MAPPING:
        return TARGET_MAPPING[target_lower]

    body_part_lower = body_part.lower()
    if body_part_lower in BODY_PART_MAPPING:
        return BODY_PART_MAPPING[body_part_lower]

    return MuscleGroup.FULL_BODY


async def fetch_all_exercises(client: httpx.AsyncClient) -> list[dict]:
    """Fetch all exercises from ExerciseDB API."""
    headers = {
        "X-RapidAPI-Key": EXERCISEDB_API_KEY,
        "X-RapidAPI-Host": "exercisedb.p.rapidapi.com"
    }

    all_exercises = []
    offset = 0
    limit = 100  # Max per request

    while True:
        logger.info("fetching_exercises", offset=offset)
        response = await client.get(
            f"{EXERCISEDB_API_URL}/exercises",
            headers=headers,
            params={"limit": limit, "offset": offset}
        )

        if response.status_code != 200:
            logger.error("api_request_failed", status_code=response.status_code, response=response.text)
            break

        exercises = response.json()
        if not exercises:
            break

        all_exercises.extend(exercises)
        logger.info("exercises_batch_fetched", batch_size=len(exercises), total=len(all_exercises))

        if len(exercises) < limit:
            break

        offset += limit

    return all_exercises


async def download_gif(client: httpx.AsyncClient, exercise_id: str, output_path: Path) -> bool:
    """Download GIF for a specific exercise."""
    headers = {
        "X-RapidAPI-Key": EXERCISEDB_API_KEY,
        "X-RapidAPI-Host": "exercisedb.p.rapidapi.com"
    }

    try:
        response = await client.get(
            f"{EXERCISEDB_API_URL}/image",
            headers=headers,
            params={"resolution": "180", "exerciseId": exercise_id}
        )

        if response.status_code == 200 and response.headers.get("content-type", "").startswith("image"):
            output_path.write_bytes(response.content)
            return True
        else:
            return False

    except Exception as e:
        logger.error("gif_download_failed", exercise_id=exercise_id, error=str(e))
        return False


async def main():
    """Main function to download all exercise GIFs."""
    if not EXERCISEDB_API_KEY:
        logger.error("api_key_not_set", variable="EXERCISEDB_API_KEY")
        return

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("download_script_started", output_dir=str(OUTPUT_DIR))

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Fetch all exercises
        logger.info("fetching_exercises_from_api")
        exercises = await fetch_all_exercises(client)
        logger.info("total_exercises_fetched", count=len(exercises))

        if not exercises:
            return

        # Download GIFs
        logger.info("downloading_gifs")

        downloaded = 0
        failed = 0
        skipped = 0

        for i, ex in enumerate(exercises):
            exercise_id = ex.get("id", "")
            if not exercise_id:
                continue

            # Pad ID to 4 characters
            exercise_id_padded = exercise_id.zfill(4)
            output_path = OUTPUT_DIR / f"{exercise_id_padded}.gif"

            # Skip if already downloaded
            if output_path.exists():
                skipped += 1
                continue

            success = await download_gif(client, exercise_id_padded, output_path)
            if success:
                downloaded += 1
            else:
                failed += 1

            # Progress every 50
            if (i + 1) % 50 == 0:
                logger.info("download_progress", processed=i + 1, total=len(exercises),
                           downloaded=downloaded, failed=failed, skipped=skipped)

            # Rate limiting - be nice to the API
            await asyncio.sleep(0.1)

        logger.info("gif_download_completed", downloaded=downloaded, failed=failed, skipped=skipped)

        # Now update the database
        logger.info("updating_database")

        async with AsyncSessionLocal() as session:
            # Clear existing public exercises
            from sqlalchemy import delete
            await session.execute(delete(Exercise).where(Exercise.is_custom == False))
            await session.commit()

            count = 0
            for ex in exercises:
                exercise_id = ex.get("id", "").zfill(4)
                gif_path = OUTPUT_DIR / f"{exercise_id}.gif"

                # Only add if GIF exists
                if not gif_path.exists():
                    continue

                instructions_list = ex.get("instructions", [])
                instructions = "\n".join(f"{j+1}. {step}" for j, step in enumerate(instructions_list)) if instructions_list else None

                secondary = ex.get("secondaryMuscles", [])

                exercise = Exercise(
                    name=ex.get("name", "").title(),
                    description=ex.get("description", f"Target: {ex.get('target', 'N/A').title()}"),
                    muscle_group=get_muscle_group(ex.get("bodyPart", ""), ex.get("target", "")),
                    secondary_muscles=secondary if secondary else None,
                    equipment=[ex.get("equipment")] if ex.get("equipment") else None,
                    image_url=f"/static/exercises/{exercise_id}.gif",  # Relative URL
                    video_url=None,
                    instructions=instructions,
                    is_custom=False,
                    is_public=True,
                )
                session.add(exercise)
                count += 1

                if count % 100 == 0:
                    await session.commit()
                    logger.info("batch_inserted", count=count)

            await session.commit()
            logger.info("database_update_completed", exercise_count=count)


if __name__ == "__main__":
    asyncio.run(main())
