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

import structlog

logger = structlog.get_logger(__name__)

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
    MuscleGroup.LEGS: [
        "https://images.unsplash.com/photo-1574680096145-d05b474e2155?w=800&q=80",  # Squats
        "https://images.unsplash.com/photo-1434608519344-49d77a699e1d?w=800&q=80",  # Leg workout
        "https://images.unsplash.com/photo-1517963879433-6ad2b056d712?w=800&q=80",  # Leg exercises
        "https://images.unsplash.com/photo-1596357395217-80de13130e92?w=800&q=80",  # Legs
    ],
    MuscleGroup.STRETCHING: [
        "https://images.unsplash.com/photo-1544367567-0f2fcb009e0b?w=800&q=80",  # Yoga stretch
        "https://images.unsplash.com/photo-1518611012118-696072aa579a?w=800&q=80",  # Stretching
        "https://images.unsplash.com/photo-1573384666979-2b1e160d2d08?w=800&q=80",  # Flexibility
        "https://images.unsplash.com/photo-1506126613408-eca07ce68773?w=800&q=80",  # Yoga pose
        "https://images.unsplash.com/photo-1599901860904-17e6ed7083a0?w=800&q=80",  # Stretching gym
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
        "video_url": "https://www.youtube.com/watch?v=rT7DgCr-3pg",
    },
    {
        "name": "Supino Inclinado com Halteres",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["dumbbell", "incline_bench"],
        "description": "Foco na parte superior do peitoral",
        "instructions": "No banco inclinado (30-45 graus), desça os halteres ate o peito e empurre.",
        "video_url": "https://www.youtube.com/watch?v=8iPEnn-ltC8",
    },
    {
        "name": "Supino Declinado",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps"],
        "equipment": ["barbell", "decline_bench"],
        "description": "Foco na parte inferior do peitoral",
        "video_url": "https://www.youtube.com/watch?v=LfyQBUKR8SE",
    },
    {
        "name": "Crucifixo com Halteres",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["shoulders"],
        "equipment": ["dumbbell", "bench"],
        "description": "Exercicio de isolamento para o peitoral",
        "instructions": "Deitado no banco, abra os bracos em arco ate sentir alongamento no peito.",
        "video_url": "https://www.youtube.com/watch?v=eozdVDA78K0",
    },
    {
        "name": "Crossover no Cabo",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["shoulders"],
        "equipment": ["cable"],
        "description": "Exercicio de isolamento com cabos",
        "video_url": "https://www.youtube.com/watch?v=taI4XduLpTk",
    },
    {
        "name": "Flexao de Bracos",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders", "abs"],
        "equipment": ["bodyweight"],
        "description": "Exercicio classico com peso corporal",
        "instructions": "Mantenha o corpo reto, desça ate o peito quase tocar o chao.",
        "video_url": "https://www.youtube.com/watch?v=IODxDxX7oi4",
    },
    {
        "name": "Mergulho em Paralelas (Peito)",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["parallel_bars"],
        "description": "Incline o corpo para frente para focar no peitoral",
        "video_url": "https://www.youtube.com/watch?v=2z8JmcrW-As",
    },

    # COSTAS (Back)
    {
        "name": "Barra Fixa (Pegada Pronada)",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "forearms"],
        "equipment": ["pull_up_bar"],
        "description": "Exercicio fundamental para costas",
        "instructions": "Pegada um pouco mais larga que os ombros, puxe ate o queixo passar a barra.",
        "video_url": "https://www.youtube.com/watch?v=eGo4IYlbE5g",
    },
    {
        "name": "Remada Curvada com Barra",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps", "forearms"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para espessura das costas",
        "instructions": "Incline o tronco a 45 graus, puxe a barra ate a cintura.",
        "video_url": "https://www.youtube.com/watch?v=FWJR5Ve8bnQ",
    },
    {
        "name": "Puxada Frontal",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["cable", "lat_pulldown"],
        "description": "Foco no latissimo do dorso",
        "video_url": "https://www.youtube.com/watch?v=CAwf7n6Luuc",
    },
    {
        "name": "Remada Unilateral com Halter",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["dumbbell", "bench"],
        "description": "Exercicio unilateral para costas",
        "instructions": "Apoie um joelho e mao no banco, puxe o halter ate a cintura.",
        "video_url": "https://www.youtube.com/watch?v=pYcpY20QaE8",
    },
    {
        "name": "Remada Cavalinho",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["t_bar"],
        "description": "Excelente para espessura das costas",
        "video_url": "https://www.youtube.com/watch?v=j3Igk5nyZE4",
    },
    {
        "name": "Pullover com Halter",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["chest", "triceps"],
        "equipment": ["dumbbell", "bench"],
        "description": "Trabalha latissimo e serrátil",
        "video_url": "https://www.youtube.com/watch?v=FK4rHfWKEac",
    },
    {
        "name": "Remada Baixa no Cabo",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["cable"],
        "description": "Remada sentado com cabo",
        "video_url": "https://www.youtube.com/watch?v=GZbfZ033f74",
    },

    # OMBROS (Shoulders)
    {
        "name": "Desenvolvimento com Barra",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["triceps"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para ombros",
        "instructions": "Em pe ou sentado, empurre a barra acima da cabeca.",
        "video_url": "https://www.youtube.com/watch?v=2yjwXTZQDDI",
    },
    {
        "name": "Desenvolvimento com Halteres",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["triceps"],
        "equipment": ["dumbbell"],
        "description": "Permite maior amplitude de movimento",
        "video_url": "https://www.youtube.com/watch?v=qEwKCR5JCog",
    },
    {
        "name": "Elevacao Lateral",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["dumbbell"],
        "description": "Isolamento para deltoide lateral",
        "instructions": "Levante os halteres lateralmente ate a altura dos ombros.",
        "video_url": "https://www.youtube.com/watch?v=3VcKaXpzqRo",
    },
    {
        "name": "Elevacao Frontal",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["dumbbell"],
        "description": "Foco no deltoide anterior",
        "video_url": "https://www.youtube.com/watch?v=sOcYlBI85xE",
    },
    {
        "name": "Crucifixo Inverso",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["back"],
        "equipment": ["dumbbell", "machine"],
        "description": "Foco no deltoide posterior",
        "video_url": "https://www.youtube.com/watch?v=lPt0GqwaqEw",
    },
    {
        "name": "Encolhimento com Barra",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["barbell"],
        "description": "Trabalha o trapezio",
        "video_url": "https://www.youtube.com/watch?v=NAqCVe2mwzM",
    },

    # BICEPS
    {
        "name": "Rosca Direta com Barra",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["barbell"],
        "description": "Exercicio basico para biceps",
        "instructions": "Mantenha os cotovelos fixos ao lado do corpo, flexione os bracos.",
        "video_url": "https://www.youtube.com/watch?v=kwG2ipFRgfo",
    },
    {
        "name": "Rosca Alternada com Halteres",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["dumbbell"],
        "description": "Permite supinacao durante o movimento",
        "video_url": "https://www.youtube.com/watch?v=sAq_ocpRh_I",
    },
    {
        "name": "Rosca Martelo",
        "muscle_group": MuscleGroup.BICEPS,
        "secondary_muscles": ["forearms"],
        "equipment": ["dumbbell"],
        "description": "Trabalha braquial e braquiorradial",
        "video_url": "https://www.youtube.com/watch?v=zC3nLlEvin4",
    },
    {
        "name": "Rosca Concentrada",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["dumbbell"],
        "description": "Isolamento maximo do biceps",
        "instructions": "Sentado, apoie o cotovelo na coxa e flexione o braco.",
        "video_url": "https://www.youtube.com/watch?v=0AUGkch3tzc",
    },
    {
        "name": "Rosca Scott",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["barbell", "preacher_bench"],
        "description": "Enfatiza a porcao inferior do biceps",
        "video_url": "https://www.youtube.com/watch?v=fIWP-FRFNU0",
    },
    {
        "name": "Rosca no Cabo",
        "muscle_group": MuscleGroup.BICEPS,
        "equipment": ["cable"],
        "description": "Tensao constante durante todo o movimento",
        "video_url": "https://www.youtube.com/watch?v=NFzTWp2qpiE",
    },

    # TRICEPS
    {
        "name": "Triceps Corda",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["cable", "rope"],
        "description": "Excelente para cabeca lateral do triceps",
        "instructions": "Mantenha os cotovelos fixos, estenda os bracos e afaste as cordas no final.",
        "video_url": "https://www.youtube.com/watch?v=kiuVA0gs3EI",
    },
    {
        "name": "Triceps Testa",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["barbell", "bench"],
        "description": "Trabalha a cabeca longa do triceps",
        "instructions": "Deitado, desça a barra ate a testa e estenda os bracos.",
        "video_url": "https://www.youtube.com/watch?v=d_KZxkY_0cM",
    },
    {
        "name": "Triceps Frances",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["dumbbell"],
        "description": "Trabalha a cabeca longa do triceps",
        "video_url": "https://www.youtube.com/watch?v=nRiJVZDpdL0",
    },
    {
        "name": "Mergulho no Banco",
        "muscle_group": MuscleGroup.TRICEPS,
        "secondary_muscles": ["chest", "shoulders"],
        "equipment": ["bench"],
        "description": "Exercicio com peso corporal para triceps",
        "video_url": "https://www.youtube.com/watch?v=0326dy_-CzM",
    },
    {
        "name": "Triceps Coice",
        "muscle_group": MuscleGroup.TRICEPS,
        "equipment": ["dumbbell"],
        "description": "Isolamento do triceps",
        "video_url": "https://www.youtube.com/watch?v=6SS6K3lAwZ8",
    },

    # PERNAS (Legs)
    {
        "name": "Agachamento Livre",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings", "abs"],
        "equipment": ["barbell", "squat_rack"],
        "description": "Rei dos exercicios para pernas",
        "instructions": "Barra nas costas, desça ate as coxas ficarem paralelas ao chao.",
        "video_url": "https://www.youtube.com/watch?v=ultWZbUMPL8",
    },
    {
        "name": "Leg Press 45 Graus",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["leg_press"],
        "description": "Permite trabalhar com cargas altas com seguranca",
        "video_url": "https://www.youtube.com/watch?v=IZxyjW7MPJQ",
    },
    {
        "name": "Cadeira Extensora",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "equipment": ["leg_extension"],
        "description": "Isolamento do quadriceps",
        "video_url": "https://www.youtube.com/watch?v=YyvSfVjQeL0",
    },
    {
        "name": "Agachamento Hack",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes"],
        "equipment": ["hack_squat"],
        "description": "Variacao guiada do agachamento",
        "video_url": "https://www.youtube.com/watch?v=0tn5K9NlCfo",
    },
    {
        "name": "Afundo com Halteres",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["dumbbell"],
        "description": "Exercicio unilateral para pernas",
        "video_url": "https://www.youtube.com/watch?v=D7KaRcUTQeE",
    },
    {
        "name": "Mesa Flexora",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "equipment": ["leg_curl"],
        "description": "Isolamento dos isquiotibiais",
        "video_url": "https://www.youtube.com/watch?v=1Tq3QdYUuHs",
    },
    {
        "name": "Stiff",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "back"],
        "equipment": ["barbell"],
        "description": "Trabalha posterior de coxa e gluteos",
        "instructions": "Mantenha as pernas quase estendidas, incline o tronco ate sentir alongamento.",
        "video_url": "https://www.youtube.com/watch?v=1uDiW5--rAE",
    },
    {
        "name": "Levantamento Terra",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["back", "glutes", "quadriceps"],
        "equipment": ["barbell"],
        "description": "Exercicio composto para posterior",
        "video_url": "https://www.youtube.com/watch?v=op9kVnSso6Q",
    },

    # GLUTEOS (Glutes)
    {
        "name": "Hip Thrust",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["barbell", "bench"],
        "description": "Melhor exercicio para ativacao glutea",
        "instructions": "Apoie as costas no banco, empurre o quadril para cima.",
        "video_url": "https://www.youtube.com/watch?v=SEdqd1n0cvg",
    },
    {
        "name": "Gluteo na Polia",
        "muscle_group": MuscleGroup.GLUTES,
        "equipment": ["cable"],
        "description": "Isolamento do gluteo com cabo",
        "video_url": "https://www.youtube.com/watch?v=uFDZmLKIRCw",
    },
    {
        "name": "Elevacao Pelvica",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["bodyweight"],
        "description": "Versao do hip thrust no chao",
        "video_url": "https://www.youtube.com/watch?v=8bbE64NuDTU",
    },

    # PANTURRILHA (Calves)
    {
        "name": "Panturrilha em Pe",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["calf_raise_machine"],
        "description": "Trabalha o gastrocnemio",
        "instructions": "Suba na ponta dos pes e desça alongando bem.",
        "video_url": "https://www.youtube.com/watch?v=Yh5TXz-wPpA",
    },
    {
        "name": "Panturrilha Sentado",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["seated_calf"],
        "description": "Foco no soleo",
        "video_url": "https://www.youtube.com/watch?v=Yh5TXz-wPpA",
    },

    # ABDOMEN (Abs)
    {
        "name": "Abdominal Crunch",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight"],
        "description": "Exercicio basico para abdomen",
        "instructions": "Deitado, contraia o abdomen levantando os ombros do chao.",
        "video_url": "https://www.youtube.com/watch?v=Xyd_fa5zoEU",
    },
    {
        "name": "Prancha",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["shoulders", "back"],
        "equipment": ["bodyweight"],
        "description": "Isometrico para core",
        "instructions": "Mantenha o corpo reto apoiado nos antebracos e pontas dos pes.",
        "video_url": "https://www.youtube.com/watch?v=pSHjTRCQxIw",
    },
    {
        "name": "Elevacao de Pernas",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight", "dip_station"],
        "description": "Trabalha a parte inferior do abdomen",
        "video_url": "https://www.youtube.com/watch?v=l4kQd9eWclE",
    },
    {
        "name": "Abdominal Obliquo",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight"],
        "description": "Trabalha os obliquos",
        "video_url": "https://www.youtube.com/watch?v=pDFCx4pHLt0",
    },
    {
        "name": "Roda Abdominal",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["back", "shoulders"],
        "equipment": ["ab_wheel"],
        "description": "Exercicio avancado para core",
        "video_url": "https://www.youtube.com/watch?v=rqiTPdK1c_I",
    },

    # CARDIO
    {
        "name": "Corrida na Esteira",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves"],
        "equipment": ["treadmill"],
        "description": "Cardio classico",
        "video_url": "https://www.youtube.com/watch?v=8SQ2Tldsnqc",
    },
    {
        "name": "Bicicleta Ergometrica",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps"],
        "equipment": ["stationary_bike"],
        "description": "Cardio de baixo impacto",
        "video_url": "https://www.youtube.com/watch?v=gWvdCwHUPog",
    },
    {
        "name": "Eliptico",
        "muscle_group": MuscleGroup.CARDIO,
        "equipment": ["elliptical"],
        "description": "Cardio de baixo impacto para corpo inteiro",
        "video_url": "https://www.youtube.com/watch?v=L7Rwz9BPBPU",
    },
    {
        "name": "Pular Corda",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["calves", "shoulders"],
        "equipment": ["jump_rope"],
        "description": "Cardio de alta intensidade",
        "video_url": "https://www.youtube.com/watch?v=1BZM2Vre5oc",
    },
    {
        "name": "Burpee",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["chest", "quadriceps", "abs"],
        "equipment": ["bodyweight"],
        "description": "Exercicio de corpo inteiro de alta intensidade",
        "video_url": "https://www.youtube.com/watch?v=dZgVxmf6jkA",
    },

    # ==================== NOVOS EXERCICIOS ====================

    # Gestantes/Mobilidade
    {
        "name": "Agachamento com Apoio",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Agachamento seguro com apoio em cadeira ou parede",
        "instructions": "Segure em uma cadeira ou parede para apoio. Desça controladamente ate onde for confortavel.",
    },
    {
        "name": "Exercicio de Kegel",
        "muscle_group": MuscleGroup.ABS,
        "equipment": ["bodyweight"],
        "description": "Fortalecimento do assoalho pelvico",
        "instructions": "Contraia os musculos do assoalho pelvico por 5 segundos, relaxe por 5 segundos. Repita.",
    },
    {
        "name": "Cat-Cow (Gato-Vaca)",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["abs"],
        "equipment": ["bodyweight"],
        "description": "Mobilidade de coluna em quatro apoios",
        "instructions": "Em quatro apoios, alterne entre arquear as costas (gato) e afundar (vaca).",
    },
    {
        "name": "Alongamento de Quadril",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["bodyweight"],
        "description": "Alongamento para flexores de quadril",
        "instructions": "Em posicao de avanço, afunde o quadril para baixo alongando a parte frontal.",
    },
    {
        "name": "Caminhada Leve",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves"],
        "equipment": ["treadmill"],
        "description": "Caminhada em ritmo leve na esteira",
        "instructions": "Caminhe em ritmo confortavel, mantendo boa postura.",
    },

    # Terceira Idade
    {
        "name": "Sentar e Levantar",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Exercicio funcional de levantar da cadeira",
        "instructions": "Sente em uma cadeira, levante sem usar as maos, sente novamente controladamente.",
    },
    {
        "name": "Subida no Step",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["step"],
        "description": "Subida em degrau baixo para fortalecimento",
        "instructions": "Suba no step com um pe, traga o outro, desça controladamente.",
    },
    {
        "name": "Flexao na Parede",
        "muscle_group": MuscleGroup.CHEST,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["bodyweight"],
        "description": "Flexao adaptada na parede para iniciantes",
        "instructions": "Apoie as maos na parede, flexione os bracos trazendo o peito a parede.",
    },
    {
        "name": "Remada com Elastico",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["biceps"],
        "equipment": ["resistance_band"],
        "description": "Remada usando banda elastica",
        "instructions": "Pise no elastico, puxe as alças ate o abdomen, contraia as costas.",
    },
    {
        "name": "Equilibrio Unipodal",
        "muscle_group": MuscleGroup.FULL_BODY,
        "equipment": ["bodyweight"],
        "description": "Treino de equilibrio em uma perna",
        "instructions": "Fique em pe em uma perna so, mantenha por 30 segundos, troque de lado.",
    },
    {
        "name": "Marcha Estacionaria",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps"],
        "equipment": ["bodyweight"],
        "description": "Marcha no lugar para aquecimento",
        "instructions": "Marche no lugar elevando os joelhos de forma controlada.",
    },

    # Kids/Coordenacao
    {
        "name": "Polichinelo",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["shoulders", "calves"],
        "equipment": ["bodyweight"],
        "description": "Exercicio classico de aquecimento",
        "instructions": "Salte abrindo pernas e bracos simultaneamente, retorne a posicao inicial.",
    },
    {
        "name": "Corrida Estacionaria",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves"],
        "equipment": ["bodyweight"],
        "description": "Corrida no lugar",
        "instructions": "Corra no lugar elevando os joelhos, mantenha ritmo constante.",
    },
    {
        "name": "Escalador (Mountain Climber)",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["abs", "shoulders", "quadriceps"],
        "equipment": ["bodyweight"],
        "description": "Exercicio de alta intensidade para core",
        "instructions": "Em posicao de prancha, alterne trazendo os joelhos ao peito rapidamente.",
    },
    {
        "name": "Agachamento com Salto",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["bodyweight"],
        "description": "Agachamento pliometrico",
        "instructions": "Faca um agachamento e salte explosivamente, aterrisse suavemente.",
    },
    {
        "name": "Skipping (Elevacao de Joelhos)",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "abs"],
        "equipment": ["bodyweight"],
        "description": "Corrida com elevacao alta de joelhos",
        "instructions": "Corra no lugar elevando os joelhos ate a altura do quadril.",
    },

    # Mobilidade/Reabilitacao
    {
        "name": "Bird-Dog",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["back", "glutes"],
        "equipment": ["bodyweight"],
        "description": "Exercicio de estabilizacao de core",
        "instructions": "Em quatro apoios, estenda braco e perna opostos, mantenha 3 segundos.",
    },
    {
        "name": "Ponte de Gluteos Unilateral",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["bodyweight"],
        "description": "Elevacao de quadril com uma perna",
        "instructions": "Deite, eleve o quadril usando apenas uma perna, mantenha a outra estendida.",
    },
    {
        "name": "Rotacao de Tronco",
        "muscle_group": MuscleGroup.ABS,
        "secondary_muscles": ["back"],
        "equipment": ["bodyweight"],
        "description": "Mobilidade de coluna toracica",
        "instructions": "Sentado ou em pe, gire o tronco para cada lado mantendo quadril fixo.",
    },
    {
        "name": "Face Pull com Elastico",
        "muscle_group": MuscleGroup.SHOULDERS,
        "secondary_muscles": ["back"],
        "equipment": ["resistance_band"],
        "description": "Fortalecimento de deltoide posterior",
        "instructions": "Puxe o elastico em direcao ao rosto, abrindo os cotovelos.",
    },
    {
        "name": "Abducao de Quadril",
        "muscle_group": MuscleGroup.GLUTES,
        "equipment": ["bodyweight"],
        "description": "Fortalecimento de gluteo medio",
        "instructions": "Deitado de lado, eleve a perna de cima mantendo-a estendida.",
    },
    {
        "name": "Extensao de Coluna (Superman)",
        "muscle_group": MuscleGroup.BACK,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Fortalecimento de extensores da coluna",
        "instructions": "Deitado de barriga para baixo, eleve bracos e pernas simultaneamente.",
    },
    {
        "name": "Rotacao Externa de Ombro",
        "muscle_group": MuscleGroup.SHOULDERS,
        "equipment": ["resistance_band"],
        "description": "Fortalecimento do manguito rotador",
        "instructions": "Cotovelo junto ao corpo, gire o antebraco para fora contra resistencia.",
    },

    # HIIT/Funcional
    {
        "name": "Box Jump",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["box"],
        "description": "Salto pliometrico em caixa",
        "instructions": "Salte sobre a caixa aterrissando com ambos os pes, desça controladamente.",
    },
    {
        "name": "Kettlebell Swing",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["glutes", "hamstrings", "shoulders"],
        "equipment": ["kettlebell"],
        "description": "Balanco de kettlebell para posterior",
        "instructions": "Balançe o kettlebell entre as pernas e projete a frente usando o quadril.",
    },
    {
        "name": "Battle Ropes",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["shoulders", "abs"],
        "equipment": ["battle_ropes"],
        "description": "Treino de cordas para condicionamento",
        "instructions": "Segure as cordas e faca ondas alternadas ou simultaneas.",
    },
    {
        "name": "Farmers Walk",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["forearms", "abs"],
        "equipment": ["dumbbell"],
        "description": "Caminhada com peso nas maos",
        "instructions": "Segure halteres pesados e caminhe mantendo postura ereta.",
    },
    {
        "name": "Thruster",
        "muscle_group": MuscleGroup.FULL_BODY,
        "secondary_muscles": ["quadriceps", "shoulders"],
        "equipment": ["dumbbell"],
        "description": "Agachamento + desenvolvimento combinados",
        "instructions": "Faca um agachamento frontal e ao subir empurre os pesos acima da cabeca.",
    },
    {
        "name": "Wall Sit (Cadeirinha)",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "equipment": ["bodyweight"],
        "description": "Isometrico de quadriceps contra parede",
        "instructions": "Apoie as costas na parede e desça ate 90 graus, mantenha a posicao.",
    },

    # ==================== EXERCÍCIOS ADICIONAIS DE PERNA ====================

    {
        "name": "Agachamento Sumô",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "adductors"],
        "equipment": ["dumbbell"],
        "description": "Agachamento com pernas afastadas focando adutores",
        "instructions": "Pernas bem afastadas, pontas dos pés para fora, desça mantendo joelhos na direção dos pés.",
        "video_url": "https://www.youtube.com/watch?v=9ZuXKqRbT9k",
    },
    {
        "name": "Agachamento Búlgaro",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["dumbbell", "bench"],
        "description": "Agachamento unilateral com pé traseiro elevado",
        "instructions": "Pé traseiro no banco, desça até o joelho quase tocar o chão.",
        "video_url": "https://www.youtube.com/watch?v=2C-uNgKwPLE",
    },
    {
        "name": "Agachamento Goblet",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "abs"],
        "equipment": ["dumbbell", "kettlebell"],
        "description": "Agachamento segurando peso no peito",
        "instructions": "Segure o halter no peito, desça mantendo tronco ereto.",
        "video_url": "https://www.youtube.com/watch?v=MeIiIdhvXT4",
    },
    {
        "name": "Leg Press Horizontal",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["leg_press"],
        "description": "Leg press na máquina horizontal",
        "instructions": "Empurre a plataforma estendendo as pernas, retorne controladamente.",
        "video_url": "https://www.youtube.com/watch?v=GvRgijoJ2xY",
    },
    {
        "name": "Passada (Walking Lunge)",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["glutes", "hamstrings"],
        "equipment": ["bodyweight", "dumbbell"],
        "description": "Avanço caminhando para frente",
        "instructions": "Dê um passo à frente, desça até o joelho quase tocar o chão, alterne as pernas.",
        "video_url": "https://www.youtube.com/watch?v=L8fvypPrzzs",
    },
    {
        "name": "Cadeira Adutora",
        "muscle_group": MuscleGroup.QUADRICEPS,
        "secondary_muscles": ["adductors"],
        "equipment": ["adductor_machine"],
        "description": "Fortalecimento dos músculos adutores",
        "instructions": "Sentado na máquina, aproxime as pernas contra a resistência.",
        "video_url": "https://www.youtube.com/watch?v=2dGETY1s0w4",
    },
    {
        "name": "Cadeira Abdutora",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["quadriceps"],
        "equipment": ["abductor_machine"],
        "description": "Fortalecimento dos músculos abdutores e glúteo médio",
        "instructions": "Sentado na máquina, afaste as pernas contra a resistência.",
        "video_url": "https://www.youtube.com/watch?v=WRYYQO3U3NY",
    },
    {
        "name": "Mesa Flexora Unilateral",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "equipment": ["leg_curl"],
        "description": "Flexão de perna unilateral para isquiotibiais",
        "instructions": "Flexione uma perna de cada vez para maior foco muscular.",
        "video_url": "https://www.youtube.com/watch?v=ELOCsoDSmrg",
    },
    {
        "name": "Stiff Unilateral",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes"],
        "equipment": ["dumbbell"],
        "description": "Stiff em uma perna só para maior ativação",
        "instructions": "Em uma perna, incline o tronco mantendo a outra perna estendida atrás.",
        "video_url": "https://www.youtube.com/watch?v=PZXS6L-Epkg",
    },
    {
        "name": "Good Morning",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "back"],
        "equipment": ["barbell"],
        "description": "Inclinação de tronco para posterior de coxa",
        "instructions": "Barra nas costas, incline o tronco mantendo pernas levemente flexionadas.",
        "video_url": "https://www.youtube.com/watch?v=YA-h3n9L4YU",
    },
    {
        "name": "Levantamento Terra Sumô",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "quadriceps", "back"],
        "equipment": ["barbell"],
        "description": "Terra com pernas afastadas",
        "instructions": "Pernas bem afastadas, pegada entre as pernas, levante mantendo costas retas.",
        "video_url": "https://www.youtube.com/watch?v=2MI5uWD8KO8",
    },
    {
        "name": "Levantamento Terra Romeno",
        "muscle_group": MuscleGroup.HAMSTRINGS,
        "secondary_muscles": ["glutes", "back"],
        "equipment": ["barbell"],
        "description": "Variação do terra com pernas estendidas",
        "instructions": "Pernas levemente flexionadas, desça a barra mantendo-a próxima ao corpo.",
        "video_url": "https://www.youtube.com/watch?v=2SHsk9AzdjA",
    },
    {
        "name": "Hip Thrust na Máquina",
        "muscle_group": MuscleGroup.GLUTES,
        "secondary_muscles": ["hamstrings"],
        "equipment": ["hip_thrust_machine"],
        "description": "Hip thrust guiado na máquina",
        "instructions": "Costas apoiadas, empurre o quadril para cima contra a resistência.",
        "video_url": "https://www.youtube.com/watch?v=xDmFkJxPzeM",
    },
    {
        "name": "Coice na Polia (Kickback)",
        "muscle_group": MuscleGroup.GLUTES,
        "equipment": ["cable"],
        "description": "Extensão de quadril no cabo baixo",
        "instructions": "Prenda a caneleira, empurre a perna para trás mantendo o joelho estendido.",
        "video_url": "https://www.youtube.com/watch?v=yk7J82xejHQ",
    },
    {
        "name": "Panturrilha no Leg Press",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["leg_press"],
        "description": "Panturrilha usando o leg press",
        "instructions": "Apoie apenas a ponta dos pés na plataforma, estenda e flexione os tornozelos.",
        "video_url": "https://www.youtube.com/watch?v=Yh5TXz-wPpA",
    },
    {
        "name": "Panturrilha Unilateral",
        "muscle_group": MuscleGroup.CALVES,
        "equipment": ["bodyweight", "step"],
        "description": "Elevação de panturrilha em uma perna",
        "instructions": "Em um step, suba e desça usando apenas uma perna.",
        "video_url": "https://www.youtube.com/watch?v=c5Kv6-fnTj8",
    },

    # ==================== EXERCÍCIOS AERÓBICOS/CARDIO ADICIONAIS ====================

    {
        "name": "HIIT na Esteira",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves", "hamstrings"],
        "equipment": ["treadmill"],
        "description": "Treino intervalado de alta intensidade na esteira",
        "instructions": "Alterne entre sprints intensos e caminhada de recuperação.",
    },
    {
        "name": "Spinning/Ciclismo Indoor",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "glutes"],
        "equipment": ["spin_bike"],
        "description": "Ciclismo indoor de alta intensidade",
        "instructions": "Pedale alternando intensidades e posições (sentado/em pé).",
    },
    {
        "name": "Remo Ergométrico",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["back", "biceps", "quadriceps"],
        "equipment": ["rowing_machine"],
        "description": "Cardio completo no remo ergométrico",
        "instructions": "Empurre com as pernas, puxe com os braços, retorne controladamente.",
    },
    {
        "name": "Escada (StairMaster)",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "glutes", "calves"],
        "equipment": ["stair_climber"],
        "description": "Subida de escada na máquina",
        "instructions": "Suba os degraus em ritmo constante, evite apoiar muito nos corrimãos.",
    },
    {
        "name": "Assault Bike",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "shoulders"],
        "equipment": ["assault_bike"],
        "description": "Bicicleta com braços para cardio total",
        "instructions": "Pedale e movimente os braços simultaneamente.",
    },
    {
        "name": "Ski Erg",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["back", "shoulders", "abs"],
        "equipment": ["ski_erg"],
        "description": "Simulador de esqui para cardio e força",
        "instructions": "Puxe as alças para baixo em movimento similar ao esqui.",
    },
    {
        "name": "Corrida ao Ar Livre",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "calves", "hamstrings"],
        "equipment": ["bodyweight"],
        "description": "Corrida em ambiente externo",
        "instructions": "Corra mantendo postura ereta, aterrisse no meio do pé.",
    },
    {
        "name": "Caminhada Inclinada",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["treadmill"],
        "description": "Caminhada na esteira com inclinação alta",
        "instructions": "Configure inclinação de 10-15% e caminhe em ritmo moderado.",
    },
    {
        "name": "Tabata Burpees",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["chest", "quadriceps", "abs"],
        "equipment": ["bodyweight"],
        "description": "Protocolo Tabata com burpees (20s trabalho, 10s descanso)",
        "instructions": "Execute burpees por 20 segundos, descanse 10 segundos, repita 8 rounds.",
    },
    {
        "name": "Sprint",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["quadriceps", "hamstrings", "glutes"],
        "equipment": ["treadmill", "bodyweight"],
        "description": "Corrida em velocidade máxima por curta distância",
        "instructions": "Corra na velocidade máxima por 20-30 segundos, recupere e repita.",
    },
    {
        "name": "Natação",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["back", "shoulders", "abs"],
        "equipment": ["pool"],
        "description": "Exercício aeróbico de baixo impacto na piscina",
        "instructions": "Nade em ritmo constante usando técnica adequada.",
    },
    {
        "name": "Circuito Cardio",
        "muscle_group": MuscleGroup.CARDIO,
        "secondary_muscles": ["full_body"],
        "equipment": ["bodyweight"],
        "description": "Sequência de exercícios cardiovasculares sem descanso",
        "instructions": "Execute uma série de exercícios (polichinelos, skipping, burpees) em sequência.",
    },

    # ==================== EXERCÍCIOS DE PERNAS (LEGS - GENÉRICO) ====================

    {
        "name": "Agachamento com Peso Corporal",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes", "abs"],
        "equipment": ["bodyweight"],
        "description": "Agachamento básico sem peso adicional",
        "instructions": "Pés na largura dos ombros, desça até as coxas ficarem paralelas ao chão.",
        "video_url": "https://www.youtube.com/watch?v=aclHkVaku9U",
    },
    {
        "name": "Avanço Estático",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Avanço mantendo a posição sem caminhar",
        "instructions": "Dê um passo à frente e desça até o joelho quase tocar o chão.",
        "video_url": "https://www.youtube.com/watch?v=QOVaHwm-Q6U",
    },
    {
        "name": "Agachamento com Salto",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["bodyweight"],
        "description": "Agachamento pliométrico para explosão",
        "instructions": "Faça um agachamento e salte explosivamente, aterrisse suavemente.",
        "video_url": "https://www.youtube.com/watch?v=Azl5tkCzDcc",
    },
    {
        "name": "Pistol Squat (Agachamento Unilateral)",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes", "abs"],
        "equipment": ["bodyweight"],
        "description": "Agachamento avançado em uma perna só",
        "instructions": "Agache em uma perna mantendo a outra estendida à frente.",
        "video_url": "https://www.youtube.com/watch?v=qDcniqddTeE",
    },
    {
        "name": "Step Up Alto",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes", "calves"],
        "equipment": ["box", "bench"],
        "description": "Subida em banco alto para força de pernas",
        "instructions": "Suba no banco alto usando a força de uma perna, alterne.",
        "video_url": "https://www.youtube.com/watch?v=dQqApCGd5Ss",
    },
    {
        "name": "Wall Sit (Cadeirinha)",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Isométrico de pernas contra a parede",
        "instructions": "Apoie as costas na parede e desça até 90 graus, mantenha.",
        "video_url": "https://www.youtube.com/watch?v=y-wV4Venusw",
    },
    {
        "name": "Sissy Squat",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["abs"],
        "equipment": ["bodyweight"],
        "description": "Agachamento com inclinação posterior para quadríceps",
        "instructions": "Incline o corpo para trás enquanto flexiona os joelhos.",
        "video_url": "https://www.youtube.com/watch?v=93vdFqwUdug",
    },
    {
        "name": "Nordic Curl",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight"],
        "description": "Flexão nórdica para posterior de coxa",
        "instructions": "Ajoelhado, desça o corpo controladamente usando os isquiotibiais.",
        "video_url": "https://www.youtube.com/watch?v=d8AAPcYxKe8",
    },
    {
        "name": "Reverse Lunge (Avanço Reverso)",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes"],
        "equipment": ["bodyweight", "dumbbell"],
        "description": "Avanço dando passo para trás",
        "instructions": "Dê um passo para trás e desça até o joelho quase tocar o chão.",
        "video_url": "https://www.youtube.com/watch?v=xrPteyQLGAo",
    },
    {
        "name": "Cossack Squat",
        "muscle_group": MuscleGroup.LEGS,
        "secondary_muscles": ["glutes", "adductors"],
        "equipment": ["bodyweight"],
        "description": "Agachamento lateral para mobilidade e força",
        "instructions": "Agache lateralmente em uma perna mantendo a outra estendida.",
        "video_url": "https://www.youtube.com/watch?v=tpczTeSkHz0",
    },

    # ALONGAMENTO (Stretching)
    {
        "name": "Alongamento de Posterior de Coxa",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["hamstrings", "lower_back"],
        "equipment": ["bodyweight"],
        "description": "Alongamento para isquiotibiais, tocando os pés",
        "instructions": "Em pé ou sentado, incline o tronco para frente mantendo as pernas estendidas até sentir alongamento na parte posterior da coxa. Mantenha 20-30 segundos.",
        "video_url": "https://www.youtube.com/watch?v=g-7ZWPCWv0U",
    },
    {
        "name": "Alongamento de Quadríceps",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["quadriceps", "hip_flexors"],
        "equipment": ["bodyweight"],
        "description": "Alongamento da parte frontal da coxa",
        "instructions": "Em pé, segure o pé e puxe o calcanhar em direção ao glúteo. Mantenha o joelho apontando para baixo e o corpo ereto. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=YvGcDPtBbic",
    },
    {
        "name": "Alongamento de Panturrilha",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["calves", "achilles"],
        "equipment": ["bodyweight"],
        "description": "Alongamento dos músculos da panturrilha contra a parede",
        "instructions": "Apoie as mãos na parede, dê um passo para trás com uma perna mantendo-a estendida e o calcanhar no chão. Incline o corpo para frente. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=B7oAMfHb9fk",
    },
    {
        "name": "Alongamento de Glúteos",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["glutes", "piriformis"],
        "equipment": ["bodyweight"],
        "description": "Alongamento do glúteo cruzando a perna",
        "instructions": "Deitado, cruze uma perna sobre o joelho oposto e puxe a coxa em direção ao peito. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=k1rIH7lnA7s",
    },
    {
        "name": "Alongamento de Adutores (Borboleta)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["adductors", "groin"],
        "equipment": ["bodyweight"],
        "description": "Alongamento da parte interna das coxas sentado",
        "instructions": "Sentado, junte as solas dos pés e deixe os joelhos caírem para os lados. Pressione suavemente os joelhos para baixo. Mantenha 20-30 segundos.",
        "video_url": "https://www.youtube.com/watch?v=8x1I7xE5Tqc",
    },
    {
        "name": "Alongamento de Flexores do Quadril",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["hip_flexors", "iliopsoas"],
        "equipment": ["bodyweight"],
        "description": "Alongamento profundo dos flexores do quadril em avanço",
        "instructions": "Em posição de avanço baixo, com joelho traseiro no chão, empurre o quadril para frente. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=OMwqXxZ9z2A",
    },
    {
        "name": "Alongamento de Peitoral na Parede",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["chest", "shoulders"],
        "equipment": ["bodyweight"],
        "description": "Alongamento do peitoral apoiando o braço na parede",
        "instructions": "Apoie o antebraço na parede em ângulo de 90 graus e gire o corpo para o lado oposto até sentir alongamento no peitoral. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=nvOLWzJ3raQ",
    },
    {
        "name": "Alongamento de Tríceps",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["triceps", "shoulders"],
        "equipment": ["bodyweight"],
        "description": "Alongamento do tríceps puxando o cotovelo atrás da cabeça",
        "instructions": "Leve o braço atrás da cabeça e com a outra mão puxe o cotovelo suavemente. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=RVmuG0pLdCw",
    },
    {
        "name": "Alongamento de Ombros (Braço Cruzado)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["shoulders", "deltoids"],
        "equipment": ["bodyweight"],
        "description": "Alongamento do ombro cruzando o braço na frente do corpo",
        "instructions": "Cruze o braço na frente do corpo e com a outra mão puxe-o em direção ao peito. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=SL6ImlIlJ3g",
    },
    {
        "name": "Alongamento de Lombar (Joelhos ao Peito)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["lower_back", "glutes"],
        "equipment": ["bodyweight"],
        "description": "Alongamento da lombar deitado trazendo os joelhos ao peito",
        "instructions": "Deitado de costas, abrace os joelhos e puxe-os em direção ao peito. Balance suavemente. Mantenha 20-30 segundos.",
        "video_url": "https://www.youtube.com/watch?v=Bt3A4d7O4yM",
    },
    {
        "name": "Alongamento Lateral de Tronco",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["obliques", "lats"],
        "equipment": ["bodyweight"],
        "description": "Alongamento dos músculos laterais do tronco",
        "instructions": "Em pé, eleve um braço e incline o corpo para o lado oposto. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=nQwKPKU1ckw",
    },
    {
        "name": "Alongamento de Pescoço Lateral",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["neck", "trapezius"],
        "equipment": ["bodyweight"],
        "description": "Alongamento suave dos músculos laterais do pescoço",
        "instructions": "Incline a cabeça para o lado, levando a orelha em direção ao ombro. A mão pode pressionar suavemente. Mantenha 15-20 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=OafoMkS5Fz8",
    },
    {
        "name": "Rotação de Coluna Sentado",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["spine", "obliques"],
        "equipment": ["bodyweight"],
        "description": "Alongamento rotacional da coluna vertebral",
        "instructions": "Sentado com pernas estendidas, cruze uma perna sobre a outra e gire o tronco para o lado da perna cruzada. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=aYlPh6dDEyk",
    },
    {
        "name": "Cat-Cow (Gato-Vaca)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["spine", "abs"],
        "equipment": ["bodyweight"],
        "description": "Mobilidade da coluna alternando flexão e extensão",
        "instructions": "De quatro apoios, alterne entre arquear as costas para cima (gato) e para baixo (vaca). Faça 10-15 repetições lentamente.",
        "video_url": "https://www.youtube.com/watch?v=kqnua4rHVVA",
    },
    {
        "name": "Alongamento do Piriforme",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["piriformis", "glutes"],
        "equipment": ["bodyweight"],
        "description": "Alongamento específico para o músculo piriforme (nervo ciático)",
        "instructions": "Deitado, cruze o tornozelo sobre o joelho oposto e puxe a coxa em direção ao peito. Mantenha 30-45 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=OAz0zEyLgNk",
    },
    {
        "name": "Child's Pose (Postura da Criança)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["back", "shoulders", "hips"],
        "equipment": ["bodyweight"],
        "description": "Postura de relaxamento e alongamento de costas e quadril",
        "instructions": "Ajoelhado, sente sobre os calcanhares e estenda os braços à frente, descansando a testa no chão. Mantenha 30-60 segundos.",
        "video_url": "https://www.youtube.com/watch?v=eqVMAPM00DM",
    },
    {
        "name": "Downward Dog (Cachorro Olhando para Baixo)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["hamstrings", "calves", "shoulders"],
        "equipment": ["bodyweight"],
        "description": "Postura de alongamento para posterior e ombros",
        "instructions": "De quatro apoios, eleve o quadril formando um V invertido. Pressione os calcanhares em direção ao chão. Mantenha 30-45 segundos.",
        "video_url": "https://www.youtube.com/watch?v=EC7RGJ975iM",
    },
    {
        "name": "Alongamento de Antebraço",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["forearms", "wrists"],
        "equipment": ["bodyweight"],
        "description": "Alongamento dos músculos do antebraço e punho",
        "instructions": "Estenda o braço com a palma para baixo e com a outra mão puxe os dedos para baixo. Depois inverta para cima. Mantenha 15-20 segundos cada posição.",
        "video_url": "https://www.youtube.com/watch?v=moeG9J4-HJQ",
    },
    {
        "name": "Cobra Stretch (Postura da Cobra)",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["abs", "hip_flexors", "chest"],
        "equipment": ["bodyweight"],
        "description": "Alongamento da cadeia anterior em extensão de coluna",
        "instructions": "Deitado de barriga para baixo, apoie as mãos e estenda os braços elevando o tronco. Mantenha o quadril no chão. Mantenha 20-30 segundos.",
        "video_url": "https://www.youtube.com/watch?v=JDcdhTuycOI",
    },
    {
        "name": "Alongamento de Trapézio",
        "muscle_group": MuscleGroup.STRETCHING,
        "secondary_muscles": ["trapezius", "neck"],
        "equipment": ["bodyweight"],
        "description": "Alongamento do músculo trapézio superior",
        "instructions": "Incline a cabeça para frente e para o lado, puxando suavemente com a mão. Mantenha 20-30 segundos cada lado.",
        "video_url": "https://www.youtube.com/watch?v=v-O7XK_WXNM",
    },
]


async def seed_exercises(session: AsyncSession, clear_existing: bool = False) -> int:
    """Seed the database with common exercises."""

    if clear_existing:
        logger.info("clearing_existing_public_exercises")
        await session.execute(delete(Exercise).where(Exercise.is_custom == False))
        await session.commit()
    else:
        # Check if exercises already exist
        result = await session.execute(select(Exercise).limit(1))
        if result.scalar_one_or_none():
            logger.info("exercises_already_exist", hint="Use --clear to replace them")
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
            video_url=exercise_data.get("video_url"),
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

    logger.info("exercise_seed_script_started", description="54 exercicios em PT-BR com imagens")

    async with AsyncSessionLocal() as session:
        count = await seed_exercises(session, clear_existing=args.clear)

    if count > 0:
        logger.info("exercises_seeded_successfully", count=count)
    else:
        logger.info("no_exercises_seeded")


if __name__ == "__main__":
    asyncio.run(main())
