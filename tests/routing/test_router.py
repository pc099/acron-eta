"""
Tests for the routing engine.
"""

import pytest

from src.exceptions import NoModelsAvailableError
from src.models.registry import ModelProfile, ModelRegistry
from src.routing.constraints import RoutingConstraints, RoutingDecision
from src.routing.router import Router


@pytest.fixture
def registry() -> ModelRegistry:
    """Create a registry with default models."""
    return ModelRegistry()


@pytest.fixture
def router(registry: ModelRegistry) -> Router:
    """Create a router with the default registry."""
    return Router(registry)


# ---------------------------------------------------------------------------
# RoutingConstraints
# ---------------------------------------------------------------------------


class TestRoutingConstraints:
    """Tests for RoutingConstraints Pydantic model."""

    def test_defaults(self) -> None:
        c = RoutingConstraints()
        assert c.quality_threshold == 3.5
        assert c.latency_budget_ms == 300
        assert c.cost_budget is None

    def test_custom_values(self) -> None:
        c = RoutingConstraints(
            quality_threshold=4.5,
            latency_budget_ms=500,
            cost_budget=0.05,
        )
        assert c.quality_threshold == 4.5
        assert c.latency_budget_ms == 500
        assert c.cost_budget == 0.05


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestRouterSelectModel:
    """Tests for Router.select_model."""

    def test_returns_routing_decision(self, router: Router) -> None:
        decision = router.select_model(RoutingConstraints())
        assert isinstance(decision, RoutingDecision)
        assert decision.model_name != ""
        assert decision.candidates_evaluated > 0

    def test_selects_best_value_model(self, router: Router) -> None:
        decision = router.select_model(
            RoutingConstraints(quality_threshold=3.5, latency_budget_ms=300)
        )
        # With quality/cost scoring, the cheapest high-quality model should win
        # claude-3-5-sonnet has quality 4.1 and low cost, great value
        assert decision.model_name in [
            "gpt-4-turbo",
            "claude-opus-4",
            "claude-3-5-sonnet",
        ]
        assert decision.fallback_used is False

    def test_high_quality_threshold_narrows_candidates(
        self, router: Router
    ) -> None:
        decision = router.select_model(
            RoutingConstraints(quality_threshold=4.5, latency_budget_ms=300)
        )
        # Only gpt-4-turbo (4.6) and claude-opus-4 (4.5) qualify
        assert decision.model_name in ["gpt-4-turbo", "claude-opus-4"]

    def test_tight_latency_filters_slow_models(self, router: Router) -> None:
        decision = router.select_model(
            RoutingConstraints(quality_threshold=3.0, latency_budget_ms=160)
        )
        # Only claude-3-5-sonnet (150ms) fits
        assert decision.model_name == "claude-3-5-sonnet"

    def test_impossible_constraints_trigger_fallback(
        self, router: Router
    ) -> None:
        decision = router.select_model(
            RoutingConstraints(quality_threshold=5.0, latency_budget_ms=10)
        )
        assert decision.fallback_used is True
        assert "Fallback" in decision.reason

    def test_fallback_selects_highest_quality(self, router: Router) -> None:
        decision = router.select_model(
            RoutingConstraints(quality_threshold=5.0, latency_budget_ms=1)
        )
        assert decision.model_name == "gpt-4-turbo"  # quality 4.6 is highest

    def test_cost_budget_filter(self, router: Router) -> None:
        decision = router.select_model(
            RoutingConstraints(
                quality_threshold=3.0,
                latency_budget_ms=9999,
                cost_budget=0.001,  # very tight budget
            )
        )
        # Should either find a cheap model or fallback
        assert decision.model_name is not None

    def test_empty_registry_raises(self) -> None:
        empty_registry = ModelRegistry.__new__(ModelRegistry)
        empty_registry._models = {}
        router = Router(empty_registry)
        with pytest.raises(NoModelsAvailableError):
            router.select_model(RoutingConstraints())

    def test_single_model_registry(self) -> None:
        registry = ModelRegistry.__new__(ModelRegistry)
        registry._models = {}
        registry.add(
            ModelProfile(
                name="only-model",
                provider="openai",
                api_key_env="KEY",
                cost_per_1k_input_tokens=0.01,
                cost_per_1k_output_tokens=0.03,
                avg_latency_ms=200,
                quality_score=4.0,
                max_input_tokens=128000,
                max_output_tokens=4096,
            )
        )
        router = Router(registry)
        decision = router.select_model(RoutingConstraints())
        assert decision.model_name == "only-model"

    def test_score_is_positive(self, router: Router) -> None:
        decision = router.select_model(RoutingConstraints())
        if not decision.fallback_used:
            assert decision.score > 0

    def test_reason_is_descriptive(self, router: Router) -> None:
        decision = router.select_model(RoutingConstraints())
        assert len(decision.reason) > 10
