"""Application settings loaded from environment variables.

Uses pydantic-settings for validation and .env file support.
Access the singleton via get_settings().
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the ASAHI SaaS backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://asahi:asahi_dev_password@localhost:5432/asahi"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Debug
    debug: bool = True

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # LLM Providers
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None

    # Auth (Clerk)
    clerk_secret_key: Optional[str] = None
    clerk_publishable_key: Optional[str] = None
    clerk_webhook_secret: Optional[str] = None
    clerk_jwks_url: Optional[str] = None

    # Stripe
    stripe_secret_key: Optional[str] = None
    stripe_webhook_secret: Optional[str] = None
    stripe_pro_price_id: Optional[str] = None

    # Email
    resend_api_key: Optional[str] = None

    # Rate limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_tokens_per_minute: int = 100_000

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings singleton."""
    return Settings()


def reset_settings() -> None:
    """Clear the settings cache. Used in tests."""
    get_settings.cache_clear()
