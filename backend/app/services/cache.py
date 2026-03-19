"""Redis cache service — exact match (Tier 1) + Pinecone semantic (Tier 2).

Key schema:
  Exact:    asahio:cache:exact:{org_id}:{query_hash}     → JSON (Redis)
  Semantic: Pinecone index with org_id metadata filter    → vector + metadata

Tier 1 uses Redis for fast exact-match lookups.
Tier 2 uses Pinecone for approximate nearest-neighbor semantic search.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.services.embeddings import embed, get_vector_dim

logger = logging.getLogger(__name__)

# Default TTLs
EXACT_CACHE_TTL = 3600  # 1 hour
SEMANTIC_CACHE_TTL = 3600  # 1 hour
SEMANTIC_THRESHOLD = 0.85  # Minimum cosine similarity for a semantic hit


PROMOTION_THRESHOLD = 0.95  # Semantic hits above this get promoted to exact


@dataclass
class CacheMetrics:
    """Tracks cache hit/miss statistics."""

    exact_hits: int = 0
    semantic_hits: int = 0
    misses: int = 0
    promotions: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.exact_hits + self.semantic_hits + self.misses
        if total == 0:
            return 0.0
        return (self.exact_hits + self.semantic_hits) / total

    def to_dict(self) -> dict:
        return {
            "exact_hits": self.exact_hits,
            "semantic_hits": self.semantic_hits,
            "misses": self.misses,
            "promotions": self.promotions,
            "hit_rate": round(self.hit_rate, 4),
        }


@dataclass
class CacheHit:
    """A cache hit result with metadata."""

    response: str
    model_used: str
    cache_tier: str  # "exact" or "semantic"
    similarity: Optional[float] = None
    cached_at: Optional[str] = None
    dependency_level: Optional[str] = None
    cache_age_seconds: float = 0.0


class RedisCache:
    """Org-scoped Redis cache with exact + semantic tiers."""

    def __init__(self, redis_client, pinecone_index=None):
        self._redis = redis_client
        self._pinecone_index = pinecone_index
        self._metrics = CacheMetrics()

    @property
    def metrics(self) -> CacheMetrics:
        return self._metrics

    # —— Pinecone lazy init ————————————————————

    def _get_pinecone_index(self):
        """Return the Pinecone index, initialising lazily if needed."""
        if self._pinecone_index is not None:
            return self._pinecone_index

        try:
            from app.config import get_settings

            settings = get_settings()
            if not settings.pinecone_api_key:
                logger.debug("Pinecone API key not set — semantic cache disabled")
                return None

            from pinecone import Pinecone

            pc = Pinecone(api_key=settings.pinecone_api_key)
            # Prefer host (skips describe_index call) over name lookup
            if settings.pinecone_host:
                self._pinecone_index = pc.Index(host=settings.pinecone_host)
                logger.info("Connected to Pinecone via host: %s", settings.pinecone_host)
            else:
                self._pinecone_index = pc.Index(settings.pinecone_index_name)
                logger.info("Connected to Pinecone index: %s", settings.pinecone_index_name)
            return self._pinecone_index
        except Exception as exc:
            logger.warning("Could not connect to Pinecone — semantic cache disabled: %s", exc)
            return None

    # —— Exact Cache (Tier 1) —————————————————

    async def exact_get(self, org_id: str, query: str) -> Optional[CacheHit]:
        """Look up an exact-match cached response."""
        key = self._exact_key(org_id, query)
        try:
            data = await self._redis.get(key)
            if data:
                parsed = json.loads(data)
                return CacheHit(
                    response=parsed["response"],
                    model_used=parsed.get("model_used", "cached"),
                    cache_tier="exact",
                    similarity=1.0,
                    cached_at=parsed.get("cached_at"),
                )
        except Exception:
            logger.exception("Exact cache get failed for org %s", org_id)
        return None

    async def exact_set(
        self,
        org_id: str,
        query: str,
        response: str,
        model_used: str,
        ttl: int = EXACT_CACHE_TTL,
    ) -> None:
        """Store an exact-match response in cache."""
        key = self._exact_key(org_id, query)
        data = json.dumps({
            "response": response,
            "model_used": model_used,
            "query": query,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            await self._redis.set(key, data, ex=ttl)
        except Exception:
            logger.exception("Exact cache set failed for org %s", org_id)

    def _exact_key(
        self, org_id: str, query: str, dependency_suffix: str = "",
    ) -> str:
        key_input = query.strip().lower() + dependency_suffix
        query_hash = hashlib.sha256(key_input.encode()).hexdigest()
        return f"asahio:cache:exact:{org_id}:{query_hash}"

    # —— Semantic Cache (Tier 2 — Pinecone) ——————————

    async def semantic_get(
        self,
        org_id: str,
        query: str,
        model: Optional[str] = None,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> Optional[CacheHit]:
        """Search for a semantically similar cached response via Pinecone."""
        index = self._get_pinecone_index()
        if index is None:
            return None

        try:
            query_vec = embed(query)

            filter_dict: dict = {"org_id": {"$eq": org_id}}
            if model:
                filter_dict["model"] = {"$eq": model}

            results = index.query(
                vector=query_vec,
                top_k=1,
                namespace=org_id,
                filter=filter_dict,
                include_metadata=True,
            )

            if results.get("matches"):
                match = results["matches"][0]
                similarity = float(match["score"])

                if similarity >= threshold:
                    meta = match.get("metadata", {})
                    return CacheHit(
                        response=meta.get("response", ""),
                        model_used=meta.get("model", "cached"),
                        cache_tier="semantic",
                        similarity=round(similarity, 4),
                        cached_at=meta.get("cached_at"),
                    )

        except Exception:
            logger.exception("Semantic cache get failed for org %s", org_id)

        return None

    async def semantic_set(
        self,
        org_id: str,
        query: str,
        response: str,
        model_used: str,
        ttl: int = SEMANTIC_CACHE_TTL,
    ) -> None:
        """Store a response with its embedding vector in Pinecone."""
        index = self._get_pinecone_index()
        if index is None:
            return

        try:
            embedding = embed(query)
            query_hash = hashlib.md5(query.encode()).hexdigest()
            vector_id = f"{org_id}:{query_hash}"

            index.upsert(
                vectors=[(
                    vector_id,
                    embedding,
                    {
                        "org_id": org_id,
                        "model": model_used,
                        "query": query,
                        "response": response,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    },
                )],
                namespace=org_id,
            )
        except Exception:
            logger.exception("Semantic cache set failed for org %s", org_id)

    # —— Combined Lookup ———————————————————————

    async def get(
        self,
        org_id: str,
        query: str,
        model: Optional[str] = None,
    ) -> Optional[CacheHit]:
        """Try exact cache first, then semantic cache."""
        # Tier 1: exact match
        hit = await self.exact_get(org_id, query)
        if hit:
            self._metrics.exact_hits += 1
            return hit

        # Tier 2: semantic similarity
        hit = await self.semantic_get(org_id, query, model=model)
        if hit:
            self._metrics.semantic_hits += 1
            # Promote high-similarity semantic hits to exact cache
            if hit.similarity is not None and hit.similarity >= PROMOTION_THRESHOLD:
                try:
                    key = self._exact_key(org_id, query)
                    data = json.dumps({
                        "response": hit.response,
                        "model_used": hit.model_used,
                        "query": query,
                        "cached_at": datetime.now(timezone.utc).isoformat(),
                    })
                    await self._redis.set(key, data, ex=EXACT_CACHE_TTL)
                    self._metrics.promotions += 1
                    logger.info(
                        "Promoted semantic hit to exact cache: org=%s similarity=%.4f",
                        org_id, hit.similarity,
                    )
                except Exception:
                    logger.exception("Cache promotion failed for org %s", org_id)
            return hit

        self._metrics.misses += 1
        return None

    async def set(
        self,
        org_id: str,
        query: str,
        response: str,
        model_used: str,
        dependency_level: Optional[str] = None,
    ) -> None:
        """Store in both exact and semantic caches."""
        await self.exact_set(org_id, query, response, model_used)
        await self.semantic_set(org_id, query, response, model_used)

    async def warm(
        self,
        org_id: str,
        entries: list[dict],
        ttl: int = EXACT_CACHE_TTL,
    ) -> int:
        """Pre-populate exact cache from a list of entries.

        Each entry must have keys: query, response, model_used.
        Returns the number of entries successfully cached.
        """
        cached = 0
        for entry in entries:
            try:
                key = self._exact_key(org_id, entry["query"])
                data = json.dumps({
                    "response": entry["response"],
                    "model_used": entry["model_used"],
                    "query": entry["query"],
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                })
                await self._redis.set(key, data, ex=ttl)
                cached += 1
            except Exception:
                logger.exception("Cache warm failed for org %s query=%s", org_id, entry.get("query", "?"))
        return cached

    # -- Context-Aware Cache -------------------------------------------------

    async def context_get(
        self,
        org_id: str,
        query: str,
        dependency_level: str,
        model: Optional[str] = None,
        session_step: Optional[int] = None,
        coherence_validator=None,
    ) -> Optional[CacheHit]:
        """Context-aware cache lookup.

        Applies dependency classification to determine whether and how to
        use cached results:
        - CRITICAL: always skip cache
        - INDEPENDENT: standard lookup (exact -> semantic)
        - PARTIAL/DEPENDENT: lookup + coherence validation on hits
        """
        from app.services.dependency_classifier import DependencyLevel

        if dependency_level == DependencyLevel.CRITICAL:
            logger.debug("Cache skip: CRITICAL dependency for org %s", org_id)
            return None

        # Build dependency fingerprint for PARTIAL/DEPENDENT cache key isolation
        dep_suffix = ""
        if dependency_level in (DependencyLevel.PARTIAL, DependencyLevel.DEPENDENT):
            dep_suffix = f":dep:{dependency_level}"
            if session_step is not None:
                dep_suffix += f":step:{session_step}"

        # Use fingerprinted key for exact lookup when dependent
        if dep_suffix:
            key = self._exact_key(org_id, query, dependency_suffix=dep_suffix)
            try:
                data = await self._redis.get(key)
                if data:
                    parsed = json.loads(data)
                    hit = CacheHit(
                        response=parsed["response"],
                        model_used=parsed.get("model_used", "cached"),
                        cache_tier="exact",
                        similarity=1.0,
                        cached_at=parsed.get("cached_at"),
                    )
                else:
                    hit = None
            except Exception:
                hit = None
            # Fall back to standard lookup if fingerprinted miss
            if not hit:
                hit = await self.get(org_id, query, model=model)
        else:
            hit = await self.get(org_id, query, model=model)
        if not hit:
            return None

        # Calculate cache age
        cache_age = 0.0
        if hit.cached_at:
            try:
                cached_dt = datetime.fromisoformat(hit.cached_at)
                cache_age = (datetime.now(timezone.utc) - cached_dt).total_seconds()
            except (ValueError, TypeError):
                pass
        hit.cache_age_seconds = cache_age
        hit.dependency_level = dependency_level

        # For INDEPENDENT requests, return cache hit without coherence check
        if dependency_level == DependencyLevel.INDEPENDENT:
            return hit

        # For PARTIAL/DEPENDENT, run coherence validation if validator provided
        if coherence_validator and hit.response:
            result = coherence_validator.validate(
                request_prompt=query,
                cached_response=hit.response,
                cache_age_seconds=cache_age,
                request_step=session_step,
            )
            if not result.is_coherent:
                logger.info(
                    "Cache rejected by coherence validator: failed=%s score=%.4f",
                    result.failed_checks, result.score,
                )
                return None

        return hit
