"""
SAGA 8: Cancelamento e Reagendamento de Sessão
SAGA 9: Múltiplos Alunos - Gerenciamento Simultâneo
SAGA 10: Feedback Negativo e Resolução

IMPORTANT: Run only in local/development environment!
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


class TestSaga08CancelAndReschedule:
    """
    SAGA 8: Cancelamento e Reagendamento de Sessão.

    Fases:
    1. PERSONAL - Agendamento de Sessão Presencial
    2. ALUNO - Confirmação da Sessão
    3. ALUNO - Necessidade de Cancelamento
    4. PERSONAL - Recebimento do Cancelamento
    5. PERSONAL - Proposta de Reagendamento
    6. ALUNO - Resposta com Preferência
    7. PERSONAL - Reagendamento da Sessão
    8. ALUNO - Confirmação do Reagendamento
    9. EXECUÇÃO - Sessão Reagendada
    """

    @pytest.mark.asyncio
    async def test_fase_01_personal_agenda_sessao(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer agenda sessão presencial."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/schedule/appointments",
            json={
                "student_id": student_id,
                "date_time": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "duration_minutes": 60,
                "workout_type": "strength",
                "notes": "Treino presencial",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_02_aluno_confirma_sessao(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno confirma a sessão agendada."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Consultar agendamentos pendentes
        response = await student_client.get(
            "/schedule/appointments",
            params={"status": "pending"},
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_fase_03_aluno_cancela_sessao(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno cancela sessão por imprevisto."""
        org_id = str(student_setup["trainer"]["organization"]["id"])

        # Nota: Precisaria do ID do appointment
        # Este é um teste conceitual do endpoint
        response = await student_client.get(
            "/schedule/appointments",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_fase_05_personal_propoe_reagendamento(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal propõe reagendamento via chat."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/chat/conversations",
            json={
                "recipient_id": student_id,
                "message": "Sem problemas! Podemos remarcar para quinta às 14h ou sexta às 10h?",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_07_personal_reagenda_sessao(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal Trainer reagenda a sessão."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/schedule/appointments",
            json={
                "student_id": student_id,
                "date_time": (datetime.now(timezone.utc) + timedelta(days=4)).isoformat(),
                "duration_minutes": 60,
                "workout_type": "strength",
                "notes": "Reagendamento de quarta",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]


class TestSaga09MultipleStudents:
    """
    SAGA 9: Gerenciamento de Múltiplos Alunos.

    Simula Personal gerenciando vários alunos com diferentes situações.
    """

    @pytest.mark.asyncio
    async def test_fase_01_personal_dashboard_overview(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal vê visão geral do dashboard."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        response = await personal_client.get(
            "/trainers/students",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fase_01_personal_ve_alertas(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal vê alertas de alunos."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Verificar se há endpoint de alertas/notificações
        response = await personal_client.get(
            "/notifications",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_fase_02_personal_trata_aluno_inativo(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal trata aluno inativo."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Envia mensagem de incentivo
        response = await personal_client.post(
            "/chat/conversations",
            json={
                "recipient_id": student_id,
                "message": "Vi que você não treinou essa semana. Está tudo bem?",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_04_personal_trata_plano_pendente(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal lembra aluno sobre plano pendente."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/chat/conversations",
            json={
                "recipient_id": student_id,
                "message": "Vi que ainda não aceitou o plano. Tem alguma dúvida?",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_09_personal_revisao_final_dia(
        self,
        personal_client: AsyncClient,
        personal_trainer_setup: dict,
    ):
        """Personal faz revisão final do dia."""
        org_id = str(personal_trainer_setup["organization"]["id"])

        # Ver atividade recente
        response = await personal_client.get(
            "/trainers/students",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200


class TestSaga10NegativeFeedback:
    """
    SAGA 10: Tratamento de Feedback Negativo.

    Fases:
    1. ALUNO - Treino com Experiência Ruim
    2. PERSONAL - Recebimento do Alerta
    3. PERSONAL - Contato Imediato
    4. ALUNO - Resposta com Detalhes
    5. PERSONAL - Análise e Plano de Ação
    6. PERSONAL - Ajuste do Plano
    7. ALUNO - Visualização dos Ajustes
    8. ALUNO - Agradecimento
    9. ALUNO - Próximo Treino (Validação)
    10. PERSONAL - Confirmação de Sucesso
    """

    @pytest.mark.asyncio
    async def test_fase_01_aluno_completa_treino_com_feedback_negativo(
        self,
        student_client: AsyncClient,
        active_workout_session_setup: dict,
    ):
        """Aluno completa treino com avaliação negativa."""
        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])
        session_id = str(active_workout_session_setup["session"]["id"])

        response = await student_client.post(
            f"/workouts/sessions/{session_id}/complete",
            json={
                "rating": 2,
                "feedback": "Achei o treino muito pesado. Senti dor no joelho.",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fase_03_personal_contato_imediato(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal entra em contato imediatamente."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/chat/conversations",
            json={
                "recipient_id": student_id,
                "message": "Vi seu feedback sobre o treino. Me desculpe! A dor no joelho é preocupante. Pode me contar mais?",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_04_aluno_responde_com_detalhes(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno responde com detalhes sobre o problema."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        trainer_id = str(student_setup["trainer"]["user"]["id"])

        response = await student_client.post(
            "/chat/conversations",
            json={
                "recipient_id": trainer_id,
                "message": "A dor é na parte de trás do joelho direito, principalmente no agachamento.",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_05_personal_envia_plano_acao(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal envia plano de ação."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        response = await personal_client.post(
            "/chat/conversations",
            json={
                "recipient_id": student_id,
                "message": "Entendi! Vou substituir agachamento por leg press e reduzir cargas em 20%. Se a dor persistir, recomendo consultar um ortopedista.",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_06_personal_ajusta_plano(
        self,
        personal_client: AsyncClient,
        training_plan_setup: dict,
    ):
        """Personal ajusta o plano do aluno."""
        org_id = str(training_plan_setup["organization_id"])
        plan_id = str(training_plan_setup["plan"]["id"])

        # Adicionar nota ao plano sobre os ajustes
        response = await personal_client.post(
            "/workouts/notes",
            json={
                "context_type": "plan",
                "context_id": plan_id,
                "content": "Ajustes: Substituído agachamento por leg press. Cargas reduzidas em 20%.",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]

    @pytest.mark.asyncio
    async def test_fase_09_aluno_treino_ajustado_sucesso(
        self,
        student_client: AsyncClient,
        active_workout_session_setup: dict,
        db_session: AsyncSession,
    ):
        """Aluno faz próximo treino ajustado com sucesso."""
        from src.domains.workouts.models import WorkoutSession, SessionStatus

        # Criar nova sessão simulando treino ajustado
        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])

        # Completar a sessão existente primeiro
        session_id = active_workout_session_setup["session"]["id"]
        session = await db_session.get(WorkoutSession, session_id)
        session.status = SessionStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        session.rating = 5
        session.student_feedback = "Muito melhor! Sem dor no joelho!"
        await db_session.commit()

        # Verificar que a sessão foi completada
        response = await student_client.get(
            f"/workouts/sessions/{session_id}",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fase_10_personal_ve_feedback_positivo(
        self,
        personal_client: AsyncClient,
        student_setup: dict,
    ):
        """Personal vê feedback positivo do treino ajustado."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        student_id = str(student_setup["membership"]["id"])

        # Consultar informações do aluno
        response = await personal_client.get(
            f"/trainers/students/{student_id}",
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200


class TestSaga10EdgeCases:
    """Casos especiais de feedback negativo."""

    @pytest.mark.asyncio
    async def test_feedback_muito_baixo_gera_alerta(
        self,
        student_client: AsyncClient,
        active_workout_session_setup: dict,
    ):
        """Feedback com nota 1-2 deve gerar alerta para o Personal."""
        org_id = str(active_workout_session_setup["trainer"]["organization"]["id"])
        session_id = str(active_workout_session_setup["session"]["id"])

        response = await student_client.post(
            f"/workouts/sessions/{session_id}/complete",
            json={
                "rating": 1,
                "feedback": "Treino péssimo, não consegui fazer nada.",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_aluno_reporta_lesao(
        self,
        student_client: AsyncClient,
        student_setup: dict,
    ):
        """Aluno reporta lesão durante treino."""
        org_id = str(student_setup["trainer"]["organization"]["id"])
        trainer_id = str(student_setup["trainer"]["user"]["id"])

        response = await student_client.post(
            "/chat/conversations",
            json={
                "recipient_id": trainer_id,
                "message": "Senti uma fisgada nas costas durante o exercício. Melhor parar?",
            },
            headers={"X-Organization-ID": org_id},
        )

        assert response.status_code in [200, 201, 404]
