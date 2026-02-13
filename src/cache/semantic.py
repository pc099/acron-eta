"""
Semantic cache (Tier 2) orchestrator for Asahi.

Orchestrates Tier 2 caching: embed the query, search the vector DB
for similar cached queries, evaluate mismatch cost, and return a
cached response or signal a miss.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.embeddings.engine import EmbeddingEngine
from src.embeddings.mismatch import MismatchCostCalculator
from src.embeddings.similarity import SimilarityCalculator
from src.embeddings.threshold import AdaptiveThresholdTuner
from src.embeddings.vector_store import VectorDBEntry, VectorDatabase

logger = logging.getLogger(__name__)


class SemanticCacheResult(BaseModel):
    """Result of a Tier 2 semantic cache lookup.

    Attributes:
        hit: Whether a suitable cached response was found.
        response: The cached response text (if hit).
        similarity: Cosine similarity of the best match (if hit).
        cached_query: The original cached query text (if hit).
        reason: Human-readable explanation of the decision.
    """

    hit: bool = False
    response: Optional[str] = None
    similarity: Optional[float] = None
    cached_query: Optional[str] = None
    reason: str = ""


class SemanticCache:
    """Tier 2 semantic similarity cache.

    Uses embeddings and vector search to find cached responses for
    semantically similar queries.  Economic decisions are made via
    the mismatch cost calculator.

    Args:
        embedding_engine: Engine for generating text embeddings.
        vector_db: Vector database for storage and search.
        similarity_calc: Calculator for cosine similarity.
        mismatch_calc: Calculator for cache-vs-recompute economics.
        threshold_tuner: Tuner for per-task similarity thresholds.
        ttl_seconds: Time-to-live for cached entries (default 24h).
    """

    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        vector_db: VectorDatabase,
        similarity_calc: SimilarityCalculator,
        mismatch_calc: MismatchCostCalculator,
        threshold_tuner: AdaptiveThresholdTuner,
        ttl_seconds: int = 86400,
    ) -> None:
        self._embedder = embedding_engine
        self._db = vector_db
        self._similarity = similarity_calc
        self._mismatch = mismatch_calc
        self._tuner = threshold_tuner
        self._ttl_seconds = ttl_seconds
        self._hits: int = 0
        self._misses: int = 0

    def get(
        self,
        query: str,
        task_type: str = "general",
        cost_sensitivity: str = "medium",
        recompute_cost: float = 0.01,
    ) -> SemanticCacheResult:
        """Look up a semantically similar cached response.

        Args:
            query: The user query to look up.
            task_type: Detected task category.
            cost_sensitivity: How aggressively to cache (high/medium/low).
            recompute_cost: Estimated dollar cost of a fresh inference.

        Returns:
            SemanticCacheResult indicating hit or miss.
        """
        try:
            query_embedding = self._embedder.embed_text(query)
        except Exception as exc:
            logger.error(
                "Failed to embed query for semantic cache lookup",
                extra={"error": str(exc)},
            )
            self._misses += 1
            return SemanticCacheResult(
                hit=False, reason=f"Embedding failed: {exc}"
            )

        results = self._db.query(
            embedding=query_embedding.tolist(), top_k=5
        )

        if not results:
            self._misses += 1
            return SemanticCacheResult(
                hit=False, reason="No entries in vector DB"
            )

        # Use the most lenient threshold from either the query's task type
        # or the cached entry's task type to handle semantically identical queries
        # that were detected as different task types
        threshold = self._tuner.get_threshold(task_type, cost_sensitivity)

        for result in results:
            # Check similarity against threshold
            if not self._similarity.above_threshold(result.score, threshold):
                # Also check against the cached entry's task type threshold
                # This handles cases where semantically identical queries are
                # detected as different task types (e.g., "What is X?" vs "Explain X")
                cached_task_type = result.metadata.get("task_type", task_type)
                if cached_task_type != task_type:
                    cached_threshold = self._tuner.get_threshold(
                        cached_task_type, cost_sensitivity
                    )
                    # Use the more lenient (lower) threshold
                    threshold = min(threshold, cached_threshold)
                    if not self._similarity.above_threshold(result.score, threshold):
                        continue
                else:
                    continue

            should_cache, reason = self._mismatch.should_use_cache(
                similarity=result.score,
                task_type=task_type,
                recompute_cost=recompute_cost,
            )

            if should_cache:
                self._hits += 1
                cached_response = result.metadata.get("response", "")
                cached_query = result.metadata.get("query", "")

                logger.info(
                    "Tier 2 cache hit",
                    extra={
                        "similarity": round(result.score, 4),
                        "task_type": task_type,
                        "cached_query_prefix": cached_query[:40],
                    },
                )

                return SemanticCacheResult(
                    hit=True,
                    response=cached_response,
                    similarity=round(result.score, 4),
                    cached_query=cached_query,
                    reason=reason,
                )

        self._misses += 1
        return SemanticCacheResult(
            hit=False,
            reason=(
                f"No sufficiently similar cached query "
                f"(best={results[0].score:.3f}, threshold={threshold})"
            ),
        )

    def set(
        self,
        query: str,
        response: str,
        model: str,
        cost: float,
        task_type: str = "general",
    ) -> None:
        """Store a query-response pair in the semantic cache.

        Args:
            query: The user query.
            response: The LLM response.
            model: Model that produced the response.
            cost: Dollar cost of the inference.
            task_type: Detected task category.
        """
        try:
            embedding = self._embedder.embed_text(query)
        except Exception as exc:
            logger.error(
                "Failed to embed query for semantic cache set",
                extra={"error": str(exc)},
            )
            return

        now = datetime.now(timezone.utc)
        vector_id = uuid.uuid4().hex[:16]

        entry = VectorDBEntry(
            vector_id=vector_id,
            embedding=embedding.tolist(),
            metadata={
                "query": query,
                "response": response,
                "model": model,
                "cost": cost,
                "task_type": task_type,
                "created_at": now.isoformat(),
                "expires_at": (
                    now + timedelta(seconds=self._ttl_seconds)
                ).isoformat(),
            },
        )

        self._db.upsert([entry])
        logger.debug(
            "Tier 2 cache set",
            extra={
                "vector_id": vector_id,
                "task_type": task_type,
            },
        )

    def invalidate(self, query: str) -> bool:
        """Remove a cached entry by re-embedding and finding the closest match.

        Args:
            query: The query whose entry should be removed.

        Returns:
            True if an entry was removed.
        """
        try:
            embedding = self._embedder.embed_text(query)
        except Exception:
            return False

        results = self._db.query(embedding=embedding.tolist(), top_k=1)
        if results and results[0].score > 0.99:
            self._db.delete([results[0].vector_id])
            return True
        return False

    def stats(self) -> Dict[str, Any]:
        """Return Tier 2 cache statistics.

        Returns:
            Dict with hit/miss counts, hit rate, and entry count.
        """
        total = self._hits + self._misses
        return {
            "tier": 2,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "entry_count": self._db.count(),
        }
