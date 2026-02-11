"""Tests for FeatureEnricher -- task-aware context injection."""

from typing import Any, Dict, List

import pytest

from src.features.client import LocalFeatureStore
from src.features.enricher import (
    EnricherConfig,
    EnrichmentResult,
    FeatureEnricher,
    TASK_FEATURE_MAP,
)


@pytest.fixture
def store() -> LocalFeatureStore:
    """Pre-loaded local feature store."""
    store = LocalFeatureStore()
    store.add_entity("user", "user-1", {
        "purchase_history": ["shoes", "jacket", "belt"],
        "preferences": "casual athletic",
        "preference_score": 0.8,
        "tier": "gold",
        "domain_expertise": "intermediate",
        "language_preferences": ["python", "typescript"],
        "recent_tickets": ["TICK-100", "TICK-101"],
        "products_owned": ["Pro Plan"],
    })
    store.add_entity("organization", "org-1", {
        "brand_voice": "professional",
        "industry": "fintech",
        "tone": "formal",
    })
    return store


@pytest.fixture
def enricher(store: LocalFeatureStore) -> FeatureEnricher:
    config = EnricherConfig(max_feature_tokens=200)
    return FeatureEnricher(client=store, config=config)


class TestEnricherConfig:
    """Tests for EnricherConfig."""

    def test_defaults(self) -> None:
        cfg = EnricherConfig()
        assert cfg.max_feature_tokens == 200
        assert cfg.freshness_threshold_seconds == 3600
        assert "general" in cfg.enabled_task_types

    def test_custom(self) -> None:
        cfg = EnricherConfig(max_feature_tokens=100, freshness_threshold_seconds=60)
        assert cfg.max_feature_tokens == 100


class TestEnrichmentResult:
    """Tests for EnrichmentResult model."""

    def test_creation(self) -> None:
        r = EnrichmentResult(
            original_prompt="hello",
            enriched_prompt="[Context]\nhello",
            features_used=["tier"],
            feature_tokens_added=5,
            enrichment_latency_ms=1.0,
            features_available=True,
        )
        assert r.features_available is True
        assert r.feature_tokens_added == 5


class TestFeatureEnricher:
    """Tests for FeatureEnricher.enrich()."""

    def test_enrich_with_user_features(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="Recommend a product",
            user_id="user-1",
            task_type="general",
        )
        assert result.features_available is True
        assert len(result.features_used) > 0
        assert "[Context from user profile]" in result.enriched_prompt
        assert "Recommend a product" in result.enriched_prompt

    def test_enrich_with_org_features(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="Write a blog post",
            organization_id="org-1",
            task_type="general",
        )
        assert result.features_available is True
        assert "Brand Voice" in result.enriched_prompt

    def test_enrich_with_both_entities(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="Help me",
            user_id="user-1",
            organization_id="org-1",
            task_type="general",
        )
        assert result.features_available is True
        assert len(result.features_used) >= 2

    def test_enrich_missing_user(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="Hello",
            user_id="nonexistent",
            task_type="general",
        )
        # No features found => enrichment result should reflect no enrichment
        assert result.features_available is False
        assert result.enriched_prompt == "Hello"

    def test_enrich_no_entity_ids(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(prompt="Just a query", task_type="general")
        assert result.features_available is False
        assert result.enriched_prompt == "Just a query"

    def test_enrich_disabled_task_type(self, enricher: FeatureEnricher) -> None:
        # Use a task type not in the enabled list
        config = EnricherConfig(enabled_task_types=["recommendation"])
        restricted = FeatureEnricher(
            client=enricher._client, config=config
        )
        result = restricted.enrich(
            prompt="Hello",
            user_id="user-1",
            task_type="coding",
        )
        assert result.features_available is False
        assert result.enriched_prompt == "Hello"

    def test_token_limit_respected(self, store: LocalFeatureStore) -> None:
        config = EnricherConfig(max_feature_tokens=10)  # very tight
        enricher = FeatureEnricher(client=store, config=config)
        result = enricher.enrich(
            prompt="Query",
            user_id="user-1",
            task_type="general",
        )
        # The enrichment should still work, but with fewer features
        assert result.feature_tokens_added <= 15  # allow small margin

    def test_stale_features_rejected(self, store: LocalFeatureStore) -> None:
        config = EnricherConfig(freshness_threshold_seconds=0)
        enricher = FeatureEnricher(client=store, config=config)
        # Features just added will have freshness > 0 seconds
        # With threshold 0, they should be rejected
        result = enricher.enrich(
            prompt="Query",
            user_id="user-1",
            task_type="general",
        )
        assert result.features_available is False

    def test_prompt_format(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="What should I buy?",
            user_id="user-1",
            task_type="general",
        )
        assert result.enriched_prompt.startswith("[Context from user profile]")
        assert "[End context]" in result.enriched_prompt
        assert result.enriched_prompt.endswith("What should I buy?")

    def test_enrichment_latency_recorded(self, enricher: FeatureEnricher) -> None:
        result = enricher.enrich(
            prompt="test", user_id="user-1", task_type="general"
        )
        assert result.enrichment_latency_ms >= 0.0


class TestGetRelevantFeatures:
    """Tests for task-feature mapping."""

    @pytest.fixture
    def enricher(self) -> FeatureEnricher:
        store = LocalFeatureStore()
        return FeatureEnricher(client=store)

    def test_recommendation_user_features(self, enricher: FeatureEnricher) -> None:
        features = enricher.get_relevant_features("recommendation", "user")
        assert "purchase_history" in features
        assert "preferences" in features

    def test_support_user_features(self, enricher: FeatureEnricher) -> None:
        features = enricher.get_relevant_features("support", "user")
        assert "tier" in features
        assert "recent_tickets" in features

    def test_coding_user_features(self, enricher: FeatureEnricher) -> None:
        features = enricher.get_relevant_features("coding", "user")
        assert "language_preferences" in features

    def test_unknown_task_falls_back_to_general(
        self, enricher: FeatureEnricher
    ) -> None:
        features = enricher.get_relevant_features("unknown_task", "user")
        # Should fall back to general
        assert "preferences" in features

    def test_unknown_entity_type_returns_empty(
        self, enricher: FeatureEnricher
    ) -> None:
        features = enricher.get_relevant_features("general", "widget")
        assert features == []


class TestFeatureEnricherErrorHandling:
    """Tests for graceful degradation on feature store errors."""

    def test_client_error_returns_unenriched(self) -> None:
        """If the client raises, enrichment degrades gracefully."""

        class FailingClient:
            def get_features(
                self, entity_id: str, entity_type: str, feature_names: list
            ) -> None:
                raise RuntimeError("Store down!")

            def get_batch_features(
                self, ids: list, entity_type: str, feature_names: list
            ) -> list:
                return []

            def health_check(self) -> bool:
                return False

        enricher = FeatureEnricher(client=FailingClient())  # type: ignore[arg-type]
        result = enricher.enrich(
            prompt="Hello",
            user_id="user-1",
            task_type="general",
        )
        assert result.features_available is False
        assert result.enriched_prompt == "Hello"
