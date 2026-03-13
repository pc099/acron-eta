"""Tests for the embedding provider system."""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.embeddings import (
    CohereProvider,
    FallbackProvider,
    LocalProvider,
    cosine_similarity,
    embed,
    embed_batch,
    embed_to_bytes,
    get_embedding_provider,
    get_vector_dim,
    reset_provider,
)


@pytest.fixture(autouse=True)
def _reset():
    """Reset the cached provider between tests."""
    reset_provider()
    yield
    reset_provider()


# -- FallbackProvider -------------------------------------------------------


class TestFallbackProvider:
    def test_embed_returns_correct_dims(self):
        p = FallbackProvider(dims=128)
        vec = p.embed("hello")
        assert len(vec) == 128

    def test_embed_deterministic(self):
        p = FallbackProvider()
        assert p.embed("hello") == p.embed("hello")

    def test_embed_different_for_different_text(self):
        p = FallbackProvider()
        assert p.embed("hello") != p.embed("world")

    def test_embed_batch(self):
        p = FallbackProvider(dims=64)
        vecs = p.embed_batch(["a", "b", "c"])
        assert len(vecs) == 3
        assert all(len(v) == 64 for v in vecs)

    def test_embed_normalized(self):
        p = FallbackProvider()
        vec = np.array(p.embed("test"), dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        assert abs(norm - 1.0) < 1e-5

    def test_dimensions_property(self):
        p = FallbackProvider(dims=256)
        assert p.dimensions == 256


# -- CohereProvider ---------------------------------------------------------


class TestCohereProvider:
    def test_embed_calls_cohere_api(self):
        mock_cohere = MagicMock()
        mock_client = MagicMock()
        mock_cohere.Client.return_value = mock_client
        mock_client.embed.return_value = MagicMock(
            embeddings=[[0.1] * 1024]
        )

        with patch.dict("sys.modules", {"cohere": mock_cohere}):
            provider = CohereProvider.__new__(CohereProvider)
            provider._client = mock_client
            provider._dims = 1024

            result = provider.embed("test query")
            assert len(result) == 1024

    def test_embed_batch_calls_cohere_api(self):
        mock_client = MagicMock()
        mock_client.embed.return_value = MagicMock(
            embeddings=[[0.1] * 1024, [0.2] * 1024]
        )

        provider = CohereProvider.__new__(CohereProvider)
        provider._client = mock_client
        provider._dims = 1024

        results = provider.embed_batch(["hello", "world"])
        assert len(results) == 2
        assert all(len(v) == 1024 for v in results)

        mock_client.embed.assert_called_once_with(
            texts=["hello", "world"],
            model="embed-english-v3.0",
            input_type="search_document",
        )

    def test_dimensions_property(self):
        provider = CohereProvider.__new__(CohereProvider)
        provider._dims = 1024
        assert provider.dimensions == 1024


# -- Provider factory -------------------------------------------------------


class TestProviderFactory:
    def test_defaults_to_fallback_when_no_deps(self):
        """Without sentence-transformers, should fall back to FallbackProvider."""
        with patch("app.services.embeddings.LocalProvider", side_effect=ImportError):
            provider = get_embedding_provider()
            assert isinstance(provider, FallbackProvider)

    def test_provider_cached(self):
        """Calling get_embedding_provider() twice returns same object."""
        p1 = get_embedding_provider()
        p2 = get_embedding_provider()
        assert p1 is p2


# -- Module-level functions -------------------------------------------------


class TestModuleFunctions:
    def test_embed_returns_list(self):
        vec = embed("hello")
        assert isinstance(vec, list)
        assert len(vec) > 0

    def test_embed_batch_returns_list_of_lists(self):
        vecs = embed_batch(["a", "b"])
        assert len(vecs) == 2
        assert all(isinstance(v, list) for v in vecs)

    def test_embed_to_bytes_returns_bytes(self):
        raw = embed_to_bytes("hello")
        assert isinstance(raw, bytes)

    def test_cosine_similarity_identical(self):
        vec = embed("hello")
        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-5

    def test_cosine_similarity_zero_vector(self):
        vec = embed("hello")
        zero = [0.0] * len(vec)
        assert cosine_similarity(vec, zero) == 0.0

    def test_get_vector_dim(self):
        dim = get_vector_dim()
        assert isinstance(dim, int)
        assert dim > 0
