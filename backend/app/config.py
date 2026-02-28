"""Application settings loaded from environment variables.

Uses pydantic-settings for validation and .env file support.
Access the singleton via get_settings().
"""

import json
from functools import lru_cache
from typing import Optional, Union

from pydantic import model_validator, Field
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

    @model_validator(mode="after")
    def _normalize_database_url(self) -> "Settings":
        """Ensure database_url uses the asyncpg driver.

        PaaS providers (Railway, Heroku) set DATABASE_URL as
        ``postgresql://...`` which defaults to psycopg2 in SQLAlchemy.
        """
        url = self.database_url
        if url.startswith("postgres://"):
            self.database_url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and "+asyncpg" not in url:
            self.database_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Debug
    debug: bool = True

    # CORS — allowed origins for browser requests (e.g. frontend on Vercel).
    # Env var: CORS_ORIGINS=https://your-app.vercel.app
    # Comma-separated: CORS_ORIGINS=https://app.vercel.app,https://custom.com
    # JSON array: CORS_ORIGINS=["https://app.vercel.app"]
    # Stored as str so pydantic-settings doesn't JSON-decode plain comma values.
    cors_origins: str = "http://localhost:3000,http://localhost:8000"

    def get_cors_origins(self) -> list[str]:
        """Parse CORS origins from string: JSON array or comma-separated."""
        v = self.cors_origins.strip()
        if not v:
            return []
        if v.startswith("["):
            try:
                items = json.loads(v)
                raw = [x.strip() for x in items if isinstance(x, str) and x.strip()]
            except json.JSONDecodeError:
                raw = [x.strip() for x in v.split(",") if x.strip()]
        else:
            raw = [x.strip() for x in v.split(",") if x.strip()]
        return [o.rstrip("/") for o in raw]

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
