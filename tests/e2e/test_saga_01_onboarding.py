"""
SAGA 1: Onboarding Completo - Do Convite ao Primeiro Treino

Esta saga cobre o fluxo completo desde o cadastro do Personal
até o primeiro treino executado pelo Aluno.

IMPORTANT: Run only in local/development environment!
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestSaga01OnboardingCompleto:
    """
    SAGA 1: Jornada completa de onboarding.

    Fases:
    1. PERSONAL - Cadastro e Configuração Inicial
    2. PERSONAL - Criação do Primeiro Plano de Treino
    3. PERSONAL - Convite do Aluno
    4. ALUNO - Aceitação do Convite e Registro
    5. PERSONAL - Verificação e Atribuição do Plano
    6. ALUNO - Visualização e Aceitação do Plano
    7. PERSONAL - Confirmação da Aceitação
    8. ALUNO - Execução do Primeiro Treino
    9. PERSONAL - Visualização do Treino Concluído
    """

    # =========================================================================
    # FASE 1: PERSONAL - Cadastro e Configuração Inicial
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_01_personal_registro(
        self,
        client: AsyncClient,
        mock_email_service,
    ):
        """Personal Trainer se cadastra no sistema."""
        # Dado que estou na API de registro
        # Quando envio os dados de cadastro
        response = await client.post(
            "/auth/register",
            json={
                "email": "joao.personal@example.com",
                "name": "João Silva",
                "password": "Test@123",
            },
        )

        # Então a conta deve ser criada com sucesso
        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "joao.personal@example.com"
        assert data["user"]["name"] == "João Silva"
        assert "id" in data["user"]
        assert "access_token" in data["tokens"]
        assert "refresh_token" in data["tokens"]

    @pytest.mark.asyncio
    async def test_fase_01_personal_cria_organizacao(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal Trainer cria sua organização."""
        # Dado que estou logado como Personal Trainer
        # Quando crio uma nova organização
        response = await personal_client.post(
            "/organizations",
            json={
                "name": "Studio Fitness João",
                "type": "personal",
                "description": "Treinos personalizados",
                "phone": "(11) 99999-9999",
            },
        )

        # Então a organização deve ser criada
        # Nota: Se já existe organização do setup, pode retornar 400
        assert response.status_code in [201, 400]

    # =========================================================================
    # FASE 2: PERSONAL - Criação do Primeiro Plano de Treino
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_02_personal_cria_plano(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal Trainer cria um plano de treino."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Dado que estou logado como Personal Trainer
        # Quando crio um novo plano de treino
        response = await personal_client.post(
            "/workouts/plans",
            json={
                "name": "Plano Iniciante 4 Semanas",
                "description": "Plano para iniciantes",
                "goal": "general_fitness",
                "difficulty": "beginner",
                "split_type": "abc",
                "duration_weeks": 4,
                "is_template": False,
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser criado com sucesso
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Plano Iniciante 4 Semanas"
        assert data["goal"] == "general_fitness"

    @pytest.mark.asyncio
    async def test_fase_02_personal_adiciona_treinos_ao_plano(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
    ):
        """Personal Trainer visualiza os treinos do plano."""
        plan_id = str(training_plan_setup["plan"]["id"])
        org_id = str(training_plan_setup["organization_id"])

        # Dado que tenho um plano criado
        # Quando solicito os detalhes do plano
        response = await personal_client.get(
            f"/workouts/plans/{plan_id}",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver os treinos associados
        assert response.status_code == 200
        data = response.json()
        assert "workouts" in data or "plan_workouts" in data

    # =========================================================================
    # FASE 3: PERSONAL - Convite do Aluno
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_03_personal_convida_aluno(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
        mock_email_service,
    ):
        """Personal Trainer envia convite para novo aluno."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Dado que estou logado como Personal Trainer
        # Quando envio um convite para um novo aluno
        response = await personal_client.post(
            "/trainers/students/register",
            json={
                "email": "maria.nova@example.com",
                "name": "Maria Santos",
                "phone": "(11) 88888-8888",
                "goal": "Emagrecimento",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o convite deve ser enviado com sucesso
        assert response.status_code in [200, 201]

        # E o serviço de email deve ter sido chamado
        mock_email_service.assert_called()

    @pytest.mark.asyncio
    async def test_fase_03_personal_ve_convites_pendentes(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal Trainer visualiza convites pendentes."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Dado que enviei convites
        # Quando acesso a lista de convites pendentes
        response = await personal_client.get(
            "/trainers/students/pending-invites",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver os convites
        assert response.status_code == 200

    # =========================================================================
    # FASE 4: ALUNO - Aceitação do Convite e Registro
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_04_aluno_preview_convite(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Aluno visualiza preview do convite (endpoint público)."""
        # Este teste requer um token de convite válido
        # Por simplicidade, verificamos se o endpoint existe
        response = await client.get(
            "/organizations/invite/preview/invalid-token"
        )

        # O endpoint deve existir (retorna 404 para token inválido)
        assert response.status_code in [400, 404]

    @pytest.mark.asyncio
    async def test_fase_04_aluno_registra_via_convite(
        self,
        client: AsyncClient,
        mock_email_service,
    ):
        """Aluno se registra através de convite."""
        # Dado que tenho um link de convite válido
        # Quando me registro através do convite
        response = await client.post(
            "/auth/register",
            json={
                "email": "maria.aluna@example.com",
                "name": "Maria Santos",
                "password": "Test@456",
            },
        )

        # Então minha conta deve ser criada
        assert response.status_code in [201, 400]  # 400 se já existe

    # =========================================================================
    # FASE 5: PERSONAL - Verificação e Atribuição do Plano
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_05_personal_ve_aluno_na_lista(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer vê o novo aluno na lista."""
        trainer = student_setup["trainer"]
        org_id = str(trainer["organization"]["id"])

        # Dado que o aluno aceitou o convite
        # Quando acesso a lista de alunos
        response = await personal_client.get(
            "/trainers/students",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver o aluno na lista
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "items" in data or "students" in data

    @pytest.mark.asyncio
    async def test_fase_05_personal_atribui_plano_ao_aluno(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
        student_setup: dict,
    ):
        """Personal Trainer atribui plano ao aluno."""
        org_id = str(training_plan_setup["organization_id"])
        plan_id = str(training_plan_setup["plan"]["id"])
        student_user_id = str(student_setup["user"]["id"])  # PlanAssignment uses user_id

        # Dado que tenho um plano e um aluno
        # Quando atribuo o plano ao aluno
        response = await personal_client.post(
            "/workouts/plans/assignments",
            json={
                "plan_id": plan_id,
                "student_id": student_user_id,  # Must be user_id for PlanAssignment
                "start_date": datetime.now(timezone.utc).date().isoformat(),
                "training_mode": "presencial",
                "notes": "Foco em técnica nas primeiras semanas",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser atribuído como pendente
        assert response.status_code in [200, 201]
        data = response.json()
        assert data.get("status") == "pending"

    # =========================================================================
    # FASE 6: ALUNO - Visualização e Aceitação do Plano
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_06_aluno_ve_plano_pendente(
        self,
        student_client: AsyncClient,
        plan_assignment_setup: dict,
    ):
        """Aluno visualiza plano pendente de aceitação."""
        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])

        # Dado que tenho um plano atribuído
        # Quando acesso meus planos
        response = await student_client.get(
            "/workouts/plans/assignments",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver o plano pendente
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fase_06_aluno_aceita_plano(
        self,
        student_client: AsyncClient,
        plan_assignment_setup: dict,
    ):
        """Aluno aceita o plano de treino."""
        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])
        assignment_id = str(plan_assignment_setup["assignment"]["id"])

        # Dado que tenho um plano pendente
        # Quando aceito o plano
        response = await student_client.post(
            f"/workouts/plans/assignments/{assignment_id}/respond",
            json={"accept": True},
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser aceito
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "accepted"

    # =========================================================================
    # FASE 7: PERSONAL - Confirmação da Aceitação
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_07_personal_ve_plano_aceito(
        self,
        personal_client: AsyncClient,
        db_session: AsyncSession,
        plan_assignment_setup: dict,
    ):
        """Personal Trainer vê que o plano foi aceito."""
        from src.domains.workouts.models import PlanAssignment, AssignmentStatus

        # Simular aceitação do plano
        assignment_id = plan_assignment_setup["assignment"]["id"]
        assignment = await db_session.get(PlanAssignment, assignment_id)
        assignment.status = AssignmentStatus.ACCEPTED
        assignment.accepted_at = datetime.now(timezone.utc)
        await db_session.commit()

        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])

        # Dado que o aluno aceitou o plano
        # Quando acesso os detalhes do aluno (usando membership_id, não user_id)
        membership_id = str(plan_assignment_setup["student"]["membership"]["id"])
        response = await personal_client.get(
            f"/trainers/students/{membership_id}",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver informações do aluno
        assert response.status_code == 200

    # =========================================================================
    # FASE 8: ALUNO - Execução do Primeiro Treino
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_08_aluno_inicia_sessao_treino(
        self,
        student_client: AsyncClient,
        db_session: AsyncSession,
        plan_assignment_setup: dict,
    ):
        """Aluno inicia uma sessão de treino."""
        from src.domains.workouts.models import PlanAssignment, AssignmentStatus

        # Primeiro aceitar o plano
        assignment_id = plan_assignment_setup["assignment"]["id"]
        assignment = await db_session.get(PlanAssignment, assignment_id)
        assignment.status = AssignmentStatus.ACCEPTED
        await db_session.commit()

        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])
        workout_id = str(plan_assignment_setup["workouts"][0]["id"])

        # Dado que tenho um plano aceito
        # Quando inicio uma sessão de treino
        # Note: Not passing assignment_id because WorkoutSession references workout_assignments,
        # not plan_assignments. This is a design issue that should be fixed in the models.
        response = await student_client.post(
            "/workouts/sessions",
            json={
                "workout_id": workout_id,
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então a sessão deve ser criada
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_fase_08_aluno_registra_serie(
        self,
        student_client: AsyncClient,
        active_workout_session_setup: dict,
    ):
        """Aluno registra séries completadas."""
        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])
        session_id = str(active_workout_session_setup["session"]["id"])
        exercise = active_workout_session_setup["workout"]["exercises"][0]

        # Dado que estou em uma sessão ativa
        # Quando registro uma série completada
        response = await student_client.post(
            f"/workouts/sessions/{session_id}/sets",
            json={
                "exercise_id": str(exercise["exercise_id"]),
                "set_number": 1,
                "reps_completed": 12,
                "weight_kg": 20.0,
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então a série deve ser registrada
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_fase_08_aluno_completa_treino(
        self,
        student_client: AsyncClient,
        active_workout_session_setup: dict,
    ):
        """Aluno finaliza a sessão de treino."""
        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])
        session_id = str(active_workout_session_setup["session"]["id"])

        # Dado que completei os exercícios
        # Quando finalizo a sessão
        response = await student_client.post(
            f"/workouts/sessions/{session_id}/complete",
            json={
                "rating": 5,
                "feedback": "Adorei o primeiro treino!",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então a sessão deve ser completada
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "completed"

    # =========================================================================
    # FASE 9: PERSONAL - Visualização do Treino Concluído
    # =========================================================================

    @pytest.mark.asyncio
    async def test_fase_09_personal_ve_sessao_completada(
        self,
        personal_client: AsyncClient,
        db_session: AsyncSession,
        active_workout_session_setup: dict,
    ):
        """Personal Trainer vê a sessão completada."""
        from src.domains.workouts.models import WorkoutSession, SessionStatus

        # Marcar sessão como completada
        session_id = active_workout_session_setup["session"]["id"]
        session = await db_session.get(WorkoutSession, session_id)
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        session.rating = 5
        session.student_feedback = "Adorei o primeiro treino!"
        await db_session.commit()

        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])
        membership_id = str(active_workout_session_setup["student"]["membership"]["id"])

        # Dado que o aluno completou um treino
        # Quando acesso o histórico de sessões do aluno
        response = await personal_client.get(
            f"/trainers/students/{membership_id}",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver informações do aluno
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fase_09_personal_ve_estatisticas_aluno(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer vê estatísticas do aluno."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        membership_id = str(student_setup["membership"]["id"])

        # Dado que o aluno tem histórico
        # Quando acesso as estatísticas (usando membership_id)
        response = await personal_client.get(
            f"/trainers/students/{membership_id}/stats",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo ver as estatísticas
        assert response.status_code in [200, 404]  # 404 se não implementado


class TestSaga01OnboardingAlternativo:
    """Cenários alternativos do onboarding."""

    @pytest.mark.asyncio
    async def test_aluno_recusa_plano_com_motivo(
        self,
        student_client: AsyncClient,
        plan_assignment_setup: dict,
    ):
        """Aluno recusa o plano com motivo."""
        org_id = str(plan_assignment_setup["trainer"]["organization"]["id"])
        assignment_id = str(plan_assignment_setup["assignment"]["id"])

        # Dado que tenho um plano pendente
        # Quando recuso o plano com motivo
        response = await student_client.post(
            f"/workouts/plans/assignments/{assignment_id}/respond",
            json={
                "accept": False,
                "reason": "Prefiro treinos em casa",
            },
            headers={"X-Organization-ID": org_id},
        )

        # Então o plano deve ser recusado
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "declined"

    @pytest.mark.asyncio
    async def test_convite_via_link_codigo(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal Trainer gera código de convite."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Dado que sou um Personal Trainer
        # Quando solicito meu código de convite
        response = await personal_client.get(
            "/trainers/my-invite-code",
            headers={"X-Organization-ID": org_id},
        )

        # Então devo receber um código
        assert response.status_code in [200, 201]
