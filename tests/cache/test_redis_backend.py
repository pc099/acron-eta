"""
Tests for the Redis-backed Tier 1 cache.

Uses fakeredis so no real Redis server is required.
"""

import pytest

from src.cache.exact import CacheEntry, CacheStats
from src.cache.redis_backend import RedisCache


@pytest.fixture
def redis_cache():
    """Create a RedisCache backed by fakeredis."""
    try:
        import fakeredis
    except ImportError:
        pytest.skip("fakeredis not installed")
    client = fakeredis.FakeStrictRedis(decode_responses=True)
    return RedisCache(
        redis_url="redis://localhost:6379/0",
        ttl_seconds=3600,
        _redis_client=client,
    )


class TestRedisCacheWithFakeredis:
    """Tests for RedisCache using an injected FakeStrictRedis."""

    def test_set_and_get(self, redis_cache: RedisCache) -> None:
        redis_cache.set(
            query="What is Python?",
            response="A programming language.",
            model="gpt-4o",
            cost=0.01,
        )
        result = redis_cache.get("What is Python?")
        assert result is not None
        assert result.response == "A programming language."
        assert result.model == "gpt-4o"

    def test_get_miss(self, redis_cache: RedisCache) -> None:
        result = redis_cache.get("nonexistent query")
        assert result is None

    def test_empty_query_rejected(self, redis_cache: RedisCache) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            redis_cache.set("", "response", "model", 0.01)

    def test_whitespace_query_rejected(self, redis_cache: RedisCache) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            redis_cache.set("   ", "response", "model", 0.01)

    def test_invalidate_existing(self, redis_cache: RedisCache) -> None:
        redis_cache.set("query", "response", "model", 0.01)
        removed = redis_cache.invalidate("query")
        assert removed is True
        assert redis_cache.get("query") is None

    def test_invalidate_nonexistent(self, redis_cache: RedisCache) -> None:
        removed = redis_cache.invalidate("nonexistent")
        assert removed is False

    def test_stats(self, redis_cache: RedisCache) -> None:
        redis_cache.set("q1", "r1", "m1", 0.01)
        redis_cache.get("q1")
        redis_cache.get("q2")
        stats = redis_cache.stats()
        assert isinstance(stats, CacheStats)
        assert stats.hits >= 1
        assert stats.misses >= 1
        assert stats.entry_count >= 1
        assert 0.0 <= stats.hit_rate <= 1.0

    def test_generate_key_deterministic(self, redis_cache: RedisCache) -> None:
        k1 = redis_cache.generate_key("hello")
        k2 = redis_cache.generate_key("hello")
        assert k1 == k2

    def test_clear(self, redis_cache: RedisCache) -> None:
        redis_cache.set("q1", "r1", "m1", 0.01)
        redis_cache.set("q2", "r2", "m2", 0.02)
        n = redis_cache.clear()
        assert n >= 2
        assert redis_cache.get("q1") is None
        assert redis_cache.get("q2") is None
