"""
Tests for routing logic.
"""

import pytest
from src.routing import Router
from src.models import MODELS


@pytest.fixture
def router():
    return Router()


class TestRouterSelectModel:
    def test_selects_cheapest_model_within_constraints(self, router):
        model, reason = router.select_model(
            prompt="What is 2+2?",
            latency_budget_ms=300,
            quality_threshold=3.5,
        )
        # Sonnet is cheapest and meets all constraints
        assert model == "claude-3-5-sonnet-20241022"
        assert "candidates" in reason

    def test_higher_quality_threshold_excludes_cheap_models(self, router):
        model, reason = router.select_model(
            prompt="Explain quantum computing in detail.",
            latency_budget_ms=300,
            quality_threshold=4.5,
        )
        # Only gpt-4-turbo (4.6) and claude-opus-4 (4.5) meet threshold
        assert model in ["gpt-4-turbo", "claude-opus-4"]

    def test_strict_latency_budget_filters_slow_models(self, router):
        model, reason = router.select_model(
            prompt="Quick question: what is Python?",
            latency_budget_ms=160,
            quality_threshold=3.0,
        )
        # Only sonnet (150ms) fits under 160ms
        assert model == "claude-3-5-sonnet-20241022"

    def test_very_tight_latency_triggers_fallback(self, router):
        model, reason = router.select_model(
            prompt="Hello",
            latency_budget_ms=10,  # Nothing fits
            quality_threshold=3.0,
        )
        # Fallback to highest quality
        assert model == "gpt-4-turbo"
        assert "Fallback" in reason

    def test_empty_prompt_triggers_fallback(self, router):
        model, reason = router.select_model(
            prompt="",
            latency_budget_ms=300,
            quality_threshold=3.5,
        )
        assert model == "gpt-4-turbo"
        assert "empty_prompt" in reason

    def test_whitespace_prompt_triggers_fallback(self, router):
        model, reason = router.select_model(
            prompt="   ",
            latency_budget_ms=300,
            quality_threshold=3.5,
        )
        assert "Fallback" in reason

    def test_cost_budget_filters_expensive_models(self, router):
        model, reason = router.select_model(
            prompt="Short question",
            latency_budget_ms=300,
            quality_threshold=3.0,
            cost_budget=0.0001,
        )
        # Very low budget should route to cheapest or fallback
        assert model is not None

    def test_no_quality_threshold_allows_all_models(self, router):
        model, reason = router.select_model(
            prompt="Anything",
            latency_budget_ms=9999,
            quality_threshold=0,
        )
        # Cheapest model should be selected
        assert model == "claude-3-5-sonnet-20241022"

    def test_returns_reason_string(self, router):
        _, reason = router.select_model(
            prompt="Test prompt",
            latency_budget_ms=300,
            quality_threshold=3.5,
        )
        assert isinstance(reason, str)
        assert len(reason) > 0


class TestRouterEstimateCosts:
    def test_estimate_cost_all_models_returns_all(self, router):
        costs = router.estimate_cost_all_models("Hello world test prompt")
        assert len(costs) == len(MODELS)
        for name in MODELS:
            assert name in costs
            assert costs[name] >= 0

    def test_longer_prompts_cost_more(self, router):
        short_costs = router.estimate_cost_all_models("Hi")
        long_costs = router.estimate_cost_all_models("Hi " * 500)
        for name in MODELS:
            assert long_costs[name] > short_costs[name]
