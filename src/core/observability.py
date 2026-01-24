"""
Observability module for MyFit API.

Provides error tracking and performance monitoring using GlitchTip
(open-source, Sentry-compatible).
"""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from src.config.settings import settings


def init_observability() -> None:
    """Initialize GlitchTip/Sentry observability."""
    if not settings.GLITCHTIP_DSN:
        print("[Observability] Disabled - no DSN configured")
        return

    # Determine sample rates based on environment
    traces_sample_rate = settings.GLITCHTIP_TRACES_SAMPLE_RATE
    profiles_sample_rate = settings.GLITCHTIP_PROFILES_SAMPLE_RATE

    if settings.is_development:
        traces_sample_rate = 1.0
        profiles_sample_rate = 1.0

    sentry_sdk.init(
        dsn=settings.GLITCHTIP_DSN,
        environment=settings.APP_ENV,
        release=f"myfit-api@1.0.0",
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
        before_send=_before_send,
    )

    print(f"[Observability] Initialized for {settings.APP_ENV}")


def _before_send(event: dict, hint: dict) -> dict | None:
    """Filter events before sending to GlitchTip."""
    # Filter out common non-actionable errors
    if "exc_info" in hint:
        exc_type, exc_value, _ = hint["exc_info"]
        exc_message = str(exc_value).lower()

        # Filter connection errors that are usually transient
        if any(
            msg in exc_message
            for msg in ["connection refused", "connection reset", "broken pipe"]
        ):
            return None

    return event


def set_user_context(
    user_id: str,
    email: str | None = None,
    role: str | None = None,
    organization_id: str | None = None,
) -> None:
    """Set user context for error reports."""
    sentry_sdk.set_user(
        {
            "id": user_id,
            "email": email,
            "role": role,
            "organization_id": organization_id,
        }
    )


def clear_user_context() -> None:
    """Clear user context."""
    sentry_sdk.set_user(None)


def capture_exception(
    exception: Exception,
    extra: dict | None = None,
    tags: dict[str, str] | None = None,
) -> str | None:
    """Capture an exception with optional context."""
    with sentry_sdk.push_scope() as scope:
        if extra:
            for key, value in extra.items():
                scope.set_extra(key, value)
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        return sentry_sdk.capture_exception(exception)


def capture_message(
    message: str,
    level: str = "info",
    extra: dict | None = None,
) -> str | None:
    """Capture a message event."""
    with sentry_sdk.push_scope() as scope:
        if extra:
            for key, value in extra.items():
                scope.set_extra(key, value)

        return sentry_sdk.capture_message(message, level=level)
