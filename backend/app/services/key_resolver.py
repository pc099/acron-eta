"""Database-backed API key resolver for BYOK (Bring Your Own Key).

Resolution priority:
  1. BYOK key from ``provider_keys`` table (decrypted)
  2. Platform environment variable (OPENAI_API_KEY, etc.)
  3. Ollama → returns empty string (no key needed)
  4. Raise ``BillingException``
"""

import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProviderKey
from app.services.encryption import decrypt_secret

logger = logging.getLogger(__name__)

_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "vercel": "AI_GATEWAY_API_KEY",
}


class DBKeyResolver:
    """Resolves API keys for a given provider and organisation.

    Async because it queries the database.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(self, provider: str, org_id: Optional[str] = None) -> str:
        """Return the API key for *provider* and *org_id*.

        Args:
            provider: Canonical provider name (e.g. ``"openai"``).
            org_id: Organisation UUID string.

        Returns:
            The decrypted API key string.

        Raises:
            ValueError: No key available for the provider.
        """
        # Ollama needs no key
        if provider == "ollama" or provider.startswith("ollama:"):
            return ""

        # 1. Check BYOK keys in database
        if org_id:
            try:
                import uuid as _uuid
                _org_uuid = _uuid.UUID(org_id) if isinstance(org_id, str) else org_id
                result = await self._db.execute(
                    select(ProviderKey).where(
                        ProviderKey.organisation_id == _org_uuid,
                        ProviderKey.provider == provider,
                        ProviderKey.is_active == True,  # noqa: E712
                    )
                )
                pk = result.scalar_one_or_none()
                if pk:
                    try:
                        decrypted = decrypt_secret(pk.encrypted_key)
                        logger.debug("Resolved BYOK key for %s (org=%s)", provider, org_id)
                        return decrypted
                    except Exception:
                        logger.warning("Failed to decrypt BYOK key for %s (org=%s)", provider, org_id)
            except Exception:
                logger.warning("Error checking BYOK key for %s (org=%s)", provider, org_id, exc_info=True)

        # 2. Vercel AI Gateway token (if gateway is enabled)
        if os.environ.get("USE_VERCEL_GATEWAY", "").lower() in ("true", "1", "yes"):
            vercel_token = os.environ.get("AI_GATEWAY_API_KEY")
            if vercel_token:
                logger.debug("Resolved Vercel gateway token for %s (org=%s)", provider, org_id)
                return vercel_token

        # 3. Platform env var
        env_var = _ENV_MAP.get(provider)
        if env_var:
            key = os.environ.get(env_var)
            if key:
                return key

        raise ValueError(
            f"No API key available for provider '{provider}'. "
            f"Store a BYOK key or set {_ENV_MAP.get(provider, 'the env var')}."
        )
