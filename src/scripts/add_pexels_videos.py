"""
Add Pexels videos to exercises.

Pexels provides free stock videos with a generous API.
Get your free API key at: https://www.pexels.com/api/

Run with:
    PEXELS_API_KEY="..." DATABASE_URL="..." python -m src.scripts.add_pexels_videos
"""

import asyncio
import os
import sys
from pathlib import Path

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import Exercise, MuscleGroup

logger = structlog.get_logger(__name__)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PEXELS_API_URL = "https://api.pexels.com/videos/search"

# Search terms for each muscle group (in English for better Pexels results)
MUSCLE_GROUP_SEARCH_TERMS = {
    MuscleGroup.CHEST: ["bench press workout", "chest workout gym", "push up exercise"],
    MuscleGroup.BACK: ["pull up workout", "back workout gym", "rowing exercise"],
    MuscleGroup.SHOULDERS: ["shoulder press workout", "dumbbell shoulder", "shoulder exercise gym"],
    MuscleGroup.BICEPS: ["bicep curl workout", "arm workout gym", "dumbbell curl"],
    MuscleGroup.TRICEPS: ["tricep workout gym", "arm exercise", "tricep extension"],
    MuscleGroup.QUADRICEPS: ["squat workout", "leg workout gym", "leg press exercise"],
    MuscleGroup.HAMSTRINGS: ["deadlift workout", "leg workout", "hamstring exercise"],
    MuscleGroup.GLUTES: ["hip thrust workout", "glute workout gym", "squat exercise"],
    MuscleGroup.CALVES: ["calf raise exercise", "leg workout", "calf workout gym"],
    MuscleGroup.LEGS: ["leg workout gym", "squat workout", "leg exercise fitness"],
    MuscleGroup.ABS: ["ab workout", "core exercise gym", "plank workout"],
    MuscleGroup.CARDIO: ["running treadmill", "cardio workout gym", "cycling exercise"],
    MuscleGroup.FULL_BODY: ["full body workout", "hiit workout gym", "fitness training"],
    MuscleGroup.FOREARMS: ["forearm workout", "arm exercise gym", "wrist curl"],
    MuscleGroup.STRETCHING: ["stretching workout", "yoga stretch", "flexibility exercise", "stretching routine"],
}

# Specific search terms for exercises (Portuguese name -> English search)
EXERCISE_SEARCH_OVERRIDES = {
    # Chest
    "Supino Reto com Barra": "barbell bench press",
    "Supino Inclinado com Halteres": "incline dumbbell press",
    "Flexao de Bracos": "push up workout",
    # Back
    "Barra Fixa (Pegada Pronada)": "pull up workout",
    "Remada Curvada com Barra": "barbell row workout",
    "Puxada Frontal": "lat pulldown exercise",
    # Shoulders
    "Desenvolvimento com Barra": "overhead press workout",
    "Elevacao Lateral": "lateral raise dumbbell",
    # Biceps
    "Rosca Direta com Barra": "barbell curl workout",
    "Rosca Martelo": "hammer curl exercise",
    # Triceps
    "Triceps Corda": "cable tricep pushdown",
    "Triceps Testa": "skull crusher exercise",
    # Legs (Generic)
    "Agachamento com Peso Corporal": "bodyweight squat workout",
    "Avanco Estatico": "static lunge exercise",
    "Pistol Squat": "pistol squat workout",
    "Nordic Curl": "nordic curl exercise",
    "Cossack Squat": "cossack squat exercise",
    "Step-Up": "step up exercise",
    "Afundo Bulgaro": "bulgarian split squat",
    "Wall Sit": "wall sit exercise",
    "Salto em Caixa": "box jump workout",
    "Agachamento com Salto": "jump squat exercise",
    # Quadriceps
    "Agachamento Livre": "barbell squat workout",
    "Leg Press 45 Graus": "leg press machine",
    # Hamstrings
    "Stiff": "romanian deadlift",
    "Levantamento Terra": "deadlift workout",
    # Glutes
    "Hip Thrust": "hip thrust workout",
    # Calves
    "Panturrilha em Pe": "standing calf raise",
    # Abs
    "Abdominal Crunch": "ab crunch workout",
    "Prancha": "plank exercise",
    # Cardio
    "Corrida na Esteira": "treadmill running",
    "Bicicleta Ergometrica": "stationary bike workout",
    # Full Body
    "Burpee": "burpee workout",
    # Stretching
    "Alongamento de Posterior de Coxa": "hamstring stretch",
    "Alongamento de Quadriceps": "quad stretch standing",
    "Alongamento de Panturrilha": "calf stretch wall",
    "Alongamento de Gluteos": "glute stretch lying",
    "Alongamento de Adutores (Borboleta)": "butterfly stretch",
    "Alongamento de Flexores do Quadril": "hip flexor stretch",
    "Alongamento de Peitoral na Parede": "chest stretch wall",
    "Alongamento de Triceps": "tricep stretch",
    "Alongamento de Ombros (Braco Cruzado)": "shoulder stretch",
    "Alongamento de Lombar (Joelhos ao Peito)": "lower back stretch",
    "Alongamento Lateral de Tronco": "side stretch standing",
    "Alongamento de Pescoco Lateral": "neck stretch",
    "Rotacao de Coluna Sentado": "seated spinal twist",
    "Cat-Cow (Gato-Vaca)": "cat cow stretch yoga",
    "Alongamento do Piriforme": "piriformis stretch",
    "Child's Pose (Postura da Crianca)": "child pose yoga",
    "Downward Dog (Cachorro Olhando para Baixo)": "downward dog yoga",
    "Alongamento de Antebraco": "forearm stretch wrist",
    "Cobra Stretch (Postura da Cobra)": "cobra pose yoga",
    "Alongamento de Trapezio": "trapezius stretch",
}


async def search_pexels_video(client: httpx.AsyncClient, query: str) -> str | None:
    """Search for a video on Pexels and return the video URL."""
    headers = {
        "Authorization": PEXELS_API_KEY,
    }

    params = {
        "query": query,
        "per_page": 5,
        "orientation": "portrait",  # Better for mobile
    }

    try:
        response = await client.get(PEXELS_API_URL, headers=headers, params=params)

        if response.status_code != 200:
            logger.error("pexels_api_error", query=query, status_code=response.status_code)
            return None

        data = response.json()
        videos = data.get("videos", [])

        if not videos:
            # Try without portrait orientation
            params["orientation"] = "landscape"
            response = await client.get(PEXELS_API_URL, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                videos = data.get("videos", [])

        if not videos:
            return None

        # Get the first video with HD quality
        for video in videos:
            video_files = video.get("video_files", [])

            # Prefer HD quality (720p or higher)
            for vf in video_files:
                if vf.get("quality") == "hd" and vf.get("width", 0) >= 720:
                    return vf.get("link")

            # Fallback to any video file
            if video_files:
                return video_files[0].get("link")

        return None

    except Exception as e:
        logger.error("pexels_search_failed", query=query, error=str(e))
        return None


async def get_video_for_exercise(
    client: httpx.AsyncClient,
    exercise_name: str,
    muscle_group: MuscleGroup,
    video_cache: dict[str, str]
) -> str | None:
    """Get a video URL for an exercise."""

    # Check cache first (by muscle group)
    cache_key = muscle_group.value
    if cache_key in video_cache:
        return video_cache[cache_key]

    # Try specific exercise search first
    if exercise_name in EXERCISE_SEARCH_OVERRIDES:
        query = EXERCISE_SEARCH_OVERRIDES[exercise_name]
        video_url = await search_pexels_video(client, query)
        if video_url:
            video_cache[cache_key] = video_url
            return video_url

    # Fall back to muscle group searches
    search_terms = MUSCLE_GROUP_SEARCH_TERMS.get(
        muscle_group,
        MUSCLE_GROUP_SEARCH_TERMS[MuscleGroup.FULL_BODY]
    )

    for term in search_terms:
        video_url = await search_pexels_video(client, term)
        if video_url:
            video_cache[cache_key] = video_url
            return video_url
        await asyncio.sleep(0.2)  # Rate limiting

    return None


async def add_videos_to_exercises(session: AsyncSession, replace_all: bool = False) -> int:
    """Add Pexels video URLs to exercises.

    Args:
        session: Database session
        replace_all: If True, replaces all videos including YouTube URLs.
                    If False, only adds videos to exercises without any video.
    """
    from sqlalchemy import or_

    if replace_all:
        # Get all non-custom exercises (replace YouTube and missing videos)
        result = await session.execute(
            select(Exercise).where(
                Exercise.is_custom == False,
                or_(
                    Exercise.video_url.is_(None),
                    Exercise.video_url.like('%youtube.com%'),
                    Exercise.video_url.like('%youtu.be%'),
                )
            )
        )
    else:
        # Get only exercises without videos
        result = await session.execute(
            select(Exercise).where(
                Exercise.is_custom == False,
                Exercise.video_url.is_(None)
            )
        )

    exercises = result.scalars().all()

    if not exercises:
        logger.info("all_exercises_have_videos")
        return 0

    logger.info("exercises_to_update", count=len(exercises))

    video_cache: dict[str, str] = {}
    updated = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for exercise in exercises:
            logger.info("processing_exercise", name=exercise.name)

            video_url = await get_video_for_exercise(
                client,
                exercise.name,
                exercise.muscle_group,
                video_cache
            )

            if video_url:
                exercise.video_url = video_url
                updated += 1
                logger.info("video_added", name=exercise.name)
            else:
                logger.debug("no_video_found", name=exercise.name)

            # Rate limiting
            await asyncio.sleep(0.3)

    await session.commit()
    return updated


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Pexels videos to exercises")
    parser.add_argument(
        "--replace-all",
        action="store_true",
        help="Replace all videos including YouTube URLs with Pexels videos"
    )
    args = parser.parse_args()

    if not PEXELS_API_KEY:
        logger.error("pexels_api_key_not_set", help_url="https://www.pexels.com/api/")
        return

    mode = "replace_all" if args.replace_all else "add_missing_only"
    logger.info("pexels_video_script_started", mode=mode)

    async with AsyncSessionLocal() as session:
        count = await add_videos_to_exercises(session, replace_all=args.replace_all)

    logger.info("pexels_video_script_completed", updated_count=count)


if __name__ == "__main__":
    asyncio.run(main())
