"""Embedding service with pluggable providers.

Supports:
- Cohere embed-english-v3.0 (1024 dims) — production
- Local sentence-transformers all-MiniLM-L6-v2 (384 dims) — development
- Deterministic hash-based fallback — testing (no ML deps needed)

Provider is selected via the ``embedding_provider`` setting.
"""

import hashlib
import logging
from typing import Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)

# --- Provider protocol ---------------------------------------------------


class EmbeddingProvider(Protocol):
    """Interface that all embedding providers implement."""

    @property
    def dimensions(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


# --- Cohere provider ------------------------------------------------------

COHERE_MODEL = "embed-english-v3.0"
COHERE_DIMS = 1024


class CohereProvider:
    """Production embedding provider using the Cohere API."""

    def __init__(self, api_key: str) -> None:
        import cohere

        self._client = cohere.Client(api_key)
        self._dims = COHERE_DIMS

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(
        self,
        texts: list[str],
        input_type: str = "search_document",
    ) -> list[list[float]]:
        response = self._client.embed(
            texts=texts,
            model=COHERE_MODEL,
            input_type=input_type,
        )
        return [list(v) for v in response.embeddings]


# --- Local provider -------------------------------------------------------

LOCAL_MODEL_NAME = "all-MiniLM-L6-v2"
LOCAL_DIMS = 384


class LocalProvider:
    """Development embedding provider using sentence-transformers."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(LOCAL_MODEL_NAME)
        self._dims = LOCAL_DIMS
        logger.info("Loaded local embedding model: %s (%d dims)", LOCAL_MODEL_NAME, LOCAL_DIMS)

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text, normalize_embeddings=True)
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return vectors.tolist()


# --- Fallback provider ----------------------------------------------------

FALLBACK_DIMS = 384


class FallbackProvider:
    """Deterministic hash-based pseudo-embeddings for testing.

    Produces consistent vectors for identical inputs so cache logic
    works without any ML model installed.
    """

    def __init__(self, dims: int = FALLBACK_DIMS) -> None:
        self._dims = dims

    @property
    def dimensions(self) -> int:
        return self._dims

    def embed(self, text: str) -> list[float]:
        h = hashlib.sha256(text.encode()).digest()
        rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
        vec = rng.randn(self._dims).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


# --- Provider factory -----------------------------------------------------

_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """Return the active embedding provider (lazy-init, cached)."""
    global _provider
    if _provider is not None:
        return _provider

    from app.config import get_settings

    settings = get_settings()

    if settings.embedding_provider == "cohere" and settings.cohere_api_key:
        try:
            _provider = CohereProvider(settings.cohere_api_key)
            logger.info("Using Cohere embedding provider (%d dims)", _provider.dimensions)
            return _provider
        except Exception:
            logger.exception("Failed to initialise Cohere provider — falling back to local")

    if settings.embedding_provider == "local":
        try:
            _provider = LocalProvider()
            return _provider
        except ImportError:
            logger.warning("sentence-transformers not installed — using fallback hash embeddings")

    _provider = FallbackProvider(dims=settings.embedding_dimensions if settings.embedding_provider == "cohere" else FALLBACK_DIMS)
    logger.info("Using fallback hash embedding provider (%d dims)", _provider.dimensions)
    return _provider


def reset_provider() -> None:
    """Clear the cached provider. Used in tests."""
    global _provider
    _provider = None


# --- Module-level convenience functions -----------------------------------
# These delegate to the active provider and maintain backward compatibility.

# Dynamic — reads from provider at call time
VECTOR_DIM = 384  # default; callers should prefer get_vector_dim()


def get_vector_dim() -> int:
    """Return the dimensionality of the active embedding provider."""
    return get_embedding_provider().dimensions


def embed(text: str) -> list[float]:
    """Embed a text string into a vector."""
    return get_embedding_provider().embed(text)


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts at once."""
    return get_embedding_provider().embed_batch(texts)


def embed_to_bytes(text: str) -> bytes:
    """Embed and return as raw bytes for vector search."""
    vector = embed(text)
    return np.array(vector, dtype=np.float32).tobytes()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_np = np.array(a, dtype=np.float32)
    b_np = np.array(b, dtype=np.float32)
    dot = np.dot(a_np, b_np)
    norm_a = np.linalg.norm(a_np)
    norm_b = np.linalg.norm(b_np)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
