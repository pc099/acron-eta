"""Tests for EmbeddingEngine."""

import numpy as np
import pytest

from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine


@pytest.fixture
def config() -> EmbeddingConfig:
    return EmbeddingConfig(provider="mock", dimension=128)


@pytest.fixture
def engine(config: EmbeddingConfig) -> EmbeddingEngine:
    return EmbeddingEngine(config)


class TestEmbedText:
    """Tests for embed_text."""

    def test_returns_ndarray(self, engine: EmbeddingEngine) -> None:
        result = engine.embed_text("Hello world")
        assert isinstance(result, np.ndarray)

    def test_correct_dimension(self, engine: EmbeddingEngine) -> None:
        result = engine.embed_text("Hello world")
        assert result.shape == (128,)

    def test_unit_norm(self, engine: EmbeddingEngine) -> None:
        result = engine.embed_text("Test text")
        norm = np.linalg.norm(result)
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_deterministic(self, engine: EmbeddingEngine) -> None:
        r1 = engine.embed_text("Same text")
        r2 = engine.embed_text("Same text")
        np.testing.assert_array_almost_equal(r1, r2)

    def test_different_texts_different_embeddings(self, engine: EmbeddingEngine) -> None:
        r1 = engine.embed_text("Hello")
        r2 = engine.embed_text("Goodbye")
        assert not np.allclose(r1, r2)

    def test_empty_text_raises(self, engine: EmbeddingEngine) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            engine.embed_text("")

    def test_whitespace_text_raises(self, engine: EmbeddingEngine) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            engine.embed_text("   ")


class TestEmbedTexts:
    """Tests for embed_texts."""

    def test_batch_single(self, engine: EmbeddingEngine) -> None:
        results = engine.embed_texts(["Hello"])
        assert len(results) == 1
        assert results[0].shape == (128,)

    def test_batch_multiple(self, engine: EmbeddingEngine) -> None:
        results = engine.embed_texts(["A", "B", "C"])
        assert len(results) == 3
        for r in results:
            assert r.shape == (128,)

    def test_batch_preserves_order(self, engine: EmbeddingEngine) -> None:
        texts = ["Alpha", "Beta", "Gamma"]
        results = engine.embed_texts(texts)
        for text, embedding in zip(texts, results):
            single = engine.embed_text(text)
            np.testing.assert_array_almost_equal(embedding, single)

    def test_batch_empty_text_raises(self, engine: EmbeddingEngine) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            engine.embed_texts(["Hello", "", "World"])

    def test_large_batch_chunking(self) -> None:
        config = EmbeddingConfig(provider="mock", dimension=64, batch_size=3)
        engine = EmbeddingEngine(config)
        results = engine.embed_texts([f"text_{i}" for i in range(10)])
        assert len(results) == 10


class TestDimension:
    """Tests for dimension property."""

    def test_dimension_matches_config(self, engine: EmbeddingEngine) -> None:
        assert engine.dimension == 128

    def test_custom_dimension(self) -> None:
        config = EmbeddingConfig(provider="mock", dimension=256)
        engine = EmbeddingEngine(config)
        assert engine.dimension == 256
