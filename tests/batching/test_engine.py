"""Tests for BatchEngine -- request batching eligibility."""

import pytest

from src.batching.engine import BatchConfig, BatchEligibility, BatchEngine
from src.exceptions import BatchingError
from src.models.registry import ModelProfile, ModelRegistry


class TestBatchConfig:
    """Tests for BatchConfig defaults and validation."""

    def test_default_values(self) -> None:
        cfg = BatchConfig()
        assert cfg.min_batch_size == 2
        assert cfg.max_batch_size == 10
        assert cfg.max_wait_ms == 500
        assert cfg.latency_threshold_ms == 200
        assert cfg.eligible_task_types == ["summarization", "faq", "translation"]

    def test_custom_values(self) -> None:
        cfg = BatchConfig(
            min_batch_size=3,
            max_batch_size=20,
            max_wait_ms=1000,
            latency_threshold_ms=100,
            eligible_task_types=["summarization", "coding"],
        )
        assert cfg.min_batch_size == 3
        assert cfg.max_batch_size == 20
        assert cfg.max_wait_ms == 1000
        assert cfg.latency_threshold_ms == 100
        assert cfg.eligible_task_types == ["summarization", "coding"]


class TestBatchEligibility:
    """Tests for BatchEligibility model."""

    def test_eligible_result(self) -> None:
        result = BatchEligibility(
            eligible=True,
            reason="OK",
            batch_group="faq:sonnet",
            max_wait_ms=300,
        )
        assert result.eligible is True
        assert result.batch_group == "faq:sonnet"
        assert result.max_wait_ms == 300

    def test_ineligible_result_defaults(self) -> None:
        result = BatchEligibility(eligible=False, reason="too fast")
        assert result.eligible is False
        assert result.batch_group is None
        assert result.max_wait_ms == 0


class TestBatchEngine:
    """Tests for BatchEngine eligibility evaluation."""

    @pytest.fixture
    def registry(self) -> ModelRegistry:
        """Model registry with a single test model."""
        reg = ModelRegistry(config_path=None)
        # Registry already has defaults loaded
        return reg

    @pytest.fixture
    def config(self) -> BatchConfig:
        return BatchConfig(
            max_batch_size=10,
            max_wait_ms=500,
            latency_threshold_ms=200,
            eligible_task_types=["summarization", "faq", "translation"],
        )

    @pytest.fixture
    def engine(self, config: BatchConfig, registry: ModelRegistry) -> BatchEngine:
        return BatchEngine(config=config, model_registry=registry)

    @pytest.fixture
    def engine_no_registry(self, config: BatchConfig) -> BatchEngine:
        return BatchEngine(config=config, model_registry=None)

    # ------------------------------------------------------------------
    # Eligible requests
    # ------------------------------------------------------------------

    def test_eligible_summarization(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Summarize this short text",
            task_type="summarization",
            model="claude-3-5-sonnet",
            latency_budget_ms=1000,
        )
        assert result.eligible is True
        assert result.batch_group == "summarization:claude-3-5-sonnet"
        assert result.max_wait_ms > 0

    def test_eligible_faq(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="What is machine learning?",
            task_type="faq",
            model="claude-3-5-sonnet",
            latency_budget_ms=800,
        )
        assert result.eligible is True
        assert result.batch_group == "faq:claude-3-5-sonnet"

    def test_eligible_translation(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Translate hello to French",
            task_type="translation",
            model="gpt-4-turbo",
            latency_budget_ms=600,
        )
        assert result.eligible is True
        assert result.batch_group == "translation:gpt-4-turbo"

    def test_eligible_max_wait_capped(self, engine: BatchEngine) -> None:
        """Max wait should not exceed config.max_wait_ms."""
        result = engine.evaluate(
            prompt="Short question",
            task_type="faq",
            model="claude-3-5-sonnet",
            latency_budget_ms=10000,
        )
        assert result.eligible is True
        assert result.max_wait_ms <= 500  # config max

    # ------------------------------------------------------------------
    # Ineligible: latency too tight
    # ------------------------------------------------------------------

    def test_ineligible_tight_latency(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Quick answer",
            task_type="faq",
            model="claude-3-5-sonnet",
            latency_budget_ms=100,
        )
        assert result.eligible is False
        assert "latency" in result.reason.lower()

    def test_ineligible_exact_threshold(self, engine: BatchEngine) -> None:
        """Latency budget exactly at threshold should be ineligible."""
        result = engine.evaluate(
            prompt="Quick answer",
            task_type="faq",
            model="claude-3-5-sonnet",
            latency_budget_ms=199,
        )
        assert result.eligible is False

    # ------------------------------------------------------------------
    # Ineligible: wrong task type
    # ------------------------------------------------------------------

    def test_ineligible_coding_task(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Write a function that adds two numbers",
            task_type="coding",
            model="claude-3-5-sonnet",
            latency_budget_ms=1000,
        )
        assert result.eligible is False
        assert "task type" in result.reason.lower()

    def test_ineligible_reasoning_task(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Explain quantum computing",
            task_type="reasoning",
            model="claude-3-5-sonnet",
            latency_budget_ms=1000,
        )
        assert result.eligible is False

    # ------------------------------------------------------------------
    # Ineligible: token limit
    # ------------------------------------------------------------------

    def test_ineligible_prompt_too_large(self, engine: BatchEngine) -> None:
        """A prompt whose tokens exceed model_max_input / max_batch_size."""
        # claude-3-5-sonnet has max_input_tokens=200000
        # per-request limit = 200000 / 10 = 20000 tokens
        # Need a prompt that estimates to >20000 tokens
        huge_prompt = " ".join(["word"] * 20000)  # ~26000 tokens
        result = engine.evaluate(
            prompt=huge_prompt,
            task_type="summarization",
            model="claude-3-5-sonnet",
            latency_budget_ms=5000,
        )
        assert result.eligible is False
        assert "token" in result.reason.lower()

    # ------------------------------------------------------------------
    # Batch group assignment
    # ------------------------------------------------------------------

    def test_batch_group_format(self, engine: BatchEngine) -> None:
        result = engine.evaluate(
            prompt="Summarize this",
            task_type="summarization",
            model="gpt-4-turbo",
            latency_budget_ms=1000,
        )
        assert result.batch_group == "summarization:gpt-4-turbo"

    def test_different_models_different_groups(self, engine: BatchEngine) -> None:
        r1 = engine.evaluate("text", "faq", "gpt-4-turbo", 1000)
        r2 = engine.evaluate("text", "faq", "claude-3-5-sonnet", 1000)
        assert r1.batch_group != r2.batch_group

    def test_different_tasks_different_groups(self, engine: BatchEngine) -> None:
        r1 = engine.evaluate("text", "faq", "claude-3-5-sonnet", 1000)
        r2 = engine.evaluate("text", "summarization", "claude-3-5-sonnet", 1000)
        assert r1.batch_group != r2.batch_group

    # ------------------------------------------------------------------
    # Without model registry
    # ------------------------------------------------------------------

    def test_eligible_without_registry(self, engine_no_registry: BatchEngine) -> None:
        result = engine_no_registry.evaluate(
            prompt="Summarize this text",
            task_type="summarization",
            model="unknown-model",
            latency_budget_ms=1000,
        )
        assert result.eligible is True
        assert result.batch_group == "summarization:unknown-model"

    def test_max_wait_without_registry_uses_default(
        self, engine_no_registry: BatchEngine
    ) -> None:
        result = engine_no_registry.evaluate(
            prompt="Short",
            task_type="faq",
            model="unknown",
            latency_budget_ms=300,
        )
        assert result.eligible is True
        # With default 100ms estimated inference: 300 - 100 = 200, min(200, 500) = 200
        assert result.max_wait_ms == 200

    # ------------------------------------------------------------------
    # Error wrapping
    # ------------------------------------------------------------------

    def test_evaluate_wraps_unexpected_error(self, config: BatchConfig) -> None:
        """Unexpected errors in _evaluate_internal are wrapped in BatchingError."""
        engine = BatchEngine(config=config, model_registry=None)
        # Monkey-patch to force an unexpected error
        engine._evaluate_internal = lambda *args, **kwargs: (_ for _ in ()).throw(  # type: ignore[assignment]
            TypeError("surprise")
        )
        with pytest.raises(BatchingError, match="Failed to evaluate"):
            engine.evaluate("text", "faq", "model", 1000)

    def test_registry_get_failure_skips_token_check(self) -> None:
        """If registry.get raises, token check is skipped gracefully."""
        registry = ModelRegistry(config_path=None)
        registry.get = lambda name: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("broken")
        )
        engine = BatchEngine(
            config=BatchConfig(),
            model_registry=registry,
        )
        result = engine.evaluate("Short text", "faq", "broken-model", 1000)
        # Should still be eligible because token check was skipped
        assert result.eligible is True

    def test_registry_get_failure_uses_default_latency(self) -> None:
        """If registry.get fails during latency estimate, default is used."""
        registry = ModelRegistry(config_path=None)
        registry.get = lambda name: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("broken")
        )
        engine = BatchEngine(
            config=BatchConfig(max_wait_ms=500),
            model_registry=registry,
        )
        result = engine.evaluate("Short text", "faq", "broken-model", 300)
        # default estimate = 100ms, so max_wait = min(300-100, 500) = 200
        assert result.eligible is True
        assert result.max_wait_ms == 200
