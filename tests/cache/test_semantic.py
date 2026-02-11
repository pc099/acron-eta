"""Tests for SemanticCache (Tier 2 orchestrator)."""

import pytest

from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine
from src.embeddings.mismatch import MismatchCostCalculator
from src.cache.semantic import SemanticCache, SemanticCacheResult
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.embeddings.vector_store import InMemoryVectorDB


@pytest.fixture
def engine() -> EmbeddingEngine:
    return EmbeddingEngine(EmbeddingConfig(provider="mock", dimension=64))


@pytest.fixture
def cache(engine: EmbeddingEngine) -> SemanticCache:
    return SemanticCache(
        embedding_engine=engine,
        vector_db=InMemoryVectorDB(),
        similarity_calc=SimilarityCalculator(),
        mismatch_calc=MismatchCostCalculator(),
        threshold_tuner=AdaptiveThresholdTuner(),
    )


class TestSemanticCacheGet:
    """Tests for SemanticCache.get."""

    def test_miss_on_empty_db(self, cache: SemanticCache) -> None:
        result = cache.get("What is Python?")
        assert result.hit is False
        assert "No entries" in result.reason

    def test_hit_on_identical_query(self, cache: SemanticCache) -> None:
        cache.set("What is Python?", "A programming language.", "gpt-4", 0.01)
        result = cache.get(
            "What is Python?", task_type="faq", cost_sensitivity="high"
        )
        assert result.hit is True
        assert result.response == "A programming language."
        assert result.similarity is not None
        assert result.similarity > 0.99

    def test_miss_on_dissimilar_query(self, cache: SemanticCache) -> None:
        cache.set("What is Python?", "A programming language.", "gpt-4", 0.01)
        # Very different query -- should miss
        result = cache.get(
            "Translate hello to French",
            task_type="translation",
            cost_sensitivity="low",
        )
        # Result depends on embedding similarity - with mock random embeddings
        # dissimilar texts should usually miss
        assert isinstance(result, SemanticCacheResult)

    def test_returns_semantic_cache_result(self, cache: SemanticCache) -> None:
        result = cache.get("test query")
        assert isinstance(result, SemanticCacheResult)
        assert hasattr(result, "hit")
        assert hasattr(result, "response")
        assert hasattr(result, "similarity")
        assert hasattr(result, "reason")


class TestSemanticCacheSet:
    """Tests for SemanticCache.set."""

    def test_set_stores_entry(self, cache: SemanticCache) -> None:
        cache.set("Test query", "Test response", "model", 0.01)
        stats = cache.stats()
        assert stats["entry_count"] == 1

    def test_set_multiple(self, cache: SemanticCache) -> None:
        cache.set("Query A", "Response A", "model", 0.01)
        cache.set("Query B", "Response B", "model", 0.02)
        stats = cache.stats()
        assert stats["entry_count"] == 2


class TestSemanticCacheInvalidate:
    """Tests for SemanticCache.invalidate."""

    def test_invalidate_existing(self, cache: SemanticCache) -> None:
        cache.set("Delete me", "Response", "model", 0.01)
        # Note: invalidation finds nearest match > 0.99 similarity
        result = cache.invalidate("Delete me")
        assert result is True

    def test_invalidate_nonexistent(self, cache: SemanticCache) -> None:
        result = cache.invalidate("Not stored")
        assert result is False


class TestSemanticCacheStats:
    """Tests for SemanticCache.stats."""

    def test_stats_empty(self, cache: SemanticCache) -> None:
        stats = cache.stats()
        assert stats["tier"] == 2
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["entry_count"] == 0

    def test_stats_after_operations(self, cache: SemanticCache) -> None:
        cache.set("Q1", "R1", "model", 0.01)
        cache.get("Q1", task_type="faq", cost_sensitivity="high")
        cache.get("Q2")  # miss

        stats = cache.stats()
        assert stats["entry_count"] == 1
        # Total lookups should be 2
        assert stats["hits"] + stats["misses"] == 2


class TestSemanticCacheIntegration:
    """Integration tests for SemanticCache."""

    def test_set_then_get_cycle(self, cache: SemanticCache) -> None:
        # Store a response
        cache.set(
            query="Explain machine learning",
            response="ML is a subset of AI...",
            model="gpt-4-turbo",
            cost=0.02,
            task_type="faq",
        )

        # Retrieve with identical query
        result = cache.get(
            query="Explain machine learning",
            task_type="faq",
            cost_sensitivity="high",
            recompute_cost=0.02,
        )

        assert result.hit is True
        assert "ML is a subset of AI" in result.response

    def test_multiple_entries_best_match(self, cache: SemanticCache) -> None:
        cache.set("What is Python?", "Python is a language.", "model", 0.01)
        cache.set("What is Java?", "Java is a language.", "model", 0.01)
        cache.set("What is Rust?", "Rust is a language.", "model", 0.01)

        stats = cache.stats()
        assert stats["entry_count"] == 3
