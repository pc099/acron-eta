"""
Redis-backed Tier 1 exact-match cache for Asahi.

Implements the same interface as the in-memory Cache in exact.py so the
optimizer can use either backend. Uses REDIS_URL from environment.
Keys: asahi:t1:{md5(query)} for entries; asahi:t1:hits, asahi:t1:misses for stats.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.cache.exact import CacheEntry, CacheStats

logger = logging.getLogger(__name__)

# Optional Redis import; fail at runtime if redis not installed when REDIS_URL is set
try:
    import redis  # type: ignore[import-untyped]
except ImportError:
    redis = None  # type: ignore[assignment]


def _serialize_entry(entry: CacheEntry) -> str:
    """Serialize CacheEntry to JSON for Redis storage."""
    return entry.model_dump_json()


def _deserialize_entry(data: str) -> CacheEntry:
    """Deserialize JSON from Redis to CacheEntry."""
    obj = json.loads(data)
    for time_field in ("created_at", "expires_at"):
        if time_field in obj and obj[time_field]:
            obj[time_field] = datetime.fromisoformat(
                obj[time_field].replace("Z", "+00:00")
            )
    return CacheEntry.model_validate(obj)


class RedisCache:
    """Redis-backed exact-match cache (Tier 1).

    Same public interface as src.cache.exact.Cache: get, set, stats,
    generate_key, invalidate, clear. Use when REDIS_URL is set for
    persistence and multi-instance consistency.

    Args:
        redis_url: Redis connection URL (e.g. redis://localhost:6379/0).
        ttl_seconds: Time-to-live for cache entries in seconds.
        key_prefix: Prefix for all keys (default asahi:t1).
    """

    KEY_PREFIX = "asahi:t1"
    HITS_KEY = "asahi:t1:hits"
    MISSES_KEY = "asahi:t1:misses"

    def __init__(
        self,
        redis_url: str,
        ttl_seconds: int = 86400,
        key_prefix: str = "asahi:t1",
        _redis_client: Optional[Any] = None,
    ) -> None:
        if redis is None:
            raise ImportError(
                "redis package is required for RedisCache. Install with: pip install redis"
            )
        if _redis_client is not None:
            self._client = _redis_client
        else:
            self._client = redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds
        self._key_prefix = key_prefix.rstrip(":")

    def _key(self, cache_key: str) -> str:
        """Return full Redis key for a cache key."""
        return f"{self._key_prefix}:{cache_key}"

    def generate_key(self, query: str, org_id: Optional[str] = None) -> str:
        """Generate a deterministic MD5 cache key from a query string.

        Args:
            query: The user query to hash.
            org_id: Optional org/tenant ID for cache isolation.

        Returns:
            Hex-encoded MD5 digest, optionally prefixed with org_id.
        """
        digest = hashlib.md5(query.encode("utf-8")).hexdigest()
        return f"{org_id}:{digest}" if org_id else digest

    def get(self, query: str, org_id: Optional[str] = None) -> Optional[CacheEntry]:
        """Look up a cached response by query.

        Args:
            query: The user query to look up.

        Returns:
            The CacheEntry on a hit, or None on a miss or on error.
        """
        key = self.generate_key(query, org_id)
        rkey = self._key(key)
        try:
            data = self._client.get(rkey)
        except Exception as e:
            logger.warning(
                "Redis get failed",
                extra={"cache_key": key, "error": str(e)},
            )
            self._client.incr(self.MISSES_KEY)
            return None

        if data is None:
            self._client.incr(self.MISSES_KEY)
            return None

        try:
            entry = _deserialize_entry(data)
        except Exception as e:
            logger.warning(
                "Redis entry deserialize failed",
                extra={"cache_key": key, "error": str(e)},
            )
            self._client.delete(rkey)
            self._client.incr(self.MISSES_KEY)
            return None

        # Check expiry in-app (Redis TTL may have been extended by other logic)
        now = datetime.now(timezone.utc)
        if now >= entry.expires_at:
            try:
                self._client.delete(rkey)
            except Exception:
                pass
            self._client.incr(self.MISSES_KEY)
            return None

        entry.access_count += 1
        self._client.incr(self.HITS_KEY)
        # Re-save with updated access_count (optional; not required for correctness)
        try:
            self._client.setex(
                rkey,
                self._ttl_seconds,
                _serialize_entry(entry),
            )
        except Exception:
            pass
        logger.debug(
            "Cache hit",
            extra={"cache_key": key, "access_count": entry.access_count},
        )
        return entry

    def set(
        self,
        query: str,
        response: str,
        model: str,
        cost: float,
        org_id: Optional[str] = None,
    ) -> CacheEntry:
        """Store a new cache entry in Redis.

        Args:
            query: The user query (must not be empty).
            response: The response text to cache.
            model: The model that produced the response.
            cost: Dollar cost of the original inference call.
            org_id: Optional org/tenant ID for cache isolation.

        Returns:
            The newly created CacheEntry.

        Raises:
            ValueError: If the query is empty.
        """
        if not query or not query.strip():
            raise ValueError("Query must not be empty")

        key = self.generate_key(query, org_id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl_seconds)
        entry = CacheEntry(
            cache_key=key,
            query=query,
            response=response,
            model=model,
            cost=cost,
            created_at=now,
            expires_at=expires_at,
            access_count=0,
        )
        rkey = self._key(key)
        try:
            self._client.setex(
                rkey,
                self._ttl_seconds,
                _serialize_entry(entry),
            )
        except Exception as e:
            logger.error(
                "Redis set failed",
                extra={"cache_key": key, "error": str(e)},
            )
            raise
        logger.debug("Cache set", extra={"cache_key": key})
        return entry

    def invalidate(self, query: str, org_id: Optional[str] = None) -> bool:
        """Remove a cache entry by query.

        Args:
            query: The query whose entry should be removed.
            org_id: Optional org/tenant ID for cache isolation.

        Returns:
            True if an entry was removed, False otherwise.
        """
        key = self.generate_key(query, org_id)
        rkey = self._key(key)
        try:
            deleted = self._client.delete(rkey)
            if deleted:
                logger.info(
                    "Cache entry invalidated",
                    extra={"cache_key": key},
                )
            return bool(deleted)
        except Exception as e:
            logger.warning(
                "Redis delete failed",
                extra={"cache_key": key, "error": str(e)},
            )
            return False

    def clear(self) -> int:
        """Remove all Tier 1 cache entries with our prefix.

        Does not reset hits/misses counters. Returns number of keys deleted.

        Returns:
            Number of entry keys removed (not including stats keys).
        """
        try:
            keys = list(self._client.scan_iter(match=f"{self._key_prefix}:*"))
            # Exclude stats keys
            entry_keys = [
                k for k in keys
                if k not in (self.HITS_KEY, self.MISSES_KEY)
            ]
            if entry_keys:
                self._client.delete(*entry_keys)
            logger.info(
                "Cache cleared",
                extra={"entries_removed": len(entry_keys)},
            )
            return len(entry_keys)
        except Exception as e:
            logger.error("Redis clear failed", extra={"error": str(e)})
            return 0

    def stats(self) -> CacheStats:
        """Return aggregate cache statistics.

        Uses Redis keys for entry count and in-Redis hit/miss counters.
        Hit rate is derived from hits and misses.

        Returns:
            CacheStats with hits, misses, hit_rate, entry_count, total_cost_saved.
        """
        try:
            hits = int(self._client.get(self.HITS_KEY) or 0)
            misses = int(self._client.get(self.MISSES_KEY) or 0)
        except Exception:
            hits = 0
            misses = 0
        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0
        try:
            entry_keys = [
                k
                for k in self._client.scan_iter(
                    match=f"{self._key_prefix}:*"
                )
                if k not in (self.HITS_KEY, self.MISSES_KEY)
            ]
            count = len(entry_keys)
        except Exception:
            count = 0
        # total_cost_saved not stored in Redis; we could maintain a key but skip for simplicity
        return CacheStats(
            hits=hits,
            misses=misses,
            hit_rate=hit_rate,
            entry_count=count,
            total_cost_saved=0.0,
        )
