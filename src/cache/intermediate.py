"""
Intermediate result cache (Tier 3) for Asahi.

Caches and retrieves intermediate results (e.g., section summaries)
keyed by composite keys ``(document_id, step_type, intent)``.
This allows different queries that need the same intermediate work
to skip redundant computation.
"""

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from src.cache.workflow import WorkflowStep

logger = logging.getLogger(__name__)


class IntermediateCacheResult(BaseModel):
    """Result of a Tier 3 intermediate cache lookup.

    Attributes:
        hit: Whether a cached result was found.
        result: The cached result text (if hit).
        step_id: The workflow step identifier.
        cache_key: The composite cache key.
    """

    hit: bool = False
    result: Optional[str] = None
    step_id: str = ""
    cache_key: str = ""


class IntermediateCache:
    """Tier 3 cache for intermediate workflow results.

    Stores results keyed by composite keys so that different queries
    requiring the same intermediate work can reuse cached results.

    Args:
        ttl_seconds: Time-to-live for entries (default 24h).
    """

    def __init__(self, ttl_seconds: int = 86400) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._ttl_seconds = ttl_seconds
        self._hits: int = 0
        self._misses: int = 0

    def get(self, cache_key: str) -> Optional[str]:
        """Look up an intermediate result by composite key.

        Args:
            cache_key: The composite cache key.

        Returns:
            The cached result string, or ``None`` on miss.
        """
        entry = self._store.get(cache_key)
        if entry is None:
            self._misses += 1
            return None

        if time.time() - entry["stored_at"] > self._ttl_seconds:
            del self._store[cache_key]
            self._misses += 1
            logger.debug(
                "Tier 3 entry expired",
                extra={"cache_key": cache_key},
            )
            return None

        self._hits += 1
        logger.debug(
            "Tier 3 cache hit",
            extra={"cache_key": cache_key},
        )
        return entry["result"]

    def set(
        self,
        cache_key: str,
        result: str,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        """Store an intermediate result.

        Args:
            cache_key: The composite cache key.
            result: The result to cache.
            metadata: Optional metadata to store alongside.
        """
        self._store[cache_key] = {
            "result": result,
            "metadata": metadata or {},
            "stored_at": time.time(),
        }
        logger.debug(
            "Tier 3 cache set",
            extra={"cache_key": cache_key},
        )

    def invalidate(self, cache_key: str) -> bool:
        """Remove an entry by its composite key.

        Args:
            cache_key: The key to invalidate.

        Returns:
            True if an entry was removed.
        """
        if cache_key in self._store:
            del self._store[cache_key]
            return True
        return False

    def invalidate_by_document(self, document_id: str) -> int:
        """Remove all entries related to a specific document.

        Args:
            document_id: The document identifier.

        Returns:
            Number of entries removed.
        """
        keys_to_remove = [
            k for k in self._store if k.startswith(f"{document_id}:")
        ]
        for key in keys_to_remove:
            del self._store[key]

        if keys_to_remove:
            logger.info(
                "Tier 3 entries invalidated by document",
                extra={
                    "document_id": document_id,
                    "count": len(keys_to_remove),
                },
            )
        return len(keys_to_remove)

    def execute_workflow(
        self,
        steps: List[WorkflowStep],
        executor: Callable[[WorkflowStep], str],
    ) -> List[WorkflowStep]:
        """Execute a workflow, using cache where possible.

        Args:
            steps: The workflow steps to execute.
            executor: Callable that executes a single step.

        Returns:
            The same steps list with ``result`` fields populated.
        """
        for step in steps:
            cached = self.get(step.cache_key)
            if cached is not None:
                step.result = cached
                logger.debug(
                    "Tier 3 workflow cache hit",
                    extra={
                        "step_id": step.step_id,
                        "cache_key": step.cache_key,
                    },
                )
            else:
                step.result = executor(step)
                self.set(
                    step.cache_key,
                    step.result,
                    metadata={
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "document_id": step.document_id,
                    },
                )
                logger.debug(
                    "Tier 3 workflow cache miss; executed and cached",
                    extra={
                        "step_id": step.step_id,
                        "cache_key": step.cache_key,
                    },
                )
        return steps

    def stats(self) -> Dict[str, Any]:
        """Return Tier 3 cache statistics.

        Returns:
            Dict with hit/miss counts, hit rate, and entry count.
        """
        total = self._hits + self._misses
        return {
            "tier": 3,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "entry_count": len(self._store),
        }
