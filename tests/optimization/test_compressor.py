"""Tests for PromptCompressor -- multi-strategy prompt compression."""

from typing import Dict, List

import pytest

from src.optimization.compressor import (
    CompressorConfig,
    CompressionResult,
    PromptCompressor,
)


class TestCompressorConfig:
    """Tests for CompressorConfig."""

    def test_default_values(self) -> None:
        cfg = CompressorConfig()
        assert cfg.default_strategy == "extractive"
        assert cfg.extractive_top_ratio == 0.5
        assert cfg.max_history_turns == 5
        assert len(cfg.template_patterns) > 0

    def test_custom_strategy(self) -> None:
        cfg = CompressorConfig(default_strategy="template")
        assert cfg.default_strategy == "template"


class TestCompressionResult:
    """Tests for CompressionResult model."""

    def test_creation(self) -> None:
        result = CompressionResult(
            original_text="hello world",
            compressed_text="hello",
            original_tokens=5,
            compressed_tokens=3,
            compression_ratio=0.6,
            strategy_used="extractive",
        )
        assert result.compression_ratio == 0.6
        assert result.strategy_used == "extractive"


class TestPromptCompressorExtractive:
    """Tests for extractive compression strategy."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        config = CompressorConfig(extractive_top_ratio=0.5)
        return PromptCompressor(config=config)

    def test_extractive_reduces_text(self, compressor: PromptCompressor) -> None:
        long_text = (
            "Machine learning is a subset of artificial intelligence. "
            "It involves training algorithms on data. "
            "The weather today is sunny and warm. "
            "Random unrelated sentence about cooking pasta. "
            "Neural networks are a key technique in deep learning. "
            "Another random thought about gardening."
        )
        result = compressor.compress(long_text, strategy="extractive")
        assert result.compressed_tokens < result.original_tokens
        assert result.compression_ratio < 1.0
        assert result.strategy_used == "extractive"

    def test_extractive_with_target_tokens(
        self, compressor: PromptCompressor
    ) -> None:
        text = (
            "First sentence about coding. "
            "Second sentence about testing. "
            "Third sentence about deployment. "
            "Fourth sentence about monitoring."
        )
        result = compressor.compress(text, target_token_count=10, strategy="extractive")
        assert result.compressed_tokens <= 15  # allow small margin

    def test_single_sentence_unchanged(self, compressor: PromptCompressor) -> None:
        text = "This is a single sentence."
        result = compressor.compress(text, strategy="extractive")
        assert result.compressed_text == text

    def test_empty_text_returns_empty(self, compressor: PromptCompressor) -> None:
        result = compressor.compress("", strategy="extractive")
        assert result.compressed_text == ""
        assert result.original_tokens == 0
        assert result.compression_ratio == 1.0


class TestPromptCompressorAbstractive:
    """Tests for abstractive compression strategy."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        return PromptCompressor()

    def test_abstractive_compresses_more(
        self, compressor: PromptCompressor
    ) -> None:
        long_text = (
            "In order to understand machine learning, it is important to note that "
            "algorithms learn patterns from data. Due to the fact that modern datasets "
            "are large, scalable approaches are needed. With regard to deep learning, "
            "neural networks form the backbone. It should be noted that training "
            "requires significant compute resources. As a result of advances in "
            "hardware, training times have decreased dramatically."
        )
        result = compressor.compress(long_text, strategy="abstractive")
        assert result.compressed_tokens < result.original_tokens
        assert result.strategy_used == "abstractive"

    def test_abstractive_with_target_tokens(
        self, compressor: PromptCompressor
    ) -> None:
        text = (
            "First important point. Second key detail. "
            "Third critical fact. Fourth essential note."
        )
        result = compressor.compress(
            text, target_token_count=8, strategy="abstractive"
        )
        assert result.compressed_tokens <= 12


class TestPromptCompressorTemplate:
    """Tests for template compression strategy."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        return PromptCompressor()

    def test_template_replaces_verbose_patterns(
        self, compressor: PromptCompressor
    ) -> None:
        text = "In order to succeed, due to the fact that effort matters."
        result = compressor.compress(text, strategy="template")
        assert "In order to" not in result.compressed_text
        assert "to succeed" in result.compressed_text
        assert result.strategy_used == "template"

    def test_template_multiple_patterns(
        self, compressor: PromptCompressor
    ) -> None:
        text = (
            "Please note that this is important. "
            "With regard to the project, in the event that issues arise, "
            "take into consideration the timeline."
        )
        result = compressor.compress(text, strategy="template")
        assert result.compressed_tokens <= result.original_tokens
        assert "Please note that" not in result.compressed_text

    def test_template_no_patterns_minimal_change(
        self, compressor: PromptCompressor
    ) -> None:
        text = "Short clean text."
        result = compressor.compress(text, strategy="template")
        assert result.compressed_text == "Short clean text."


class TestCompressSystemPrompt:
    """Tests for compress_system_prompt method."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        return PromptCompressor()

    def test_uses_template_strategy(self, compressor: PromptCompressor) -> None:
        result = compressor.compress_system_prompt(
            "Please note that you are a helpful assistant."
        )
        assert result.strategy_used == "template"

    def test_reduces_verbose_system_prompt(
        self, compressor: PromptCompressor
    ) -> None:
        verbose = (
            "It is important to note that you are a helpful AI assistant. "
            "In order to provide the best responses, take into consideration "
            "the user's needs. With regard to accuracy, it should be noted that "
            "facts must be verified."
        )
        result = compressor.compress_system_prompt(verbose)
        assert result.compressed_tokens < result.original_tokens


class TestCompressHistory:
    """Tests for compress_history method."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        config = CompressorConfig(max_history_turns=3)
        return PromptCompressor(config=config)

    def test_truncates_old_turns(self, compressor: PromptCompressor) -> None:
        history: List[Dict[str, str]] = [
            {"role": "user", "content": f"Question {i}"} for i in range(10)
        ]
        result = compressor.compress_history(history)
        assert result.strategy_used == "history_truncation"
        # Should only keep last 3 turns
        assert "Question 9" in result.compressed_text
        assert "Question 0" not in result.compressed_text

    def test_empty_history(self, compressor: PromptCompressor) -> None:
        result = compressor.compress_history([])
        assert result.compressed_text == ""
        assert result.compression_ratio == 1.0

    def test_short_history_unchanged(self, compressor: PromptCompressor) -> None:
        history = [{"role": "user", "content": "Hello"}]
        result = compressor.compress_history(history)
        assert "Hello" in result.compressed_text


class TestCompressDocument:
    """Tests for compress_document method."""

    @pytest.fixture
    def compressor(self) -> PromptCompressor:
        return PromptCompressor()

    def test_document_compression_with_query(
        self, compressor: PromptCompressor
    ) -> None:
        document = (
            "Python is a programming language used for web development. "
            "The weather in London is often rainy. "
            "Python supports multiple programming paradigms. "
            "Cooking requires patience and good ingredients. "
            "Python has a large ecosystem of libraries."
        )
        result = compressor.compress_document(document, "Tell me about Python")
        assert "Python" in result.compressed_text
        assert result.strategy_used == "extractive"

    def test_empty_document(self, compressor: PromptCompressor) -> None:
        result = compressor.compress_document("", "query")
        assert result.compressed_text == ""
        assert result.compression_ratio == 1.0
