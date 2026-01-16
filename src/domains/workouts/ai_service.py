"""AI Service for intelligent exercise suggestions using OpenAI."""

import json
from typing import Any

from openai import AsyncOpenAI

from src.config.settings import settings
from src.domains.workouts.models import Difficulty, MuscleGroup, WorkoutGoal


class AIExerciseService:
    """Service for AI-powered exercise suggestions."""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def suggest_exercises(
        self,
        available_exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        count: int = 6,
        exclude_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Use AI to suggest the best exercises based on context.

        Falls back to rule-based selection if AI is not available.
        """
        # Filter available exercises by muscle group
        filtered = [
            ex for ex in available_exercises
            if ex["muscle_group"].lower() in [mg.lower() for mg in muscle_groups]
            and (not exclude_ids or str(ex["id"]) not in exclude_ids)
        ]

        if not filtered:
            return {
                "suggestions": [],
                "message": "Nenhum exercicio encontrado para os grupos musculares selecionados.",
            }

        # Try AI-powered suggestion if available
        if self.client and settings.OPENAI_API_KEY:
            try:
                return await self._ai_suggest(filtered, muscle_groups, goal, difficulty, count)
            except Exception as e:
                print(f"AI suggestion failed, falling back to rules: {e}")

        # Fallback to rule-based selection
        return self._rule_based_suggest(filtered, muscle_groups, goal, difficulty, count)

    async def _ai_suggest(
        self,
        exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        count: int,
    ) -> dict[str, Any]:
        """Use OpenAI to intelligently select and configure exercises."""

        # Build exercise list for prompt
        exercise_list = "\n".join([
            f"- ID: {ex['id']}, Nome: {ex['name']}, Grupo: {ex['muscle_group']}"
            for ex in exercises[:50]  # Limit to avoid token limits
        ])

        goal_descriptions = {
            WorkoutGoal.HYPERTROPHY: "hipertrofia (ganho de massa muscular)",
            WorkoutGoal.STRENGTH: "forca maxima",
            WorkoutGoal.FAT_LOSS: "emagrecimento e queima de gordura",
            WorkoutGoal.ENDURANCE: "resistencia muscular",
            WorkoutGoal.FUNCTIONAL: "funcionalidade e mobilidade",
        }

        difficulty_descriptions = {
            Difficulty.BEGINNER: "iniciante (exercicios simples e seguros)",
            Difficulty.INTERMEDIATE: "intermediario (exercicios compostos e isolados)",
            Difficulty.ADVANCED: "avancado (tecnicas avancadas e alta intensidade)",
        }

        prompt = f"""Voce e um personal trainer experiente. Selecione os {count} melhores exercicios para um treino com as seguintes caracteristicas:

OBJETIVO: {goal_descriptions.get(goal, goal.value)}
NIVEL: {difficulty_descriptions.get(difficulty, difficulty.value)}
GRUPOS MUSCULARES: {', '.join(muscle_groups)}

EXERCICIOS DISPONIVEIS:
{exercise_list}

REGRAS:
1. Selecione exercicios variados que trabalhem os grupos musculares solicitados
2. Comece com exercicios compostos e termine com isolados
3. Configure series, repeticoes e descanso apropriados para o objetivo
4. Para hipertrofia: 3-4 series, 8-12 reps, 60-90s descanso
5. Para forca: 4-5 series, 3-6 reps, 120-180s descanso
6. Para emagrecimento: 3 series, 12-15 reps, 30-45s descanso
7. Para resistencia: 2-3 series, 15-20 reps, 30s descanso

Responda APENAS com um JSON valido no formato:
{{
  "suggestions": [
    {{
      "exercise_id": "uuid-do-exercicio",
      "name": "Nome do Exercicio",
      "muscle_group": "grupo_muscular",
      "sets": 3,
      "reps": "10-12",
      "rest_seconds": 60,
      "order": 0,
      "reason": "Motivo da escolha"
    }}
  ],
  "message": "Dica geral sobre o treino"
}}"""

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Voce e um personal trainer que responde apenas em JSON valido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        content = response.choices[0].message.content

        # Parse JSON response
        # Handle potential markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())

        # Validate exercise IDs exist
        valid_ids = {str(ex["id"]) for ex in exercises}
        result["suggestions"] = [
            s for s in result["suggestions"]
            if s["exercise_id"] in valid_ids
        ]

        return result

    def _rule_based_suggest(
        self,
        exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        count: int,
    ) -> dict[str, Any]:
        """Rule-based fallback for exercise selection."""

        # Determine sets/reps based on goal
        config_map = {
            WorkoutGoal.HYPERTROPHY: (4, "8-12", 60, "Foque em contracao controlada e tempo sob tensao."),
            WorkoutGoal.STRENGTH: (5, "3-6", 120, "Priorize cargas pesadas com descanso adequado."),
            WorkoutGoal.FAT_LOSS: (3, "12-15", 45, "Mantenha o ritmo elevado entre exercicios."),
            WorkoutGoal.ENDURANCE: (3, "15-20", 30, "Use cargas moderadas com muitas repeticoes."),
            WorkoutGoal.FUNCTIONAL: (3, "10-12", 60, "Priorize movimentos compostos e estabilidade."),
        }

        sets, reps, rest, message = config_map.get(
            goal, (3, "10-12", 60, "Bom treino!")
        )

        suggestions = []
        used_ids = set()

        # Distribute exercises across muscle groups
        exercises_per_group = max(1, count // len(muscle_groups))

        for mg in muscle_groups:
            mg_lower = mg.lower()
            group_exercises = [
                ex for ex in exercises
                if ex["muscle_group"].lower() == mg_lower
                and str(ex["id"]) not in used_ids
            ]

            for i, ex in enumerate(group_exercises[:exercises_per_group]):
                suggestions.append({
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                    "order": len(suggestions),
                    "reason": f"Exercicio para {ex['muscle_group']}",
                })
                used_ids.add(str(ex["id"]))

        # Fill remaining slots
        remaining = count - len(suggestions)
        for ex in exercises:
            if remaining <= 0:
                break
            if str(ex["id"]) not in used_ids:
                suggestions.append({
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                    "order": len(suggestions),
                    "reason": f"Exercicio complementar para {ex['muscle_group']}",
                })
                used_ids.add(str(ex["id"]))
                remaining -= 1

        return {
            "suggestions": suggestions[:count],
            "message": message,
        }
