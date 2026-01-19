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
                "normal": '"normal": Exercicio padrao (1 exercicio isolado)',
                "dropset": '"dropset": Dropset - reducao de carga sem descanso (1 exercicio)',
                "rest_pause": '"rest_pause": Rest-pause - pausas curtas de 10-15s (1 exercicio)',
                "cluster": '"cluster": Cluster set - series fracionadas (1 exercicio)',
                "biset": '"biset": Bi-set - EXATAMENTE 2 exercicios do MESMO grupo muscular, sem descanso entre eles',
                "superset": '"superset": Superset - EXATAMENTE 2 exercicios de grupos musculares DIFERENTES (antagonistas), sem descanso entre eles',
                "triset": '"triset": Tri-set - EXATAMENTE 3 exercicios do mesmo grupo muscular, sem descanso entre eles',
                "giantset": '"giantset": Giant set - 4 a 8 exercicios (minimo 4, maximo 8), sem descanso entre eles',
            }

            allowed_list = [technique_descriptions.get(t, f'"{t}"') for t in allowed_techniques if t in technique_descriptions]

            # Check if only group techniques are allowed (no normal)
            group_techniques = {"biset", "superset", "triset", "giantset"}
            only_group_techniques = all(t in group_techniques for t in allowed_techniques)

            if only_group_techniques:
                # Calculate pairs/groups needed
                if "triset" in allowed_techniques:
                    group_size = 3
                elif "giantset" in allowed_techniques:
                    group_size = 4
                elif "biset" in allowed_techniques or "superset" in allowed_techniques:
                    group_size = 2
                else:
                    group_size = 2

                num_groups = count // group_size

                techniques_section = f"""

TECNICAS PERMITIDAS (OBRIGATORIO usar APENAS estas):
{chr(10).join('- ' + t for t in allowed_list)}

REGRAS CRITICAS - LEIA COM ATENCAO:
1. NAO crie exercicios com technique_type "normal" - TODOS devem usar as tecnicas permitidas
2. Voce DEVE criar EXATAMENTE {num_groups} grupos de {group_size} exercicios cada

REGRAS DE QUANTIDADE POR TECNICA:
- biset: EXATAMENTE 2 exercicios por grupo (mesmo grupo muscular)
- superset: EXATAMENTE 2 exercicios por grupo (grupos musculares diferentes/antagonistas)
- triset: EXATAMENTE 3 exercicios por grupo (mesmo grupo muscular)
- giantset: 4 a 8 exercicios por grupo (MINIMO 4, MAXIMO 8)

REGRAS DE GRUPOS MUSCULARES:
- BI-SET: Os 2 exercicios DEVEM ser do MESMO grupo muscular (ex: 2 exercicios de peito)
- SUPERSET: Os 2 exercicios DEVEM ser de grupos DIFERENTES (ex: 1 peito + 1 costas)
- TRI-SET: Os 3 exercicios DEVEM ser do MESMO grupo muscular (ex: 3 exercicios de biceps)
- GIANT-SET: Os 4+ exercicios podem ser do mesmo ou diferentes grupos

REGRAS DE ESTRUTURA JSON:
1. Gere um UUID unico para cada grupo (ex: "group-abc12345")
2. TODOS exercicios do grupo devem ter o MESMO "exercise_group_id"
3. Use "exercise_group_order": 0 para o primeiro, 1 para o segundo, etc.
4. TODOS exceto o ultimo do grupo: "rest_seconds": 0
5. Ultimo exercicio do grupo: "rest_seconds": 60-90

EXEMPLO de bi-set (2 exercicios de peito):
[
  {{"exercise_id": "...", "muscle_group": "chest", "technique_type": "biset", "exercise_group_id": "group-abc123", "exercise_group_order": 0, "rest_seconds": 0}},
  {{"exercise_id": "...", "muscle_group": "chest", "technique_type": "biset", "exercise_group_id": "group-abc123", "exercise_group_order": 1, "rest_seconds": 60}}
]

EXEMPLO de superset (peito + costas):
[
  {{"exercise_id": "...", "muscle_group": "chest", "technique_type": "superset", "exercise_group_id": "group-xyz789", "exercise_group_order": 0, "rest_seconds": 0}},
  {{"exercise_id": "...", "muscle_group": "back", "technique_type": "superset", "exercise_group_id": "group-xyz789", "exercise_group_order": 1, "rest_seconds": 60}}
]"""
            else:
                techniques_section = f"""

TECNICAS PERMITIDAS (use APENAS estas):
{chr(10).join('- ' + t for t in allowed_list)}

IMPORTANTE: Voce DEVE usar SOMENTE as tecnicas listadas acima. NAO use outras tecnicas.

REGRAS DE QUANTIDADE POR TECNICA:
- biset: EXATAMENTE 2 exercicios do MESMO grupo muscular
- superset: EXATAMENTE 2 exercicios de grupos DIFERENTES (antagonistas)
- triset: EXATAMENTE 3 exercicios do mesmo grupo muscular
- giantset: 4 a 8 exercicios (MINIMO 4, MAXIMO 8)

REGRAS DE ESTRUTURA PARA GRUPOS:
1. Gere um UUID unico para cada grupo (ex: "group-" + 8 caracteres)
2. TODOS exercicios do grupo devem ter o MESMO "exercise_group_id"
3. Use "exercise_group_order": 0, 1, 2... para ordenar dentro do grupo
4. TODOS exceto o ultimo: "rest_seconds": 0
5. Ultimo do grupo: "rest_seconds": 60-90"""

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

                validated_suggestions.append(s)

        # POST-VALIDATION: Validate group sizes match technique requirements
        # Rules:
        # - biset/superset: exactly 2 exercises
        # - triset: exactly 3 exercises
        # - giantset: 4+ exercises
        validated_suggestions = self._validate_and_fix_groups(
            validated_suggestions,
            exercises,
            allowed_techniques,
            group_techniques,
        )

        result["suggestions"] = validated_suggestions
        return result

    def _validate_and_fix_groups(
        self,
        suggestions: list[dict[str, Any]],
        available_exercises: list[dict[str, Any]],
        allowed_techniques: list[str] | None,
        group_techniques: set[str],
    ) -> list[dict[str, Any]]:
        """
        Validate that exercise groups have the correct number of exercises
        and follow the rules for each technique.

        Rules:
        - Bi-set: exactly 2 exercises of the SAME muscle group
        - Superset: exactly 2 exercises of DIFFERENT muscle groups (antagonist)
        - Tri-set: exactly 3 exercises of the SAME muscle group
        - Giant set: 4-8 exercises (min 4, max 8)
        """

        # Required group sizes for each technique
        technique_sizes = {
            "biset": 2,      # EXACTLY 2 exercises, SAME muscle group
            "superset": 2,   # EXACTLY 2 exercises, DIFFERENT muscle groups (antagonist)
            "triset": 3,     # EXACTLY 3 exercises, SAME muscle group
            "giantset": 4,   # 4-8 exercises, any muscle groups
        }
        # Giant set limits
        giantset_min = 4
        giantset_max = 8

        # Group exercises by group_id
        groups: dict[str, list[dict[str, Any]]] = {}
        ungrouped: list[dict[str, Any]] = []

        for s in suggestions:
            group_id = s.get("exercise_group_id")
            if group_id:
                if group_id not in groups:
                    groups[group_id] = []
                groups[group_id].append(s)
            else:
                ungrouped.append(s)

        # Get used exercise IDs
        used_ids = {s["exercise_id"] for s in suggestions}

        # Get available exercises not yet used
        available_unused = [
            ex for ex in available_exercises
            if str(ex["id"]) not in used_ids
        ]

        # Validate each group
        fixed_grouped: list[dict[str, Any]] = []

        for group_id, group_exercises in groups.items():
            if not group_exercises:
                continue

            technique = group_exercises[0]["technique_type"]
            required_size = technique_sizes.get(technique, 2)
            current_size = len(group_exercises)

            if technique == "giantset":
                # Giant set: 4-8 exercises
                if giantset_min <= current_size <= giantset_max:
                    # Valid giant set (4-8 exercises)
                    for i, ex in enumerate(group_exercises):
                        ex["exercise_group_order"] = i
                        ex["rest_seconds"] = 60 if i == current_size - 1 else 0
                    fixed_grouped.extend(group_exercises)

                elif current_size > giantset_max:
                    # Too many exercises - split into multiple giant sets of 4-8
                    idx = 0
                    while idx < current_size:
                        # Determine size of this group (prefer 4-6)
                        remaining = current_size - idx
                        if remaining >= giantset_min:
                            # Take up to giantset_max, but leave at least giantset_min for next group if needed
                            if remaining > giantset_max and remaining - giantset_max >= giantset_min:
                                take = giantset_max
                            elif remaining <= giantset_max:
                                take = remaining
                            else:
                                # Split evenly if we'd leave orphans
                                take = remaining // 2 if remaining // 2 >= giantset_min else giantset_min

                            new_group_id = f"group-{uuid.uuid4().hex[:8]}"
                            for order in range(take):
                                ex = group_exercises[idx]
                                ex["exercise_group_id"] = new_group_id
                                ex["exercise_group_order"] = order
                                ex["rest_seconds"] = 60 if order == take - 1 else 0
                                fixed_grouped.append(ex)
                                idx += 1
                        else:
                            # Remaining exercises can't form a giant set
                            for ex in group_exercises[idx:]:
                                if allowed_techniques and "normal" not in allowed_techniques:
                                    fixed_grouped.append(ex)
                                else:
                                    ex["technique_type"] = "normal"
                                    ex["exercise_group_id"] = None
                                    ex["exercise_group_order"] = 0
                                    ex["rest_seconds"] = 60
                                    ungrouped.append(ex)
                            break

                elif current_size < giantset_min and available_unused:
                    # Try to complete to minimum 4
                    needed = giantset_min - current_size
                    for _ in range(needed):
                        if available_unused:
                            new_ex = available_unused.pop(0)
                            group_exercises.append({
                                "exercise_id": str(new_ex["id"]),
                                "name": new_ex["name"],
                                "muscle_group": new_ex["muscle_group"],
                                "sets": group_exercises[0].get("sets", 3),
                                "reps": group_exercises[0].get("reps", "10-12"),
                                "rest_seconds": 0,
                                "order": len(suggestions) + len(fixed_grouped),
                                "reason": f"Adicionado para completar giant set",
                                "technique_type": technique,
                                "exercise_group_id": group_id,
                                "exercise_group_order": len(group_exercises) - 1,
                                "execution_instructions": None,
                                "isometric_seconds": None,
                            })
                            used_ids.add(str(new_ex["id"]))

                    # Set rest times correctly (0 for all except last)
                    for i, ex in enumerate(group_exercises):
                        ex["exercise_group_order"] = i
                        ex["rest_seconds"] = 60 if i == len(group_exercises) - 1 else 0

                    if len(group_exercises) >= giantset_min:
                        fixed_grouped.extend(group_exercises)
                    else:
                        # Convert to normal if can't complete
                        for ex in group_exercises:
                            if allowed_techniques and "normal" not in allowed_techniques:
                                fixed_grouped.append(ex)
                            else:
                                ex["technique_type"] = "normal"
                                ex["exercise_group_id"] = None
                                ex["exercise_group_order"] = 0
                                ex["rest_seconds"] = 60
                                ungrouped.append(ex)
                else:
                    # Not enough exercises and can't complete
                    for ex in group_exercises:
                        if allowed_techniques and "normal" not in allowed_techniques:
                            fixed_grouped.append(ex)
                        else:
                            ex["technique_type"] = "normal"
                            ex["exercise_group_id"] = None
                            ex["exercise_group_order"] = 0
                            ex["rest_seconds"] = 60
                            ungrouped.append(ex)

            elif current_size == required_size:
                # Perfect match
                # Ensure rest times are correct
                for i, ex in enumerate(group_exercises):
                    ex["exercise_group_order"] = i
                    ex["rest_seconds"] = 60 if i == required_size - 1 else 0
                fixed_grouped.extend(group_exercises)

            elif current_size < required_size:
                # Need more exercises to complete the group
                needed = required_size - current_size
                added = 0

                for _ in range(needed):
                    if available_unused:
                        new_ex = available_unused.pop(0)
                        group_exercises.append({
                            "exercise_id": str(new_ex["id"]),
                            "name": new_ex["name"],
                            "muscle_group": new_ex["muscle_group"],
                            "sets": group_exercises[0].get("sets", 3),
                            "reps": group_exercises[0].get("reps", "10-12"),
                            "rest_seconds": 0,
                            "order": len(suggestions) + len(fixed_grouped) + added,
                            "reason": f"Adicionado para completar {technique}",
                            "technique_type": technique,
                            "exercise_group_id": group_id,
                            "exercise_group_order": current_size + added,
                            "execution_instructions": None,
                            "isometric_seconds": None,
                        })
                        used_ids.add(str(new_ex["id"]))
                        added += 1

                # Check if we completed the group
                if len(group_exercises) == required_size:
                    # Set rest times correctly
                    for i, ex in enumerate(group_exercises):
                        ex["exercise_group_order"] = i
                        ex["rest_seconds"] = 60 if i == required_size - 1 else 0
                    fixed_grouped.extend(group_exercises)
                else:
                    # Couldn't complete - convert to normal if allowed
                    for ex in group_exercises:
                        if allowed_techniques and "normal" not in allowed_techniques:
                            # Keep incomplete but can't convert to normal
                            fixed_grouped.append(ex)
                        else:
                            ex["technique_type"] = "normal"
                            ex["exercise_group_id"] = None
                            ex["exercise_group_order"] = 0
                            ex["rest_seconds"] = 60
                            ungrouped.append(ex)

            else:
                # Too many exercises - split into proper groups
                # Create complete groups and leave extras
                num_complete_groups = current_size // required_size
                remainder = current_size % required_size

                idx = 0
                for g in range(num_complete_groups):
                    new_group_id = f"group-{uuid.uuid4().hex[:8]}"
                    for order in range(required_size):
                        ex = group_exercises[idx]
                        ex["exercise_group_id"] = new_group_id
                        ex["exercise_group_order"] = order
                        ex["rest_seconds"] = 60 if order == required_size - 1 else 0
                        fixed_grouped.append(ex)
                        idx += 1

                # Handle remainder
                for i in range(remainder):
                    ex = group_exercises[idx]
                    if allowed_techniques and "normal" not in allowed_techniques:
                        # Create a new incomplete group (best effort)
                        fixed_grouped.append(ex)
                    else:
                        ex["technique_type"] = "normal"
                        ex["exercise_group_id"] = None
                        ex["exercise_group_order"] = 0
                        ex["rest_seconds"] = 60
                        ungrouped.append(ex)
                    idx += 1

        # Combine and reorder
        result = fixed_grouped + ungrouped

        # Reorder all exercises
        for i, ex in enumerate(result):
            ex["order"] = i

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
        """
        Generate exercises in pairs/groups when only group techniques are allowed.

        Rules:
        - Bi-set: 2 exercises from SAME muscle group
        - Superset: 2 exercises from DIFFERENT muscle groups (antagonist)
        - Tri-set: 3 exercises from SAME muscle group
        - Giant-set: 4+ exercises (any)
        """

        suggestions = []
        used_ids = set()

        # Check existing exercises to avoid duplicates
        existing_names = set()
        if context and context.get("existing_exercises"):
            existing_names = {name.lower() for name in context["existing_exercises"]}

        # Determine group size and technique based on allowed techniques
        if "triset" in allowed_techniques:
            group_size = 3
            technique = "triset"
            same_muscle = True  # Tri-set = same muscle group
        elif "giantset" in allowed_techniques:
            group_size = 4
            technique = "giantset"
            same_muscle = False  # Giant set = any
        elif "biset" in allowed_techniques:
            group_size = 2
            technique = "biset"
            same_muscle = True  # Bi-set = SAME muscle group
        elif "superset" in allowed_techniques:
            group_size = 2
            technique = "superset"
            same_muscle = False  # Superset = DIFFERENT muscle groups
        else:
            group_size = 2
            technique = "biset"
            same_muscle = True

        # Organize exercises by muscle group
        exercises_by_muscle: dict[str, list[dict[str, Any]]] = {}
        for ex in exercises:
            mg = ex["muscle_group"].lower()
            if mg in [m.lower() for m in muscle_groups]:
                if ex["name"].lower() not in existing_names:
                    if mg not in exercises_by_muscle:
                        exercises_by_muscle[mg] = []
                    exercises_by_muscle[mg].append(ex)

        num_groups = count // group_size

        if technique == "superset":
            # Superset: pair exercises from DIFFERENT muscle groups
            suggestions = self._generate_supersets(
                exercises_by_muscle, num_groups, group_size, sets, reps, rest, used_ids
            )
        elif technique in ("biset", "triset"):
            # Bi-set/Tri-set: group exercises from SAME muscle group
            suggestions = self._generate_same_muscle_groups(
                exercises_by_muscle, num_groups, group_size, sets, reps, rest, technique, used_ids
            )
        else:
            # Giant-set: any combination
            all_available = []
            for mg_exercises in exercises_by_muscle.values():
                all_available.extend(mg_exercises)

            for group_num in range(num_groups):
                group_id = f"group-{uuid.uuid4().hex[:8]}"

                for order_in_group in range(group_size):
                    if not all_available:
                        break

                    ex = all_available.pop(0)
                    ex_rest = rest if order_in_group == group_size - 1 else 0

                    suggestions.append({
                        "exercise_id": str(ex["id"]),
                        "name": ex["name"],
                        "muscle_group": ex["muscle_group"],
                        "sets": sets,
                        "reps": reps,
                        "rest_seconds": ex_rest,
                        "order": len(suggestions),
                        "reason": f"Giant set - exercicio {order_in_group + 1}",
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

    def _generate_supersets(
        self,
        exercises_by_muscle: dict[str, list[dict[str, Any]]],
        num_groups: int,
        group_size: int,
        sets: int,
        reps: str,
        rest: int,
        used_ids: set[str],
    ) -> list[dict[str, Any]]:
        """
        Generate supersets - pairs of exercises from DIFFERENT muscle groups.

        Superset rule: 2 exercises from antagonist/different muscle groups.
        Example: chest + back, biceps + triceps, quads + hamstrings
        """
        suggestions = []
        muscle_list = list(exercises_by_muscle.keys())

        if len(muscle_list) < 2:
            # Not enough different muscle groups for supersets
            # Fall back to using what we have
            all_exercises = []
            for mg_exercises in exercises_by_muscle.values():
                all_exercises.extend(mg_exercises)

            for group_num in range(num_groups):
                group_id = f"group-{uuid.uuid4().hex[:8]}"
                for order in range(group_size):
                    if all_exercises:
                        ex = all_exercises.pop(0)
                        ex_rest = rest if order == group_size - 1 else 0
                        suggestions.append({
                            "exercise_id": str(ex["id"]),
                            "name": ex["name"],
                            "muscle_group": ex["muscle_group"],
                            "sets": sets,
                            "reps": reps,
                            "rest_seconds": ex_rest,
                            "order": len(suggestions),
                            "reason": f"Superset - exercicio {order + 1}",
                            "technique_type": "superset",
                            "exercise_group_id": group_id,
                            "exercise_group_order": order,
                            "execution_instructions": None,
                            "isometric_seconds": None,
                        })
                        used_ids.add(str(ex["id"]))
            return suggestions

        # Create superset pairs from different muscle groups
        muscle_idx = 0
        for group_num in range(num_groups):
            group_id = f"group-{uuid.uuid4().hex[:8]}"

            # Get two different muscle groups
            mg1 = muscle_list[muscle_idx % len(muscle_list)]
            mg2 = muscle_list[(muscle_idx + 1) % len(muscle_list)]

            # Get exercise from first muscle group
            if exercises_by_muscle[mg1]:
                ex1 = exercises_by_muscle[mg1].pop(0)
                suggestions.append({
                    "exercise_id": str(ex1["id"]),
                    "name": ex1["name"],
                    "muscle_group": ex1["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": 0,  # No rest before second exercise
                    "order": len(suggestions),
                    "reason": f"Superset - {ex1['muscle_group']}",
                    "technique_type": "superset",
                    "exercise_group_id": group_id,
                    "exercise_group_order": 0,
                    "execution_instructions": None,
                    "isometric_seconds": None,
                })
                used_ids.add(str(ex1["id"]))

                # Get exercise from second (different) muscle group
                if exercises_by_muscle[mg2]:
                    ex2 = exercises_by_muscle[mg2].pop(0)
                    suggestions.append({
                        "exercise_id": str(ex2["id"]),
                        "name": ex2["name"],
                        "muscle_group": ex2["muscle_group"],
                        "sets": sets,
                        "reps": reps,
                        "rest_seconds": rest,  # Rest after superset
                        "order": len(suggestions),
                        "reason": f"Superset - {ex2['muscle_group']}",
                        "technique_type": "superset",
                        "exercise_group_id": group_id,
                        "exercise_group_order": 1,
                        "execution_instructions": None,
                        "isometric_seconds": None,
                    })
                    used_ids.add(str(ex2["id"]))

            muscle_idx += 2  # Move to next pair of muscles

        return suggestions

    def _generate_same_muscle_groups(
        self,
        exercises_by_muscle: dict[str, list[dict[str, Any]]],
        num_groups: int,
        group_size: int,
        sets: int,
        reps: str,
        rest: int,
        technique: str,
        used_ids: set[str],
    ) -> list[dict[str, Any]]:
        """
        Generate bi-sets or tri-sets - exercises from the SAME muscle group.

        Bi-set rule: 2 exercises from the same muscle group
        Tri-set rule: 3 exercises from the same muscle group
        """
        suggestions = []

        # Find muscle groups with enough exercises
        viable_muscles = [
            mg for mg, exercises in exercises_by_muscle.items()
            if len(exercises) >= group_size
        ]

        if not viable_muscles:
            # Not enough exercises in any single muscle group
            # Use what we have, combining from different groups if needed
            all_exercises = []
            for mg_exercises in exercises_by_muscle.values():
                all_exercises.extend(mg_exercises)

            for group_num in range(num_groups):
                group_id = f"group-{uuid.uuid4().hex[:8]}"
                for order in range(group_size):
                    if all_exercises:
                        ex = all_exercises.pop(0)
                        ex_rest = rest if order == group_size - 1 else 0
                        suggestions.append({
                            "exercise_id": str(ex["id"]),
                            "name": ex["name"],
                            "muscle_group": ex["muscle_group"],
                            "sets": sets,
                            "reps": reps,
                            "rest_seconds": ex_rest,
                            "order": len(suggestions),
                            "reason": f"{technique.capitalize()} - exercicio {order + 1}",
                            "technique_type": technique,
                            "exercise_group_id": group_id,
                            "exercise_group_order": order,
                            "execution_instructions": None,
                            "isometric_seconds": None,
                        })
                        used_ids.add(str(ex["id"]))
            return suggestions

        # Create groups from same muscle group
        muscle_idx = 0
        for group_num in range(num_groups):
            # Cycle through viable muscle groups
            mg = viable_muscles[muscle_idx % len(viable_muscles)]

            # Check if this muscle group still has enough exercises
            while len(exercises_by_muscle[mg]) < group_size and len(viable_muscles) > 1:
                viable_muscles.remove(mg)
                if not viable_muscles:
                    break
                mg = viable_muscles[muscle_idx % len(viable_muscles)]

            if not viable_muscles or len(exercises_by_muscle[mg]) < group_size:
                break

            group_id = f"group-{uuid.uuid4().hex[:8]}"

            for order in range(group_size):
                ex = exercises_by_muscle[mg].pop(0)
                ex_rest = rest if order == group_size - 1 else 0

                suggestions.append({
                    "exercise_id": str(ex["id"]),
                    "name": ex["name"],
                    "muscle_group": ex["muscle_group"],
                    "sets": sets,
                    "reps": reps,
                    "rest_seconds": ex_rest,
                    "order": len(suggestions),
                    "reason": f"{technique.capitalize()} de {ex['muscle_group']} - exercicio {order + 1}",
                    "technique_type": technique,
                    "exercise_group_id": group_id,
                    "exercise_group_order": order,
                    "execution_instructions": None,
                    "isometric_seconds": None,
                })
                used_ids.add(str(ex["id"]))

            muscle_idx += 1

        return suggestions

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
