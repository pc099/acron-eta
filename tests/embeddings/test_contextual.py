"""Tests for ContextualEmbeddingEngine."""

import numpy as np
import pytest

from src.embeddings.contextual import ContextualEmbeddingEngine
from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine
from src.embeddings.vector_store import InMemoryVectorDB, VectorDBEntry


@pytest.fixture
def base_engine() -> EmbeddingEngine:
    return EmbeddingEngine(EmbeddingConfig(provider="mock", dimension=64))


@pytest.fixture
def contextual(base_engine: EmbeddingEngine) -> ContextualEmbeddingEngine:
    return ContextualEmbeddingEngine(
        embedding_engine=base_engine, use_mock=True
    )


class TestGenerateContext:
    """Tests for generate_context."""

    def test_returns_string(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        ctx = contextual.generate_context("What is Python?")
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_includes_task_type(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        ctx = contextual.generate_context(
            "What is Python?", task_type="faq"
        )
        assert "faq" in ctx

    def test_includes_agent_id(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        ctx = contextual.generate_context(
            "Test", agent_id="agent-42"
        )
        assert "agent-42" in ctx


class TestEmbedWithContext:
    """Tests for embed_with_context."""

    def test_returns_tuple(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        embedding, context, contextual_text = contextual.embed_with_context(
            "What is Python?"
        )
        assert isinstance(embedding, np.ndarray)
        assert isinstance(context, str)
        assert isinstance(contextual_text, str)

    def test_embedding_has_correct_dimension(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        embedding, _, _ = contextual.embed_with_context("Test")
        assert embedding.shape == (64,)

    def test_embedding_is_normalized(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        embedding, _, _ = contextual.embed_with_context("Test")
        norm = np.linalg.norm(embedding)
        assert norm == pytest.approx(1.0, abs=1e-5)

    def test_contextual_text_includes_context(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        _, context, contextual_text = contextual.embed_with_context("Test")
        assert context in contextual_text
        assert "[Context:" in contextual_text

    def test_different_contexts_produce_different_embeddings(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        e1, _, _ = contextual.embed_with_context(
            "Hello", task_type="faq"
        )
        e2, _, _ = contextual.embed_with_context(
            "Hello", task_type="coding"
        )
        # Different contexts should produce different embeddings
        assert not np.allclose(e1, e2)


class TestRetrieveWithContext:
    """Tests for retrieve_with_context."""

    def test_retrieve_from_populated_db(
        self,
        contextual: ContextualEmbeddingEngine,
        base_engine: EmbeddingEngine,
    ) -> None:
        db = InMemoryVectorDB()

        # Store an entry using contextual embedding
        embedding, _, _ = contextual.embed_with_context("What is Python?")
        db.upsert([
            VectorDBEntry(
                vector_id="v1",
                embedding=embedding.tolist(),
                metadata={"response": "Python is a language."},
            )
        ])

        # Retrieve with same query
        result = contextual.retrieve_with_context(
            "What is Python?",
            vector_db=db,
            threshold=0.5,
        )
        assert result is not None
        assert result["score"] > 0.5

    def test_retrieve_no_match(
        self, contextual: ContextualEmbeddingEngine
    ) -> None:
        db = InMemoryVectorDB()
        result = contextual.retrieve_with_context(
            "Test", vector_db=db, threshold=0.5
        )
        assert result is None

    def test_retrieve_below_threshold(
        self,
        contextual: ContextualEmbeddingEngine,
        base_engine: EmbeddingEngine,
    ) -> None:
        db = InMemoryVectorDB()
        # Store a random entry
        db.upsert([
            VectorDBEntry(
                vector_id="v1",
                embedding=np.random.randn(64).tolist(),
                metadata={"response": "Random."},
            )
        ])

        # Use very high threshold
        result = contextual.retrieve_with_context(
            "Something completely different",
            vector_db=db,
            threshold=0.999,
        )
        # Likely no match at such a high threshold
        # (could be None or a match if embeddings happen to align)
        assert result is None or result["score"] >= 0.999
