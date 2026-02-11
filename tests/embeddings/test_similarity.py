"""Tests for SimilarityCalculator."""

import numpy as np
import pytest

from src.embeddings.similarity import SimilarityCalculator


class TestCosineSimilarity:
    """Tests for cosine_similarity."""

    def test_identical_vectors(self) -> None:
        vec = np.array([1.0, 0.0, 0.0])
        assert SimilarityCalculator.cosine_similarity(vec, vec) == pytest.approx(1.0)

    def test_orthogonal_vectors(self) -> None:
        v1 = np.array([1.0, 0.0, 0.0])
        v2 = np.array([0.0, 1.0, 0.0])
        assert SimilarityCalculator.cosine_similarity(v1, v2) == pytest.approx(0.0)

    def test_opposite_vectors(self) -> None:
        v1 = np.array([1.0, 0.0])
        v2 = np.array([-1.0, 0.0])
        assert SimilarityCalculator.cosine_similarity(v1, v2) == pytest.approx(-1.0)

    def test_similar_vectors(self) -> None:
        v1 = np.array([1.0, 1.0, 0.0])
        v2 = np.array([1.0, 0.9, 0.1])
        sim = SimilarityCalculator.cosine_similarity(v1, v2)
        assert 0.9 < sim < 1.0

    def test_mismatched_dimensions_raises(self) -> None:
        v1 = np.array([1.0, 0.0])
        v2 = np.array([1.0, 0.0, 0.0])
        with pytest.raises(ValueError, match="mismatch"):
            SimilarityCalculator.cosine_similarity(v1, v2)

    def test_zero_vector(self) -> None:
        v1 = np.zeros(3)
        v2 = np.array([1.0, 0.0, 0.0])
        assert SimilarityCalculator.cosine_similarity(v1, v2) == 0.0

    def test_normalised_vectors_dot_equals_cosine(self) -> None:
        v1 = np.array([3.0, 4.0])
        v2 = np.array([1.0, 2.0])
        v1_norm = v1 / np.linalg.norm(v1)
        v2_norm = v2 / np.linalg.norm(v2)
        sim = SimilarityCalculator.cosine_similarity(v1_norm, v2_norm)
        dot = float(np.dot(v1_norm, v2_norm))
        assert sim == pytest.approx(dot, abs=1e-6)


class TestBatchSimilarity:
    """Tests for batch_similarity."""

    def test_batch_empty(self) -> None:
        query = np.array([1.0, 0.0])
        assert SimilarityCalculator.batch_similarity(query, []) == []

    def test_batch_single(self) -> None:
        query = np.array([1.0, 0.0])
        candidates = [np.array([1.0, 0.0])]
        result = SimilarityCalculator.batch_similarity(query, candidates)
        assert len(result) == 1
        assert result[0] == pytest.approx(1.0)

    def test_batch_multiple(self) -> None:
        query = np.array([1.0, 0.0, 0.0])
        candidates = [
            np.array([1.0, 0.0, 0.0]),  # identical
            np.array([0.0, 1.0, 0.0]),  # orthogonal
            np.array([0.7, 0.7, 0.0]),  # similar
        ]
        result = SimilarityCalculator.batch_similarity(query, candidates)
        assert len(result) == 3
        assert result[0] == pytest.approx(1.0, abs=0.01)
        assert result[1] == pytest.approx(0.0, abs=0.01)
        assert 0.5 < result[2] < 1.0

    def test_batch_dimension_mismatch(self) -> None:
        query = np.array([1.0, 0.0])
        candidates = [np.array([1.0, 0.0, 0.0])]
        with pytest.raises(ValueError, match="mismatch"):
            SimilarityCalculator.batch_similarity(query, candidates)


class TestAboveThreshold:
    """Tests for above_threshold."""

    def test_above(self) -> None:
        assert SimilarityCalculator.above_threshold(0.95, 0.90) is True

    def test_below(self) -> None:
        assert SimilarityCalculator.above_threshold(0.80, 0.90) is False

    def test_exact(self) -> None:
        assert SimilarityCalculator.above_threshold(0.90, 0.90) is True
