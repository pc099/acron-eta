"""
Tests for the core InferenceOptimizer.

Includes unit tests, baseline vs optimized comparison, and integration tests.
"""

import json
import os
import pytest
from src.optimizer import InferenceOptimizer
from src.models import MODELS


@pytest.fixture
def optimizer():
    return InferenceOptimizer(use_mock=True)


class TestInferBasic:
    def test_returns_expected_fields(self, optimizer):
        result = optimizer.infer(prompt="What is Python?", task_id="t1")
        assert "response" in result
        assert "model_used" in result
        assert "cost" in result
        assert "latency_ms" in result
        assert "cache_hit" in result
        assert "tokens_input" in result
        assert "tokens_output" in result
        assert "tokens_total" in result
        assert "routing_reason" in result
        assert "timestamp" in result

    def test_cost_is_positive(self, optimizer):
        result = optimizer.infer(prompt="Hello world", task_id="t2")
        assert result["cost"] > 0

    def test_model_used_is_valid(self, optimizer):
        result = optimizer.infer(prompt="Test prompt", task_id="t3")
        assert result["model_used"] in MODELS

    def test_token_counts_are_positive(self, optimizer):
        result = optimizer.infer(prompt="Explain machine learning", task_id="t4")
        assert result["tokens_input"] > 0
        assert result["tokens_output"] > 0
        assert result["tokens_total"] == result["tokens_input"] + result["tokens_output"]

    def test_empty_prompt_returns_error(self, optimizer):
        result = optimizer.infer(prompt="", task_id="t5")
        assert result.get("error") == "Empty prompt"
        assert result["cost"] == 0

    def test_whitespace_prompt_returns_error(self, optimizer):
        result = optimizer.infer(prompt="   ", task_id="t6")
        assert result.get("error") == "Empty prompt"


class TestCaching:
    def test_second_call_is_cache_hit(self, optimizer):
        prompt = "What is the speed of light?"
        r1 = optimizer.infer(prompt=prompt, task_id="c1")
        r2 = optimizer.infer(prompt=prompt, task_id="c2")
        assert r1["cache_hit"] is False
        assert r2["cache_hit"] is True

    def test_different_prompts_are_cache_miss(self, optimizer):
        r1 = optimizer.infer(prompt="Question A", task_id="c3")
        r2 = optimizer.infer(prompt="Question B", task_id="c4")
        assert r1["cache_hit"] is False
        assert r2["cache_hit"] is False

    def test_cache_hit_preserves_response(self, optimizer):
        prompt = "Explain gravity"
        r1 = optimizer.infer(prompt=prompt, task_id="c5")
        r2 = optimizer.infer(prompt=prompt, task_id="c6")
        assert r2["response"] == r1["response"]
        assert r2["model_used"] == r1["model_used"]


class TestForceModel:
    def test_force_gpt4(self, optimizer):
        result = optimizer.infer(
            prompt="Test", task_id="f1", force_model="gpt-4-turbo"
        )
        assert result["model_used"] == "gpt-4-turbo"

    def test_force_sonnet(self, optimizer):
        result = optimizer.infer(
            prompt="Test", task_id="f2", force_model="claude-3-5-sonnet-20241022"
        )
        assert result["model_used"] == "claude-3-5-sonnet-20241022"

    def test_force_unknown_model_falls_back_to_routing(self, optimizer):
        result = optimizer.infer(
            prompt="Test", task_id="f3", force_model="nonexistent-model"
        )
        assert result["model_used"] in MODELS


class TestRouting:
    def test_low_quality_threshold_routes_to_cheapest(self, optimizer):
        result = optimizer.infer(
            prompt="Simple question",
            task_id="r1",
            quality_threshold=3.0,
            latency_budget_ms=9999,
        )
        assert result["model_used"] == "claude-3-5-sonnet-20241022"

    def test_high_quality_threshold_routes_to_premium(self, optimizer):
        result = optimizer.infer(
            prompt="Complex reasoning task",
            task_id="r2",
            quality_threshold=4.5,
            latency_budget_ms=9999,
        )
        assert result["model_used"] in ["gpt-4-turbo", "claude-opus-4"]


class TestMetrics:
    def test_metrics_after_inferences(self, optimizer):
        optimizer.infer(prompt="Q1", task_id="m1")
        optimizer.infer(prompt="Q2", task_id="m2")
        optimizer.infer(prompt="Q1", task_id="m3")  # cache hit

        metrics = optimizer.get_metrics()
        assert metrics["requests"] == 3
        assert metrics["total_cost"] > 0
        assert metrics["cache_hit_rate"] > 0


class TestBaselineVsOptimized:
    """Integration test: run baseline and optimized scenarios and compare."""

    def test_optimized_is_cheaper_than_baseline(self):
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

        # Baseline: all GPT-4
        baseline = InferenceOptimizer(use_mock=True)
        for i, q in enumerate(queries):
            baseline.infer(prompt=q, task_id=f"base_{i}", force_model="gpt-4-turbo")
        baseline_cost = baseline.get_metrics()["total_cost"]

        # Optimized: smart routing
        optimized = InferenceOptimizer(use_mock=True)
        for i, q in enumerate(queries):
            optimized.infer(
                prompt=q,
                task_id=f"opt_{i}",
                latency_budget_ms=300,
                quality_threshold=3.5,
            )
        optimized_cost = optimized.get_metrics()["total_cost"]

        assert optimized_cost < baseline_cost, (
            f"Optimized (${optimized_cost:.4f}) should be cheaper than "
            f"baseline (${baseline_cost:.4f})"
        )

    def test_savings_exceed_50_percent(self):
        """Validate the 50% savings target using the full test dataset if available."""
        queries_path = os.path.join("data", "test_queries.json")
        if not os.path.exists(queries_path):
            pytest.skip("data/test_queries.json not found")

        with open(queries_path) as f:
            queries = json.load(f)

        test_queries = queries[:50]

        # Baseline
        baseline = InferenceOptimizer(use_mock=True)
        for q in test_queries:
            baseline.infer(
                prompt=q["text"],
                task_id=f"base_{q['id']}",
                force_model="gpt-4-turbo",
            )
        b_metrics = baseline.get_metrics()

        # Optimized
        optimized = InferenceOptimizer(use_mock=True)
        for q in test_queries:
            optimized.infer(
                prompt=q["text"],
                task_id=f"opt_{q['id']}",
                latency_budget_ms=300,
                quality_threshold=3.5,
            )
        o_metrics = optimized.get_metrics()

        savings_pct = o_metrics.get("estimated_savings_vs_gpt4", 0)
        assert savings_pct >= 50, (
            f"Expected >=50% savings, got {savings_pct:.1f}%"
        )
