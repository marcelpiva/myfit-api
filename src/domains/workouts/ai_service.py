"""AI Service for intelligent exercise suggestions using OpenAI."""

import json
import uuid
from typing import Any

from openai import AsyncOpenAI

from src.config.settings import settings
from src.domains.workouts.models import Difficulty, MuscleGroup, SplitType, TechniqueType, WorkoutGoal


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
        context: dict[str, Any] | None = None,
        allow_advanced_techniques: bool = True,
        allowed_techniques: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Use AI to suggest the best exercises based on context.

        Falls back to rule-based selection if AI is not available.

        Args:
            allowed_techniques: If provided, ONLY these techniques are allowed.
                               E.g., ['biset', 'superset'] means only bi-sets and supersets.
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
                return await self._ai_suggest(
                    filtered, muscle_groups, goal, difficulty, count,
                    context=context,
                    allow_advanced_techniques=allow_advanced_techniques,
                    allowed_techniques=allowed_techniques,
                )
            except Exception as e:
                print(f"AI suggestion failed, falling back to rules: {e}")

        # Fallback to rule-based selection
        return self._rule_based_suggest(
            filtered, muscle_groups, goal, difficulty, count,
            context=context,
            allow_advanced_techniques=allow_advanced_techniques,
            allowed_techniques=allowed_techniques,
        )

    async def _ai_suggest(
        self,
        exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        count: int,
        context: dict[str, Any] | None = None,
        allow_advanced_techniques: bool = True,
        allowed_techniques: list[str] | None = None,
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

        # Build context section
        context_section = ""
        if context:
            context_parts = []
            if context.get("plan_name"):
                context_parts.append(f"PLANO: {context['plan_name']}")
            if context.get("workout_name"):
                context_parts.append(f"TREINO: {context['workout_name']}")
            if context.get("workout_label"):
                context_parts.append(f"LABEL: {context['workout_label']}")
            if context.get("plan_split_type"):
                context_parts.append(f"DIVISAO: {context['plan_split_type']}")
            if context.get("existing_exercises"):
                context_parts.append(f"EXERCICIOS JA NO TREINO: {', '.join(context['existing_exercises'])}")
            if context_parts:
                context_section = "\nCONTEXTO DO TREINO:\n" + "\n".join(context_parts) + "\n"

        # Build advanced techniques section
        techniques_section = ""

        # If specific techniques are required, build a restricted prompt
        if allowed_techniques and len(allowed_techniques) > 0:
            technique_descriptions = {
                "normal": '"normal": Exercicio padrao',
                "dropset": '"dropset": Dropset - reducao de carga sem descanso',
                "rest_pause": '"rest_pause": Rest-pause - pausas curtas de 10-15s',
                "cluster": '"cluster": Cluster set - series fracionadas',
                "biset": '"biset": Bi-set - dois exercicios do mesmo grupo SEM descanso',
                "superset": '"superset": Superset - dois exercicios de grupos DIFERENTES sem descanso',
                "triset": '"triset": Tri-set - tres exercicios sem descanso',
                "giantset": '"giantset": Giant set - quatro ou mais exercicios sem descanso',
            }

            allowed_list = [technique_descriptions.get(t, f'"{t}"') for t in allowed_techniques if t in technique_descriptions]

            # Check if only group techniques are allowed (no normal)
            group_techniques = {"biset", "superset", "triset", "giantset"}
            only_group_techniques = all(t in group_techniques for t in allowed_techniques)

            if only_group_techniques:
                # Calculate pairs/groups needed
                if "biset" in allowed_techniques or "superset" in allowed_techniques:
                    group_size = 2
                elif "triset" in allowed_techniques:
                    group_size = 3
                else:
                    group_size = 4

                techniques_section = f"""

TECNICAS PERMITIDAS (OBRIGATORIO usar APENAS estas):
{chr(10).join('- ' + t for t in allowed_list)}

REGRA CRITICA: Voce DEVE usar SOMENTE as tecnicas listadas acima.
NAO crie exercicios com technique_type "normal" - TODOS devem usar as tecnicas permitidas.

Como "normal" NAO esta permitido, TODOS os {count} exercicios devem estar em grupos de {group_size}.
Isso significa que voce deve criar {count // group_size} grupos.

REGRAS OBRIGATORIAS PARA GRUPOS:
1. Gere um UUID unico para cada grupo (ex: "group-" + 8 caracteres aleatorios)
2. TODOS exercicios do grupo devem ter o MESMO "exercise_group_id"
3. Use "exercise_group_order": 0 para o primeiro, 1 para o segundo, etc.
4. TODOS exceto o ultimo do grupo: "rest_seconds": 0
5. Ultimo exercicio do grupo: "rest_seconds": 60-90
6. Para bi-set do mesmo grupo muscular: "technique_type": "biset"
7. Para superset de grupos diferentes: "technique_type": "superset"

EXEMPLO de bi-set:
[
  {{"exercise_id": "...", "technique_type": "biset", "exercise_group_id": "group-abc123", "exercise_group_order": 0, "rest_seconds": 0}},
  {{"exercise_id": "...", "technique_type": "biset", "exercise_group_id": "group-abc123", "exercise_group_order": 1, "rest_seconds": 60}}
]"""
            else:
                techniques_section = f"""

TECNICAS PERMITIDAS (use APENAS estas):
{chr(10).join('- ' + t for t in allowed_list)}

IMPORTANTE: Voce DEVE usar SOMENTE as tecnicas listadas acima. NAO use outras tecnicas.

REGRAS PARA BI-SET/SUPERSET/TRI-SET/GIANT-SET:
1. Gere um UUID unico para cada grupo (ex: "group-" + 8 caracteres)
2. TODOS exercicios do grupo devem ter o MESMO "exercise_group_id"
3. Use "exercise_group_order": 0 para o primeiro, 1 para o segundo, etc.
4. TODOS exceto o ultimo do grupo: "rest_seconds": 0
5. Ultimo exercicio do grupo: "rest_seconds": 60-90"""

        elif allow_advanced_techniques and difficulty != Difficulty.BEGINNER:
            # Original behavior - allow all techniques
            techniques_section = """

TECNICAS AVANCADAS (opcional - use quando apropriado):
Voce pode sugerir tecnicas avancadas para intensificar o treino. Use-as com moderacao.

TIPOS DE TECNICA:
- "normal": Exercicio padrao (default)
- "dropset": Dropset - reducao de carga sem descanso (bom para hipertrofia)
- "rest_pause": Rest-pause - pausas curtas de 10-15s entre mini-series
- "cluster": Cluster set - series fracionadas com descanso intra-serie
- "isometric": Isometrico - pausa estatica em um ponto do movimento
- "biset": Bi-set - dois exercicios do mesmo grupo muscular sem descanso
- "superset": Superset - dois exercicios de grupos diferentes sem descanso
- "triset": Tri-set - tres exercicios sem descanso
- "giantset": Giant set - quatro ou mais exercicios sem descanso

REGRAS PARA TECNICAS:
1. Para biset/superset/triset/giantset: agrupe exercicios consecutivos usando o mesmo "exercise_group_id"
2. Dentro do grupo, use "exercise_group_order" para indicar a ordem (0, 1, 2...)
3. Use "execution_instructions" para instrucoes especificas da tecnica
4. Para isometric, defina "isometric_seconds" (ex: 3-5 segundos)
5. Nao use tecnicas avancadas para TODOS os exercicios - apenas 1-2 por treino
6. Dropset e rest-pause sao bons para o ULTIMO exercicio de cada grupo muscular"""

        prompt = f"""Voce e um personal trainer experiente. Selecione os {count} melhores exercicios para um treino com as seguintes caracteristicas:

OBJETIVO: {goal_descriptions.get(goal, goal.value)}
NIVEL: {difficulty_descriptions.get(difficulty, difficulty.value)}
GRUPOS MUSCULARES: {', '.join(muscle_groups)}
{context_section}
EXERCICIOS DISPONIVEIS:
{exercise_list}

REGRAS GERAIS:
1. Selecione exercicios variados que trabalhem os grupos musculares solicitados
2. Comece com exercicios compostos e termine com isolados
3. Configure series, repeticoes e descanso apropriados para o objetivo
4. Para hipertrofia: 3-4 series, 8-12 reps, 60-90s descanso
5. Para forca: 4-5 series, 3-6 reps, 120-180s descanso
6. Para emagrecimento: 3 series, 12-15 reps, 30-45s descanso
7. Para resistencia: 2-3 series, 15-20 reps, 30s descanso
8. Considere os exercicios ja existentes no treino para evitar redundancia
{techniques_section}

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
      "reason": "Motivo da escolha",
      "technique_type": "normal",
      "exercise_group_id": null,
      "exercise_group_order": 0,
      "execution_instructions": null,
      "isometric_seconds": null
    }}
  ],
  "message": "Dica geral sobre o treino"
}}"""

        response = await self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
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

        # Validate exercise IDs exist and normalize technique fields
        valid_ids = {str(ex["id"]) for ex in exercises}
        # Valid database technique types (must match TechniqueType enum)
        valid_db_techniques = {"normal", "dropset", "rest_pause", "cluster", "superset", "biset", "triset", "giantset"}

        # Single-exercise techniques should NOT have group_id
        single_exercise_techniques = {"dropset", "rest_pause", "cluster", "normal"}
        # Group techniques require group_id
        group_techniques = {"superset", "biset", "triset", "giantset"}

        validated_suggestions = []
        for s in result["suggestions"]:
            if s["exercise_id"] in valid_ids:
                # Ensure technique fields have default values if missing
                s.setdefault("technique_type", "normal")
                s.setdefault("exercise_group_id", None)
                s.setdefault("exercise_group_order", 0)
                s.setdefault("execution_instructions", None)
                s.setdefault("isometric_seconds", None)

                # Normalize technique type names to match database enum
                technique = s["technique_type"].lower()
                if technique == "isometric":
                    # Isometric is handled via isometric_seconds field, not as a technique type
                    technique = "normal"
                elif technique == "bi_set":
                    technique = "biset"
                elif technique == "tri_set":
                    technique = "triset"
                elif technique == "giant_set":
                    technique = "giantset"

                # Validate technique_type against database values
                if technique not in valid_db_techniques:
                    technique = "normal"

                # ENFORCE allowed_techniques restriction
                if allowed_techniques and len(allowed_techniques) > 0:
                    if technique not in allowed_techniques:
                        # Technique not allowed - use first allowed technique
                        # Prefer group techniques if they're in the allowed list
                        for allowed in allowed_techniques:
                            if allowed in group_techniques:
                                technique = allowed
                                break
                        else:
                            technique = allowed_techniques[0]

                s["technique_type"] = technique

                # IMPORTANT: Single-exercise techniques should NEVER have a group_id
                if s["technique_type"] in single_exercise_techniques:
                    s["exercise_group_id"] = None
                    s["exercise_group_order"] = 0

                # Group techniques without group_id should be converted to normal
                # BUT only if "normal" is allowed
                if s["technique_type"] in group_techniques and not s.get("exercise_group_id"):
                    if allowed_techniques and "normal" not in allowed_techniques:
                        # Generate a group_id since we can't fall back to normal
                        s["exercise_group_id"] = f"group-{uuid.uuid4().hex[:8]}"
                    else:
                        s["technique_type"] = "normal"

                validated_suggestions.append(s)

        result["suggestions"] = validated_suggestions
        return result

    def _rule_based_suggest(
        self,
        exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        count: int,
        context: dict[str, Any] | None = None,
        allow_advanced_techniques: bool = True,
        allowed_techniques: list[str] | None = None,
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

        # Check if only group techniques are allowed (no normal)
        group_techniques = {"biset", "superset", "triset", "giantset"}
        only_group_techniques = (
            allowed_techniques
            and len(allowed_techniques) > 0
            and all(t in group_techniques for t in allowed_techniques)
        )

        # If only group techniques are allowed, use the paired suggestion method
        if only_group_techniques:
            return self._generate_paired_suggestions(
                exercises, muscle_groups, goal, count, sets, reps, rest, allowed_techniques, context
            )

        suggestions = []
        used_ids = set()

        # Check existing exercises to avoid duplicates
        existing_names = set()
        if context and context.get("existing_exercises"):
            existing_names = {name.lower() for name in context["existing_exercises"]}

        # Distribute exercises across muscle groups
        exercises_per_group = max(1, count // len(muscle_groups))

        for mg in muscle_groups:
            mg_lower = mg.lower()
            group_exercises = [
                ex for ex in exercises
                if ex["muscle_group"].lower() == mg_lower
                and str(ex["id"]) not in used_ids
                and ex["name"].lower() not in existing_names
            ]

            for i, ex in enumerate(group_exercises[:exercises_per_group]):
                technique = "normal"
                execution_instructions = None
                reason = f"Exercicio para {ex['muscle_group']}"

                # For advanced users with hypertrophy goal, suggest dropset on last exercise of each group
                if (allow_advanced_techniques
                    and difficulty == Difficulty.ADVANCED
                    and goal == WorkoutGoal.HYPERTROPHY
                    and i == exercises_per_group - 1):
                    # Only use dropset if it's allowed
                    if not allowed_techniques or "dropset" in allowed_techniques:
                        technique = "dropset"
                        execution_instructions = "Faca 2-3 reducoes de carga de 20-30%"
                        reason = f"Dropset para maxima hipertrofia em {ex['muscle_group']}"

                # Enforce allowed_techniques
                if allowed_techniques and technique not in allowed_techniques:
                    technique = allowed_techniques[0] if allowed_techniques else "normal"

                suggestion = {
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                    "order": len(suggestions),
                    "reason": reason,
                    "technique_type": technique,
                    "exercise_group_id": None,
                    "exercise_group_order": 0,
                    "execution_instructions": execution_instructions,
                    "isometric_seconds": None,
                }

                suggestions.append(suggestion)
                used_ids.add(str(ex["id"]))

        # Fill remaining slots
        remaining = count - len(suggestions)
        for ex in exercises:
            if remaining <= 0:
                break
            if str(ex["id"]) not in used_ids and ex["name"].lower() not in existing_names:
                technique = "normal"
                if allowed_techniques and "normal" not in allowed_techniques:
                    technique = allowed_techniques[0]

                suggestions.append({
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": rest,
                    "order": len(suggestions),
                    "reason": f"Exercicio complementar para {ex['muscle_group']}",
                    "technique_type": technique,
                    "exercise_group_id": None,
                    "exercise_group_order": 0,
                    "execution_instructions": None,
                    "isometric_seconds": None,
                })
                used_ids.add(str(ex["id"]))
                remaining -= 1

        return {
            "suggestions": suggestions[:count],
            "message": message,
        }

    def _generate_paired_suggestions(
        self,
        exercises: list[dict[str, Any]],
        muscle_groups: list[str],
        goal: WorkoutGoal,
        count: int,
        sets: int,
        reps: str,
        rest: int,
        allowed_techniques: list[str],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate exercises in pairs/groups when only group techniques are allowed."""

        suggestions = []
        used_ids = set()

        # Check existing exercises to avoid duplicates
        existing_names = set()
        if context and context.get("existing_exercises"):
            existing_names = {name.lower() for name in context["existing_exercises"]}

        # Determine group size based on allowed techniques
        if "triset" in allowed_techniques:
            group_size = 3
            technique = "triset"
        elif "giantset" in allowed_techniques:
            group_size = 4
            technique = "giantset"
        else:
            group_size = 2
            technique = "biset" if "biset" in allowed_techniques else "superset"

        # Get all available exercises
        available = [
            ex for ex in exercises
            if ex["muscle_group"].lower() in [mg.lower() for mg in muscle_groups]
            and str(ex["id"]) not in used_ids
            and ex["name"].lower() not in existing_names
        ]

        # Create groups
        num_groups = count // group_size
        exercise_idx = 0

        for group_num in range(num_groups):
            group_id = f"group-{uuid.uuid4().hex[:8]}"

            for order_in_group in range(group_size):
                if exercise_idx >= len(available):
                    break

                ex = available[exercise_idx]
                exercise_idx += 1

                # Last exercise in group gets rest, others get 0
                ex_rest = rest if order_in_group == group_size - 1 else 0

                suggestions.append({
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": ex_rest,
                    "order": len(suggestions),
                    "reason": f"{technique.capitalize()} - exercicio {order_in_group + 1} do grupo",
                    "technique_type": technique,
                    "exercise_group_id": group_id,
                    "exercise_group_order": order_in_group,
                    "execution_instructions": None,
                    "isometric_seconds": None,
                })
                used_ids.add(str(ex["id"]))

        return {
            "suggestions": suggestions[:count],
            "message": f"Treino com {technique}s para maior intensidade.",
        }

    async def generate_full_plan(
        self,
        available_exercises: list[dict],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        days_per_week: int,
        minutes_per_session: int,
        equipment: str,
        injuries: list[str] | None = None,
        preferences: str = "mixed",
        duration_weeks: int = 8,
    ) -> dict:
        """
        Generate a complete training plan using OpenAI.

        Falls back to None if AI is not available (caller should use rule-based).
        """
        if not self.client or not settings.OPENAI_API_KEY:
            return None

        try:
            return await self._ai_generate_plan(
                available_exercises=available_exercises,
                goal=goal,
                difficulty=difficulty,
                days_per_week=days_per_week,
                minutes_per_session=minutes_per_session,
                equipment=equipment,
                injuries=injuries,
                preferences=preferences,
                duration_weeks=duration_weeks,
            )
        except Exception as e:
            print(f"AI plan generation failed: {e}")
            return None

    async def _ai_generate_plan(
        self,
        available_exercises: list[dict],
        goal: WorkoutGoal,
        difficulty: Difficulty,
        days_per_week: int,
        minutes_per_session: int,
        equipment: str,
        injuries: list[str] | None = None,
        preferences: str = "mixed",
        duration_weeks: int = 8,
    ) -> dict:
        """Use OpenAI to generate a complete training plan."""

        # Build exercise list for prompt (limit to avoid token limits)
        exercise_list = "\n".join([
            f"- ID: {ex['id']}, Nome: {ex['name']}, Grupo: {ex['muscle_group']}"
            for ex in available_exercises[:100]
        ])

        goal_descriptions = {
            WorkoutGoal.HYPERTROPHY: "hipertrofia (ganho de massa muscular)",
            WorkoutGoal.STRENGTH: "forca maxima",
            WorkoutGoal.FAT_LOSS: "emagrecimento e queima de gordura",
            WorkoutGoal.ENDURANCE: "resistencia muscular",
            WorkoutGoal.FUNCTIONAL: "funcionalidade e mobilidade",
            WorkoutGoal.GENERAL_FITNESS: "condicionamento geral",
        }

        difficulty_descriptions = {
            Difficulty.BEGINNER: "iniciante (exercicios simples, sem tecnicas avancadas)",
            Difficulty.INTERMEDIATE: "intermediario (exercicios compostos, tecnicas moderadas)",
            Difficulty.ADVANCED: "avancado (tecnicas avancadas como dropset, bi-set, rest-pause)",
        }

        # Determine split type based on days
        split_info = {
            1: "Full Body (treino completo)",
            2: "Full Body (2 treinos alternados)",
            3: "ABC (3 treinos diferentes)",
            4: "Upper/Lower (superior/inferior)",
            5: "ABCDE (5 treinos diferentes)",
            6: "Push/Pull/Legs (2x por semana)",
        }

        injuries_text = ""
        if injuries:
            injuries_text = f"\nLESOES/RESTRICOES: {', '.join(injuries)} - EVITE exercicios que afetem essas areas!"

        # Build advanced techniques section based on difficulty
        techniques_section = ""
        if difficulty == Difficulty.INTERMEDIATE:
            techniques_section = """

TECNICAS AVANCADAS - OBRIGATORIO usar pelo menos 1-2 tecnicas por treino:
- "dropset": Reducao de carga sem descanso (use no ultimo exercicio de cada grupo muscular)
- "rest_pause": Pausas curtas de 10-15s entre mini-series
- "superset": Bi-set - 2 exercicios consecutivos do mesmo grupo SEM descanso entre eles

COMO CRIAR BI-SET:
1. Gere um UUID unico para o grupo (ex: "group-123")
2. Ambos exercicios devem ter o MESMO "exercise_group_id": "group-123"
3. Use "exercise_group_order": 0 para o primeiro, 1 para o segundo
4. Primeiro exercicio: "rest_seconds": 0
5. Segundo exercicio: "rest_seconds": 60-90
6. Ambos devem ter "technique_type": "superset"
"""
        elif difficulty == Difficulty.ADVANCED:
            techniques_section = """

TECNICAS AVANCADAS - OBRIGATORIO usar 2-4 tecnicas por treino para nivel avancado:

TECNICAS DISPONIVEIS:
- "dropset": Reducao de carga sem descanso (OBRIGATORIO em pelo menos 1 exercicio por treino)
- "rest_pause": Pausas curtas de 10-15s entre mini-series
- "superset": Bi-set - 2 exercicios consecutivos sem descanso
- "triset": Tri-set - 3 exercicios consecutivos sem descanso
- "giant_set": Giant set - 4+ exercicios consecutivos sem descanso

COMO CRIAR BI-SET/TRI-SET/GIANT-SET:
1. Gere um UUID unico para o grupo (ex: "group-abc-123")
2. TODOS exercicios do grupo devem ter o MESMO "exercise_group_id"
3. Use "exercise_group_order": 0, 1, 2... para cada exercicio
4. TODOS exceto o ultimo: "rest_seconds": 0
5. Ultimo do grupo: "rest_seconds": 60-90
6. Bi-set: "technique_type": "superset" (2 exercicios)
7. Tri-set: "technique_type": "triset" (3 exercicios)
8. Giant-set: "technique_type": "giant_set" (4+ exercicios)

ISOMETRIA (opcional):
- Use "isometric_seconds": 3-7 para pausas isometricas
- Combine com "technique_type": "normal"

IMPORTANTE: Para nivel AVANCADO, CADA treino DEVE ter pelo menos:
- 1 dropset no ultimo exercicio de um grupo muscular
- 1 bi-set ou tri-set
"""

        prompt = f"""Voce e um personal trainer experiente. Crie um plano de treino COMPLETO com as seguintes caracteristicas:

OBJETIVO: {goal_descriptions.get(goal, goal.value)}
NIVEL: {difficulty_descriptions.get(difficulty, difficulty.value)}
DIAS POR SEMANA: {days_per_week}
DURACAO POR SESSAO: {minutes_per_session} minutos
EQUIPAMENTO: {equipment}
PREFERENCIA: {preferences}
DURACAO DO PLANO: {duration_weeks} semanas
DIVISAO SUGERIDA: {split_info.get(days_per_week, "Personalizado")}
{injuries_text}

EXERCICIOS DISPONIVEIS:
{exercise_list}
{techniques_section}

REGRAS GERAIS:
1. Crie exatamente {days_per_week} treinos diferentes
2. Cada treino deve ter 4-8 exercicios (dependendo do tempo disponivel)
3. Distribua os grupos musculares de forma inteligente pela semana
4. Comece cada treino com exercicios compostos, termine com isolados
5. Configure series, repeticoes e descanso apropriados para o objetivo:
   - Hipertrofia: 3-4 series, 8-12 reps, 60-90s descanso
   - Forca: 4-5 series, 3-6 reps, 120-180s descanso
   - Emagrecimento: 3 series, 12-15 reps, 30-45s descanso
   - Resistencia: 2-3 series, 15-20 reps, 30s descanso
6. NAO repita exercicios entre treinos (use variedade)
7. Use apenas IDs de exercicios da lista fornecida

Responda APENAS com um JSON valido no formato:
{{
  "name": "Nome do Plano",
  "description": "Descricao breve do plano",
  "workouts": [
    {{
      "label": "A",
      "name": "Treino A - Peito e Triceps",
      "order": 0,
      "target_muscles": ["chest", "triceps"],
      "exercises": [
        {{
          "exercise_id": "uuid-do-exercicio",
          "name": "Nome do Exercicio",
          "muscle_group": "grupo_muscular",
          "sets": 4,
          "reps": "8-12",
          "rest_seconds": 60,
          "order": 0,
          "reason": "Motivo da escolha",
          "technique_type": "normal",
          "exercise_group_id": null,
          "exercise_group_order": 0,
          "execution_instructions": null,
          "isometric_seconds": null
        }}
      ]
    }}
  ],
  "message": "Dica geral sobre o plano"
}}"""

        response = await self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "Voce e um personal trainer. Responda APENAS em JSON valido, sem markdown, sem explicacoes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=3000,
            timeout=60.0,  # 60 second timeout
        )

        content = response.choices[0].message.content

        # Parse JSON response - handle potential markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        result = json.loads(content.strip())

        # Validate and clean up the response
        valid_ids = {str(ex["id"]) for ex in available_exercises}
        # Valid database technique types (must match TechniqueType enum)
        valid_db_techniques = {"normal", "dropset", "rest_pause", "cluster", "superset", "biset", "triset", "giantset"}

        # Single-exercise techniques should NOT have group_id
        single_exercise_techniques = {"dropset", "rest_pause", "cluster", "normal"}
        # Group techniques require group_id
        group_techniques = {"superset", "biset", "triset", "giantset"}

        for workout in result.get("workouts", []):
            validated_exercises = []
            workout_muscle_groups = set()  # Track muscle groups from exercises

            for ex in workout.get("exercises", []):
                if ex.get("exercise_id") in valid_ids:
                    # Ensure all fields have defaults
                    ex.setdefault("technique_type", "normal")
                    ex.setdefault("exercise_group_id", None)
                    ex.setdefault("exercise_group_order", 0)
                    ex.setdefault("execution_instructions", None)
                    ex.setdefault("isometric_seconds", None)
                    ex.setdefault("rest_seconds", 60)
                    ex.setdefault("sets", 3)
                    ex.setdefault("reps", "10-12")

                    # Normalize technique type names to match database enum
                    technique = ex["technique_type"].lower()
                    if technique == "isometric":
                        # Isometric is handled via isometric_seconds field, not as a technique type
                        technique = "normal"
                    elif technique == "bi_set":
                        technique = "biset"
                    elif technique == "tri_set":
                        technique = "triset"
                    elif technique == "giant_set":
                        technique = "giantset"

                    # Validate technique_type against database values
                    if technique not in valid_db_techniques:
                        technique = "normal"
                    ex["technique_type"] = technique

                    # IMPORTANT: Single-exercise techniques should NEVER have a group_id
                    if ex["technique_type"] in single_exercise_techniques:
                        ex["exercise_group_id"] = None
                        ex["exercise_group_order"] = 0

                    # Group techniques without group_id should be converted to normal
                    if ex["technique_type"] in group_techniques and not ex.get("exercise_group_id"):
                        ex["technique_type"] = "normal"

                    # Track muscle group for this exercise
                    if ex.get("muscle_group"):
                        workout_muscle_groups.add(ex["muscle_group"].lower())

                    validated_exercises.append(ex)

            workout["exercises"] = validated_exercises

            # Ensure target_muscles is present - infer from exercises if missing
            if not workout.get("target_muscles") or len(workout.get("target_muscles", [])) == 0:
                workout["target_muscles"] = list(workout_muscle_groups)

        # Add goal and difficulty to response for frontend
        result["goal"] = goal.value
        result["difficulty"] = difficulty.value
        result["duration_weeks"] = duration_weeks
        result["split_type"] = self._determine_split_type_name(days_per_week)

        return result

    def _determine_split_type_name(self, days_per_week: int) -> str:
        """Determine split type name based on training frequency."""
        if days_per_week <= 2:
            return "full_body"
        elif days_per_week == 3:
            return "abc"
        elif days_per_week == 4:
            return "upper_lower"
        elif days_per_week == 5:
            return "abcde"
        else:
            return "push_pull_legs"
