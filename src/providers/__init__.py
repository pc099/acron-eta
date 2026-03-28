"""Provider abstraction layer — registry, resolver, re-exports.

Usage::

    from src.providers import get_provider, get_provider_for_model, EnvKeyResolver

    provider = get_provider("openai")
    key = EnvKeyResolver().resolve("openai")
    response = provider.call(InferenceRequest(model="gpt-4o", prompt="Hi"), key)
"""

import logging
import os
from typing import Optional

from src.providers.base import (
    BillingException,
    InferenceRequest,
    InferenceResponse,
    ProviderAdapter,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderServerError,
)
from src.providers.providers import (
    AnthropicProvider,
    DeepSeekProvider,
    GoogleProvider,
    MistralProvider,
    OllamaProvider,
    OpenAIProvider,
)

logger = logging.getLogger(__name__)

__all__ = [
    # DTOs + base
    "InferenceRequest",
    "InferenceResponse",
    "ProviderAdapter",
    # Exceptions
    "BillingException",
    "ProviderRateLimitError",
    "ProviderRequestError",
    "ProviderServerError",
    # Registry functions
    "PROVIDER_REGISTRY",
    "get_provider",
    "get_provider_for_model",
    "register_ollama",
    # Key resolver
    "EnvKeyResolver",
    # Vercel AI Gateway
    "is_vercel_gateway_enabled",
]


# ── Module-level singleton registry ─────────────────────────────────────

PROVIDER_REGISTRY: dict[str, ProviderAdapter] = {
    "openai": OpenAIProvider(),
    "anthropic": AnthropicProvider(),
    "google": GoogleProvider(),
    "deepseek": DeepSeekProvider(),
    "mistral": MistralProvider(),
}


# ── Vercel AI Gateway (feature-flagged) ───────────────────────────────

_vercel_registry: dict[str, ProviderAdapter] = {}
_vercel_enabled: bool = False


def _init_vercel_gateway() -> None:
    """Initialise Vercel Gateway adapters if USE_VERCEL_GATEWAY is enabled."""
    global _vercel_registry, _vercel_enabled

    flag = os.environ.get("USE_VERCEL_GATEWAY", "").lower()
    if flag not in ("true", "1", "yes"):
        return

    gateway_url = os.environ.get(
        "VERCEL_GATEWAY_URL", "https://ai-gateway.vercel.sh/v1"
    )

    from src.providers.vercel_gateway import VercelGatewayProvider

    for provider_name in ("openai", "anthropic", "google", "deepseek", "mistral"):
        _vercel_registry[provider_name] = VercelGatewayProvider(
            gateway_url=gateway_url,
            upstream_provider=provider_name,
        )

    _vercel_enabled = True
    logger.info(
        "Vercel AI Gateway enabled: %d providers wrapped (url=%s)",
        len(_vercel_registry),
        gateway_url,
    )


_init_vercel_gateway()


def is_vercel_gateway_enabled() -> bool:
    """Return True if the Vercel AI Gateway feature flag is active."""
    return _vercel_enabled


# ── Registry lookup ────────────────────────────────────────────────────


def get_provider(provider_name: str) -> ProviderAdapter:
    """Look up a provider adapter by canonical name.

    When the Vercel AI Gateway is enabled, returns the gateway-wrapped
    adapter.  Falls back to the direct adapter otherwise.

    Raises:
        ValueError: Unknown provider name.
    """
    if _vercel_enabled:
        adapter = _vercel_registry.get(provider_name)
        if adapter is not None:
            return adapter

    adapter = PROVIDER_REGISTRY.get(provider_name)
    if adapter is None:
        raise ValueError(f"Unknown provider: {provider_name}")
    return adapter


def get_provider_for_model(model_id: str) -> ProviderAdapter:
    """Find the adapter that handles a given model ID.

    Uses ``supports_model()`` prefix matching.  Returns the first match.
    Checks the Vercel registry first when the gateway is enabled.

    Raises:
        ValueError: No provider found for the model.
    """
    if _vercel_enabled:
        for adapter in _vercel_registry.values():
            if adapter.supports_model(model_id):
                return adapter

    for adapter in PROVIDER_REGISTRY.values():
        if adapter.supports_model(model_id):
            return adapter
    raise ValueError(f"No provider found for model: {model_id}")


def register_ollama(name: str, base_url: str) -> OllamaProvider:
    """Register (or update) an Ollama instance in the global registry.

    The key in the registry is ``"ollama:{name}"`` so multiple instances
    can coexist.

    Returns:
        The created OllamaProvider instance.
    """
    key = f"ollama:{name}"
    provider = OllamaProvider(base_url=base_url)
    PROVIDER_REGISTRY[key] = provider
    logger.info("Registered Ollama instance: %s -> %s", key, base_url)
    return provider


# ── Key Resolver ────────────────────────────────────────────────────────

_ENV_MAP: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "vercel": "AI_GATEWAY_API_KEY",
}


class EnvKeyResolver:
    """Resolves API keys from environment variables.

    This is the default resolver used in tests and local development.
    The production backend uses ``DBKeyResolver`` which checks BYOK keys
    in the database first.
    """

    def resolve(self, provider: str, org_id: Optional[str] = None) -> str:
        """Return the API key for *provider*.

        Args:
            provider: Canonical provider name (e.g. ``"openai"``).
            org_id: Ignored in the env resolver.

        Returns:
            The API key string.

        Raises:
            BillingException: No env var set for the provider.
        """
        if provider == "ollama" or provider.startswith("ollama:"):
            return ""  # Ollama needs no key

        env_var = _ENV_MAP.get(provider)
        if not env_var:
            raise BillingException(
                f"No key mapping for provider: {provider}"
            )

        key = os.environ.get(env_var)
        if not key:
            raise BillingException(
                f"API key not configured for {provider} "
                f"(set {env_var} environment variable)"
            )
        return key
