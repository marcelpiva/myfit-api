"""
Seed script for populating the database with workout programs and templates.

This creates:
1. Sample workout programs with workouts and exercises
2. Catalog templates (public programs) for the marketplace

Run with:
    python -m src.scripts.seed_workout_programs
    python -m src.scripts.seed_workout_programs --clear  # Replace existing

Or from the api directory:
    PYTHONPATH=. python src/scripts/seed_workout_programs.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import UUID

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.database import AsyncSessionLocal
from src.domains.workouts.models import (
    Exercise,
    Workout,
    WorkoutExercise,
    TrainingPlan,
    PlanWorkout,
    MuscleGroup,
    Difficulty,
    WorkoutGoal,
    SplitType,
)
from src.domains.users.models import User


# ==================== Exercise References ====================
# Maps exercise names to their configurations for workouts

EXERCISE_CONFIGS = {
    # Peito (Chest)
    "Supino Reto com Barra": {"sets": 4, "reps": "8-10", "rest": 90},
    "Supino Inclinado com Halteres": {"sets": 4, "reps": "10-12", "rest": 75},
    "Supino Declinado": {"sets": 3, "reps": "10-12", "rest": 75},
    "Crucifixo com Halteres": {"sets": 3, "reps": "12-15", "rest": 60},
    "Crossover no Cabo": {"sets": 3, "reps": "15", "rest": 60},
    "Flexao de Bracos": {"sets": 3, "reps": "AMRAP", "rest": 60},

    # Costas (Back)
    "Barra Fixa (Pegada Pronada)": {"sets": 4, "reps": "6-8", "rest": 90},
    "Remada Curvada com Barra": {"sets": 4, "reps": "8-10", "rest": 90},
    "Puxada Frontal": {"sets": 4, "reps": "10-12", "rest": 75},
    "Remada Unilateral com Halter": {"sets": 3, "reps": "10-12", "rest": 60},
    "Remada Cavalinho": {"sets": 3, "reps": "10-12", "rest": 75},
    "Pullover com Halter": {"sets": 3, "reps": "12-15", "rest": 60},
    "Remada Baixa no Cabo": {"sets": 3, "reps": "12-15", "rest": 60},

    # Ombros (Shoulders)
    "Desenvolvimento com Barra": {"sets": 4, "reps": "8-10", "rest": 90},
    "Desenvolvimento com Halteres": {"sets": 4, "reps": "10-12", "rest": 75},
    "Elevacao Lateral": {"sets": 4, "reps": "12-15", "rest": 60},
    "Elevacao Frontal": {"sets": 3, "reps": "12-15", "rest": 60},
    "Crucifixo Inverso": {"sets": 3, "reps": "12-15", "rest": 60},
    "Encolhimento com Barra": {"sets": 4, "reps": "10-12", "rest": 60},

    # Biceps
    "Rosca Direta com Barra": {"sets": 4, "reps": "8-10", "rest": 75},
    "Rosca Alternada com Halteres": {"sets": 3, "reps": "10-12", "rest": 60},
    "Rosca Martelo": {"sets": 3, "reps": "10-12", "rest": 60},
    "Rosca Concentrada": {"sets": 3, "reps": "12", "rest": 60},
    "Rosca Scott": {"sets": 3, "reps": "10-12", "rest": 60},
    "Rosca no Cabo": {"sets": 3, "reps": "12-15", "rest": 45},

    # Triceps
    "Triceps Corda": {"sets": 4, "reps": "12-15", "rest": 60},
    "Triceps Testa": {"sets": 3, "reps": "10-12", "rest": 75},
    "Triceps Frances": {"sets": 3, "reps": "10-12", "rest": 60},
    "Mergulho no Banco": {"sets": 3, "reps": "12-15", "rest": 60},
    "Triceps Coice": {"sets": 3, "reps": "12-15", "rest": 45},

    # Pernas (Legs)
    "Agachamento Livre": {"sets": 4, "reps": "8-10", "rest": 120},
    "Leg Press 45 Graus": {"sets": 4, "reps": "10-12", "rest": 90},
    "Cadeira Extensora": {"sets": 4, "reps": "12-15", "rest": 60},
    "Agachamento Hack": {"sets": 3, "reps": "10-12", "rest": 90},
    "Afundo com Halteres": {"sets": 3, "reps": "10-12", "rest": 75},
    "Mesa Flexora": {"sets": 4, "reps": "10-12", "rest": 60},
    "Stiff": {"sets": 4, "reps": "10-12", "rest": 90},
    "Levantamento Terra": {"sets": 4, "reps": "6-8", "rest": 120},

    # Gluteos
    "Hip Thrust": {"sets": 4, "reps": "10-12", "rest": 75},
    "Gluteo na Polia": {"sets": 3, "reps": "15", "rest": 45},
    "Elevacao Pelvica": {"sets": 3, "reps": "15-20", "rest": 45},

    # Panturrilha
    "Panturrilha em Pe": {"sets": 4, "reps": "15-20", "rest": 45},
    "Panturrilha Sentado": {"sets": 4, "reps": "15-20", "rest": 45},

    # Abdomen
    "Abdominal Crunch": {"sets": 3, "reps": "15-20", "rest": 45},
    "Prancha": {"sets": 3, "reps": "30-60s", "rest": 45},
    "Elevacao de Pernas": {"sets": 3, "reps": "15", "rest": 45},
    "Abdominal Obliquo": {"sets": 3, "reps": "15", "rest": 45},
    "Roda Abdominal": {"sets": 3, "reps": "10-15", "rest": 60},

    # Cardio
    "Corrida na Esteira": {"sets": 1, "reps": "20-30min", "rest": 0},
    "Bicicleta Ergometrica": {"sets": 1, "reps": "20-30min", "rest": 0},
    "Eliptico": {"sets": 1, "reps": "20-30min", "rest": 0},
    "Pular Corda": {"sets": 5, "reps": "1min", "rest": 30},
    "Burpee": {"sets": 4, "reps": "10-15", "rest": 60},

    # ==================== NOVOS EXERCICIOS ====================

    # Gestantes/Mobilidade
    "Agachamento com Apoio": {"sets": 3, "reps": "10-12", "rest": 60},
    "Exercicio de Kegel": {"sets": 3, "reps": "10x5s", "rest": 30},
    "Cat-Cow (Gato-Vaca)": {"sets": 3, "reps": "10", "rest": 30},
    "Alongamento de Quadril": {"sets": 2, "reps": "30s", "rest": 30},
    "Caminhada Leve": {"sets": 1, "reps": "10-15min", "rest": 0},

    # Terceira Idade
    "Sentar e Levantar": {"sets": 3, "reps": "10-12", "rest": 60},
    "Subida no Step": {"sets": 3, "reps": "10", "rest": 60},
    "Flexao na Parede": {"sets": 3, "reps": "10-15", "rest": 60},
    "Remada com Elastico": {"sets": 3, "reps": "12-15", "rest": 60},
    "Equilibrio Unipodal": {"sets": 2, "reps": "30s", "rest": 30},
    "Marcha Estacionaria": {"sets": 1, "reps": "2-3min", "rest": 0},

    # Kids/Coordenacao
    "Polichinelo": {"sets": 3, "reps": "20", "rest": 30},
    "Corrida Estacionaria": {"sets": 3, "reps": "1min", "rest": 30},
    "Escalador (Mountain Climber)": {"sets": 3, "reps": "20", "rest": 45},
    "Agachamento com Salto": {"sets": 3, "reps": "10", "rest": 60},
    "Skipping (Elevacao de Joelhos)": {"sets": 3, "reps": "30s", "rest": 30},

    # Mobilidade/Reabilitacao
    "Bird-Dog": {"sets": 3, "reps": "10", "rest": 45},
    "Ponte de Gluteos Unilateral": {"sets": 3, "reps": "10", "rest": 45},
    "Rotacao de Tronco": {"sets": 2, "reps": "10", "rest": 30},
    "Face Pull com Elastico": {"sets": 3, "reps": "15", "rest": 45},
    "Abducao de Quadril": {"sets": 3, "reps": "15", "rest": 45},
    "Extensao de Coluna (Superman)": {"sets": 3, "reps": "12", "rest": 45},
    "Rotacao Externa de Ombro": {"sets": 3, "reps": "15", "rest": 45},

    # HIIT/Funcional
    "Box Jump": {"sets": 4, "reps": "8-10", "rest": 60},
    "Kettlebell Swing": {"sets": 4, "reps": "15", "rest": 60},
    "Battle Ropes": {"sets": 4, "reps": "30s", "rest": 45},
    "Farmers Walk": {"sets": 3, "reps": "30m", "rest": 60},
    "Thruster": {"sets": 4, "reps": "10-12", "rest": 75},
    "Wall Sit (Cadeirinha)": {"sets": 3, "reps": "30-45s", "rest": 45},
}


# ==================== Program Definitions ====================

PLANS = [
    {
        "name": "ABC - Hipertrofia Iniciante",
        "description": "Programa de 3 dias ideal para iniciantes focado em ganho de massa muscular. Divide o treino em Peito/Triceps, Costas/Biceps e Pernas/Ombros.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Treino A - Peito e Triceps",
                "description": "Foco no peitoral e triceps",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 50,
                "target_muscles": ["chest", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Crucifixo com Halteres",
                    "Triceps Corda",
                    "Triceps Frances",
                ],
            },
            {
                "label": "B",
                "name": "Treino B - Costas e Biceps",
                "description": "Foco nas costas e biceps",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 50,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Puxada Frontal",
                    "Remada Curvada com Barra",
                    "Remada Unilateral com Halter",
                    "Rosca Direta com Barra",
                    "Rosca Martelo",
                ],
            },
            {
                "label": "C",
                "name": "Treino C - Pernas e Ombros",
                "description": "Foco em pernas e ombros",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 60,
                "target_muscles": ["quadriceps", "hamstrings", "shoulders"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Mesa Flexora",
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                    "Panturrilha em Pe",
                ],
            },
        ],
    },
    {
        "name": "ABCD - Hipertrofia Intermediario",
        "description": "Programa de 4 dias para praticantes intermediarios. Maior volume de treino com divisao mais especifica dos grupos musculares.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Treino A - Peito",
                "description": "Treino completo de peitoral",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["chest"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Supino Declinado",
                    "Crucifixo com Halteres",
                    "Crossover no Cabo",
                ],
            },
            {
                "label": "B",
                "name": "Treino B - Costas",
                "description": "Treino completo de costas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["back"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Remada Cavalinho",
                    "Pullover com Halter",
                ],
            },
            {
                "label": "C",
                "name": "Treino C - Ombros e Bracos",
                "description": "Ombros, biceps e triceps",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 60,
                "target_muscles": ["shoulders", "biceps", "triceps"],
                "exercises": [
                    "Desenvolvimento com Barra",
                    "Elevacao Lateral",
                    "Crucifixo Inverso",
                    "Rosca Direta com Barra",
                    "Rosca Alternada com Halteres",
                    "Triceps Corda",
                    "Triceps Testa",
                ],
            },
            {
                "label": "D",
                "name": "Treino D - Pernas Completo",
                "description": "Treino completo de membros inferiores",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 65,
                "target_muscles": ["quadriceps", "hamstrings", "glutes", "calves"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Cadeira Extensora",
                    "Mesa Flexora",
                    "Stiff",
                    "Panturrilha em Pe",
                    "Panturrilha Sentado",
                ],
            },
        ],
    },
    {
        "name": "Push Pull Legs - Avancado",
        "description": "Divisao classica Push/Pull/Legs para praticantes avancados. Alta frequencia e volume de treino.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.PUSH_PULL_LEGS,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Push",
                "name": "Push - Empurrar",
                "description": "Peito, ombros e triceps",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 70,
                "target_muscles": ["chest", "shoulders", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Desenvolvimento com Barra",
                    "Elevacao Lateral",
                    "Elevacao Frontal",
                    "Triceps Corda",
                    "Triceps Frances",
                ],
            },
            {
                "label": "Pull",
                "name": "Pull - Puxar",
                "description": "Costas e biceps",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 65,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Remada Cavalinho",
                    "Remada Baixa no Cabo",
                    "Rosca Direta com Barra",
                    "Rosca Martelo",
                ],
            },
            {
                "label": "Legs",
                "name": "Legs - Pernas",
                "description": "Treino completo de pernas",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 75,
                "target_muscles": ["quadriceps", "hamstrings", "glutes", "calves"],
                "exercises": [
                    "Agachamento Livre",
                    "Levantamento Terra",
                    "Leg Press 45 Graus",
                    "Agachamento Hack",
                    "Mesa Flexora",
                    "Hip Thrust",
                    "Panturrilha em Pe",
                ],
            },
        ],
    },
    {
        "name": "Upper Lower - Forca",
        "description": "Programa focado em ganho de forca com divisao superior/inferior. Ideal para quem quer aumentar cargas nos exercicios compostos.",
        "goal": WorkoutGoal.STRENGTH,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.UPPER_LOWER,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Upper",
                "name": "Superior - Forca",
                "description": "Foco em forca para parte superior",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 60,
                "target_muscles": ["chest", "back", "shoulders"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Desenvolvimento com Barra",
                    "Barra Fixa (Pegada Pronada)",
                    "Supino Inclinado com Halteres",
                    "Rosca Direta com Barra",
                    "Triceps Corda",
                ],
            },
            {
                "label": "Lower",
                "name": "Inferior - Forca",
                "description": "Foco em forca para parte inferior",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 65,
                "target_muscles": ["quadriceps", "hamstrings", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Levantamento Terra",
                    "Leg Press 45 Graus",
                    "Stiff",
                    "Afundo com Halteres",
                    "Panturrilha em Pe",
                ],
            },
        ],
    },
    {
        "name": "Full Body - Emagrecimento",
        "description": "Programa de corpo inteiro com foco em perda de gordura. Combina treino resistido com elementos de alta intensidade.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body A",
                "description": "Circuito de corpo inteiro",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento Livre",
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Desenvolvimento com Halteres",
                    "Prancha",
                    "Burpee",
                ],
            },
            {
                "label": "B",
                "name": "Full Body B",
                "description": "Circuito de corpo inteiro alternativo",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Levantamento Terra",
                    "Flexao de Bracos",
                    "Puxada Frontal",
                    "Afundo com Halteres",
                    "Abdominal Crunch",
                    "Pular Corda",
                ],
            },
        ],
    },
    {
        "name": "Treino Feminino - Gluteos",
        "description": "Programa com enfase em gluteos e posterior de coxa. Ideal para mulheres que buscam hipertrofia na regiao inferior.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Gluteos e Posterior",
                "description": "Foco maximo em gluteos",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["glutes", "hamstrings"],
                "exercises": [
                    "Hip Thrust",
                    "Agachamento Livre",
                    "Stiff",
                    "Gluteo na Polia",
                    "Elevacao Pelvica",
                    "Mesa Flexora",
                ],
            },
            {
                "label": "B",
                "name": "Superior Completo",
                "description": "Treino de parte superior",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["back", "chest", "shoulders"],
                "exercises": [
                    "Puxada Frontal",
                    "Remada Baixa no Cabo",
                    "Supino Inclinado com Halteres",
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                ],
            },
            {
                "label": "C",
                "name": "Quadriceps e Gluteos",
                "description": "Foco em quadriceps com gluteos",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Leg Press 45 Graus",
                    "Agachamento Hack",
                    "Cadeira Extensora",
                    "Afundo com Halteres",
                    "Hip Thrust",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "D",
                "name": "Bracos e Abdomen",
                "description": "Bracos e core",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["biceps", "triceps", "abs"],
                "exercises": [
                    "Rosca Direta com Barra",
                    "Rosca Martelo",
                    "Triceps Corda",
                    "Triceps Frances",
                    "Prancha",
                    "Elevacao de Pernas",
                    "Abdominal Obliquo",
                ],
            },
        ],
    },

    # ==================== GESTANTES (4 programas) ====================

    {
        "name": "Gestante - 1º Trimestre",
        "description": "Programa seguro para gestantes no primeiro trimestre. Foco em fortalecimento geral, mobilidade e adaptacao ao exercicio durante a gravidez. Exercicios de baixo impacto.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body - Gestante 1T",
                "description": "Treino completo seguro para primeiro trimestre",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Elevacao Pelvica",
                    "Cat-Cow (Gato-Vaca)",
                    "Exercicio de Kegel",
                ],
            },
            {
                "label": "B",
                "name": "Mobilidade e Core",
                "description": "Foco em mobilidade e fortalecimento de core",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["abs", "glutes"],
                "exercises": [
                    "Marcha Estacionaria",
                    "Bird-Dog",
                    "Alongamento de Quadril",
                    "Prancha",
                    "Elevacao Pelvica",
                    "Exercicio de Kegel",
                ],
            },
        ],
    },
    {
        "name": "Gestante - 2º Trimestre",
        "description": "Programa para segundo trimestre de gestacao. Manutencao de forca e mobilidade com exercicios adaptados para o crescimento da barriga.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Pernas e Gluteos",
                "description": "Fortalecimento de membros inferiores",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Subida no Step",
                    "Elevacao Pelvica",
                    "Abducao de Quadril",
                    "Alongamento de Quadril",
                ],
            },
            {
                "label": "B",
                "name": "Superior e Core",
                "description": "Costas e core seguro",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["back", "abs"],
                "exercises": [
                    "Remada com Elastico",
                    "Flexao na Parede",
                    "Bird-Dog",
                    "Cat-Cow (Gato-Vaca)",
                    "Exercicio de Kegel",
                ],
            },
            {
                "label": "C",
                "name": "Cardio Leve e Mobilidade",
                "description": "Caminhada e alongamentos",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["cardio"],
                "exercises": [
                    "Caminhada Leve",
                    "Marcha Estacionaria",
                    "Alongamento de Quadril",
                    "Cat-Cow (Gato-Vaca)",
                ],
            },
        ],
    },
    {
        "name": "Gestante - 3º Trimestre",
        "description": "Programa para terceiro trimestre. Exercicios muito leves focados em preparacao para o parto, respiracao e manutencao da mobilidade.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 10,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Preparacao para o Parto",
                "description": "Exercicios de fortalecimento pelvico",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["glutes", "abs"],
                "exercises": [
                    "Exercicio de Kegel",
                    "Agachamento com Apoio",
                    "Elevacao Pelvica",
                    "Cat-Cow (Gato-Vaca)",
                    "Alongamento de Quadril",
                ],
            },
            {
                "label": "B",
                "name": "Mobilidade e Relaxamento",
                "description": "Foco em mobilidade e bem-estar",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 20,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Marcha Estacionaria",
                    "Bird-Dog",
                    "Cat-Cow (Gato-Vaca)",
                    "Alongamento de Quadril",
                    "Exercicio de Kegel",
                ],
            },
        ],
    },
    {
        "name": "Pos-Parto - Recuperacao",
        "description": "Programa de recuperacao pos-parto. Fortalecimento gradual do assoalho pelvico, core e retorno seguro a atividade fisica. Consulte seu medico antes de iniciar.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Recuperacao Pelvica",
                "description": "Fortalecimento do assoalho pelvico",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 20,
                "target_muscles": ["abs", "glutes"],
                "exercises": [
                    "Exercicio de Kegel",
                    "Elevacao Pelvica",
                    "Bird-Dog",
                    "Cat-Cow (Gato-Vaca)",
                ],
            },
            {
                "label": "B",
                "name": "Retorno Gradual",
                "description": "Fortalecimento geral leve",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Prancha",
                    "Exercicio de Kegel",
                ],
            },
        ],
    },

    # ==================== TERCEIRA IDADE (4 programas) ====================

    {
        "name": "Senior - Mobilidade e Equilibrio",
        "description": "Programa para idosos focado em melhorar equilibrio e prevenir quedas. Exercicios seguros e funcionais para o dia-a-dia.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Equilibrio e Coordenacao",
                "description": "Treino de equilibrio",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Marcha Estacionaria",
                    "Equilibrio Unipodal",
                    "Sentar e Levantar",
                    "Subida no Step",
                    "Cat-Cow (Gato-Vaca)",
                ],
            },
            {
                "label": "B",
                "name": "Forca Funcional",
                "description": "Fortalecimento para atividades diarias",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["quadriceps", "back"],
                "exercises": [
                    "Sentar e Levantar",
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Elevacao Pelvica",
                    "Equilibrio Unipodal",
                ],
            },
        ],
    },
    {
        "name": "Senior - Forca Funcional",
        "description": "Programa de fortalecimento para idosos ativos. Exercicios funcionais que simulam movimentos do dia-a-dia.",
        "goal": WorkoutGoal.STRENGTH,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Inferior e Core",
                "description": "Pernas e estabilidade",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["quadriceps", "abs"],
                "exercises": [
                    "Sentar e Levantar",
                    "Subida no Step",
                    "Agachamento com Apoio",
                    "Bird-Dog",
                    "Equilibrio Unipodal",
                    "Elevacao Pelvica",
                ],
            },
            {
                "label": "B",
                "name": "Superior Completo",
                "description": "Bracos e costas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["back", "chest"],
                "exercises": [
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Face Pull com Elastico",
                    "Rotacao de Tronco",
                    "Cat-Cow (Gato-Vaca)",
                ],
            },
        ],
    },
    {
        "name": "Senior - Saude Ossea",
        "description": "Programa com foco em saude ossea e prevencao de osteoporose. Inclui exercicios de impacto leve e fortalecimento.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Impacto Leve",
                "description": "Exercicios com impacto controlado",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Marcha Estacionaria",
                    "Subida no Step",
                    "Sentar e Levantar",
                    "Equilibrio Unipodal",
                ],
            },
            {
                "label": "B",
                "name": "Fortalecimento",
                "description": "Fortalecimento muscular",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["quadriceps", "back"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Elevacao Pelvica",
                ],
            },
            {
                "label": "C",
                "name": "Mobilidade",
                "description": "Flexibilidade e mobilidade",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 20,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Cat-Cow (Gato-Vaca)",
                    "Rotacao de Tronco",
                    "Alongamento de Quadril",
                    "Bird-Dog",
                ],
            },
        ],
    },
    {
        "name": "Senior Ativo - Intermediario",
        "description": "Para idosos ja treinados que buscam manter ou aumentar a forca. Exercicios com maior intensidade.",
        "goal": WorkoutGoal.STRENGTH,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABC,
        "duration_weeks": 10,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Pernas",
                "description": "Fortalecimento de membros inferiores",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Subida no Step",
                    "Elevacao Pelvica",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "B",
                "name": "Superior",
                "description": "Peito, costas e ombros",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["chest", "back", "shoulders"],
                "exercises": [
                    "Supino Inclinado com Halteres",
                    "Puxada Frontal",
                    "Remada Baixa no Cabo",
                    "Desenvolvimento com Halteres",
                    "Face Pull com Elastico",
                ],
            },
            {
                "label": "C",
                "name": "Core e Bracos",
                "description": "Estabilidade e bracos",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 35,
                "target_muscles": ["abs", "biceps", "triceps"],
                "exercises": [
                    "Prancha",
                    "Bird-Dog",
                    "Rosca Alternada com Halteres",
                    "Triceps Corda",
                    "Rotacao de Tronco",
                ],
            },
        ],
    },

    # ==================== CRIANCAS E ADOLESCENTES (3 programas) ====================

    {
        "name": "Kids Fun Training (8-12 anos)",
        "description": "Programa ludico para criancas de 8 a 12 anos. Foco em coordenacao motora, diversao e habitos saudaveis. Sem carga externa.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Circuito Divertido",
                "description": "Exercicios ludicos em circuito",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Polichinelo",
                    "Corrida Estacionaria",
                    "Agachamento com Apoio",
                    "Flexao na Parede",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "Coordenacao e Agilidade",
                "description": "Foco em coordenacao motora",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["cardio"],
                "exercises": [
                    "Skipping (Elevacao de Joelhos)",
                    "Polichinelo",
                    "Equilibrio Unipodal",
                    "Escalador (Mountain Climber)",
                    "Bird-Dog",
                ],
            },
        ],
    },
    {
        "name": "Teen Fitness (13-17 anos)",
        "description": "Iniciacao ao treinamento de forca para adolescentes. Foco em aprender a tecnica correta dos exercicios com cargas leves.",
        "goal": WorkoutGoal.GENERAL_FITNESS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Introducao - Pernas",
                "description": "Tecnica de exercicios de pernas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Afundo com Halteres",
                    "Elevacao Pelvica",
                    "Panturrilha em Pe",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "Introducao - Superior",
                "description": "Tecnica de exercicios de tronco",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["chest", "back"],
                "exercises": [
                    "Flexao de Bracos",
                    "Puxada Frontal",
                    "Remada com Elastico",
                    "Desenvolvimento com Halteres",
                    "Abdominal Crunch",
                ],
            },
            {
                "label": "C",
                "name": "Condicionamento",
                "description": "Cardio e core",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["cardio", "abs"],
                "exercises": [
                    "Polichinelo",
                    "Burpee",
                    "Escalador (Mountain Climber)",
                    "Prancha",
                    "Corrida Estacionaria",
                ],
            },
        ],
    },
    {
        "name": "Teen Athlete - Preparacao Esportiva",
        "description": "Programa para jovens atletas de 13-17 anos. Desenvolvimento de forca, explosao e condicionamento para melhora esportiva.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Forca Inferior",
                "description": "Forca de pernas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Levantamento Terra",
                    "Afundo com Halteres",
                    "Leg Press 45 Graus",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "B",
                "name": "Explosao",
                "description": "Potencia e velocidade",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Box Jump",
                    "Agachamento com Salto",
                    "Burpee",
                    "Kettlebell Swing",
                    "Escalador (Mountain Climber)",
                ],
            },
            {
                "label": "C",
                "name": "Forca Superior",
                "description": "Peito, costas e ombros",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["chest", "back", "shoulders"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Desenvolvimento com Barra",
                    "Barra Fixa (Pegada Pronada)",
                    "Face Pull com Elastico",
                ],
            },
            {
                "label": "D",
                "name": "Core e Condicionamento",
                "description": "Estabilidade e resistencia",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["abs", "cardio"],
                "exercises": [
                    "Prancha",
                    "Bird-Dog",
                    "Elevacao de Pernas",
                    "Battle Ropes",
                    "Pular Corda",
                ],
            },
        ],
    },

    # ==================== BULKING (4 programas) ====================

    {
        "name": "Bulking - Iniciante",
        "description": "Programa de ganho de massa para iniciantes. Foco em exercicios compostos com volume moderado. Recomendado superavit calorico de +300kcal e 1.8g/kg de proteina.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABC,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Peito e Triceps - Volume",
                "description": "Alto volume para peitoral",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["chest", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Crucifixo com Halteres",
                    "Crossover no Cabo",
                    "Triceps Corda",
                    "Triceps Frances",
                ],
            },
            {
                "label": "B",
                "name": "Costas e Biceps - Volume",
                "description": "Alto volume para costas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Remada Unilateral com Halter",
                    "Rosca Direta com Barra",
                    "Rosca Martelo",
                ],
            },
            {
                "label": "C",
                "name": "Pernas e Ombros - Volume",
                "description": "Alto volume para pernas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 60,
                "target_muscles": ["quadriceps", "hamstrings", "shoulders"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Stiff",
                    "Cadeira Extensora",
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                ],
            },
        ],
    },
    {
        "name": "Bulking - PPL Volume",
        "description": "Push/Pull/Legs de alto volume para ganho de massa. Para praticantes avancados. Superavit de +500kcal e 2g/kg de proteina recomendados.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.PUSH_PULL_LEGS,
        "duration_weeks": 16,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Push",
                "name": "Push - Alto Volume",
                "description": "Peito, ombros, triceps com volume alto",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 70,
                "target_muscles": ["chest", "shoulders", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Supino Declinado",
                    "Desenvolvimento com Barra",
                    "Elevacao Lateral",
                    "Crossover no Cabo",
                    "Triceps Corda",
                    "Triceps Testa",
                ],
            },
            {
                "label": "Pull",
                "name": "Pull - Alto Volume",
                "description": "Costas, biceps com volume alto",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 70,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Remada Cavalinho",
                    "Remada Baixa no Cabo",
                    "Pullover com Halter",
                    "Rosca Direta com Barra",
                    "Rosca Scott",
                ],
            },
            {
                "label": "Legs",
                "name": "Legs - Alto Volume",
                "description": "Pernas completas com volume alto",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 75,
                "target_muscles": ["quadriceps", "hamstrings", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Agachamento Hack",
                    "Levantamento Terra",
                    "Stiff",
                    "Mesa Flexora",
                    "Hip Thrust",
                    "Panturrilha em Pe",
                ],
            },
        ],
    },
    {
        "name": "Bulking - Forca e Massa",
        "description": "Programa hibrido de forca e hipertrofia. Combina trabalho pesado com volume moderado. Superavit de +400kcal.",
        "goal": WorkoutGoal.STRENGTH,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.UPPER_LOWER,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Upper A",
                "name": "Superior - Forca",
                "description": "Foco em forca no superior",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 65,
                "target_muscles": ["chest", "back", "shoulders"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Desenvolvimento com Barra",
                    "Supino Inclinado com Halteres",
                    "Barra Fixa (Pegada Pronada)",
                    "Rosca Direta com Barra",
                    "Triceps Corda",
                ],
            },
            {
                "label": "Lower A",
                "name": "Inferior - Forca",
                "description": "Foco em forca no inferior",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 70,
                "target_muscles": ["quadriceps", "hamstrings", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Levantamento Terra",
                    "Leg Press 45 Graus",
                    "Stiff",
                    "Hip Thrust",
                    "Panturrilha em Pe",
                ],
            },
        ],
    },
    {
        "name": "Lean Bulk - Ganho Limpo",
        "description": "Programa para ganho de massa com minimo de gordura. Volume alto, cardio moderado. Superavit controlado de +200kcal.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 16,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Peito e Triceps",
                "description": "Volume moderado com controle",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["chest", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Crucifixo com Halteres",
                    "Triceps Corda",
                    "Triceps Frances",
                ],
            },
            {
                "label": "B",
                "name": "Costas e Biceps",
                "description": "Volume moderado",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Puxada Frontal",
                    "Remada Curvada com Barra",
                    "Remada Unilateral com Halter",
                    "Rosca Direta com Barra",
                    "Rosca Martelo",
                ],
            },
            {
                "label": "C",
                "name": "Pernas",
                "description": "Pernas completas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 55,
                "target_muscles": ["quadriceps", "hamstrings", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Stiff",
                    "Cadeira Extensora",
                    "Mesa Flexora",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "D",
                "name": "Ombros e Abs",
                "description": "Ombros e core",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["shoulders", "abs"],
                "exercises": [
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                    "Crucifixo Inverso",
                    "Prancha",
                    "Abdominal Crunch",
                    "Bicicleta Ergometrica",
                ],
            },
        ],
    },

    # ==================== CUTTING (4 programas) ====================

    {
        "name": "Cutting - Iniciante",
        "description": "Programa de definicao para iniciantes. Manutencao de massa com deficit calorico moderado de -300kcal. Alta proteina (2g/kg).",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABC,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Superior + HIIT",
                "description": "Tronco com cardio",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["chest", "back"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Puxada Frontal",
                    "Desenvolvimento com Halteres",
                    "Remada Baixa no Cabo",
                    "Burpee",
                    "Escalador (Mountain Climber)",
                ],
            },
            {
                "label": "B",
                "name": "Inferior + HIIT",
                "description": "Pernas com cardio",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Stiff",
                    "Hip Thrust",
                    "Pular Corda",
                    "Agachamento com Salto",
                ],
            },
            {
                "label": "C",
                "name": "Full Body + Cardio",
                "description": "Circuito queima gordura",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Thruster",
                    "Burpee",
                    "Kettlebell Swing",
                    "Escalador (Mountain Climber)",
                    "Prancha",
                    "Corrida na Esteira",
                ],
            },
        ],
    },
    {
        "name": "Cutting - Preservar Massa",
        "description": "Programa de cutting focado em preservar massa muscular. Volume moderado, intensidade alta. Deficit de -400kcal.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.ABCD,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Peito e Triceps - Intenso",
                "description": "Manter intensidade, reduzir volume",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 50,
                "target_muscles": ["chest", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Supino Inclinado com Halteres",
                    "Crossover no Cabo",
                    "Triceps Corda",
                    "Mergulho no Banco",
                ],
            },
            {
                "label": "B",
                "name": "Costas e Biceps - Intenso",
                "description": "Manter cargas pesadas",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 50,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Rosca Direta com Barra",
                    "Rosca Concentrada",
                ],
            },
            {
                "label": "C",
                "name": "Pernas - Intenso",
                "description": "Pernas pesadas",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 55,
                "target_muscles": ["quadriceps", "hamstrings"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Levantamento Terra",
                    "Cadeira Extensora",
                    "Mesa Flexora",
                ],
            },
            {
                "label": "D",
                "name": "Ombros + HIIT",
                "description": "Ombros e cardio intenso",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 50,
                "target_muscles": ["shoulders", "cardio"],
                "exercises": [
                    "Desenvolvimento com Barra",
                    "Elevacao Lateral",
                    "Crucifixo Inverso",
                    "Battle Ropes",
                    "Burpee",
                ],
            },
        ],
    },
    {
        "name": "Cutting Agressivo",
        "description": "Cutting de curta duracao com deficit agressivo de -600kcal. Muito cardio, volume baixo. Para praticantes avancados.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.PUSH_PULL_LEGS,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Push",
                "name": "Push + Cardio",
                "description": "Empurrar com cardio intenso",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 55,
                "target_muscles": ["chest", "shoulders", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Desenvolvimento com Halteres",
                    "Crucifixo com Halteres",
                    "Triceps Corda",
                    "Burpee",
                    "Escalador (Mountain Climber)",
                ],
            },
            {
                "label": "Pull",
                "name": "Pull + Cardio",
                "description": "Puxar com cardio intenso",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 55,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Rosca Direta com Barra",
                    "Kettlebell Swing",
                    "Battle Ropes",
                ],
            },
            {
                "label": "Legs",
                "name": "Legs + HIIT",
                "description": "Pernas com HIIT",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 60,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Hip Thrust",
                    "Agachamento com Salto",
                    "Box Jump",
                    "Pular Corda",
                ],
            },
        ],
    },
    {
        "name": "Mini-Cut 4 Semanas",
        "description": "Cutting intenso de 4 semanas para perda rapida de gordura. Deficit de -500kcal. Treino diario. Nao recomendado por longos periodos.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 4,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body Intenso A",
                "description": "Circuito metabolico",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento Livre",
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Thruster",
                    "Burpee",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "Full Body Intenso B",
                "description": "Circuito metabolico alternativo",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Levantamento Terra",
                    "Desenvolvimento com Barra",
                    "Puxada Frontal",
                    "Kettlebell Swing",
                    "Escalador (Mountain Climber)",
                    "Battle Ropes",
                ],
            },
        ],
    },

    # ==================== ESPORTES ESPECIFICOS (4 programas) ====================

    {
        "name": "Preparacao Fisica - Futebol",
        "description": "Programa de preparacao fisica para jogadores de futebol. Foco em explosao, resistencia e prevencao de lesoes.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Forca de Membros Inferiores",
                "description": "Base de forca para pernas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["quadriceps", "hamstrings"],
                "exercises": [
                    "Agachamento Livre",
                    "Levantamento Terra",
                    "Afundo com Halteres",
                    "Mesa Flexora",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "B",
                "name": "Explosao e Potencia",
                "description": "Treino pliometrico",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Box Jump",
                    "Agachamento com Salto",
                    "Skipping (Elevacao de Joelhos)",
                    "Burpee",
                    "Escalador (Mountain Climber)",
                ],
            },
            {
                "label": "C",
                "name": "Core e Estabilidade",
                "description": "Prevencao de lesoes",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["abs", "glutes"],
                "exercises": [
                    "Prancha",
                    "Bird-Dog",
                    "Hip Thrust",
                    "Abducao de Quadril",
                    "Rotacao de Tronco",
                ],
            },
            {
                "label": "D",
                "name": "Resistencia",
                "description": "Condicionamento aerobico",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["cardio"],
                "exercises": [
                    "Corrida na Esteira",
                    "Pular Corda",
                    "Polichinelo",
                    "Corrida Estacionaria",
                ],
            },
        ],
    },
    {
        "name": "Preparacao Fisica - Corrida",
        "description": "Programa complementar para corredores. Fortalecimento de pernas, core e prevencao de lesoes comuns em corredores.",
        "goal": WorkoutGoal.ENDURANCE,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABC,
        "duration_weeks": 10,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Forca de Pernas",
                "description": "Fortalecimento para corredores",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["quadriceps", "hamstrings", "calves"],
                "exercises": [
                    "Agachamento Livre",
                    "Afundo com Halteres",
                    "Stiff",
                    "Elevacao Pelvica",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "B",
                "name": "Core e Estabilidade",
                "description": "Core forte para corrida",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 35,
                "target_muscles": ["abs", "glutes"],
                "exercises": [
                    "Prancha",
                    "Bird-Dog",
                    "Hip Thrust",
                    "Abducao de Quadril",
                    "Abdominal Crunch",
                ],
            },
            {
                "label": "C",
                "name": "Prevencao de Lesoes",
                "description": "Mobilidade e equilibrio",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Equilibrio Unipodal",
                    "Alongamento de Quadril",
                    "Cat-Cow (Gato-Vaca)",
                    "Ponte de Gluteos Unilateral",
                    "Rotacao de Tronco",
                ],
            },
        ],
    },
    {
        "name": "Preparacao Fisica - Natacao",
        "description": "Programa para nadadores. Foco em fortalecimento de ombros, costas e core para melhor desempenho na agua.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.UPPER_LOWER,
        "duration_weeks": 10,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Upper",
                "name": "Superior para Nadadores",
                "description": "Foco em ombros e costas",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["shoulders", "back"],
                "exercises": [
                    "Puxada Frontal",
                    "Remada Curvada com Barra",
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                    "Face Pull com Elastico",
                    "Rotacao Externa de Ombro",
                ],
            },
            {
                "label": "Lower",
                "name": "Inferior e Core",
                "description": "Pernas e estabilidade",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["quadriceps", "abs"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Prancha",
                    "Bird-Dog",
                    "Elevacao de Pernas",
                    "Hip Thrust",
                ],
            },
        ],
    },
    {
        "name": "Preparacao Fisica - Artes Marciais",
        "description": "Programa para praticantes de artes marciais. Forca funcional, explosao, core forte e condicionamento.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.ADVANCED,
        "split_type": SplitType.PUSH_PULL_LEGS,
        "duration_weeks": 12,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "Push",
                "name": "Empurrar e Explosao",
                "description": "Socos e empurroes",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 50,
                "target_muscles": ["chest", "shoulders", "triceps"],
                "exercises": [
                    "Supino Reto com Barra",
                    "Desenvolvimento com Barra",
                    "Flexao de Bracos",
                    "Triceps Corda",
                    "Escalador (Mountain Climber)",
                ],
            },
            {
                "label": "Pull",
                "name": "Puxar e Agarrar",
                "description": "Forca de agarre",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 50,
                "target_muscles": ["back", "biceps"],
                "exercises": [
                    "Barra Fixa (Pegada Pronada)",
                    "Remada Curvada com Barra",
                    "Puxada Frontal",
                    "Rosca Martelo",
                    "Farmers Walk",
                ],
            },
            {
                "label": "Legs",
                "name": "Chutes e Movimentacao",
                "description": "Pernas e explosao",
                "difficulty": Difficulty.ADVANCED,
                "duration_min": 55,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Box Jump",
                    "Agachamento com Salto",
                    "Hip Thrust",
                    "Kettlebell Swing",
                    "Prancha",
                ],
            },
        ],
    },

    # ==================== OBJETIVOS ESPECIFICOS (5 programas) ====================

    {
        "name": "Postura e Correcao",
        "description": "Programa para melhorar a postura. Fortalecimento de costas, core e alongamento de peitorais e flexores de quadril.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Fortalecimento Postural",
                "description": "Fortalecimento para boa postura",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["back", "abs"],
                "exercises": [
                    "Remada com Elastico",
                    "Face Pull com Elastico",
                    "Extensao de Coluna (Superman)",
                    "Bird-Dog",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "Mobilidade e Alongamento",
                "description": "Alongamentos para postura",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Cat-Cow (Gato-Vaca)",
                    "Alongamento de Quadril",
                    "Rotacao de Tronco",
                    "Rotacao Externa de Ombro",
                    "Equilibrio Unipodal",
                ],
            },
        ],
    },
    {
        "name": "Definicao Abdominal",
        "description": "Programa focado em definicao abdominal. Combina treino de core intenso com exercicios metabolicos. Requer deficit calorico.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Core Intenso",
                "description": "Treino pesado de abdomen",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 30,
                "target_muscles": ["abs"],
                "exercises": [
                    "Prancha",
                    "Elevacao de Pernas",
                    "Abdominal Crunch",
                    "Abdominal Obliquo",
                    "Bird-Dog",
                ],
            },
            {
                "label": "B",
                "name": "HIIT Metabolico",
                "description": "Queima de gordura",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 30,
                "target_muscles": ["cardio"],
                "exercises": [
                    "Burpee",
                    "Escalador (Mountain Climber)",
                    "Kettlebell Swing",
                    "Pular Corda",
                ],
            },
            {
                "label": "C",
                "name": "Full Body + Core",
                "description": "Treino completo com enfase em core",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento Livre",
                    "Supino Reto com Barra",
                    "Remada Curvada com Barra",
                    "Prancha",
                    "Roda Abdominal",
                ],
            },
            {
                "label": "D",
                "name": "Cardio e Core",
                "description": "Cardio com finalizacao de core",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 35,
                "target_muscles": ["cardio", "abs"],
                "exercises": [
                    "Corrida na Esteira",
                    "Elevacao de Pernas",
                    "Prancha",
                    "Escalador (Mountain Climber)",
                ],
            },
        ],
    },
    {
        "name": "Bracos Definidos",
        "description": "Programa de especializacao em bracos. Volume alto para biceps e triceps com treinos complementares para o resto do corpo.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABC,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Biceps Intenso",
                "description": "Foco total em biceps",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["biceps", "back"],
                "exercises": [
                    "Rosca Direta com Barra",
                    "Rosca Alternada com Halteres",
                    "Rosca Martelo",
                    "Rosca Scott",
                    "Puxada Frontal",
                ],
            },
            {
                "label": "B",
                "name": "Triceps Intenso",
                "description": "Foco total em triceps",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["triceps", "chest"],
                "exercises": [
                    "Triceps Corda",
                    "Triceps Testa",
                    "Triceps Frances",
                    "Mergulho no Banco",
                    "Supino Reto com Barra",
                ],
            },
            {
                "label": "C",
                "name": "Complementar",
                "description": "Pernas e core",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["quadriceps", "abs"],
                "exercises": [
                    "Agachamento Livre",
                    "Leg Press 45 Graus",
                    "Prancha",
                    "Elevacao de Pernas",
                ],
            },
        ],
    },
    {
        "name": "Gluteos 30 Dias",
        "description": "Desafio intensivo de 30 dias focado em gluteos. 4 treinos por semana com exercicios variados para maximo desenvolvimento.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.ABCD,
        "duration_weeks": 4,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Gluteos - Forca",
                "description": "Exercicios pesados",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 45,
                "target_muscles": ["glutes"],
                "exercises": [
                    "Hip Thrust",
                    "Agachamento Livre",
                    "Stiff",
                    "Gluteo na Polia",
                ],
            },
            {
                "label": "B",
                "name": "Gluteos - Volume",
                "description": "Alto volume",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 40,
                "target_muscles": ["glutes"],
                "exercises": [
                    "Elevacao Pelvica",
                    "Abducao de Quadril",
                    "Ponte de Gluteos Unilateral",
                    "Afundo com Halteres",
                ],
            },
            {
                "label": "C",
                "name": "Pernas Completas",
                "description": "Pernas com enfase em gluteos",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 50,
                "target_muscles": ["glutes", "quadriceps"],
                "exercises": [
                    "Leg Press 45 Graus",
                    "Agachamento Hack",
                    "Hip Thrust",
                    "Mesa Flexora",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "D",
                "name": "Ativacao e Metabolico",
                "description": "Ativacao glutea e cardio",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 35,
                "target_muscles": ["glutes", "cardio"],
                "exercises": [
                    "Abducao de Quadril",
                    "Elevacao Pelvica",
                    "Agachamento com Salto",
                    "Escalador (Mountain Climber)",
                ],
            },
        ],
    },
    {
        "name": "Condicionamento Geral",
        "description": "Programa de condicionamento para quem esta voltando a treinar ou iniciando. Base para progressao futura.",
        "goal": WorkoutGoal.GENERAL_FITNESS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 6,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body A",
                "description": "Introducao aos exercicios",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Prancha",
                    "Marcha Estacionaria",
                ],
            },
            {
                "label": "B",
                "name": "Full Body B",
                "description": "Progressao gradual",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Sentar e Levantar",
                    "Flexao de Bracos",
                    "Puxada Frontal",
                    "Bird-Dog",
                    "Polichinelo",
                ],
            },
        ],
    },

    # ==================== TREINO EM CASA (4 programas) ====================

    {
        "name": "Home - Sem Equipamento",
        "description": "Treino completo usando apenas o peso corporal. Ideal para treinar em casa sem nenhum equipamento.",
        "goal": WorkoutGoal.GENERAL_FITNESS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body Peso Corporal A",
                "description": "Treino completo sem equipamento",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Flexao de Bracos",
                    "Elevacao Pelvica",
                    "Prancha",
                    "Polichinelo",
                ],
            },
            {
                "label": "B",
                "name": "Full Body Peso Corporal B",
                "description": "Alternativo sem equipamento",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Afundo com Halteres",
                    "Flexao na Parede",
                    "Bird-Dog",
                    "Abdominal Crunch",
                    "Corrida Estacionaria",
                ],
            },
        ],
    },
    {
        "name": "Home - Halteres Basico",
        "description": "Treino em casa com par de halteres e banco. Programa completo de hipertrofia para ambiente domestico.",
        "goal": WorkoutGoal.HYPERTROPHY,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Superior com Halteres",
                "description": "Peito e costas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["chest", "back"],
                "exercises": [
                    "Supino Inclinado com Halteres",
                    "Crucifixo com Halteres",
                    "Remada Unilateral com Halter",
                    "Pullover com Halter",
                    "Flexao de Bracos",
                ],
            },
            {
                "label": "B",
                "name": "Inferior com Halteres",
                "description": "Pernas completas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 40,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento Livre",
                    "Afundo com Halteres",
                    "Stiff",
                    "Elevacao Pelvica",
                    "Panturrilha em Pe",
                ],
            },
            {
                "label": "C",
                "name": "Bracos e Ombros",
                "description": "Bracos com halteres",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["biceps", "triceps", "shoulders"],
                "exercises": [
                    "Desenvolvimento com Halteres",
                    "Elevacao Lateral",
                    "Rosca Alternada com Halteres",
                    "Triceps Frances",
                    "Prancha",
                ],
            },
        ],
    },
    {
        "name": "Home - Elasticos",
        "description": "Treino completo usando apenas bandas elasticas. Portatil e eficiente para qualquer lugar.",
        "goal": WorkoutGoal.GENERAL_FITNESS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 6,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Full Body Elastico A",
                "description": "Treino completo com bandas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Remada com Elastico",
                    "Face Pull com Elastico",
                    "Abducao de Quadril",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "Full Body Elastico B",
                "description": "Alternativo com bandas",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 35,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Afundo com Halteres",
                    "Flexao de Bracos",
                    "Rotacao Externa de Ombro",
                    "Elevacao Pelvica",
                    "Bird-Dog",
                ],
            },
        ],
    },
    {
        "name": "Home HIIT - Emagrecimento",
        "description": "Treino intervalado de alta intensidade para fazer em casa. Foco em queima de gordura sem equipamentos.",
        "goal": WorkoutGoal.FAT_LOSS,
        "difficulty": Difficulty.INTERMEDIATE,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 6,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "HIIT Circuito A",
                "description": "Circuito metabolico",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Burpee",
                    "Agachamento com Salto",
                    "Escalador (Mountain Climber)",
                    "Polichinelo",
                    "Prancha",
                ],
            },
            {
                "label": "B",
                "name": "HIIT Circuito B",
                "description": "Circuito alternativo",
                "difficulty": Difficulty.INTERMEDIATE,
                "duration_min": 30,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Skipping (Elevacao de Joelhos)",
                    "Flexao de Bracos",
                    "Agachamento Livre",
                    "Corrida Estacionaria",
                    "Elevacao de Pernas",
                ],
            },
        ],
    },

    # ==================== REABILITACAO (4 programas) ====================

    {
        "name": "Reabilitacao - Lombar",
        "description": "Programa de fortalecimento para quem sofre de dores lombares. Fortalecimento de core e mobilidade de coluna. Consulte um profissional antes.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Fortalecimento Lombar",
                "description": "Core e extensores",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["abs", "back"],
                "exercises": [
                    "Bird-Dog",
                    "Prancha",
                    "Elevacao Pelvica",
                    "Cat-Cow (Gato-Vaca)",
                    "Extensao de Coluna (Superman)",
                ],
            },
            {
                "label": "B",
                "name": "Mobilidade e Alongamento",
                "description": "Flexibilidade lombar",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["back", "glutes"],
                "exercises": [
                    "Cat-Cow (Gato-Vaca)",
                    "Rotacao de Tronco",
                    "Alongamento de Quadril",
                    "Abducao de Quadril",
                ],
            },
        ],
    },
    {
        "name": "Reabilitacao - Ombro",
        "description": "Programa para recuperacao e fortalecimento de ombros. Foco em manguito rotador e estabilizadores. Consulte um fisioterapeuta.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Fortalecimento de Ombro",
                "description": "Manguito rotador",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["shoulders"],
                "exercises": [
                    "Rotacao Externa de Ombro",
                    "Face Pull com Elastico",
                    "Elevacao Lateral",
                    "Flexao na Parede",
                ],
            },
            {
                "label": "B",
                "name": "Mobilidade de Ombro",
                "description": "Amplitude e mobilidade",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 20,
                "target_muscles": ["shoulders", "back"],
                "exercises": [
                    "Cat-Cow (Gato-Vaca)",
                    "Rotacao de Tronco",
                    "Face Pull com Elastico",
                    "Remada com Elastico",
                ],
            },
        ],
    },
    {
        "name": "Reabilitacao - Joelho",
        "description": "Programa para fortalecimento de joelhos. Foco em quadriceps, posterior e estabilidade. Consulte um profissional antes de iniciar.",
        "goal": WorkoutGoal.FUNCTIONAL,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.FULL_BODY,
        "duration_weeks": 8,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Fortalecimento de Joelho",
                "description": "Quadriceps e posterior",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["quadriceps", "hamstrings"],
                "exercises": [
                    "Sentar e Levantar",
                    "Wall Sit (Cadeirinha)",
                    "Elevacao Pelvica",
                    "Subida no Step",
                    "Equilibrio Unipodal",
                ],
            },
            {
                "label": "B",
                "name": "Estabilidade e Mobilidade",
                "description": "Equilibrio e flexibilidade",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Equilibrio Unipodal",
                    "Ponte de Gluteos Unilateral",
                    "Alongamento de Quadril",
                    "Abducao de Quadril",
                ],
            },
        ],
    },
    {
        "name": "Retorno ao Treino",
        "description": "Programa para quem esta retornando apos lesao ou longo periodo sem treinar. Progressao gradual e segura.",
        "goal": WorkoutGoal.GENERAL_FITNESS,
        "difficulty": Difficulty.BEGINNER,
        "split_type": SplitType.ABC,
        "duration_weeks": 6,
        "is_template": True,
        "is_public": True,
        "workouts": [
            {
                "label": "A",
                "name": "Readaptacao - Inferior",
                "description": "Pernas com carga leve",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["quadriceps", "glutes"],
                "exercises": [
                    "Agachamento com Apoio",
                    "Sentar e Levantar",
                    "Elevacao Pelvica",
                    "Equilibrio Unipodal",
                ],
            },
            {
                "label": "B",
                "name": "Readaptacao - Superior",
                "description": "Tronco com carga leve",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 30,
                "target_muscles": ["chest", "back"],
                "exercises": [
                    "Flexao na Parede",
                    "Remada com Elastico",
                    "Face Pull com Elastico",
                    "Prancha",
                ],
            },
            {
                "label": "C",
                "name": "Mobilidade Geral",
                "description": "Alongamento e mobilidade",
                "difficulty": Difficulty.BEGINNER,
                "duration_min": 25,
                "target_muscles": ["full_body"],
                "exercises": [
                    "Cat-Cow (Gato-Vaca)",
                    "Alongamento de Quadril",
                    "Rotacao de Tronco",
                    "Bird-Dog",
                    "Marcha Estacionaria",
                ],
            },
        ],
    },
]


async def get_system_user(session: AsyncSession) -> User | None:
    """Get or create a system user for seed data."""
    result = await session.execute(
        select(User).where(User.email == "system@myfit.app")
    )
    user = result.scalar_one_or_none()

    if not user:
        # Try to get the first admin user
        result = await session.execute(
            select(User).limit(1)
        )
        user = result.scalar_one_or_none()

    return user


async def get_exercise_by_name(session: AsyncSession, name: str) -> Exercise | None:
    """Get exercise by name."""
    result = await session.execute(
        select(Exercise).where(Exercise.name == name)
    )
    return result.scalar_one_or_none()


async def seed_workout_programs(session: AsyncSession, clear_existing: bool = False) -> dict:
    """Seed the database with workout programs and templates."""

    # Get system user for created_by
    user = await get_system_user(session)
    if not user:
        print("ERROR: No user found in database. Please create a user first.")
        return {"plans": 0, "workouts": 0, "exercises_linked": 0}

    print(f"Using user: {user.email} (id: {user.id})")

    if clear_existing:
        print("Clearing existing programs and workouts...")
        await session.execute(delete(PlanWorkout))
        await session.execute(delete(WorkoutExercise))
        await session.execute(delete(TrainingPlan).where(TrainingPlan.is_template == True))
        await session.execute(delete(Workout).where(Workout.is_template == True))
        await session.commit()
    else:
        # Check if programs already exist
        result = await session.execute(
            select(TrainingPlan).where(TrainingPlan.is_template == True).limit(1)
        )
        if result.scalar_one_or_none():
            print("Template programs already exist. Use --clear to replace them.")
            return {"plans": 0, "workouts": 0, "exercises_linked": 0}

    plans_count = 0
    workouts_count = 0
    exercises_linked = 0

    for plan_data in PLANS:
        print(f"\nCreating plan: {plan_data['name']}")

        # Create the plan (no created_by_id for system templates)
        plan = TrainingPlan(
            name=plan_data["name"],
            description=plan_data["description"],
            goal=plan_data["goal"],
            difficulty=plan_data["difficulty"],
            split_type=plan_data["split_type"],
            duration_weeks=plan_data.get("duration_weeks"),
            is_template=plan_data["is_template"],
            is_public=plan_data["is_public"],
            created_by_id=None,  # System templates have no owner
        )
        session.add(plan)
        await session.flush()  # Get the plan ID
        plans_count += 1

        # Create workouts for this plan
        for order, workout_data in enumerate(plan_data["workouts"]):
            print(f"  - Creating workout: {workout_data['name']}")

            workout = Workout(
                name=workout_data["name"],
                description=workout_data.get("description"),
                difficulty=workout_data["difficulty"],
                estimated_duration_min=workout_data.get("duration_min", 60),
                target_muscles=workout_data.get("target_muscles"),
                is_template=True,
                is_public=True,
                created_by_id=None,  # System templates have no owner
            )
            session.add(workout)
            await session.flush()
            workouts_count += 1

            # Link workout to plan
            plan_workout = PlanWorkout(
                plan_id=plan.id,
                workout_id=workout.id,
                order=order,
                label=workout_data["label"],
            )
            session.add(plan_workout)

            # Add exercises to workout
            for ex_order, exercise_name in enumerate(workout_data.get("exercises", [])):
                exercise = await get_exercise_by_name(session, exercise_name)
                if exercise:
                    config = EXERCISE_CONFIGS.get(exercise_name, {})
                    workout_exercise = WorkoutExercise(
                        workout_id=workout.id,
                        exercise_id=exercise.id,
                        order=ex_order,
                        sets=config.get("sets", 3),
                        reps=config.get("reps", "10-12"),
                        rest_seconds=config.get("rest", 60),
                    )
                    session.add(workout_exercise)
                    exercises_linked += 1
                else:
                    print(f"    WARNING: Exercise not found: {exercise_name}")

    await session.commit()

    return {
        "plans": plans_count,
        "workouts": workouts_count,
        "exercises_linked": exercises_linked,
    }


async def main():
    """Main function to run the seed."""
    import argparse

    parser = argparse.ArgumentParser(description="Seed workout programs database")
    parser.add_argument("--clear", action="store_true", help="Clear existing templates first")
    args = parser.parse_args()

    print("=" * 60)
    print("Workout Programs Seed Script")
    print("=" * 60)

    async with AsyncSessionLocal() as session:
        result = await seed_workout_programs(session, clear_existing=args.clear)

    print("\n" + "=" * 60)
    print(f"Successfully seeded:")
    print(f"  - {result['programs']} programs")
    print(f"  - {result['workouts']} workouts")
    print(f"  - {result['exercises_linked']} exercise links")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
