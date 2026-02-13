"""
Exact-match caching layer for Asahi inference optimizer (Tier 1).

Stores and retrieves inference responses keyed by MD5 hash of the
user query.  Ignores system prompts.  Enforces TTL-based expiration.
Tracks hit/miss statistics.
"""

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from pydantic import BaseModel, Field

from src.config import get_settings

logger = logging.getLogger(__name__)


class CacheEntry(BaseModel):
    """A single cached inference response.

    Attributes:
        cache_key: MD5 hex digest of the original query.
        query: The original user query text.
        response: Cached response text.
        model: Model that produced the response.
        cost: Dollar cost of the original inference call.
        created_at: UTC timestamp when the entry was stored.
        expires_at: UTC timestamp when the entry becomes stale.
        access_count: Number of times this entry has been served.
    """

    cache_key: str
    query: str
    response: str
    model: str
    cost: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0


class CacheStats(BaseModel):
    """Aggregate cache statistics.

    Attributes:
        hits: Total cache hit count.
        misses: Total cache miss count.
        hit_rate: Ratio of hits to total lookups (0.0 if no lookups).
        entry_count: Current number of entries in the cache.
        total_cost_saved: Sum of original costs for all cache hits.
    """

    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    entry_count: int = 0
    total_cost_saved: float = 0.0


class Cache:
    """In-memory exact-match cache with TTL expiration.

    Uses MD5 hash of the user query as the cache key.  System prompts
    are intentionally excluded to maximize hit rate.

    Args:
        ttl_seconds: Time-to-live for cache entries in seconds.
            Defaults to 86400 (24 hours).
    """

    def __init__(self, ttl_seconds: Optional[int] = None) -> None:
        self._store: Dict[str, CacheEntry] = {}
        self._ttl_seconds = ttl_seconds if ttl_seconds is not None else get_settings().cache.ttl_seconds
        self._hits: int = 0
        self._misses: int = 0
        self._total_cost_saved: float = 0.0

    def generate_key(self, query: str) -> str:
        """Generate a deterministic MD5 cache key from a query string.

        Args:
            query: The user query to hash.

        Returns:
            Hex-encoded MD5 digest.
        """
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def get(self, query: str) -> Optional[CacheEntry]:
        """Look up a cached response by query.

        If the entry exists but has expired, it is deleted and counted
        as a miss.  On a hit the ``access_count`` is incremented.

        Args:
            query: The user query to look up.

        Returns:
            The CacheEntry on a hit, or ``None`` on a miss.
        """
        key = self.generate_key(query)
        entry = self._store.get(key)

        if entry is None:
            self._misses += 1
            return None

        now = datetime.now(timezone.utc)
        if now >= entry.expires_at:
            del self._store[key]
            self._misses += 1
            logger.debug(
                "Cache entry expired",
                extra={"cache_key": key, "query_prefix": query[:40]},
            )
            return None

        entry.access_count += 1
        self._hits += 1
        self._total_cost_saved += entry.cost
        logger.debug(
            "Cache hit",
            extra={
                "cache_key": key,
                "access_count": entry.access_count,
            },
        )
        return entry

    def set(
        self,
        query: str,
        response: str,
        model: str,
        cost: float,
    ) -> CacheEntry:
        """Store a new cache entry.

        Args:
            query: The user query (must not be empty).
            response: The response text to cache.
            model: The model that produced the response.
            cost: Dollar cost of the original inference call.

        Returns:
            The newly created CacheEntry.

        Raises:
            ValueError: If the query is empty.
        """
        if not query or not query.strip():
            raise ValueError("Query must not be empty")

        key = self.generate_key(query)
        now = datetime.now(timezone.utc)

        if key in self._store:
            logger.warning(
                "Cache key collision or overwrite",
                extra={
                    "cache_key": key,
                    "old_query_prefix": self._store[key].query[:40],
                    "new_query_prefix": query[:40],
                },
            )

        entry = CacheEntry(
            cache_key=key,
            query=query,
            response=response,
            model=model,
            cost=cost,
            created_at=now,
            expires_at=now + timedelta(seconds=self._ttl_seconds),
            access_count=0,
        )
        self._store[key] = entry
        logger.debug("Cache set", extra={"cache_key": key})
        return entry

    def invalidate(self, query: str) -> bool:
        """Remove a cache entry by query.

        Args:
            query: The query whose entry should be removed.

        Returns:
            ``True`` if an entry was removed, ``False`` otherwise.
        """
        key = self.generate_key(query)
        if key in self._store:
            del self._store[key]
            logger.info("Cache entry invalidated", extra={"cache_key": key})
            return True
        return False

    def clear(self) -> int:
        """Remove all entries from the cache.

        Returns:
            Number of entries removed.
        """
        count = len(self._store)
        self._store.clear()
        logger.info("Cache cleared", extra={"entries_removed": count})
        return count

    def stats(self) -> CacheStats:
        """Return aggregate cache statistics.

        Returns:
            CacheStats with current hit/miss counts and derived metrics.
        """
        total = self._hits + self._misses
        return CacheStats(
            hits=self._hits,
            misses=self._misses,
            hit_rate=self._hits / total if total > 0 else 0.0,
            entry_count=len(self._store),
            total_cost_saved=round(self._total_cost_saved, 6),
        )

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        Returns:
            Number of entries removed.
        """
        now = datetime.now(timezone.utc)
        expired_keys = [
            key
            for key, entry in self._store.items()
            if now >= entry.expires_at
        ]
        for key in expired_keys:
            del self._store[key]

        if expired_keys:
            logger.info(
                "Expired entries cleaned up",
                extra={"count": len(expired_keys)},
            )
        return len(expired_keys)

    @property
    def size(self) -> int:
        """Current number of entries in the cache."""
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        """Current hit rate as a float between 0.0 and 1.0."""
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0
