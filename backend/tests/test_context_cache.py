"""Tests for context-aware cache integration."""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cache import CacheHit, RedisCache
from app.services.coherence_validator import CoherenceValidator
from app.services.dependency_classifier import DependencyClassifier, DependencyLevel


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def cache(mock_redis: AsyncMock) -> RedisCache:
    return RedisCache(mock_redis)


@pytest.fixture
def validator() -> CoherenceValidator:
    return CoherenceValidator()


@pytest.fixture
def classifier() -> DependencyClassifier:
    return DependencyClassifier()


class TestContextAwareGet:
    """Tests for RedisCache.context_get."""

    @pytest.mark.asyncio
    async def test_critical_skips_cache(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """CRITICAL dependency should always skip cache."""
        # Even with data in cache, CRITICAL should return None
        cached_data = json.dumps({
            "response": "cached answer",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        result = await cache.context_get(
            org_id="org-1",
            query="Execute deployment now",
            dependency_level=DependencyLevel.CRITICAL,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_independent_returns_cache_hit(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """INDEPENDENT requests should use cache normally."""
        cached_data = json.dumps({
            "response": "Python is a programming language",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        result = await cache.context_get(
            org_id="org-1",
            query="What is Python?",
            dependency_level=DependencyLevel.INDEPENDENT,
        )
        assert result is not None
        assert result.response == "Python is a programming language"
        assert result.dependency_level == DependencyLevel.INDEPENDENT

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """Cache miss should return None regardless of dependency level."""
        mock_redis.get = AsyncMock(return_value=None)

        result = await cache.context_get(
            org_id="org-1",
            query="What is Python?",
            dependency_level=DependencyLevel.INDEPENDENT,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_partial_with_coherence_pass(
        self, cache: RedisCache, mock_redis: AsyncMock, validator: CoherenceValidator,
    ) -> None:
        """PARTIAL dependency with coherent cache should return hit."""
        cached_data = json.dumps({
            "response": "Python supports object-oriented programming patterns.",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        result = await cache.context_get(
            org_id="org-1",
            query="Additionally, explain the OOP patterns",
            dependency_level=DependencyLevel.PARTIAL,
            coherence_validator=validator,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_partial_with_coherence_fail(
        self, cache: RedisCache, mock_redis: AsyncMock, validator: CoherenceValidator,
    ) -> None:
        """PARTIAL dependency with incoherent cache should return None."""
        cached_data = json.dumps({
            "response": "The weather today is sunny.",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        result = await cache.context_get(
            org_id="org-1",
            query='Return the current "Bitcoin price" as JSON',
            dependency_level=DependencyLevel.PARTIAL,
            coherence_validator=validator,
            session_step=3,
        )
        # Should fail on format_continuity (wants JSON) and entity_consistency
        assert result is None


class TestDependencyClassifierIntegration:
    """Tests for DependencyClassifier used in cache flow."""

    def test_classify_independent(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("What is the capital of France?")
        assert result.level == DependencyLevel.INDEPENDENT

    def test_classify_critical(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Run the migration script now")
        assert result.level == DependencyLevel.CRITICAL

    def test_classify_dependent(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Based on what you said earlier, fix the function above")
        assert result.level == DependencyLevel.DEPENDENT


class TestCacheKeyFingerprint:
    """Tests for dependency fingerprint in cache keys."""

    def test_cache_key_different_for_dependent_vs_independent(self) -> None:
        from app.services.cache import RedisCache
        # Use a mock redis
        cache = RedisCache.__new__(RedisCache)
        key_independent = cache._exact_key("org1", "hello world")
        key_dependent = cache._exact_key("org1", "hello world", dependency_suffix=":dep:DEPENDENT:step:3")
        assert key_independent != key_dependent

    def test_cache_key_same_without_suffix(self) -> None:
        from app.services.cache import RedisCache
        cache = RedisCache.__new__(RedisCache)
        key1 = cache._exact_key("org1", "hello world")
        key2 = cache._exact_key("org1", "hello world", dependency_suffix="")
        assert key1 == key2


class TestCacheMetrics:
    """Tests for CacheMetrics tracking in RedisCache."""

    @pytest.mark.asyncio
    async def test_exact_hit_increments_counter(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        cached_data = json.dumps({
            "response": "Hello",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        mock_redis.get = AsyncMock(return_value=cached_data)

        await cache.get("org-1", "hi")
        assert cache.metrics.exact_hits == 1
        assert cache.metrics.semantic_hits == 0
        assert cache.metrics.misses == 0

    @pytest.mark.asyncio
    async def test_miss_increments_counter(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        mock_redis.get = AsyncMock(return_value=None)

        await cache.get("org-1", "unknown query")
        assert cache.metrics.misses == 1
        assert cache.metrics.exact_hits == 0

    @pytest.mark.asyncio
    async def test_hit_rate_calculation(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        cached_data = json.dumps({
            "response": "Hello",
            "model_used": "gpt-4o",
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        # 2 hits, 1 miss
        mock_redis.get = AsyncMock(return_value=cached_data)
        await cache.get("org-1", "q1")
        await cache.get("org-1", "q2")
        mock_redis.get = AsyncMock(return_value=None)
        await cache.get("org-1", "q3")

        assert cache.metrics.exact_hits == 2
        assert cache.metrics.misses == 1
        assert 0.66 <= cache.metrics.hit_rate <= 0.67

    @pytest.mark.asyncio
    async def test_hit_rate_zero_when_empty(self, cache: RedisCache) -> None:
        assert cache.metrics.hit_rate == 0.0

    def test_to_dict(self) -> None:
        from app.services.cache import CacheMetrics
        m = CacheMetrics(exact_hits=5, semantic_hits=2, misses=3, promotions=1)
        d = m.to_dict()
        assert d["exact_hits"] == 5
        assert d["semantic_hits"] == 2
        assert d["misses"] == 3
        assert d["promotions"] == 1
        assert d["hit_rate"] == 0.7


class TestCachePromotion:
    """Tests for semantic-to-exact cache promotion."""

    @pytest.mark.asyncio
    async def test_promotion_triggers_above_threshold(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """Semantic hit with similarity >= 0.95 should be promoted to exact cache."""
        # exact_get returns None (miss), semantic_get returns high-similarity hit
        mock_redis.get = AsyncMock(return_value=None)

        semantic_hit = CacheHit(
            response="Promoted answer",
            model_used="gpt-4o",
            cache_tier="semantic",
            similarity=0.97,
        )
        # Patch semantic_get to return our controlled hit
        cache.semantic_get = AsyncMock(return_value=semantic_hit)

        result = await cache.get("org-1", "test query")
        assert result is not None
        assert result.cache_tier == "semantic"
        assert cache.metrics.semantic_hits == 1
        assert cache.metrics.promotions == 1
        # exact_set should have been called for promotion
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_promotion_skipped_below_threshold(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """Semantic hit with similarity < 0.95 should NOT be promoted."""
        mock_redis.get = AsyncMock(return_value=None)

        semantic_hit = CacheHit(
            response="Not promoted",
            model_used="gpt-4o",
            cache_tier="semantic",
            similarity=0.90,
        )
        cache.semantic_get = AsyncMock(return_value=semantic_hit)

        result = await cache.get("org-1", "test query")
        assert result is not None
        assert cache.metrics.semantic_hits == 1
        assert cache.metrics.promotions == 0
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_promotion_failure_does_not_break_get(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """If promotion fails, the semantic hit should still be returned."""
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.set = AsyncMock(side_effect=Exception("Redis write error"))

        semantic_hit = CacheHit(
            response="Still returned",
            model_used="gpt-4o",
            cache_tier="semantic",
            similarity=0.98,
        )
        cache.semantic_get = AsyncMock(return_value=semantic_hit)

        result = await cache.get("org-1", "test query")
        assert result is not None
        assert result.response == "Still returned"
        assert cache.metrics.semantic_hits == 1
        assert cache.metrics.promotions == 0  # Failed, not counted


class TestCacheWarming:
    """Tests for cache warming (pre-population)."""

    @pytest.mark.asyncio
    async def test_warm_success(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        entries = [
            {"query": "What is Python?", "response": "A programming language.", "model_used": "gpt-4o"},
            {"query": "What is Rust?", "response": "A systems language.", "model_used": "gpt-4o"},
        ]
        count = await cache.warm("org-1", entries)
        assert count == 2
        assert mock_redis.set.call_count == 2

    @pytest.mark.asyncio
    async def test_warm_partial_failure(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        """If some entries fail, warm should still cache the rest."""
        call_count = 0

        async def flaky_set(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Redis error")

        mock_redis.set = AsyncMock(side_effect=flaky_set)

        entries = [
            {"query": "Q1", "response": "A1", "model_used": "gpt-4o"},
            {"query": "Q2", "response": "A2", "model_used": "gpt-4o"},
            {"query": "Q3", "response": "A3", "model_used": "gpt-4o"},
        ]
        count = await cache.warm("org-1", entries)
        assert count == 2  # 1st and 3rd succeed, 2nd fails

    @pytest.mark.asyncio
    async def test_warm_empty_entries(self, cache: RedisCache, mock_redis: AsyncMock) -> None:
        count = await cache.warm("org-1", [])
        assert count == 0
        mock_redis.set.assert_not_called()


class TestPineconeSemanticCache:
    """Tests for Pinecone-backed semantic cache."""

    @pytest.fixture
    def mock_pinecone_index(self) -> MagicMock:
        index = MagicMock()
        index.query = MagicMock(return_value={"matches": []})
        index.upsert = MagicMock()
        return index

    @pytest.fixture
    def pinecone_cache(self, mock_redis: AsyncMock, mock_pinecone_index: MagicMock) -> RedisCache:
        return RedisCache(mock_redis, pinecone_index=mock_pinecone_index)

    @pytest.mark.asyncio
    async def test_semantic_get_returns_hit(self, pinecone_cache: RedisCache, mock_pinecone_index: MagicMock) -> None:
        """Pinecone semantic_get should return a CacheHit when match found."""
        mock_pinecone_index.query.return_value = {
            "matches": [{
                "id": "org-1:abc123",
                "score": 0.92,
                "metadata": {
                    "org_id": "org-1",
                    "model": "gpt-4o",
                    "response": "Python is great",
                    "cached_at": "2025-01-01T00:00:00+00:00",
                },
            }],
        }

        result = await pinecone_cache.semantic_get("org-1", "Tell me about Python")
        assert result is not None
        assert result.response == "Python is great"
        assert result.model_used == "gpt-4o"
        assert result.cache_tier == "semantic"
        assert result.similarity == 0.92

    @pytest.mark.asyncio
    async def test_semantic_get_returns_none_below_threshold(
        self, pinecone_cache: RedisCache, mock_pinecone_index: MagicMock,
    ) -> None:
        """Low-similarity matches should not be returned."""
        mock_pinecone_index.query.return_value = {
            "matches": [{
                "id": "org-1:abc123",
                "score": 0.50,
                "metadata": {"response": "irrelevant", "model": "gpt-4o"},
            }],
        }

        result = await pinecone_cache.semantic_get("org-1", "something different")
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_get_returns_none_on_empty(
        self, pinecone_cache: RedisCache, mock_pinecone_index: MagicMock,
    ) -> None:
        """No matches should return None."""
        mock_pinecone_index.query.return_value = {"matches": []}
        result = await pinecone_cache.semantic_get("org-1", "query")
        assert result is None

    @pytest.mark.asyncio
    async def test_semantic_set_upserts(
        self, pinecone_cache: RedisCache, mock_pinecone_index: MagicMock,
    ) -> None:
        """semantic_set should upsert vector + metadata to Pinecone."""
        await pinecone_cache.semantic_set("org-1", "hello", "world", "gpt-4o")
        mock_pinecone_index.upsert.assert_called_once()
        call_args = mock_pinecone_index.upsert.call_args
        vectors = call_args[1]["vectors"]
        assert len(vectors) == 1
        vec_id, embedding, metadata = vectors[0]
        assert vec_id.startswith("org-1:")
        assert metadata["org_id"] == "org-1"
        assert metadata["response"] == "world"

    @pytest.mark.asyncio
    async def test_no_pinecone_skips_semantic(self, mock_redis: AsyncMock) -> None:
        """When no Pinecone index is configured, semantic ops are no-ops."""
        cache = RedisCache(mock_redis)
        # Without pinecone_api_key set, _get_pinecone_index should return None
        cache._get_pinecone_index = MagicMock(return_value=None)

        result = await cache.semantic_get("org-1", "query")
        assert result is None

        # semantic_set should silently skip
        await cache.semantic_set("org-1", "query", "response", "model")

    @pytest.mark.asyncio
    async def test_combined_get_exact_then_semantic(
        self, pinecone_cache: RedisCache, mock_redis: AsyncMock, mock_pinecone_index: MagicMock,
    ) -> None:
        """Combined get should try exact first, fall through to semantic."""
        # Exact miss
        mock_redis.get = AsyncMock(return_value=None)
        # Semantic hit
        mock_pinecone_index.query.return_value = {
            "matches": [{
                "id": "org-1:abc",
                "score": 0.90,
                "metadata": {"response": "semantic answer", "model": "gpt-4o"},
            }],
        }

        result = await pinecone_cache.get("org-1", "query")
        assert result is not None
        assert result.cache_tier == "semantic"
        assert pinecone_cache.metrics.semantic_hits == 1
