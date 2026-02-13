"""Email service for sending transactional emails using Resend."""
import logging
from typing import Optional

import resend

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Initialize Resend with API key
resend.api_key = settings.RESEND_API_KEY


class EmailService:
    """Service for sending emails via Resend."""

    @staticmethod
    async def send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
    ) -> bool:
        """Send an email using Resend.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            text_content: Plain text fallback (optional)

        Returns:
            True if email was sent successfully, False otherwise
        """
        if not settings.email_enabled:
            logger.warning(f"Email not sent to {to_email}: Resend API key not configured")
            return False

        try:
            params: resend.Emails.SendParams = {
                "from": settings.EMAIL_FROM,
                "to": [to_email],
                "subject": subject,
                "html": html_content,
            }

            if text_content:
                params["text"] = text_content

            email = resend.Emails.send(params)
            logger.info(f"Email sent successfully to {to_email}, id: {email.get('id')}")
            return True

        except (resend.exceptions.ResendError, ConnectionError, OSError) as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False


# Email templates

def get_welcome_email_html(name: str, email: str, temp_password: str, trainer_name: str) -> str:
    """Generate HTML for welcome email with temporary password."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bem-vindo ao MyFit!</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .credentials {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0; }}
            .credentials p {{ margin: 8px 0; }}
            .credentials strong {{ color: #6366f1; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Bem-vindo ao MyFit! 🎉</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{name}</strong>,</p>
                <p>Você foi convidado por <strong>{trainer_name}</strong> para fazer parte do MyFit!</p>
                <p>Sua conta foi criada com sucesso. Use as credenciais abaixo para fazer seu primeiro acesso:</p>

                <div class="credentials">
                    <p><strong>Email:</strong> {email}</p>
                    <p><strong>Senha temporária:</strong> {temp_password}</p>
                </div>

                <p>⚠️ <strong>Importante:</strong> Por segurança, recomendamos que você altere sua senha no primeiro acesso.</p>

                <p style="text-align: center;">
                    <a href="https://myfit.app" class="button">Acessar MyFit</a>
                </p>

                <p>Se você tiver dúvidas, entre em contato com seu personal trainer ou nossa equipe de suporte.</p>

                <p>Bons treinos! 💪</p>
            </div>
            <div class="footer">
                <p>Este email foi enviado pelo MyFit.<br>Se você não solicitou esta conta, por favor ignore este email.</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_welcome_email_text(name: str, email: str, temp_password: str, trainer_name: str) -> str:
    """Generate plain text for welcome email."""
    return f"""
Bem-vindo ao MyFit!

Olá {name},

Você foi convidado por {trainer_name} para fazer parte do MyFit!

Sua conta foi criada com sucesso. Use as credenciais abaixo para fazer seu primeiro acesso:

Email: {email}
Senha temporária: {temp_password}

IMPORTANTE: Por segurança, recomendamos que você altere sua senha no primeiro acesso.

Acesse: https://myfit.app

Se você tiver dúvidas, entre em contato com seu personal trainer ou nossa equipe de suporte.

Bons treinos!

---
Este email foi enviado pelo MyFit.
Se você não solicitou esta conta, por favor ignore este email.
    """.strip()


def get_invite_email_html(email: str, trainer_name: str, org_name: str, invite_url: str) -> str:
    """Generate HTML for organization invite email."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Convite para o MyFit</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Você foi convidado! 🎉</h1>
            </div>
            <div class="content">
                <p>Olá!</p>
                <p><strong>{trainer_name}</strong> convidou você para fazer parte de <strong>{org_name}</strong> no MyFit!</p>
                <p>O MyFit é uma plataforma completa para acompanhamento de treinos, nutrição e evolução fitness.</p>

                <p style="text-align: center;">
                    <a href="{invite_url}" class="button">Aceitar Convite</a>
                </p>

                <p>Se você já tem uma conta, basta fazer login e o convite será aplicado automaticamente.</p>
                <p>Se ainda não tem conta, crie uma usando o email <strong>{email}</strong>.</p>

                <p>Vamos juntos alcançar seus objetivos! 💪</p>
            </div>
            <div class="footer">
                <p>Este email foi enviado pelo MyFit.<br>Se você não conhece {trainer_name}, por favor ignore este email.</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_invite_email_text(email: str, trainer_name: str, org_name: str, invite_url: str) -> str:
    """Generate plain text for organization invite email."""
    return f"""
Você foi convidado para o MyFit!

Olá!

{trainer_name} convidou você para fazer parte de {org_name} no MyFit!

O MyFit é uma plataforma completa para acompanhamento de treinos, nutrição e evolução fitness.

Aceite o convite acessando: {invite_url}

Se você já tem uma conta, basta fazer login e o convite será aplicado automaticamente.
Se ainda não tem conta, crie uma usando o email {email}.

Vamos juntos alcançar seus objetivos!

---
Este email foi enviado pelo MyFit.
Se você não conhece {trainer_name}, por favor ignore este email.
    """.strip()


def get_workout_reminder_email_html(name: str, workout_name: str, trainer_name: str) -> str:
    """Generate HTML for workout reminder email."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lembrete de Treino</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #10b981; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .workout-card {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Hora de Treinar! 🏋️</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{name}</strong>,</p>
                <p>Seu personal <strong>{trainer_name}</strong> tem um treino esperando por você!</p>

                <div class="workout-card">
                    <h3 style="margin-top: 0; color: #10b981;">📋 {workout_name}</h3>
                    <p>Não deixe para depois. Cada treino conta!</p>
                </div>

                <p style="text-align: center;">
                    <a href="https://myfit.app" class="button">Iniciar Treino</a>
                </p>

                <p>Bons treinos! 💪</p>
            </div>
            <div class="footer">
                <p>Este email foi enviado pelo MyFit.</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_payment_reminder_email_html(name: str, amount: float, due_date: str, trainer_name: str) -> str:
    """Generate HTML for payment reminder email."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lembrete de Pagamento</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #f59e0b; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            .payment-card {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Lembrete de Pagamento 💰</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{name}</strong>,</p>
                <p>Este é um lembrete sobre seu pagamento pendente com <strong>{trainer_name}</strong>.</p>

                <div class="payment-card">
                    <p><strong>Valor:</strong> R$ {amount:.2f}</p>
                    <p><strong>Vencimento:</strong> {due_date}</p>
                </div>

                <p>Por favor, efetue o pagamento para continuar aproveitando todos os benefícios do seu plano.</p>

                <p style="text-align: center;">
                    <a href="https://myfit.app/billing" class="button">Ver Detalhes</a>
                </p>

                <p>Se você já efetuou o pagamento, por favor desconsidere este email.</p>
            </div>
            <div class="footer">
                <p>Este email foi enviado pelo MyFit.</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_verification_code_email_html(name: str, code: str) -> str:
    """Generate HTML for email verification code."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Código de Verificação</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .code-box {{ background: white; padding: 30px; border-radius: 8px; margin: 20px 0; text-align: center; border: 2px dashed #6366f1; }}
            .code {{ font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #6366f1; font-family: monospace; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Verificação de Email 🔐</h1>
            </div>
            <div class="content">
                <p>Olá <strong>{name}</strong>,</p>
                <p>Use o código abaixo para verificar seu email no MyFit:</p>

                <div class="code-box">
                    <p class="code">{code}</p>
                </div>

                <p>⚠️ <strong>Importante:</strong></p>
                <ul>
                    <li>Este código expira em <strong>15 minutos</strong></li>
                    <li>Não compartilhe este código com ninguém</li>
                    <li>Se você não solicitou este código, ignore este email</li>
                </ul>
            </div>
            <div class="footer">
                <p>Este email foi enviado pelo MyFit.</p>
            </div>
        </div>
    </body>
    </html>
    """


def get_verification_code_email_text(name: str, code: str) -> str:
    """Generate plain text for email verification code."""
    return f"""
Verificação de Email - MyFit

Olá {name},

Use o código abaixo para verificar seu email no MyFit:

{code}

IMPORTANTE:
- Este código expira em 15 minutos
- Não compartilhe este código com ninguém
- Se você não solicitou este código, ignore este email

---
Este email foi enviado pelo MyFit.
    """.strip()


async def send_verification_code_email(
    to_email: str,
    name: str,
    code: str,
) -> bool:
    """Send email verification code."""
    html_content = get_verification_code_email_html(name, code)
    text_content = get_verification_code_email_text(name, code)

    return await EmailService.send_email(
        to_email=to_email,
        subject=f"Seu código de verificação MyFit: {code}",
        html_content=html_content,
        text_content=text_content,
    )


async def send_welcome_email(
    to_email: str,
    name: str,
    temp_password: str,
    trainer_name: str,
) -> bool:
    """Send welcome email with temporary password to new student."""
    html_content = get_welcome_email_html(name, to_email, temp_password, trainer_name)
    text_content = get_welcome_email_text(name, to_email, temp_password, trainer_name)

    return await EmailService.send_email(
        to_email=to_email,
        subject="Bem-vindo ao MyFit! 🎉",
        html_content=html_content,
        text_content=text_content,
    )


async def send_invite_email(
    to_email: str,
    trainer_name: str,
    org_name: str,
    invite_token: str,
) -> bool:
    """Send organization invite email."""
    invite_url = f"https://myfit.app/invite/{invite_token}"
    html_content = get_invite_email_html(to_email, trainer_name, org_name, invite_url)
    text_content = get_invite_email_text(to_email, trainer_name, org_name, invite_url)

    return await EmailService.send_email(
        to_email=to_email,
        subject=f"{trainer_name} convidou você para o MyFit!",
        html_content=html_content,
        text_content=text_content,
    )


async def send_invite_reminder_email(
    to_email: str,
    inviter_name: str,
    org_name: str,
    invite_token: str,
    is_final: bool = False,
) -> bool:
    """Send invite reminder email.

    Args:
        to_email: Recipient email
        inviter_name: Name of the person who sent the invite
        org_name: Organization name
        invite_token: Invite token for the link
        is_final: True if this is the final reminder (14 days)
    """
    invite_url = f"https://myfit.app/invite/{invite_token}"

    if is_final:
        subject = f"Último lembrete: {inviter_name} ainda está esperando sua resposta!"
        urgency_text = "Este é seu último lembrete. O convite expira em breve!"
    else:
        subject = f"Lembrete: {inviter_name} convidou você para o MyFit"
        urgency_text = "Não deixe seu personal esperando!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Lembrete de Convite</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
            .content {{ background: #f8fafc; padding: 30px; border-radius: 0 0 8px 8px; }}
            .button {{ display: inline-block; background: #6366f1; color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; margin: 20px 0; font-weight: 600; }}
            .urgency {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px 16px; margin: 20px 0; }}
            .footer {{ text-align: center; color: #64748b; font-size: 14px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{"⚠️ Último Lembrete!" if is_final else "📬 Lembrete de Convite"}</h1>
            </div>
            <div class="content">
                <p>Olá!</p>
                <p><strong>{inviter_name}</strong> de <strong>{org_name}</strong> ainda está aguardando você aceitar o convite para o MyFit.</p>

                <div class="urgency">
                    <p style="margin: 0;"><strong>{urgency_text}</strong></p>
                </div>

                <p>Com o MyFit você pode:</p>
                <ul>
                    <li>Acompanhar seus treinos personalizados</li>
                    <li>Registrar seu progresso</li>
                    <li>Comunicar-se com seu personal</li>
                </ul>

                <p style="text-align: center;">
                    <a href="{invite_url}" class="button">Aceitar Convite</a>
                </p>

                <p style="font-size: 14px; color: #64748b;">
                    Se você não solicitou este convite, pode ignorar este email.
                </p>
            </div>
            <div class="footer">
                <p>MyFit - Sua jornada fitness começa aqui</p>
            </div>
        </div>
    </body>
    </html>
    """

    return await EmailService.send_email(
        to_email=to_email,
        subject=subject,
        html_content=html_content,
    )


async def send_workout_reminder_email(
    to_email: str,
    name: str,
    workout_name: str,
    trainer_name: str,
) -> bool:
    """Send workout reminder email."""
    html_content = get_workout_reminder_email_html(name, workout_name, trainer_name)

    return await EmailService.send_email(
        to_email=to_email,
        subject=f"Lembrete: {workout_name} está esperando por você!",
        html_content=html_content,
    )


async def send_payment_reminder_email(
    to_email: str,
    name: str,
    amount: float,
    due_date: str,
    trainer_name: str,
) -> bool:
    """Send payment reminder email."""
    html_content = get_payment_reminder_email_html(name, amount, due_date, trainer_name)

    return await EmailService.send_email(
        to_email=to_email,
        subject="Lembrete de Pagamento - MyFit",
        html_content=html_content,
    )
