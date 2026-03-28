"""Vercel AI Gateway adapter — routes LLM calls through Vercel's gateway.

The Vercel AI Gateway accepts OpenAI-compatible requests with model IDs in
``{provider}/{model}`` format (e.g. ``openai/gpt-4o``, ``anthropic/claude-sonnet-4-6``).

This adapter is registered in place of individual provider adapters when
``USE_VERCEL_GATEWAY=true``.  Model IDs are translated internally so DB records,
config, and external APIs continue using the short form (``gpt-4o``).
"""

import logging
from typing import Optional

from src.providers._openai_compat import OpenAICompatMixin
from src.providers.base import (
    InferenceRequest,
    InferenceResponse,
    ProviderAdapter,
)

logger = logging.getLogger(__name__)

# Model prefix patterns per provider — used by supports_model delegation
_MODEL_PREFIXES: dict[str, tuple[str, ...]] = {
    "openai": ("gpt-", "o1-", "o3-", "o3"),
    "anthropic": ("claude-",),
    "google": ("gemini-",),
    "deepseek": ("deepseek-",),
    "mistral": ("mistral-", "codestral-", "open-mistral-", "open-mixtral-"),
}


class VercelGatewayProvider(OpenAICompatMixin, ProviderAdapter):
    """Routes LLM calls through Vercel AI Gateway.

    One instance is created per upstream provider (openai, anthropic, etc.).
    The ``provider_name`` property returns the upstream name so that all
    DB records, analytics, and logs are unchanged.

    Args:
        gateway_url: Base URL for Vercel AI Gateway (e.g. ``https://ai-gateway.vercel.sh/v1``).
        upstream_provider: Canonical provider name (e.g. ``"openai"``).
    """

    def __init__(self, gateway_url: str, upstream_provider: str) -> None:
        self._gateway_url = gateway_url.rstrip("/")
        self._upstream_provider = upstream_provider

    @property
    def _base_url(self) -> str:  # type: ignore[override]
        return self._gateway_url

    @property
    def provider_name(self) -> str:
        return self._upstream_provider

    def call(self, request: InferenceRequest, api_key: str) -> InferenceResponse:
        """Execute inference via Vercel AI Gateway.

        Translates ``gpt-4o`` to ``openai/gpt-4o`` for the gateway API,
        then restores the original model ID in the response.
        """
        vercel_model = f"{self._upstream_provider}/{request.model}"
        vercel_request = InferenceRequest(
            model=vercel_model,
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system_prompt=request.system_prompt,
        )

        logger.debug(
            "Vercel Gateway call: %s → %s",
            request.model,
            vercel_model,
        )

        response = self._call_openai_compat(vercel_request, api_key)

        # Restore original model ID so DB/logs use canonical form
        response.model = request.model
        return response

    def supports_model(self, model_id: str) -> bool:
        """Check if this adapter's upstream provider handles the given model."""
        prefixes = _MODEL_PREFIXES.get(self._upstream_provider)
        if not prefixes:
            return False
        return model_id.startswith(prefixes)
