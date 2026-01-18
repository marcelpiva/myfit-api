"""
Seed script for populating the database with common exercises.

Run with:
    python -m src.scripts.seed_exercises
    python -m src.scripts.seed_exercises --clear  # Replace existing exercises

Or from the api directory:
    PYTHONPATH=. python src/scripts/seed_exercises.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import Exercise, MuscleGroup


# Unsplash image URLs by muscle group (free, high-quality fitness images)
MUSCLE_GROUP_IMAGES = {
    MuscleGroup.CHEST: [
        "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80",  # Bench press
        "https://images.unsplash.com/photo-1598971639058-fab3c3109a00?w=800&q=80",  # Push-ups
        "https://images.unsplash.com/photo-1597452485669-2c7bb5fef90d?w=800&q=80",  # Chest workout
        "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800&q=80",  # Gym chest
        "https://images.unsplash.com/photo-1581009146145-b5ef050c149a?w=800&q=80",  # Dumbbell press
    ],
    MuscleGroup.BACK: [
        "https://images.unsplash.com/photo-1603287681836-b174ce5074c2?w=800&q=80",  # Pull-ups
        "https://images.unsplash.com/photo-1541534741688-6078c6bfb5c5?w=800&q=80",  # Back workout
        "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=800&q=80",  # Lat pulldown
        "https://images.unsplash.com/photo-1597347316205-36f6c451902a?w=800&q=80",  # Rowing
        "https://images.unsplash.com/photo-1605296867304-46d5465a13f1?w=800&q=80",  # Back muscles
    ],
    MuscleGroup.SHOULDERS: [
        "https://images.unsplash.com/photo-1532029837206-abbe2b7620e3?w=800&q=80",  # Shoulder press
        "https://images.unsplash.com/photo-1581009137042-c552e485697a?w=800&q=80",  # Lateral raises
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80",  # Shoulder workout
        "https://images.unsplash.com/photo-1584466977773-e625c37cdd50?w=800&q=80",  # Deltoids
    ],
    MuscleGroup.BICEPS: [
        "https://images.unsplash.com/photo-1581009146145-b5ef050c149a?w=800&q=80",  # Bicep curls
        "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=800&q=80",  # Dumbbell curls
        "https://images.unsplash.com/photo-1534368786749-b63e05c90863?w=800&q=80",  # Arm workout
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",  # Biceps
    ],
    MuscleGroup.TRICEPS: [
        "https://images.unsplash.com/photo-1530822847156-5df684ec5ee1?w=800&q=80",  # Tricep dips
        "https://images.unsplash.com/photo-1598971639058-fab3c3109a00?w=800&q=80",  # Tricep workout
        "https://images.unsplash.com/photo-1584466977773-e625c37cdd50?w=800&q=80",  # Arms
        "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80",  # Tricep press
    ],
    MuscleGroup.QUADRICEPS: [
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80",  # Squats
        "https://images.unsplash.com/photo-1434608519344-49d77a699e1d?w=800&q=80",  # Leg press
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Leg workout
        "https://images.unsplash.com/photo-1596357395217-80de13130e92?w=800&q=80",  # Quads
    ],
    MuscleGroup.HAMSTRINGS: [
        "https://images.unsplash.com/photo-1434608519344-49d77a699e1d?w=800&q=80",  # Deadlift
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Leg workout
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80",  # Posterior chain
    ],
    MuscleGroup.GLUTES: [
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80",  # Hip thrust
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Glute workout
        "https://images.unsplash.com/photo-1596357395217-80de13130e92?w=800&q=80",  # Glutes
    ],
    MuscleGroup.CALVES: [
        "https://images.unsplash.com/photo-1434608519344-49d77a699e1d?w=800&q=80",  # Calf raises
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Leg workout
    ],
    MuscleGroup.ABS: [
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",  # Abs workout
        "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80",  # Plank
        "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=800&q=80",  # Core workout
        "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=800&q=80",  # Crunches
    ],
    MuscleGroup.CARDIO: [
        "https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=800&q=80",  # Running
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Cardio
        "https://images.unsplash.com/photo-1534787238916-9ba6764efd4f?w=800&q=80",  # Treadmill
        "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=800&q=80",  # Cycling
    ],
    MuscleGroup.FULL_BODY: [
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Full body
        "https://images.unsplash.com/photo-1571019613454-1cb2f99b2d8b?w=800&q=80",  # Workout
    ],
}


def get_image_for_exercise(muscle_group: MuscleGroup, index: int) -> str:
    """Get an image URL for an exercise based on its muscle group."""
    images = MUSCLE_GROUP_IMAGES.get(muscle_group, MUSCLE_GROUP_IMAGES[MuscleGroup.FULL_BODY])
    return images[index % len(images)]


EXERCISES = [
    # PEITO (Chest)
    {
        "name": "Supino Reto com Barra",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["barbell", "bench"],
        "description": "Exercicio composto para desenvolvimento do peitoral",
        "instructions": "Deite no banco, segure a barra na largura dos ombros, desça ate o peito e empurre.",
    },
    {
        "name": "Supino Inclinado com Halteres",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["dumbbell", "incline_bench"],
        "description": "Foco na parte superior do peitoral",
        "instructions": "No banco inclinado (30-45 graus), desça os halteres ate o peito e empurre.",
    },
    {
        "name": "Supino Declinado",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps"],
        "equipment": ["barbell", "decline_bench"],
        "description": "Foco na parte inferior do peitoral",
    },
    {
        "name": "Crucifixo com Halteres",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["shoulders"],
        "equipment": ["dumbbell", "bench"],
        "description": "Exercicio de isolamento para o peitoral",
        "instructions": "Deitado no banco, abra os bracos em arco ate sentir alongamento no peito.",
    },
    {
        "name": "Crossover no Cabo",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["shoulders"],
        "equipment": ["cable"],
        "description": "Exercicio de isolamento com cabos",
    },
    {
        "name": "Flexao de Bracos",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders", "abs"],
        "equipment": ["bodyweight"],
        "description": "Exercicio classico com peso corporal",
        "instructions": "Mantenha o corpo reto, desça ate o peito quase tocar o chao.",
    },
    {
        "name": "Mergulho em Paralelas (Peito)",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["parallel_bars"],
        "description": "Incline o corpo para frente para focar no peitoral",
    },

    # COSTAS (Back)
    {
        "name": "Barra Fixa (Pegada Pronada)",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "forearms"],
        "equipment": ["pull_up_bar"],
        "description": "Exercicio fundamental para costas",
        "instructions": "Pegada um pouco mais larga que os ombros, puxe ate o queixo passar a barra.",
    },
    {
        "name": "Remada Curvada com Barra",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "forearms"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para espessura das costas",
        "instructions": "Incline o tronco a 45 graus, puxe a barra ate a cintura.",
    },
    {
        "name": "Puxada Frontal",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["cable", "lat_pulldown"],
        "description": "Foco no latissimo do dorso",
    },
    {
        "name": "Remada Unilateral com Halter",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["dumbbell", "bench"],
        "description": "Exercicio unilateral para costas",
        "instructions": "Apoie um joelho e mao no banco, puxe o halter ate a cintura.",
    },
    {
        "name": "Remada Cavalinho",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["t_bar"],
        "description": "Excelente para espessura das costas",
    },
    {
        "name": "Pullover com Halter",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["chest", "triceps"],
        "equipment": ["dumbbell", "bench"],
        "description": "Trabalha latissimo e serrátil",
    },
    {
        "name": "Remada Baixa no Cabo",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["cable"],
        "description": "Remada sentado com cabo",
    },

    # OMBROS (Shoulders)
    {
        "name": "Desenvolvimento com Barra",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["triceps"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para ombros",
        "instructions": "Em pe ou sentado, empurre a barra acima da cabeca.",
    },
    {
        "name": "Desenvolvimento com Halteres",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["triceps"],
        "equipment": ["dumbbell"],
        "description": "Permite maior amplitude de movimento",
    },
    {
        "name": "Elevacao Lateral",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["dumbbell"],
        "description": "Isolamento para deltoide lateral",
        "instructions": "Levante os halteres lateralmente ate a altura dos ombros.",
    },
    {
        "name": "Elevacao Frontal",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["dumbbell"],
        "description": "Foco no deltoide anterior",
    },
    {
        "name": "Crucifixo Inverso",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["back"],
        "equipment": ["dumbbell", "machine"],
        "description": "Foco no deltoide posterior",
    },
    {
        "name": "Encolhimento com Barra",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["barbell"],
        "description": "Trabalha o trapezio",
    },

    # BICEPS
    {
        "name": "Rosca Direta com Barra",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["barbell"],
        "description": "Exercicio basico para biceps",
        "instructions": "Mantenha os cotovelos fixos ao lado do corpo, flexione os bracos.",
    },
    {
        "name": "Rosca Alternada com Halteres",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["dumbbell"],
        "description": "Permite supinacao durante o movimento",
    },
    {
        "name": "Rosca Martelo",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["dumbbell"],
        "description": "Trabalha braquial e braquiorradial",
    },
    {
        "name": "Rosca Concentrada",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["dumbbell"],
        "description": "Isolamento maximo do biceps",
        "instructions": "Sentado, apoie o cotovelo na coxa e flexione o braco.",
    },
    {
        "name": "Rosca Scott",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["barbell", "preacher_bench"],
        "description": "Enfatiza a porcao inferior do biceps",
    },
    {
        "name": "Rosca no Cabo",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["cable"],
        "description": "Tensao constante durante todo o movimento",
    },

    # TRICEPS
    {
        "name": "Triceps Corda",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["cable", "rope"],
        "description": "Excelente para cabeca lateral do triceps",
        "instructions": "Mantenha os cotovelos fixos, estenda os bracos e afaste as cordas no final.",
    },
    {
        "name": "Triceps Testa",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["barbell", "bench"],
        "description": "Trabalha a cabeca longa do triceps",
        "instructions": "Deitado, desça a barra ate a testa e estenda os bracos.",
    },
    {
        "name": "Triceps Frances",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["dumbbell"],
        "description": "Trabalha a cabeca longa do triceps",
    },
    {
        "name": "Mergulho no Banco",
        "muscle_group": MuscleGroup.TRICEPS,
        "secondary_muscles": ["chest", "shoulders"],
        "equipment": ["bench"],
        "description": "Exercicio com peso corporal para triceps",
    },
    {
        "name": "Triceps Coice",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["dumbbell"],
        "description": "Isolamento do triceps",
    },

    # PERNAS (Legs)
    {
        "name": "Agachamento Livre",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings", "abs"],
        "equipment": ["barbell", "squat_rack"],
        "description": "Rei dos exercicios para pernas",
        "instructions": "Barra nas costas, desça ate as coxas ficarem paralelas ao chao.",
    },
    {
        "name": "Leg Press 45 Graus",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["leg_press"],
        "description": "Permite trabalhar com cargas altas com seguranca",
    },
    {
        "name": "Cadeira Extensora",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "equipment": ["leg_extension"],
        "description": "Isolamento do quadriceps",
    },
    {
        "name": "Agachamento Hack",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes"],
        "equipment": ["hack_squat"],
        "description": "Variacao guiada do agachamento",
    },
    {
        "name": "Afundo com Halteres",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["dumbbell"],
        "description": "Exercicio unilateral para pernas",
    },
    {
        "name": "Mesa Flexora",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "equipment": ["leg_curl"],
        "description": "Isolamento dos isquiotibiais",
    },
    {
        "name": "Stiff",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "back"],
        "equipment": ["barbell"],
        "description": "Trabalha posterior de coxa e gluteos",
        "instructions": "Mantenha as pernas quase estendidas, incline o tronco ate sentir alongamento.",
    },
    {
        "name": "Levantamento Terra",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["back", "glutes", "quadriceps"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para posterior",
    },

    # GLUTEOS (Glutes)
    {
        "name": "Hip Thrust",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["barbell", "bench"],
        "description": "Melhor exercicio para ativacao glutea",
        "instructions": "Apoie as costas no banco, empurre o quadril para cima.",
    },
    {
        "name": "Gluteo na Polia",
        "muscle_group": MuscleGroup.GLUTES,
        "equipment": ["cable"],
        "description": "Isolamento do gluteo com cabo",
    },
    {
        "name": "Elevacao Pelvica",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["bodyweight"],
        "description": "Versao do hip thrust no chao",
    },

    # PANTURRILHA (Calves)
    {
        "name": "Panturrilha em Pe",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["calf_raise_machine"],
        "description": "Trabalha o gastrocnemio",
        "instructions": "Suba na ponta dos pes e desça alongando bem.",
    },
    {
        "name": "Panturrilha Sentado",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["seated_calf"],
        "description": "Foco no soleo",
    },

    # ABDOMEN (Abs)
    {
        "name": "Abdominal Crunch",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight"],
        "description": "Exercicio basico para abdomen",
        "instructions": "Deitado, contraia o abdomen levantando os ombros do chao.",
    },
    {
        "name": "Prancha",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["shoulders", "back"],
        "equipment": ["bodyweight"],
        "description": "Isometrico para core",
        "instructions": "Mantenha o corpo reto apoiado nos antebracos e pontas dos pes.",
    },
    {
        "name": "Elevacao de Pernas",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight", "dip_station"],
        "description": "Trabalha a parte inferior do abdomen",
    },
    {
        "name": "Abdominal Obliquo",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight"],
        "description": "Trabalha os obliquos",
    },
    {
        "name": "Roda Abdominal",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["back", "shoulders"],
        "equipment": ["ab_wheel"],
        "description": "Exercicio avancado para core",
    },

    # CARDIO
    {
        "name": "Corrida na Esteira",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves"],
        "equipment": ["treadmill"],
        "description": "Cardio classico",
    },
    {
        "name": "Bicicleta Ergometrica",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps"],
        "equipment": ["stationary_bike"],
        "description": "Cardio de baixo impacto",
    },
    {
        "name": "Eliptico",
        "muscle_group": MuscleGroup.CARDIO,
        "equipment": ["elliptical"],
        "description": "Cardio de baixo impacto para corpo inteiro",
    },
    {
        "name": "Pular Corda",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["calves", "shoulders"],
        "equipment": ["jump_rope"],
        "description": "Cardio de alta intensidade",
    },
    {
        "name": "Burpee",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["chest", "quadriceps", "abs"],
        "equipment": ["bodyweight"],
        "description": "Exercicio de corpo inteiro de alta intensidade",
    },
]


async def seed_exercises(session: AsyncSession, clear_existing: bool = False) -> int:
    """Seed the database with common exercises."""

    if clear_existing:
        print("Clearing existing public exercises...")
        await session.execute(delete(Exercise).where(Exercise.is_custom == False))
        await session.commit()
    else:
        # Check if exercises already exist
        result = await session.execute(select(Exercise).limit(1))
        if result.scalar_one_or_none():
            print("Exercises already exist in database. Use --clear to replace them.")
            return 0

    # Track index per muscle group for image rotation
    muscle_group_counters: dict[MuscleGroup, int] = {}

    count = 0
    for exercise_data in EXERCISES:
        muscle_group = exercise_data["muscle_group"]

        # Get image for this exercise
        idx = muscle_group_counters.get(muscle_group, 0)
        image_url = get_image_for_exercise(muscle_group, idx)
        muscle_group_counters[muscle_group] = idx + 1

        exercise = Exercise(
            name=exercise_data["name"],
            muscle_group=muscle_group,
            secondary_muscles=exercise_data.get("secondary_muscles"),
            equipment=exercise_data.get("equipment"),
            description=exercise_data.get("description"),
            instructions=exercise_data.get("instructions"),
            image_url=image_url,
            is_custom=False,
            is_public=True,
        )
        session.add(exercise)
        count += 1

    await session.commit()
    return count


async def main():
    """Main function to run the seed."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed exercises database")
    parser.add_argument("--clear", action="store_true", help="Clear existing public exercises first")
    args = parser.parse_args()

    print("=" * 60)
    print("Exercise Seed Script (54 exercicios em PT-BR com imagens)")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        count = await seed_exercises(session, clear_existing=args.clear)

    if count > 0:
        print("=" * 60)
        print(f"Successfully seeded {count} exercises with images!")
        print("=" * 60)
    else:
        print("No exercises were seeded.")


if __name__ == "__main__":
    asyncio.run(main())
