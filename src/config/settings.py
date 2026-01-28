from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "MyFit API"
    APP_VERSION: str = "0.6.8"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    APP_URL: str = "https://app.myfitplatform.com"  # Frontend URL for invite links

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./myfit.db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "your-super-secret-key-change-in-production"
    JWT_REFRESH_SECRET_KEY: str = "your-refresh-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8080",
        "http://192.168.0.102:8080",
        "http://192.168.0.101:8080",
        "http://192.168.0.109:8080",
        "https://myfitplatform.com",
        "https://app.myfitplatform.com",
    ]

    # Storage (S3 / Cloudflare R2)
    STORAGE_PROVIDER: Literal["s3", "r2", "local"] = "local"  # s3, r2, or local for development
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "myfit-uploads"
    S3_ENDPOINT_URL: str = ""  # For R2: https://<account_id>.r2.cloudflarestorage.com
    CDN_BASE_URL: str = ""  # CDN URL for serving files (e.g., https://cdn.myfit.app)
    LOCAL_STORAGE_PATH: str = "./uploads"  # For local development

    # AI Services
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    ANTHROPIC_API_KEY: str = ""

    # Payment Gateways
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Email (Resend)
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "MyFit <noreply@myfit.app>"

    # Social Login - Google
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_ID_IOS: str = ""
    GOOGLE_CLIENT_ID_ANDROID: str = ""

    # Social Login - Apple
    APPLE_CLIENT_ID: str = ""  # Bundle ID (e.g., com.myfit.app)
    APPLE_TEAM_ID: str = ""

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True

    # Observability (GlitchTip/Sentry)
    GLITCHTIP_DSN: str = ""
    GLITCHTIP_TRACES_SAMPLE_RATE: float = 0.2
    GLITCHTIP_PROFILES_SAMPLE_RATE: float = 0.1

    @property
    def email_enabled(self) -> bool:
        """Check if email is configured."""
        return bool(self.RESEND_API_KEY)

    @property
    def storage_enabled(self) -> bool:
        """Check if cloud storage is configured."""
        if self.STORAGE_PROVIDER == "local":
            return True
        return bool(self.AWS_ACCESS_KEY_ID and self.AWS_SECRET_ACCESS_KEY)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
