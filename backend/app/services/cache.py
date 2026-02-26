"""Redis cache service — exact match (Tier 1) + semantic (Tier 2).

Key schema:
  Exact:    asahi:cache:exact:{org_id}:{query_hash}     → JSON
  Semantic: asahi:cache:semantic:{org_id}:{embedding_md5} → JSON (with vector)

Semantic cache uses Redis Stack Vector Search (RediSearch) for
approximate nearest-neighbor lookup with cosine similarity.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from app.services.embeddings import VECTOR_DIM, embed, embed_to_bytes

logger = logging.getLogger(__name__)

# Default TTLs
EXACT_CACHE_TTL = 3600  # 1 hour
SEMANTIC_CACHE_TTL = 3600  # 1 hour
SEMANTIC_THRESHOLD = 0.85  # Minimum cosine similarity for a semantic hit

SEMANTIC_INDEX_NAME = "asahi_semantic_cache"


@dataclass
class CacheHit:
    """A cache hit result with metadata."""

    response: str
    model_used: str
    cache_tier: str  # "exact" or "semantic"
    similarity: Optional[float] = None
    cached_at: Optional[str] = None


class RedisCache:
    """Org-scoped Redis cache with exact + semantic tiers."""

    def __init__(self, redis_client):
        self._redis = redis_client

    # ── Exact Cache (Tier 1) ─────────────────

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

    def _exact_key(self, org_id: str, query: str) -> str:
        query_hash = hashlib.sha256(query.strip().lower().encode()).hexdigest()
        return f"asahi:cache:exact:{org_id}:{query_hash}"

    # ── Semantic Cache (Tier 2) ──────────────

    async def setup_semantic_index(self) -> None:
        """Create the Redis vector search index if it doesn't exist."""
        try:
            await self._redis.ft(SEMANTIC_INDEX_NAME).info()
            logger.info("Semantic cache index already exists")
        except Exception:
            try:
                from redis.commands.search.field import TextField, VectorField
                from redis.commands.search.indexDefinition import (
                    IndexDefinition,
                    IndexType,
                )

                schema = (
                    TextField("$.org_id", as_name="org_id"),
                    TextField("$.model", as_name="model"),
                    VectorField(
                        "$.embedding",
                        "HNSW",
                        {
                            "TYPE": "FLOAT32",
                            "DIM": VECTOR_DIM,
                            "DISTANCE_METRIC": "COSINE",
                        },
                        as_name="embedding",
                    ),
                )
                await self._redis.ft(SEMANTIC_INDEX_NAME).create_index(
                    schema,
                    definition=IndexDefinition(
                        prefix=["asahi:cache:semantic:"],
                        index_type=IndexType.JSON,
                    ),
                )
                logger.info("Created semantic cache vector index")
            except Exception:
                logger.warning("Could not create semantic index — semantic cache disabled")

    async def semantic_get(
        self,
        org_id: str,
        query: str,
        model: Optional[str] = None,
        threshold: float = SEMANTIC_THRESHOLD,
    ) -> Optional[CacheHit]:
        """Search for a semantically similar cached response.

        1. Embed the query locally (~3ms)
        2. Vector search in Redis for org_id match + similarity > threshold
        3. Return cached response if found
        """
        try:
            from redis.commands.search.query import Query

            query_vec = embed_to_bytes(query)

            # Build filter: always filter by org_id
            filter_str = f"@org_id:{{{org_id}}}"
            if model:
                filter_str += f" @model:{{{model}}}"

            search_query = (
                Query(f"{filter_str}=>[KNN 1 @embedding $vec AS score]")
                .sort_by("score")
                .return_fields("response", "model", "score", "cached_at")
                .dialect(2)
            )

            results = await self._redis.ft(SEMANTIC_INDEX_NAME).search(
                search_query,
                query_params={"vec": query_vec},
            )

            if results.docs:
                doc = results.docs[0]
                # Redis COSINE distance: 0 = identical, 2 = opposite
                # Convert to similarity: similarity = 1 - distance
                distance = float(doc.score)
                similarity = 1.0 - distance

                if similarity >= threshold:
                    return CacheHit(
                        response=doc.response,
                        model_used=doc.model if hasattr(doc, "model") else "cached",
                        cache_tier="semantic",
                        similarity=round(similarity, 4),
                        cached_at=doc.cached_at if hasattr(doc, "cached_at") else None,
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
        """Store a response with its embedding vector for semantic search."""
        try:
            embedding = embed(query)
            query_hash = hashlib.md5(query.encode()).hexdigest()
            key = f"asahi:cache:semantic:{org_id}:{query_hash}"

            await self._redis.json().set(
                key,
                "$",
                {
                    "org_id": org_id,
                    "model": model_used,
                    "query": query,
                    "embedding": embedding,
                    "response": response,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            await self._redis.expire(key, ttl)
        except Exception:
            logger.exception("Semantic cache set failed for org %s", org_id)

    # ── Combined Lookup ──────────────────────

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
            return hit

        # Tier 2: semantic similarity
        hit = await self.semantic_get(org_id, query, model=model)
        if hit:
            return hit

        return None

    async def set(
        self,
        org_id: str,
        query: str,
        response: str,
        model_used: str,
    ) -> None:
        """Store in both exact and semantic caches."""
        await self.exact_set(org_id, query, response, model_used)
        await self.semantic_set(org_id, query, response, model_used)
