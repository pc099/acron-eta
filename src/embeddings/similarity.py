"""
Cosine similarity utilities for Asahi semantic caching.

Provides vectorized similarity computation between embedding vectors,
used by Tier 2 and Tier 3 caching to determine whether a cached
response is reusable.
"""

import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)


class SimilarityCalculator:
    """Compute cosine similarity between embedding vectors.

    All methods are static -- no state is required.  Vectors are
    expected to be L2-normalised (unit length) so that the dot product
    equals the cosine similarity.
    """

    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            vec1: First embedding vector.
            vec2: Second embedding vector.

        Returns:
            Similarity score in the range ``[-1.0, 1.0]``.
            For normalised vectors the range is ``[0.0, 1.0]``.

        Raises:
            ValueError: If the vectors have different dimensions.
        """
        if vec1.shape != vec2.shape:
            raise ValueError(
                f"Vector dimension mismatch: {vec1.shape} vs {vec2.shape}"
            )

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0.0 or norm2 == 0.0:
            return 0.0

        similarity = float(np.dot(vec1, vec2) / (norm1 * norm2))
        # Clamp to handle floating-point rounding
        return max(-1.0, min(1.0, similarity))

    @staticmethod
    def batch_similarity(
        query: np.ndarray, candidates: List[np.ndarray]
    ) -> List[float]:
        """Compute cosine similarity between a query and multiple candidates.

        Uses vectorized numpy operations for performance.

        Args:
            query: Query embedding vector.
            candidates: List of candidate embedding vectors.

        Returns:
            List of similarity scores, one per candidate, in the
            same order as the input.

        Raises:
            ValueError: If any candidate has a different dimension
                than the query.
        """
        if not candidates:
            return []

        for i, c in enumerate(candidates):
            if c.shape != query.shape:
                raise ValueError(
                    f"Candidate {i} dimension mismatch: "
                    f"{c.shape} vs query {query.shape}"
                )

        # Stack into matrix for vectorised computation
        matrix = np.vstack(candidates)  # shape: (N, D)
        query_norm = np.linalg.norm(query)

        if query_norm == 0.0:
            return [0.0] * len(candidates)

        # Dot products: (N, D) @ (D,) -> (N,)
        dots = matrix @ query
        norms = np.linalg.norm(matrix, axis=1)

        # Avoid division by zero
        safe_norms = np.where(norms == 0.0, 1.0, norms)
        similarities = dots / (safe_norms * query_norm)

        # Zero out where candidate norm was zero
        similarities = np.where(norms == 0.0, 0.0, similarities)

        # Clamp
        similarities = np.clip(similarities, -1.0, 1.0)

        return similarities.tolist()

    @staticmethod
    def above_threshold(similarity: float, threshold: float) -> bool:
        """Check whether a similarity score meets a threshold.

        Args:
            similarity: The computed similarity score.
            threshold: The minimum required similarity.

        Returns:
            ``True`` if ``similarity >= threshold``.
        """
        return similarity >= threshold
