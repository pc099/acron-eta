"""
Caching layer for Asahi inference optimizer.

Provides deterministic prompt-based caching to avoid redundant API calls.
"""

import hashlib
import time


def generate_cache_key(prompt: str) -> str:
    """Generate a stable MD5 hash for prompt caching."""
    return hashlib.md5(prompt.encode("utf-8")).hexdigest()


class InferenceCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._store: dict[str, dict] = {}
        self._timestamps: dict[str, float] = {}
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0

    def get(self, prompt: str) -> dict | None:
        """Look up a cached result by prompt. Returns None on miss."""
        key = generate_cache_key(prompt)
        if key in self._store:
            # Check TTL
            if time.time() - self._timestamps[key] > self.ttl_seconds:
                del self._store[key]
                del self._timestamps[key]
                self.misses += 1
                return None
            self.hits += 1
            return self._store[key]
        self.misses += 1
        return None

    def put(self, prompt: str, result: dict) -> None:
        """Store a result in the cache."""
        key = generate_cache_key(prompt)
        self._store[key] = result
        self._timestamps[key] = time.time()

    def clear(self) -> None:
        """Clear all cached entries."""
        self._store.clear()
        self._timestamps.clear()
        self.hits = 0
        self.misses = 0

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total
