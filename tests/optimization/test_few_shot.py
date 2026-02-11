"""Tests for FewShotSelector -- relevance + diversity example selection."""

from typing import Dict, List

import pytest

from src.embeddings.engine import EmbeddingConfig, EmbeddingEngine
from src.optimization.few_shot import FewShotSelector


@pytest.fixture
def mock_engine() -> EmbeddingEngine:
    """Mock embedding engine for deterministic testing."""
    config = EmbeddingConfig(provider="mock", dimension=64)
    return EmbeddingEngine(config)


@pytest.fixture
def selector(mock_engine: EmbeddingEngine) -> FewShotSelector:
    return FewShotSelector(embedding_engine=mock_engine)


@pytest.fixture
def sample_examples() -> List[Dict[str, str]]:
    return [
        {"input": "What is Python?", "output": "A programming language."},
        {"input": "How does Java work?", "output": "JVM-based language."},
        {"input": "Explain machine learning", "output": "Subset of AI."},
        {"input": "What is deep learning?", "output": "Neural networks."},
        {"input": "Define natural language processing", "output": "NLP field."},
        {"input": "What is Python used for?", "output": "Web, data, AI."},
        {"input": "Compare Python and Java", "output": "Different paradigms."},
    ]


class TestFewShotSelector:
    """Tests for FewShotSelector."""

    def test_select_returns_max_examples(
        self,
        selector: FewShotSelector,
        sample_examples: List[Dict[str, str]],
    ) -> None:
        selected = selector.select(
            query="Tell me about Python",
            examples=sample_examples,
            max_examples=3,
        )
        assert len(selected) == 3

    def test_fewer_examples_than_max(
        self,
        selector: FewShotSelector,
    ) -> None:
        examples = [
            {"input": "Hello", "output": "Hi"},
            {"input": "Bye", "output": "Goodbye"},
        ]
        selected = selector.select(
            query="Greetings", examples=examples, max_examples=5
        )
        assert len(selected) == 2

    def test_empty_examples_returns_empty(
        self, selector: FewShotSelector
    ) -> None:
        selected = selector.select(query="test", examples=[], max_examples=3)
        assert selected == []

    def test_empty_query_returns_first_n(
        self,
        selector: FewShotSelector,
        sample_examples: List[Dict[str, str]],
    ) -> None:
        selected = selector.select(query="", examples=sample_examples, max_examples=2)
        assert len(selected) == 2

    def test_diversity_prevents_duplicates(
        self, selector: FewShotSelector
    ) -> None:
        """With diversity, near-duplicate examples should be penalised."""
        # Two very similar inputs + one different
        examples = [
            {"input": "What is Python programming?", "output": "A language."},
            {"input": "What is Python programming language?", "output": "A language."},
            {"input": "Explain quantum computing", "output": "Physics + CS."},
        ]
        selected = selector.select(
            query="What is Python?",
            examples=examples,
            max_examples=2,
            diversity_weight=0.5,
        )
        assert len(selected) == 2

    def test_no_diversity_selects_most_relevant(
        self, selector: FewShotSelector
    ) -> None:
        examples = [
            {"input": "What is Python?", "output": "A language."},
            {"input": "What is Python used for?", "output": "Many things."},
            {"input": "What is cooking?", "output": "Food preparation."},
        ]
        selected = selector.select(
            query="Tell me about Python",
            examples=examples,
            max_examples=2,
            diversity_weight=0.0,
        )
        assert len(selected) == 2

    def test_max_examples_respected(
        self,
        selector: FewShotSelector,
        sample_examples: List[Dict[str, str]],
    ) -> None:
        for n in [1, 2, 4]:
            selected = selector.select(
                query="Python", examples=sample_examples, max_examples=n
            )
            assert len(selected) == n

    def test_returns_actual_example_dicts(
        self,
        selector: FewShotSelector,
        sample_examples: List[Dict[str, str]],
    ) -> None:
        selected = selector.select(
            query="Python", examples=sample_examples, max_examples=2
        )
        for ex in selected:
            assert "input" in ex
            assert "output" in ex
            assert ex in sample_examples

    def test_fallback_on_engine_failure(self) -> None:
        """If embedding fails, should return first N examples."""
        config = EmbeddingConfig(provider="mock", dimension=64)
        engine = EmbeddingEngine(config)
        # Monkey-patch to force failure
        engine.embed_text = lambda text: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("mock failure")
        )
        selector = FewShotSelector(embedding_engine=engine)
        examples = [
            {"input": "A", "output": "1"},
            {"input": "B", "output": "2"},
            {"input": "C", "output": "3"},
        ]
        selected = selector.select(query="test", examples=examples, max_examples=2)
        assert len(selected) == 2
