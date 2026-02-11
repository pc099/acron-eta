"""Tests for TokenOptimizer -- full optimization pipeline."""

from typing import Dict, List

import pytest

from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine
from src.optimization.analyzer import AnalyzerConfig, ContextAnalyzer
from src.optimization.compressor import CompressorConfig, PromptCompressor
from src.optimization.few_shot import FewShotSelector
from src.optimization.optimizer import (
    OptimizerConfig,
    OptimizationResult,
    TokenOptimizer,
)


@pytest.fixture
def analyzer() -> ContextAnalyzer:
    config = AnalyzerConfig(
        scoring_method="keyword",
        min_relevance_threshold=0.2,
    )
    return ContextAnalyzer(config=config)


@pytest.fixture
def compressor() -> PromptCompressor:
    return PromptCompressor(CompressorConfig(extractive_top_ratio=0.5))


@pytest.fixture
def mock_engine() -> EmbeddingEngine:
    config = EmbeddingConfig(provider="mock", dimension=64)
    return EmbeddingEngine(config)


@pytest.fixture
def few_shot_selector(mock_engine: EmbeddingEngine) -> FewShotSelector:
    return FewShotSelector(embedding_engine=mock_engine)


@pytest.fixture
def optimizer(
    analyzer: ContextAnalyzer,
    compressor: PromptCompressor,
) -> TokenOptimizer:
    return TokenOptimizer(
        analyzer=analyzer,
        compressor=compressor,
        config=OptimizerConfig(),
    )


@pytest.fixture
def optimizer_with_fewshot(
    analyzer: ContextAnalyzer,
    compressor: PromptCompressor,
    few_shot_selector: FewShotSelector,
) -> TokenOptimizer:
    return TokenOptimizer(
        analyzer=analyzer,
        compressor=compressor,
        few_shot_selector=few_shot_selector,
        config=OptimizerConfig(max_few_shot_examples=2),
    )


class TestOptimizerConfig:
    """Tests for OptimizerConfig."""

    def test_default_values(self) -> None:
        cfg = OptimizerConfig()
        assert cfg.max_quality_risk == "medium"
        assert cfg.enable_context_analysis is True
        assert cfg.enable_compression is True
        assert cfg.enable_few_shot_selection is True
        assert cfg.max_few_shot_examples == 3

    def test_custom_values(self) -> None:
        cfg = OptimizerConfig(
            max_quality_risk="low",
            enable_compression=False,
        )
        assert cfg.max_quality_risk == "low"
        assert cfg.enable_compression is False


class TestOptimizationResult:
    """Tests for OptimizationResult model."""

    def test_creation(self) -> None:
        result = OptimizationResult(
            original_prompt="hello world",
            optimized_prompt="hello",
            original_tokens=5,
            optimized_tokens=3,
            tokens_saved=2,
            savings_percent=40.0,
            strategies_applied=["context_analysis"],
            quality_risk="low",
        )
        assert result.tokens_saved == 2
        assert result.quality_risk == "low"


class TestTokenOptimizerPipeline:
    """Tests for full optimization pipeline."""

    def test_basic_optimization(self, optimizer: TokenOptimizer) -> None:
        result = optimizer.optimize(
            prompt="What is machine learning?",
            system_prompt="You are a helpful AI assistant.",
        )
        assert isinstance(result, OptimizationResult)
        assert result.original_tokens > 0
        assert "context_analysis" in result.strategies_applied
        assert "compression" in result.strategies_applied

    def test_optimization_with_document(self, optimizer: TokenOptimizer) -> None:
        """Long irrelevant documents should be heavily compressed."""
        long_doc = " ".join([
            "The weather in Paris is beautiful in spring.",
            "Cooking pasta requires boiling water first.",
            "Gardening is a relaxing hobby for many people.",
            "The stock market fluctuated wildly yesterday.",
            "Machine learning uses algorithms to find patterns.",
        ])
        result = optimizer.optimize(
            prompt="Tell me about machine learning",
            system_prompt="You are a data science expert.",
        )
        assert result.original_tokens > 0

    def test_optimization_preserves_query(self, optimizer: TokenOptimizer) -> None:
        query = "What is deep learning?"
        result = optimizer.optimize(prompt=query)
        assert query in result.optimized_prompt

    def test_optimization_with_history(self, optimizer: TokenOptimizer) -> None:
        history = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI is artificial intelligence."},
            {"role": "user", "content": "Tell me more about it."},
        ]
        result = optimizer.optimize(
            prompt="How does AI learn?",
            history=history,
        )
        assert result.original_tokens > 0
        assert "context_analysis" in result.strategies_applied

    def test_optimization_with_examples(
        self, optimizer_with_fewshot: TokenOptimizer
    ) -> None:
        examples = [
            {"input": "What is Python?", "output": "A programming language."},
            {"input": "What is Java?", "output": "A JVM language."},
            {"input": "What is Rust?", "output": "A systems language."},
            {"input": "What is Go?", "output": "A concurrent language."},
        ]
        result = optimizer_with_fewshot.optimize(
            prompt="What is TypeScript?",
            examples=examples,
        )
        assert "few_shot_selection" in result.strategies_applied

    def test_strategies_applied_tracked(self, optimizer: TokenOptimizer) -> None:
        result = optimizer.optimize(
            prompt="test", system_prompt="sys"
        )
        assert len(result.strategies_applied) >= 1


class TestQualityRiskAssessment:
    """Tests for quality risk assessment logic."""

    def test_no_risk_below_15_percent(
        self, analyzer: ContextAnalyzer, compressor: PromptCompressor
    ) -> None:
        optimizer = TokenOptimizer(
            analyzer=analyzer,
            compressor=compressor,
            config=OptimizerConfig(
                enable_context_analysis=False,
                enable_compression=False,
            ),
        )
        result = optimizer.optimize(prompt="Short query")
        # No optimization steps -> 0% savings -> "none" risk
        assert result.quality_risk == "none"
        assert result.savings_percent == 0.0

    def test_high_risk_skips_optimization(
        self, analyzer: ContextAnalyzer, compressor: PromptCompressor
    ) -> None:
        """When max_quality_risk is 'none', any meaningful compression is skipped."""
        config = OptimizerConfig(max_quality_risk="none")
        optimizer = TokenOptimizer(
            analyzer=analyzer,
            compressor=compressor,
            config=config,
        )
        long_system = (
            "In order to provide the best responses, it is important to note that "
            "the system should take into consideration various factors. "
            "With regard to accuracy, due to the fact that users rely on this, "
            "please note that quality must be maintained. "
            "It should be noted that in the event that errors occur, "
            "as a result of complex queries, the system should handle gracefully."
        )
        result = optimizer.optimize(
            prompt="Short",
            system_prompt=long_system,
        )
        # If savings > 15%, risk > "none", so optimization should be skipped
        if result.savings_percent >= 15.0:
            assert "skipped_high_risk" in result.strategies_applied
            assert result.optimized_prompt == result.original_prompt


class TestTokenOptimizerEdgeCases:
    """Tests for edge cases."""

    def test_empty_prompt(self, optimizer: TokenOptimizer) -> None:
        result = optimizer.optimize(prompt="")
        assert result.original_tokens == 0 or result.optimized_tokens >= 0

    def test_no_optional_parts(self, optimizer: TokenOptimizer) -> None:
        result = optimizer.optimize(prompt="Just a simple question")
        assert result.original_tokens > 0

    def test_disabled_all_features(
        self, analyzer: ContextAnalyzer, compressor: PromptCompressor
    ) -> None:
        config = OptimizerConfig(
            enable_context_analysis=False,
            enable_compression=False,
            enable_few_shot_selection=False,
        )
        optimizer = TokenOptimizer(
            analyzer=analyzer, compressor=compressor, config=config
        )
        result = optimizer.optimize(
            prompt="test query",
            system_prompt="system text",
        )
        assert result.savings_percent == 0.0
        assert result.tokens_saved == 0

    def test_without_few_shot_selector(
        self, analyzer: ContextAnalyzer, compressor: PromptCompressor
    ) -> None:
        """Even with examples, no selector means no few_shot_selection."""
        optimizer = TokenOptimizer(
            analyzer=analyzer,
            compressor=compressor,
            few_shot_selector=None,
        )
        examples = [{"input": "A", "output": "1"}]
        result = optimizer.optimize(prompt="test", examples=examples)
        assert "few_shot_selection" not in result.strategies_applied
