"""Tests for ContextAnalyzer -- prompt segment relevance scoring."""

from typing import Dict, List

import pytest

from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine
from src.optimization.analyzer import AnalyzerConfig, ContextAnalyzer, SegmentScore


class TestAnalyzerConfig:
    """Tests for AnalyzerConfig defaults and validation."""

    def test_default_values(self) -> None:
        cfg = AnalyzerConfig()
        assert cfg.min_relevance_threshold == 0.3
        assert cfg.protected_categories == ["query"]
        assert cfg.max_history_turns == 5
        assert cfg.scoring_method == "keyword"
        assert cfg.system_boost == 0.2

    def test_custom_values(self) -> None:
        cfg = AnalyzerConfig(
            min_relevance_threshold=0.5,
            protected_categories=["query", "system"],
            max_history_turns=3,
            scoring_method="tfidf",
            system_boost=0.1,
        )
        assert cfg.min_relevance_threshold == 0.5
        assert cfg.scoring_method == "tfidf"


class TestSegmentScore:
    """Tests for SegmentScore model."""

    def test_creation(self) -> None:
        seg = SegmentScore(
            segment_id="doc-abc123",
            text="Some document text",
            token_count=10,
            relevance_score=0.75,
            category="document",
        )
        assert seg.segment_id == "doc-abc123"
        assert seg.category == "document"
        assert seg.relevance_score == 0.75


class TestContextAnalyzerKeyword:
    """Tests for ContextAnalyzer using keyword scoring."""

    @pytest.fixture
    def analyzer(self) -> ContextAnalyzer:
        config = AnalyzerConfig(scoring_method="keyword")
        return ContextAnalyzer(config=config)

    def test_analyze_returns_segments(self, analyzer: ContextAnalyzer) -> None:
        parts = {
            "system": "You are a helpful assistant.",
            "document": "Python is a programming language.",
            "query": "What is Python?",
        }
        segments = analyzer.analyze(parts, "What is Python?")
        assert len(segments) == 3
        assert all(isinstance(s, SegmentScore) for s in segments)

    def test_query_always_has_full_relevance(self, analyzer: ContextAnalyzer) -> None:
        parts = {"query": "Tell me about machine learning"}
        segments = analyzer.analyze(parts, "Tell me about machine learning")
        assert segments[0].relevance_score == 1.0

    def test_irrelevant_document_gets_low_score(
        self, analyzer: ContextAnalyzer
    ) -> None:
        parts = {
            "query": "What is the capital of France?",
            "document": "Photosynthesis is the process by which plants convert sunlight.",
        }
        segments = analyzer.analyze(parts, "What is the capital of France?")
        doc_seg = [s for s in segments if s.category == "document"][0]
        assert doc_seg.relevance_score < 0.5

    def test_relevant_document_gets_higher_score(
        self, analyzer: ContextAnalyzer
    ) -> None:
        parts = {
            "query": "What is Python programming?",
            "document": "Python programming is a popular language for data science.",
        }
        segments = analyzer.analyze(parts, "What is Python programming?")
        doc_seg = [s for s in segments if s.category == "document"][0]
        assert doc_seg.relevance_score > 0.0

    def test_system_prompt_gets_boost(self, analyzer: ContextAnalyzer) -> None:
        parts = {
            "system": "You are a coding assistant that helps with Python.",
            "query": "Help me with Python",
        }
        segments = analyzer.analyze(parts, "Help me with Python")
        sys_seg = [s for s in segments if s.category == "system"][0]
        # System boost should push the score up
        assert sys_seg.relevance_score > 0.0

    def test_empty_parts_skipped(self, analyzer: ContextAnalyzer) -> None:
        parts: Dict[str, str] = {"query": "hello", "document": "", "system": "   "}
        segments = analyzer.analyze(parts, "hello")
        assert len(segments) == 1
        assert segments[0].category == "query"

    def test_history_truncated(self) -> None:
        config = AnalyzerConfig(scoring_method="keyword", max_history_turns=2)
        analyzer = ContextAnalyzer(config=config)
        long_history = "Turn 1\n\nTurn 2\n\nTurn 3\n\nTurn 4\n\nTurn 5"
        parts = {"query": "test", "history": long_history}
        segments = analyzer.analyze(parts, "test")
        history_seg = [s for s in segments if s.category == "history"][0]
        # Should only have last 2 turns
        assert "Turn 4" in history_seg.text
        assert "Turn 5" in history_seg.text
        assert "Turn 1" not in history_seg.text

    def test_token_count_is_positive(self, analyzer: ContextAnalyzer) -> None:
        parts = {"query": "What is machine learning?"}
        segments = analyzer.analyze(parts, "What is machine learning?")
        assert segments[0].token_count > 0


class TestContextAnalyzerTfidf:
    """Tests for TF-IDF scoring method."""

    @pytest.fixture
    def analyzer(self) -> ContextAnalyzer:
        config = AnalyzerConfig(scoring_method="tfidf")
        return ContextAnalyzer(config=config)

    def test_tfidf_scoring_produces_values(self, analyzer: ContextAnalyzer) -> None:
        parts = {
            "query": "machine learning algorithms",
            "document": "Machine learning algorithms are used in data science.",
        }
        segments = analyzer.analyze(parts, "machine learning algorithms")
        doc_seg = [s for s in segments if s.category == "document"][0]
        assert 0.0 <= doc_seg.relevance_score <= 1.0


class TestContextAnalyzerEmbedding:
    """Tests for embedding-based scoring."""

    @pytest.fixture
    def mock_engine(self) -> EmbeddingEngine:
        config = EmbeddingConfig(provider="mock", dimension=64)
        return EmbeddingEngine(config)

    def test_embedding_scoring_with_engine(
        self, mock_engine: EmbeddingEngine
    ) -> None:
        config = AnalyzerConfig(scoring_method="embedding")
        analyzer = ContextAnalyzer(config=config, embedding_engine=mock_engine)
        parts = {
            "query": "What is Python?",
            "document": "Python is a programming language.",
        }
        segments = analyzer.analyze(parts, "What is Python?")
        doc_seg = [s for s in segments if s.category == "document"][0]
        assert 0.0 <= doc_seg.relevance_score <= 1.0

    def test_embedding_fallback_without_engine(self) -> None:
        """Without engine, embedding mode falls back to keyword."""
        config = AnalyzerConfig(scoring_method="embedding")
        analyzer = ContextAnalyzer(config=config, embedding_engine=None)
        # Should not crash -- falls back to keyword
        parts = {"query": "test", "document": "some document"}
        segments = analyzer.analyze(parts, "test")
        assert len(segments) == 2


class TestFilterByRelevance:
    """Tests for the filter_by_relevance method."""

    @pytest.fixture
    def analyzer(self) -> ContextAnalyzer:
        config = AnalyzerConfig(scoring_method="keyword", min_relevance_threshold=0.3)
        return ContextAnalyzer(config=config)

    def test_filter_removes_low_relevance(self, analyzer: ContextAnalyzer) -> None:
        segments = [
            SegmentScore(
                segment_id="s1", text="relevant", token_count=5,
                relevance_score=0.8, category="document"
            ),
            SegmentScore(
                segment_id="s2", text="irrelevant", token_count=5,
                relevance_score=0.1, category="document"
            ),
        ]
        filtered = analyzer.filter_by_relevance(segments)
        assert len(filtered) == 1
        assert filtered[0].segment_id == "s1"

    def test_protected_categories_always_kept(
        self, analyzer: ContextAnalyzer
    ) -> None:
        segments = [
            SegmentScore(
                segment_id="q1", text="query text", token_count=5,
                relevance_score=0.0, category="query"
            ),
        ]
        filtered = analyzer.filter_by_relevance(segments)
        assert len(filtered) == 1

    def test_custom_threshold(self, analyzer: ContextAnalyzer) -> None:
        segments = [
            SegmentScore(
                segment_id="s1", text="text", token_count=5,
                relevance_score=0.5, category="document"
            ),
        ]
        # With higher threshold
        filtered = analyzer.filter_by_relevance(segments, min_relevance=0.6)
        assert len(filtered) == 0


class TestEstimateTokenSavings:
    """Tests for token savings estimation."""

    @pytest.fixture
    def analyzer(self) -> ContextAnalyzer:
        return ContextAnalyzer(config=AnalyzerConfig(scoring_method="keyword"))

    def test_savings_calculation(self, analyzer: ContextAnalyzer) -> None:
        original = [
            SegmentScore(
                segment_id="s1", text="hello world", token_count=10,
                relevance_score=0.8, category="document"
            ),
            SegmentScore(
                segment_id="s2", text="irrelevant stuff", token_count=20,
                relevance_score=0.1, category="document"
            ),
        ]
        filtered = [original[0]]
        savings = analyzer.estimate_token_savings(original, filtered)
        assert savings["original_tokens"] == 30
        assert savings["filtered_tokens"] == 10
        assert savings["tokens_saved"] == 20
        assert savings["savings_percent"] == pytest.approx(66.7, abs=0.1)

    def test_savings_by_category(self, analyzer: ContextAnalyzer) -> None:
        original = [
            SegmentScore(
                segment_id="s1", text="sys", token_count=100,
                relevance_score=0.9, category="system"
            ),
            SegmentScore(
                segment_id="s2", text="doc", token_count=200,
                relevance_score=0.1, category="document"
            ),
        ]
        filtered = [original[0]]
        savings = analyzer.estimate_token_savings(original, filtered)
        assert savings["by_category"]["document"]["saved"] == 200
        assert savings["by_category"]["system"]["saved"] == 0

    def test_savings_empty_original(self, analyzer: ContextAnalyzer) -> None:
        savings = analyzer.estimate_token_savings([], [])
        assert savings["savings_percent"] == 0.0
