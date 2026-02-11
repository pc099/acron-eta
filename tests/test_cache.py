"""
Tests for the exact-match cache layer.
"""

import time
from datetime import datetime, timedelta, timezone

import pytest

from src.cache import Cache, CacheEntry, CacheStats


class TestCacheEntry:
    """Tests for CacheEntry Pydantic model."""

    def test_create_entry(self) -> None:
        entry = CacheEntry(
            cache_key="abc123",
            query="test query",
            response="test response",
            model="gpt-4-turbo",
            cost=0.01,
        )
        assert entry.cache_key == "abc123"
        assert entry.access_count == 0
        assert isinstance(entry.created_at, datetime)


class TestCache:
    """Tests for the Cache class."""

    @pytest.fixture
    def cache(self) -> Cache:
        return Cache(ttl_seconds=3600)

    def test_set_and_get(self, cache: Cache) -> None:
        entry = cache.set(
            query="What is Python?",
            response="A programming language.",
            model="gpt-4-turbo",
            cost=0.01,
        )
        assert isinstance(entry, CacheEntry)

        result = cache.get("What is Python?")
        assert result is not None
        assert result.response == "A programming language."
        assert result.model == "gpt-4-turbo"

    def test_get_miss(self, cache: Cache) -> None:
        result = cache.get("nonexistent query")
        assert result is None

    def test_get_increments_access_count(self, cache: Cache) -> None:
        cache.set("query", "response", "model", 0.01)
        cache.get("query")
        cache.get("query")
        entry = cache.get("query")
        assert entry is not None
        assert entry.access_count == 3

    def test_ttl_expiry(self) -> None:
        cache = Cache(ttl_seconds=1)
        cache.set("query", "response", "model", 0.01)
        time.sleep(1.1)
        result = cache.get("query")
        assert result is None

    def test_empty_query_rejected(self, cache: Cache) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            cache.set("", "response", "model", 0.01)

    def test_whitespace_query_rejected(self, cache: Cache) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            cache.set("   ", "response", "model", 0.01)

    def test_invalidate_existing(self, cache: Cache) -> None:
        cache.set("query", "response", "model", 0.01)
        removed = cache.invalidate("query")
        assert removed is True
        assert cache.get("query") is None

    def test_invalidate_nonexistent(self, cache: Cache) -> None:
        removed = cache.invalidate("nonexistent")
        assert removed is False

    def test_clear(self, cache: Cache) -> None:
        cache.set("q1", "r1", "model", 0.01)
        cache.set("q2", "r2", "model", 0.02)
        count = cache.clear()
        assert count == 2
        assert cache.size == 0

    def test_stats(self, cache: Cache) -> None:
        cache.set("q1", "r1", "model", 0.05)
        cache.get("q1")  # hit
        cache.get("q1")  # hit
        cache.get("missing")  # miss

        stats = cache.stats()
        assert isinstance(stats, CacheStats)
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.hit_rate == pytest.approx(2 / 3, abs=0.01)
        assert stats.entry_count == 1
        assert stats.total_cost_saved == pytest.approx(0.10, abs=0.01)

    def test_stats_empty(self, cache: Cache) -> None:
        stats = cache.stats()
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.hit_rate == 0.0
        assert stats.entry_count == 0

    def test_cleanup_expired(self) -> None:
        cache = Cache(ttl_seconds=1)
        cache.set("q1", "r1", "model", 0.01)
        cache.set("q2", "r2", "model", 0.02)
        time.sleep(1.1)
        removed = cache.cleanup_expired()
        assert removed == 2
        assert cache.size == 0

    def test_size_property(self, cache: Cache) -> None:
        assert cache.size == 0
        cache.set("q1", "r1", "model", 0.01)
        assert cache.size == 1
        cache.set("q2", "r2", "model", 0.02)
        assert cache.size == 2

    def test_hit_rate_property(self, cache: Cache) -> None:
        assert cache.hit_rate == 0.0
        cache.set("q1", "r1", "model", 0.01)
        cache.get("q1")
        assert cache.hit_rate > 0.0

    def test_generate_key_deterministic(self, cache: Cache) -> None:
        key1 = cache.generate_key("test query")
        key2 = cache.generate_key("test query")
        assert key1 == key2

    def test_generate_key_different_queries(self, cache: Cache) -> None:
        key1 = cache.generate_key("query A")
        key2 = cache.generate_key("query B")
        assert key1 != key2

    def test_different_queries_different_entries(self, cache: Cache) -> None:
        cache.set("query A", "response A", "model", 0.01)
        cache.set("query B", "response B", "model", 0.02)
        assert cache.get("query A") is not None
        assert cache.get("query B") is not None
        assert cache.get("query A").response == "response A"
        assert cache.get("query B").response == "response B"
