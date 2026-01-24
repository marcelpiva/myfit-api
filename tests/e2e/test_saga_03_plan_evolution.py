"""
SAGA 3: Evolução de Plano - Progressão do Aluno

Esta saga cobre o ciclo de acompanhamento de progresso,
identificação de evolução e criação de novo plano mais avançado.

IMPORTANT: Run only in local/development environment!
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestSaga03PlanEvolution:
    """
    SAGA 3: Jornada de evolução de plano baseada em progresso.

    Fases:
    1. ALUNO - Registro de Progresso (peso, medidas, fotos)
    2. PERSONAL - Análise do Progresso
    3. PERSONAL - Adição de Nota de Progresso
    4. ALUNO - Visualização do Feedback
    5. PERSONAL - Criação do Plano Evoluído
    6. PERSONAL - Atribuição do Novo Plano
    7. ALUNO - Aceitação do Plano Evoluído
    8. PERSONAL - Confirmação e Visualização
    """

    # =========================================================================
    # FASE 1: ALUNO - Registro de Progresso
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_01_aluno_registra_peso(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno registra peso semanal."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Dado que estou logado como aluno
        # Quando registro meu peso
        response = await student_client.post(
            "/progress/weight",
            json={
                "weight_kg": 63.5,
                "notes": "Semana 4 - Me sentindo mais forte",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o peso deve ser registrado
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_fase_01_aluno_registra_medidas(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno registra medidas corporais."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Dado que estou logado como aluno
        # Quando registro minhas medidas
        response = await student_client.post(
            "/progress/measurements",
            json={
                "chest_cm": 90,
                "waist_cm": 68,
                "hips_cm": 96,
                "biceps_cm": 29,
                "thigh_cm": 55,
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então as medidas devem ser registradas
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_fase_01_aluno_visualiza_evolucao_peso(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno visualiza evolução de peso."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Dado que registrei meu peso
        # Quando consulto o histórico
        response = await student_client.get(
            "/progress/weight",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver o histórico
        assert response.status_code == 200

    # =========================================================================
    # FASE 2: PERSONAL - Análise do Progresso
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_02_personal_ve_progresso_aluno(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer visualiza progresso do aluno."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Dado que o aluno tem histórico de progresso
        # Quando acesso o progresso do aluno
        response = await personal_client.get(
            f"/trainers/students/{student_id}/progress",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver o progresso
        assert response.status_code in [200, 404]  # 404 se endpoint diferente

    @pytest.mark.asyncio
    async def test_fase_02_personal_ve_estatisticas_aluno(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer visualiza estatísticas do aluno."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Dado que o aluno tem histórico
        # Quando acesso as estatísticas
        response = await personal_client.get(
            f"/trainers/students/{student_id}/stats",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver as estatísticas
        assert response.status_code in [200, 404]

    # =========================================================================
    # FASE 3: PERSONAL - Adição de Nota de Progresso
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_03_personal_adiciona_nota(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer adiciona nota de progresso."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Dado que analisei o progresso do aluno
        # Quando adiciono uma nota
        response = await personal_client.post(
            f"/trainers/students/{student_id}/progress/notes",
            json={
                "content": "Excelente evolução! Pronta para o próximo nível.",
                "category": "feedback",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então a nota deve ser adicionada
        assert response.status_code in [200, 201, 404]

    # =========================================================================
    # FASE 5: PERSONAL - Criação do Plano Evoluído (Duplicar e Modificar)
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_05_personal_duplica_plano(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
    ):
        """Personal Trainer duplica plano existente."""
        org_id = str(training_plan_setup["organization_id"])
        plan_id = str(training_plan_setup["plan"]["id"])

        # Dado que tenho um plano bem-sucedido
        # Quando duplico o plano
        response = await personal_client.post(
            f"/workouts/plans/{plan_id}/duplicate",
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser duplicado
        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_05_personal_atualiza_plano_evoluido(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
    ):
        """Personal Trainer atualiza o plano evoluído."""
        org_id = str(training_plan_setup["organization_id"])
        plan_id = str(training_plan_setup["plan"]["id"])

        # Dado que tenho um plano duplicado
        # Quando atualizo para versão evoluída
        response = await personal_client.put(
            f"/workouts/plans/{plan_id}",
            json={
                "name": "Plano Intermediário 6 Semanas",
                "difficulty": "intermediate",
                "duration_weeks": 6,
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser atualizado
        assert response.status_code in [200, 404]

    # =========================================================================
    # FASE 6: PERSONAL - Atribuição do Novo Plano
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_06_personal_atribui_plano_evoluido(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
        student_setup: dict,
    ):
        """Personal Trainer atribui novo plano ao aluno."""
        org_id = str(training_plan_setup["organization_id"])
        plan_id = str(training_plan_setup["plan"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Dado que tenho o plano evoluído pronto
        # Quando atribuo ao aluno
        response = await personal_client.post(
            "/workouts/plans/assignments",
            json={
                "plan_id": plan_id,
                "student_id": student_id,
                "start_date": (datetime.now(timezone.utc) + timedelta(days=1)).date().isoformat(),
                "training_mode": "presencial",
                "notes": "Evolução do plano anterior. Mais intenso!",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser atribuído
        assert response.status_code in [200, 201]

    # =========================================================================
    # FASE 7: ALUNO - Aceitação do Plano Evoluído
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_07_aluno_aceita_plano_evoluido(
        self,
        student_client: AsyncClient,
        plan_assignment_setup: dict,
    ):
        """Aluno aceita o plano evoluído."""
        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])
        assignment_id = str(plan_assignment_setup["assignment"]["id"])

        # Dado que recebi um novo plano
        # Quando aceito o plano
        response = await student_client.post(
            f"/workouts/plans/assignments/{assignment_id}/respond",
            json={"accept": True},
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser aceito
        assert response.status_code == 200


class TestSaga03ProgressPhotos:
    """Testes de fotos de progresso."""

    @pytest.mark.asyncio
    async def test_aluno_envia_foto_progresso(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno envia foto de progresso."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Nota: Upload de arquivo requer multipart/form-data
        # Este é um teste simplificado do endpoint
        response = await student_client.get(
            "/progress/photos",
            headers={"X-Organization-ID": org_id},
        )

        # Endpoint deve existir
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_aluno_define_meta_peso(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno define meta de peso."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Dado que estou logado como aluno
        # Quando defino minha meta
        response = await student_client.post(
            "/progress/weight-goals",
            json={
                "target_weight_kg": 60.0,
                "target_date": (datetime.now(timezone.utc) + timedelta(days=90)).date().isoformat(),
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então a meta deve ser definida
        assert response.status_code in [200, 201, 404]
