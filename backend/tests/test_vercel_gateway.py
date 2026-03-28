"""Tests for Vercel AI Gateway adapter and feature-flagged provider registry."""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.providers.base import InferenceRequest, InferenceResponse
from src.providers.vercel_gateway import VercelGatewayProvider, _MODEL_PREFIXES


# ── VercelGatewayProvider unit tests ──────────────────────────────────


class TestVercelGatewayProvider:
    """Unit tests for the Vercel Gateway adapter."""

    def test_provider_name_returns_upstream(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="openai",
        )
        assert adapter.provider_name == "openai"

    def test_provider_name_anthropic(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="anthropic",
        )
        assert adapter.provider_name == "anthropic"

    def test_base_url_is_gateway(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="openai",
        )
        assert adapter._base_url == "https://ai-gateway.vercel.sh/v1"

    def test_base_url_strips_trailing_slash(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1/",
            upstream_provider="openai",
        )
        assert adapter._base_url == "https://ai-gateway.vercel.sh/v1"

    def test_model_translation_openai(self) -> None:
        """Model ID should be translated to {provider}/{model} for gateway API."""
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="openai",
        )
        request = InferenceRequest(model="gpt-4o", prompt="Hello")

        # Mock _call_openai_compat to capture translated request
        mock_response = InferenceResponse(
            text="Hi",
            model="openai/gpt-4o",
            input_tokens=5,
            output_tokens=2,
            latency_ms=100,
            provider="openai",
        )
        adapter._call_openai_compat = MagicMock(return_value=mock_response)

        response = adapter.call(request, "fake-key")

        # Verify the gateway received the translated model ID
        call_args = adapter._call_openai_compat.call_args
        translated_request = call_args[0][0]
        assert translated_request.model == "openai/gpt-4o"
        assert call_args[0][1] == "fake-key"

        # Verify response model ID is restored to original
        assert response.model == "gpt-4o"

    def test_model_translation_anthropic(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="anthropic",
        )
        request = InferenceRequest(model="claude-sonnet-4-6", prompt="Hello")

        mock_response = InferenceResponse(
            text="Hi",
            model="anthropic/claude-sonnet-4-6",
            input_tokens=5,
            output_tokens=2,
            latency_ms=100,
            provider="anthropic",
        )
        adapter._call_openai_compat = MagicMock(return_value=mock_response)

        response = adapter.call(request, "fake-key")

        call_args = adapter._call_openai_compat.call_args
        translated_request = call_args[0][0]
        assert translated_request.model == "anthropic/claude-sonnet-4-6"
        assert response.model == "claude-sonnet-4-6"

    def test_model_translation_preserves_request_fields(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="openai",
        )
        request = InferenceRequest(
            model="gpt-4o",
            prompt="Hello world",
            max_tokens=500,
            temperature=0.7,
            system_prompt="You are helpful.",
        )

        mock_response = InferenceResponse(
            text="Hi", model="openai/gpt-4o", input_tokens=5, output_tokens=2,
            latency_ms=100, provider="openai",
        )
        adapter._call_openai_compat = MagicMock(return_value=mock_response)

        adapter.call(request, "fake-key")

        translated = adapter._call_openai_compat.call_args[0][0]
        assert translated.prompt == "Hello world"
        assert translated.max_tokens == 500
        assert translated.temperature == 0.7
        assert translated.system_prompt == "You are helpful."

    def test_supports_model_openai(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="openai",
        )
        assert adapter.supports_model("gpt-4o") is True
        assert adapter.supports_model("gpt-3.5-turbo") is True
        assert adapter.supports_model("o1-mini") is True
        assert adapter.supports_model("o3-mini") is True
        assert adapter.supports_model("o3") is True
        assert adapter.supports_model("claude-sonnet-4-6") is False
        assert adapter.supports_model("gemini-pro") is False

    def test_supports_model_anthropic(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="anthropic",
        )
        assert adapter.supports_model("claude-sonnet-4-6") is True
        assert adapter.supports_model("claude-3-haiku") is True
        assert adapter.supports_model("gpt-4o") is False

    def test_supports_model_google(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="google",
        )
        assert adapter.supports_model("gemini-pro") is True
        assert adapter.supports_model("gemini-1.5-flash") is True
        assert adapter.supports_model("gpt-4o") is False

    def test_supports_model_deepseek(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="deepseek",
        )
        assert adapter.supports_model("deepseek-chat") is True
        assert adapter.supports_model("deepseek-coder") is True
        assert adapter.supports_model("gpt-4o") is False

    def test_supports_model_mistral(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="mistral",
        )
        assert adapter.supports_model("mistral-large") is True
        assert adapter.supports_model("codestral-latest") is True
        assert adapter.supports_model("open-mistral-nemo") is True
        assert adapter.supports_model("open-mixtral-8x7b") is True
        assert adapter.supports_model("gpt-4o") is False

    def test_supports_model_unknown_provider(self) -> None:
        adapter = VercelGatewayProvider(
            gateway_url="https://ai-gateway.vercel.sh/v1",
            upstream_provider="unknown_provider",
        )
        assert adapter.supports_model("gpt-4o") is False
        assert adapter.supports_model("anything") is False


# ── Feature flag tests ────────────────────────────────────────────────


class TestFeatureFlag:
    """Test that the feature flag correctly enables/disables Vercel gateway."""

    def test_feature_flag_off_returns_direct_provider(self) -> None:
        """When USE_VERCEL_GATEWAY is not set, get_provider returns direct adapter."""
        env = {k: v for k, v in os.environ.items() if k != "USE_VERCEL_GATEWAY"}
        with patch.dict(os.environ, env, clear=True):
            # Re-import to trigger _init_vercel_gateway with fresh env
            import importlib
            import src.providers as providers_mod

            # Save original state
            orig_enabled = providers_mod._vercel_enabled
            orig_registry = providers_mod._vercel_registry.copy()

            try:
                providers_mod._vercel_enabled = False
                providers_mod._vercel_registry = {}

                provider = providers_mod.get_provider("openai")
                from src.providers.providers import OpenAIProvider
                assert isinstance(provider, OpenAIProvider)
                assert not providers_mod.is_vercel_gateway_enabled()
            finally:
                providers_mod._vercel_enabled = orig_enabled
                providers_mod._vercel_registry = orig_registry

    def test_feature_flag_on_returns_vercel_adapter(self) -> None:
        """When USE_VERCEL_GATEWAY=true, get_provider returns VercelGatewayProvider."""
        import src.providers as providers_mod

        # Save original state
        orig_enabled = providers_mod._vercel_enabled
        orig_registry = providers_mod._vercel_registry.copy()

        try:
            # Manually set up the Vercel registry
            providers_mod._vercel_enabled = True
            providers_mod._vercel_registry = {
                "openai": VercelGatewayProvider(
                    gateway_url="https://ai-gateway.vercel.sh/v1",
                    upstream_provider="openai",
                ),
            }

            provider = providers_mod.get_provider("openai")
            assert isinstance(provider, VercelGatewayProvider)
            assert provider.provider_name == "openai"
            assert providers_mod.is_vercel_gateway_enabled()
        finally:
            providers_mod._vercel_enabled = orig_enabled
            providers_mod._vercel_registry = orig_registry

    def test_feature_flag_on_falls_back_for_ollama(self) -> None:
        """Ollama should still use direct registry even when Vercel is enabled."""
        import src.providers as providers_mod
        from src.providers.providers import OllamaProvider

        orig_enabled = providers_mod._vercel_enabled
        orig_registry = providers_mod._vercel_registry.copy()

        try:
            providers_mod._vercel_enabled = True
            providers_mod._vercel_registry = {
                "openai": VercelGatewayProvider(
                    gateway_url="https://ai-gateway.vercel.sh/v1",
                    upstream_provider="openai",
                ),
            }

            # Register Ollama and verify it's not wrapped
            providers_mod.register_ollama("local", "http://localhost:11434")
            provider = providers_mod.get_provider("ollama:local")
            assert isinstance(provider, OllamaProvider)
        finally:
            providers_mod._vercel_enabled = orig_enabled
            providers_mod._vercel_registry = orig_registry
            # Clean up ollama registration
            providers_mod.PROVIDER_REGISTRY.pop("ollama:local", None)

    def test_get_provider_for_model_uses_vercel_when_enabled(self) -> None:
        """get_provider_for_model should return Vercel adapter when gateway enabled."""
        import src.providers as providers_mod

        orig_enabled = providers_mod._vercel_enabled
        orig_registry = providers_mod._vercel_registry.copy()

        try:
            providers_mod._vercel_enabled = True
            providers_mod._vercel_registry = {
                "openai": VercelGatewayProvider(
                    gateway_url="https://ai-gateway.vercel.sh/v1",
                    upstream_provider="openai",
                ),
                "anthropic": VercelGatewayProvider(
                    gateway_url="https://ai-gateway.vercel.sh/v1",
                    upstream_provider="anthropic",
                ),
            }

            provider = providers_mod.get_provider_for_model("gpt-4o")
            assert isinstance(provider, VercelGatewayProvider)
            assert provider.provider_name == "openai"

            provider = providers_mod.get_provider_for_model("claude-sonnet-4-6")
            assert isinstance(provider, VercelGatewayProvider)
            assert provider.provider_name == "anthropic"
        finally:
            providers_mod._vercel_enabled = orig_enabled
            providers_mod._vercel_registry = orig_registry

    def test_get_provider_for_model_uses_direct_when_disabled(self) -> None:
        """get_provider_for_model should return direct adapter when gateway disabled."""
        import src.providers as providers_mod
        from src.providers.providers import OpenAIProvider

        orig_enabled = providers_mod._vercel_enabled
        orig_registry = providers_mod._vercel_registry.copy()

        try:
            providers_mod._vercel_enabled = False
            providers_mod._vercel_registry = {}

            provider = providers_mod.get_provider_for_model("gpt-4o")
            assert isinstance(provider, OpenAIProvider)
        finally:
            providers_mod._vercel_enabled = orig_enabled
            providers_mod._vercel_registry = orig_registry


# ── Key resolver tests ────────────────────────────────────────────────


class TestKeyResolverVercel:
    """Test that key resolver uses Vercel token when gateway is enabled."""

    @pytest.mark.asyncio
    async def test_key_resolver_vercel_priority(self) -> None:
        """When gateway enabled, Vercel token should be returned even for openai."""
        from app.services.key_resolver import DBKeyResolver
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        # scalar_one_or_none() is sync on SQLAlchemy Result — use MagicMock for result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resolver = DBKeyResolver(mock_db)

        with patch.dict(os.environ, {
            "USE_VERCEL_GATEWAY": "true",
            "AI_GATEWAY_API_KEY": "vercel-test-token-123",
        }):
            key = await resolver.resolve("openai", org_id="00000000-0000-0000-0000-000000000001")
            assert key == "vercel-test-token-123"

    @pytest.mark.asyncio
    async def test_key_resolver_byok_still_wins(self) -> None:
        """BYOK key from database should still override Vercel token."""
        from app.services.key_resolver import DBKeyResolver
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        mock_pk = MagicMock()
        mock_pk.encrypted_key = "encrypted_byok_key"

        # scalar_one_or_none() is sync — use MagicMock for result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pk
        mock_db.execute.return_value = mock_result

        resolver = DBKeyResolver(mock_db)

        with patch.dict(os.environ, {
            "USE_VERCEL_GATEWAY": "true",
            "AI_GATEWAY_API_KEY": "vercel-test-token-123",
        }):
            with patch("app.services.key_resolver.decrypt_secret", return_value="my-byok-key"):
                key = await resolver.resolve("openai", org_id="00000000-0000-0000-0000-000000000001")
                assert key == "my-byok-key"

    @pytest.mark.asyncio
    async def test_key_resolver_falls_back_to_env_when_gateway_off(self) -> None:
        """Without gateway, resolver should use platform env var."""
        from app.services.key_resolver import DBKeyResolver
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        # scalar_one_or_none() is sync — use MagicMock for result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resolver = DBKeyResolver(mock_db)

        env = {k: v for k, v in os.environ.items()}
        env.pop("USE_VERCEL_GATEWAY", None)
        env["OPENAI_API_KEY"] = "sk-test-direct-key"

        with patch.dict(os.environ, env, clear=True):
            key = await resolver.resolve("openai", org_id="00000000-0000-0000-0000-000000000001")
            assert key == "sk-test-direct-key"
