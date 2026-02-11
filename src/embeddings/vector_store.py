"""
Vector database abstraction for Asahi semantic caching.

Provides a backend-agnostic Protocol plus an in-memory implementation
for development/testing and a Pinecone implementation for production.
"""

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field

from src.exceptions import VectorDBError

logger = logging.getLogger(__name__)


class VectorDBEntry(BaseModel):
    """An entry to upsert into the vector database.

    Attributes:
        vector_id: Unique identifier for this vector.
        embedding: The embedding vector as a list of floats.
        metadata: Arbitrary metadata to store alongside the vector.
    """

    vector_id: str
    embedding: List[float]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VectorSearchResult(BaseModel):
    """A single result from a vector similarity search.

    Attributes:
        vector_id: Identifier of the matched vector.
        score: Cosine similarity score (0.0 to 1.0 for normalised vectors).
        metadata: Stored metadata for the matched vector.
    """

    vector_id: str
    score: float
    metadata: Dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class VectorDatabase(Protocol):
    """Protocol for vector database backends.

    Any backend must implement upsert, query, delete, and count.
    """

    def upsert(self, entries: List[VectorDBEntry]) -> int:
        """Insert or update vectors. Return count of upserted entries."""
        ...

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """Find the top-k most similar vectors."""
        ...

    def delete(self, vector_ids: List[str]) -> int:
        """Delete vectors by ID. Return count of deleted entries."""
        ...

    def count(self) -> int:
        """Return total number of stored vectors."""
        ...


class InMemoryVectorDB:
    """In-memory vector database using brute-force cosine search.

    Suitable for development and testing.  Not recommended for
    production workloads above ~10 000 vectors.
    """

    def __init__(self) -> None:
        self._vectors: Dict[str, np.ndarray] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}

    def upsert(self, entries: List[VectorDBEntry]) -> int:
        """Insert or update vectors.

        Args:
            entries: List of entries to upsert.

        Returns:
            Number of entries upserted.

        Raises:
            VectorDBError: If embedding dimensions are inconsistent.
        """
        count = 0
        for entry in entries:
            vec = np.array(entry.embedding, dtype=np.float32)

            # Validate dimension consistency
            if self._vectors and entry.vector_id not in self._vectors:
                existing_dim = next(iter(self._vectors.values())).shape[0]
                if vec.shape[0] != existing_dim:
                    raise VectorDBError(
                        f"Dimension mismatch: expected {existing_dim}, "
                        f"got {vec.shape[0]}"
                    )

            self._vectors[entry.vector_id] = vec
            self._metadata[entry.vector_id] = entry.metadata
            count += 1

        logger.debug("Vectors upserted", extra={"count": count})
        return count

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[VectorSearchResult]:
        """Find the top-k most similar vectors using brute-force cosine search.

        Args:
            embedding: Query embedding vector.
            top_k: Maximum number of results to return.
            filter: Optional metadata filter (key-value exact match).

        Returns:
            List of VectorSearchResult sorted by similarity (highest first).
        """
        if not self._vectors:
            return []

        query_vec = np.array(embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        results: List[VectorSearchResult] = []

        for vid, vec in self._vectors.items():
            # Apply metadata filter
            if filter:
                meta = self._metadata.get(vid, {})
                if not all(meta.get(k) == v for k, v in filter.items()):
                    continue

            vec_norm = np.linalg.norm(vec)
            if vec_norm == 0:
                continue

            score = float(np.dot(query_vec, vec) / (query_norm * vec_norm))
            score = max(0.0, min(1.0, score))

            results.append(
                VectorSearchResult(
                    vector_id=vid,
                    score=score,
                    metadata=self._metadata.get(vid, {}),
                )
            )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def delete(self, vector_ids: List[str]) -> int:
        """Delete vectors by ID.

        Args:
            vector_ids: IDs to delete.

        Returns:
            Number of actually deleted entries.
        """
        count = 0
        for vid in vector_ids:
            if vid in self._vectors:
                del self._vectors[vid]
                self._metadata.pop(vid, None)
                count += 1

        logger.debug("Vectors deleted", extra={"count": count})
        return count

    def count(self) -> int:
        """Return total number of stored vectors."""
        return len(self._vectors)
