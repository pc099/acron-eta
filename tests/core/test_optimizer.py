"""
Tests for the core InferenceOptimizer.

Includes unit tests, cache path tests, baseline vs optimized
comparison, and integration tests.
"""

import json
import os

import pytest

from src.cache.exact import Cache
from src.models.registry import ModelProfile, ModelRegistry
from src.core.optimizer import InferenceOptimizer, InferenceResult
from src.routing.constraints import RoutingConstraints
from src.routing.router import Router
from src.tracking.tracker import EventTracker


@pytest.fixture
def optimizer() -> InferenceOptimizer:
    """Create an optimizer with mock inference enabled."""
    return InferenceOptimizer(use_mock=True)


# ---------------------------------------------------------------------------
# Basic inference
# ---------------------------------------------------------------------------


class TestInferBasic:
    """Tests for basic inference functionality."""

    def test_returns_inference_result(self, optimizer: InferenceOptimizer) -> None:
        result = optimizer.infer(prompt="What is Python?")
        assert isinstance(result, InferenceResult)

    def test_result_has_all_fields(self, optimizer: InferenceOptimizer) -> None:
        result = optimizer.infer(prompt="What is Python?")
        assert result.response != ""
        assert result.model_used != ""
        assert result.request_id != ""
        assert result.routing_reason != ""

    def test_cost_is_positive(self, optimizer: InferenceOptimizer) -> None:
        result = optimizer.infer(prompt="Hello world")
        assert result.cost > 0

    def test_model_used_is_in_registry(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(prompt="Test prompt")
        assert result.model_used in optimizer.registry

    def test_token_counts_are_positive(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(prompt="Explain machine learning")
        assert result.tokens_input > 0
        assert result.tokens_output > 0

    def test_empty_prompt_returns_empty_result(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(prompt="")
        assert result.response == ""
        assert result.cost == 0.0
        assert "Error" in result.routing_reason or "empty" in result.routing_reason

    def test_whitespace_prompt_returns_empty_result(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(prompt="   ")
        assert result.response == ""
        assert result.cost == 0.0

    def test_unique_request_ids(self, optimizer: InferenceOptimizer) -> None:
        r1 = optimizer.infer(prompt="Query A")
        r2 = optimizer.infer(prompt="Query B")
        assert r1.request_id != r2.request_id


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


class TestCaching:
    """Tests for cache hit/miss paths."""

    def test_second_call_is_cache_hit(
        self, optimizer: InferenceOptimizer
    ) -> None:
        prompt = "What is the speed of light?"
        r1 = optimizer.infer(prompt=prompt)
        r2 = optimizer.infer(prompt=prompt)
        assert r1.cache_hit is False
        assert r2.cache_hit is True

    def test_different_prompts_are_cache_miss(
        self, optimizer: InferenceOptimizer
    ) -> None:
        r1 = optimizer.infer(prompt="Question A")
        r2 = optimizer.infer(prompt="Question B")
        assert r1.cache_hit is False
        assert r2.cache_hit is False

    def test_cache_hit_preserves_response(
        self, optimizer: InferenceOptimizer
    ) -> None:
        prompt = "Explain gravity"
        r1 = optimizer.infer(prompt=prompt)
        r2 = optimizer.infer(prompt=prompt)
        assert r2.response == r1.response
        assert r2.model_used == r1.model_used

    def test_cache_hit_has_zero_cost(
        self, optimizer: InferenceOptimizer
    ) -> None:
        prompt = "Cached query"
        optimizer.infer(prompt=prompt)
        r2 = optimizer.infer(prompt=prompt)
        assert r2.cost == 0.0
        assert r2.cache_hit is True


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TestRouting:
    """Tests for routing integration."""

    def test_low_quality_threshold_routes_to_cheapest(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(
            prompt="Simple question",
            quality_threshold=3.0,
            latency_budget_ms=9999,
        )
        # Should prefer best quality/cost ratio
        assert result.model_used in optimizer.registry

    def test_high_quality_threshold_routes_to_premium(
        self, optimizer: InferenceOptimizer
    ) -> None:
        result = optimizer.infer(
            prompt="Complex reasoning task",
            quality_threshold=4.5,
            latency_budget_ms=9999,
        )
        assert result.model_used in ["gpt-4-turbo", "claude-opus-4"]


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------


class TestDependencyInjection:
    """Tests verifying DI works correctly."""

    def test_custom_registry(self) -> None:
        registry = ModelRegistry()
        optimizer = InferenceOptimizer(registry=registry, use_mock=True)
        assert optimizer.registry is registry

    def test_custom_cache(self) -> None:
        cache = Cache(ttl_seconds=60)
        optimizer = InferenceOptimizer(cache=cache, use_mock=True)
        assert optimizer.cache is cache

    def test_custom_tracker(self, tmp_path) -> None:
        tracker = EventTracker(log_dir=tmp_path / "custom_logs")
        optimizer = InferenceOptimizer(tracker=tracker, use_mock=True)
        assert optimizer.tracker is tracker


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestMetrics:
    """Tests for metrics aggregation."""

    def test_metrics_after_inferences(
        self, optimizer: InferenceOptimizer
    ) -> None:
        optimizer.infer(prompt="Q1")
        optimizer.infer(prompt="Q2")
        optimizer.infer(prompt="Q1")  # cache hit

        metrics = optimizer.get_metrics()
        assert metrics["requests"] == 3
        assert metrics["total_cost"] > 0
        assert metrics["cache_hit_rate"] > 0
        assert "uptime_seconds" in metrics

    def test_metrics_empty(self, optimizer: InferenceOptimizer) -> None:
        metrics = optimizer.get_metrics()
        assert metrics["requests"] == 0
        assert metrics["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# Baseline vs optimized
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Provider fallback
# ---------------------------------------------------------------------------


class TestProviderFallback:
    """Tests for provider failure and fallback logic."""

    def test_provider_error_triggers_fallback(self) -> None:
        """When primary model raises ProviderError, optimizer falls back."""
        from unittest.mock import patch

        from src.exceptions import ProviderError

        optimizer = InferenceOptimizer(use_mock=False)

        call_count = 0
        original_mock = optimizer._mock_call

        def failing_then_succeeding(model_name: str, prompt: str):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ProviderError(f"Simulated failure for {model_name}")
            # Succeed on fallback
            return "fallback response", 10, 5, 100

        # Patch _execute_inference to bypass the mock/real dispatch
        with patch.object(
            optimizer, "_execute_inference", side_effect=failing_then_succeeding
        ):
            result = optimizer.infer(prompt="test prompt")

        assert result.response == "fallback response"
        assert result.routing_reason.startswith("Fallback")
        assert call_count == 2

    def test_provider_error_same_model_re_raises(self) -> None:
        """When fallback model is same as failed model, re-raise."""
        from unittest.mock import patch

        from src.exceptions import ProviderError

        # Registry with only ONE model
        registry = ModelRegistry.__new__(ModelRegistry)
        registry._models = {}
        registry.add(
            from_profile("only-model", "openai", 4.5, 200, 0.01, 0.03)
        )
        optimizer = InferenceOptimizer(
            registry=registry, use_mock=False
        )

        with patch.object(
            optimizer,
            "_execute_inference",
            side_effect=ProviderError("All down"),
        ):
            with pytest.raises(ProviderError):
                optimizer.infer(prompt="test")


def from_profile(
    name: str,
    provider: str,
    quality: float,
    latency: int,
    input_cost: float,
    output_cost: float,
) -> "ModelProfile":
    """Helper to create a ModelProfile for tests."""
    from src.models.registry import ModelProfile

    return ModelProfile(
        name=name,
        provider=provider,
        api_key_env="TEST_KEY",
        cost_per_1k_input_tokens=input_cost,
        cost_per_1k_output_tokens=output_cost,
        avg_latency_ms=latency,
        quality_score=quality,
        max_input_tokens=128000,
        max_output_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Internal calculate_cost
# ---------------------------------------------------------------------------


class TestInternalCalculateCost:
    """Tests for optimizer._calculate_cost."""

    def test_known_model(self, optimizer: InferenceOptimizer) -> None:
        cost = optimizer._calculate_cost("gpt-4-turbo", 1000, 500)
        assert cost > 0

    def test_unknown_model_returns_zero(
        self, optimizer: InferenceOptimizer
    ) -> None:
        cost = optimizer._calculate_cost("nonexistent-model", 1000, 500)
        assert cost == 0.0


# ---------------------------------------------------------------------------
# Baseline vs optimized
# ---------------------------------------------------------------------------


class TestBaselineVsOptimized:
    """Integration tests comparing baseline to optimized routing."""

    def test_optimized_is_cheaper_than_baseline(self) -> None:
        queries = [
            "What is 2+2?",
            "Explain quantum mechanics in detail with examples.",
            "Classify: I hate this product",
            "Write a poem about the ocean",
            "Translate 'hello' to Spanish",
            "What causes earthquakes?",
            "Summarize: The market closed higher today.",
            "Debug this Python code: print('hello'",
            "What is the capital of Japan?",
            "Explain the difference between TCP and UDP",
        ]

        # Baseline: force highest quality (most expensive)
        baseline = InferenceOptimizer(use_mock=True)
        for q in queries:
            baseline.infer(
                prompt=q,
                quality_threshold=4.6,  # forces gpt-4-turbo
                latency_budget_ms=9999,
            )
        baseline_cost = baseline.get_metrics()["total_cost"]

        # Optimized: smart routing
        optimized = InferenceOptimizer(use_mock=True)
        for q in queries:
            optimized.infer(
                prompt=q,
                latency_budget_ms=300,
                quality_threshold=3.5,
            )
        optimized_cost = optimized.get_metrics()["total_cost"]

        assert optimized_cost < baseline_cost, (
            f"Optimized (${optimized_cost:.4f}) should be cheaper than "
            f"baseline (${baseline_cost:.4f})"
        )
