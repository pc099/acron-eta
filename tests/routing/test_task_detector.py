"""Tests for TaskTypeDetector."""

import pytest

from src.routing.task_detector import TaskDetection, TaskTypeDetector


@pytest.fixture
def detector() -> TaskTypeDetector:
    return TaskTypeDetector()


class TestTaskTypeDetector:
    """Tests for TaskTypeDetector.detect."""

    def test_summarization(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Summarize this article about climate change")
        assert result.task_type == "summarization"
        assert result.confidence > 0.0

    def test_reasoning(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Explain why the sky is blue")
        assert result.task_type == "reasoning"

    def test_faq(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("What is the capital of France?")
        assert result.task_type == "faq"

    def test_coding(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Write code to implement a binary search function")
        assert result.task_type == "coding"

    def test_translation(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Translate this to Spanish: Hello, how are you?")
        assert result.task_type == "translation"

    def test_classification(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Classify the sentiment of this review")
        assert result.task_type == "classification"

    def test_creative(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Write a poem about the ocean")
        assert result.task_type == "creative"

    def test_legal(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Review this contract for compliance issues")
        assert result.task_type == "legal"

    def test_general_fallback(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("Do something interesting")
        assert result.task_type == "general"
        assert result.confidence < 0.5

    def test_empty_prompt(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("")
        assert result.task_type == "general"
        assert result.confidence == 0.0

    def test_whitespace_prompt(self, detector: TaskTypeDetector) -> None:
        result = detector.detect("   ")
        assert result.task_type == "general"
        assert result.confidence == 0.0

    def test_multiple_patterns_increase_confidence(
        self, detector: TaskTypeDetector
    ) -> None:
        result = detector.detect(
            "Explain why and analyze the reason the economy is growing"
        )
        assert result.task_type == "reasoning"
        assert result.confidence > 0.3

    def test_returns_task_detection_model(
        self, detector: TaskTypeDetector
    ) -> None:
        result = detector.detect("What is Python?")
        assert isinstance(result, TaskDetection)
        assert hasattr(result, "task_type")
        assert hasattr(result, "confidence")
        assert hasattr(result, "intent")
