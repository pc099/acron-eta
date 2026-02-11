"""Tests for WorkflowDecomposer."""

import pytest

from src.cache.workflow import WorkflowDecomposer, WorkflowStep


@pytest.fixture
def decomposer() -> WorkflowDecomposer:
    return WorkflowDecomposer()


class TestDecompose:
    """Tests for decompose."""

    def test_single_question(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose("What is the capital of France?")
        assert len(steps) == 1
        assert steps[0].step_type == "answer"

    def test_empty_prompt(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose("")
        assert steps == []

    def test_comparison_question(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose("Compare Python and Java")
        assert len(steps) == 3
        assert steps[0].step_type == "summarize"
        assert steps[1].step_type == "summarize"
        assert steps[2].step_type == "answer"

    def test_difference_between(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose(
            "What is the difference between TCP and UDP?"
        )
        assert len(steps) == 3  # summarize A, summarize B, compare

    def test_multi_part_numbered(self, decomposer: WorkflowDecomposer) -> None:
        prompt = "1. What is Python? 2. What is Java? 3. Which is better?"
        steps = decomposer.decompose(prompt)
        assert len(steps) >= 3

    def test_multi_question_marks(self, decomposer: WorkflowDecomposer) -> None:
        prompt = "What is AI? How does it work? Why is it important?"
        steps = decomposer.decompose(prompt)
        assert len(steps) >= 3

    def test_document_reference(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose(
            "Based on the document, summarize the main points"
        )
        assert len(steps) == 2
        assert steps[0].step_type == "summarize"
        assert steps[1].step_type == "answer"

    def test_explicit_document_id(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose(
            "Summarize this", document_id="doc_123"
        )
        assert any(s.document_id == "doc_123" for s in steps)

    def test_returns_workflow_steps(self, decomposer: WorkflowDecomposer) -> None:
        steps = decomposer.decompose("What is Python?")
        assert all(isinstance(s, WorkflowStep) for s in steps)

    def test_cache_keys_are_deterministic(self, decomposer: WorkflowDecomposer) -> None:
        s1 = decomposer.decompose("What is Python?")
        s2 = decomposer.decompose("What is Python?")
        assert s1[0].cache_key == s2[0].cache_key

    def test_different_queries_different_cache_keys(
        self, decomposer: WorkflowDecomposer
    ) -> None:
        s1 = decomposer.decompose("What is Python?")
        s2 = decomposer.decompose("What is Java?")
        assert s1[0].cache_key != s2[0].cache_key


class TestExtractIntent:
    """Tests for extract_intent."""

    def test_short_text(self, decomposer: WorkflowDecomposer) -> None:
        intent = decomposer.extract_intent("What is Python?")
        assert "Python" in intent

    def test_long_text_truncated(self, decomposer: WorkflowDecomposer) -> None:
        intent = decomposer.extract_intent("x " * 200)
        assert len(intent) <= 83  # 80 chars + "..."
