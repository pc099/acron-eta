"""Local embedding service — no external API calls needed.

Uses sentence-transformers all-MiniLM-L6-v2 (384 dimensions, ~3ms per embed).
Model is loaded once at module level and cached for the process lifetime.
"""

import hashlib
import logging
from functools import lru_cache
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
VECTOR_DIM = 384

# Module-level model cache — loaded lazily on first call
_model = None


def _get_model():
    """Lazy-load the sentence-transformer model."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(MODEL_NAME)
            logger.info("Loaded embedding model: %s (%d dims)", MODEL_NAME, VECTOR_DIM)
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — using fallback hash embeddings"
            )
            _model = "fallback"
    return _model


def embed(text: str) -> list[float]:
    """Embed a text string into a vector.

    Returns a list of floats with VECTOR_DIM dimensions.
    Falls back to deterministic hash-based pseudo-embeddings if
    sentence-transformers is not installed.
    """
    model = _get_model()

    if model == "fallback":
        return _fallback_embed(text)

    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts at once (more efficient than individual calls)."""
    model = _get_model()

    if model == "fallback":
        return [_fallback_embed(t) for t in texts]

    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_to_bytes(text: str) -> bytes:
    """Embed and return as raw bytes (for Redis vector search)."""
    vector = embed(text)
    return np.array(vector, dtype=np.float32).tobytes()


def _fallback_embed(text: str) -> list[float]:
    """Deterministic hash-based pseudo-embedding for dev/testing.

    Produces consistent vectors for identical inputs so exact-match
    cache logic works without the ML model installed.
    """
    h = hashlib.sha256(text.encode()).digest()
    # Expand to VECTOR_DIM values deterministically
    rng = np.random.RandomState(int.from_bytes(h[:4], "big"))
    vec = rng.randn(VECTOR_DIM).astype(np.float32)
    # Normalize to unit length
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


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
