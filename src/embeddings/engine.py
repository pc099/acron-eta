"""
Embedding engine for Asahi semantic caching.

Generates dense vector embeddings for text queries and cached items.
This is the foundation for all semantic matching in Tier 2 and
Tier 3 caching.
"""

import logging
import os
import time
from typing import List, Literal, Optional

import numpy as np
from pydantic import BaseModel, Field

from src.exceptions import ConfigurationError, EmbeddingError

logger = logging.getLogger(__name__)


class EmbeddingConfig(BaseModel):
    """Configuration for the embedding engine.

    Attributes:
        provider: Which embedding API to use.
        model_name: Specific model identifier.
        api_key_env: Environment variable holding the API key.
        dimension: Expected vector dimension.
        batch_size: Maximum texts per API call.
        timeout_seconds: API call timeout.
        max_retries: Retry count on transient failures.
    """

    provider: Literal["cohere", "openai", "ollama", "mock"] = "cohere"
    model_name: str = "embed-english-v3.0"
    api_key_env: str = "COHERE_API_KEY"
    dimension: int = Field(default=1024, gt=0)
    batch_size: int = Field(default=96, gt=0)
    timeout_seconds: int = Field(default=30, gt=0)
    max_retries: int = Field(default=3, ge=0)


class EmbeddingEngine:
    """Generate dense vector embeddings for text.

    Supports multiple providers (Cohere, OpenAI, Ollama) and a mock
    mode for testing.  All returned vectors are L2-normalised so that
    dot product equals cosine similarity.

    Args:
        config: Embedding engine configuration.
    """

    def __init__(self, config: EmbeddingConfig) -> None:
        self._config = config
        self._client: Optional[object] = None
        self._init_client()

    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text string.

        Args:
            text: The text to embed (must not be empty).

        Returns:
            Numpy array of shape ``(dimension,)`` with unit L2 norm.

        Raises:
            ValueError: If text is empty.
            EmbeddingError: If the API call fails after retries.
        """
        if not text or not text.strip():
            raise ValueError("Text must not be empty")

        results = self.embed_texts([text])
        return results[0]

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """Embed multiple texts in batches.

        Splits the input into chunks of ``batch_size``, calls the
        provider API for each chunk, and returns results in the
        same order as the input.

        Args:
            texts: List of text strings (none may be empty).

        Returns:
            List of numpy arrays, each of shape ``(dimension,)``.

        Raises:
            ValueError: If any text is empty.
            EmbeddingError: If the API call fails after retries.
        """
        for i, text in enumerate(texts):
            if not text or not text.strip():
                raise ValueError(f"Text at index {i} must not be empty")

        all_embeddings: List[np.ndarray] = []

        # Process in batches
        for start in range(0, len(texts), self._config.batch_size):
            batch = texts[start : start + self._config.batch_size]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    @property
    def dimension(self) -> int:
        """Return the expected embedding dimension."""
        return self._config.dimension

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Initialise the provider-specific API client."""
        if self._config.provider == "mock":
            self._client = None
            return

        api_key = os.getenv(self._config.api_key_env)
        if not api_key and self._config.provider != "ollama":
            raise ConfigurationError(
                f"API key not found in environment variable "
                f"'{self._config.api_key_env}' for provider "
                f"'{self._config.provider}'"
            )

        if self._config.provider == "cohere":
            try:
                import cohere

                self._client = cohere.Client(api_key=api_key)
            except ImportError as exc:
                raise ConfigurationError(
                    "cohere package not installed"
                ) from exc
        elif self._config.provider == "openai":
            try:
                from openai import OpenAI

                self._client = OpenAI(api_key=api_key)
            except ImportError as exc:
                raise ConfigurationError(
                    "openai package not installed"
                ) from exc

    def _embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed a single batch with retry logic.

        Args:
            texts: Batch of texts to embed.

        Returns:
            List of normalised embedding vectors.

        Raises:
            EmbeddingError: After all retries are exhausted.
        """
        last_error: Optional[Exception] = None

        for attempt in range(self._config.max_retries + 1):
            try:
                return self._call_provider(texts)
            except EmbeddingError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < self._config.max_retries:
                    wait = 2**attempt
                    logger.warning(
                        "Embedding API call failed, retrying",
                        extra={
                            "attempt": attempt + 1,
                            "wait_seconds": wait,
                            "error": str(exc),
                        },
                    )
                    time.sleep(wait)

        raise EmbeddingError(
            f"Embedding failed after {self._config.max_retries + 1} "
            f"attempts: {last_error}"
        )

    def _call_provider(self, texts: List[str]) -> List[np.ndarray]:
        """Dispatch to the correct provider.

        Args:
            texts: Texts to embed.

        Returns:
            List of normalised embedding vectors.
        """
        if self._config.provider == "mock":
            return self._mock_embed(texts)
        elif self._config.provider == "cohere":
            return self._embed_cohere(texts)
        elif self._config.provider == "openai":
            return self._embed_openai(texts)
        else:
            raise EmbeddingError(
                f"Unsupported provider: {self._config.provider}"
            )

    def _embed_cohere(self, texts: List[str]) -> List[np.ndarray]:
        """Call Cohere embedding API.

        Args:
            texts: Texts to embed.

        Returns:
            Normalised embedding vectors.
        """
        response = self._client.embed(  # type: ignore[union-attr]
            texts=texts,
            model=self._config.model_name,
            input_type="search_query",
        )
        embeddings = response.embeddings
        return [self._normalise(np.array(e, dtype=np.float32)) for e in embeddings]

    def _embed_openai(self, texts: List[str]) -> List[np.ndarray]:
        """Call OpenAI embedding API.

        Args:
            texts: Texts to embed.

        Returns:
            Normalised embedding vectors.
        """
        response = self._client.embeddings.create(  # type: ignore[union-attr]
            model=self._config.model_name,
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]
        return [self._normalise(np.array(e, dtype=np.float32)) for e in embeddings]

    def _mock_embed(self, texts: List[str]) -> List[np.ndarray]:
        """Generate deterministic mock embeddings for testing.

        Uses a simple hash-based approach so the same text always
        produces the same embedding vector.

        Args:
            texts: Texts to embed.

        Returns:
            Normalised embedding vectors of the configured dimension.
        """
        results: List[np.ndarray] = []
        for text in texts:
            # Seed RNG with text hash for determinism
            seed = hash(text) % (2**32)
            rng = np.random.RandomState(seed)
            vec = rng.randn(self._config.dimension).astype(np.float32)
            results.append(self._normalise(vec))
        return results

    def _normalise(self, vec: np.ndarray) -> np.ndarray:
        """L2-normalise a vector to unit length.

        Args:
            vec: Input vector.

        Returns:
            Normalised vector.

        Raises:
            EmbeddingError: If the vector dimension does not match config.
        """
        if vec.shape[0] != self._config.dimension:
            raise EmbeddingError(
                f"Dimension mismatch: expected {self._config.dimension}, "
                f"got {vec.shape[0]}"
            )
        norm = np.linalg.norm(vec)
        if norm == 0:
            return vec
        return vec / norm
