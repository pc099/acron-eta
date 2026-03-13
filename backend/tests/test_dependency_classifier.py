"""Tests for the context dependency classifier service."""

import pytest

from app.services.dependency_classifier import (
    DependencyClassifier,
    DependencyLevel,
)


@pytest.fixture
def classifier() -> DependencyClassifier:
    return DependencyClassifier()


class TestDependencyClassifier:
    """Tests for DependencyClassifier."""

    def test_independent_simple_query(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("What is Python?")
        assert result.level == DependencyLevel.INDEPENDENT

    def test_independent_first_step(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Tell me more about that", session_step=1)
        assert result.level == DependencyLevel.INDEPENDENT
        assert result.confidence == 1.0
        assert "first_step" in result.signals

    def test_critical_execute(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Execute the deployment now")
        assert result.level == DependencyLevel.CRITICAL

    def test_critical_deploy(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Deploy this to production")
        assert result.level == DependencyLevel.CRITICAL

    def test_critical_delete(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Delete all old records")
        assert result.level == DependencyLevel.CRITICAL

    def test_dependent_reference_above(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Apply that to the code above")
        assert result.level == DependencyLevel.DEPENDENT

    def test_dependent_based_on_previous(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Based on what you said earlier, modify the function")
        assert result.level == DependencyLevel.DEPENDENT

    def test_partial_tell_me_more(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Tell me more about this topic")
        assert result.level in (DependencyLevel.PARTIAL, DependencyLevel.DEPENDENT)

    def test_partial_additionally(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Additionally, can you explain the architecture?")
        assert result.level == DependencyLevel.PARTIAL

    def test_partial_continue(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("Continue with the next steps")
        assert result.level in (DependencyLevel.PARTIAL, DependencyLevel.DEPENDENT)

    def test_confidence_range(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("What is 2+2?")
        assert 0.0 <= result.confidence <= 1.0

    def test_signals_populated(self, classifier: DependencyClassifier) -> None:
        result = classifier.classify("What is Python?")
        assert len(result.signals) > 0


class TestPriorContentDetector:
    """Tests for verbatim fragment detection from prior outputs."""

    def test_prior_content_detected(self, classifier: DependencyClassifier) -> None:
        prior = ["Microservices architecture provides loose coupling between services"]
        result = classifier.classify(
            "Tell me more about loose coupling between services",
            session_step=3,
            prior_outputs=prior,
        )
        assert any("prior_content" in s for s in result.signals)

    def test_prior_content_no_match(self, classifier: DependencyClassifier) -> None:
        prior = ["Python is a programming language"]
        result = classifier.classify(
            "What is JavaScript?",
            session_step=3,
            prior_outputs=prior,
        )
        assert not any("prior_content" in s for s in result.signals)


class TestSequenceDepthScorer:
    """Tests for sequence depth scoring."""

    def test_sequence_depth_step1(self, classifier: DependencyClassifier) -> None:
        score, signal = classifier._score_sequence_depth(1)
        assert score == 0.0

    def test_sequence_depth_step2(self, classifier: DependencyClassifier) -> None:
        score, signal = classifier._score_sequence_depth(2)
        assert score == 0.1
        assert "early" in signal

    def test_sequence_depth_step5(self, classifier: DependencyClassifier) -> None:
        score, signal = classifier._score_sequence_depth(5)
        assert score == 0.2
        assert "mid" in signal

    def test_sequence_depth_step10(self, classifier: DependencyClassifier) -> None:
        score, signal = classifier._score_sequence_depth(10)
        assert score == 0.3
        assert "deep" in signal


class TestEntityReferenceCounter:
    """Tests for entity reference detection from prior outputs."""

    def test_entity_reference_found(self, classifier: DependencyClassifier) -> None:
        prior = ["React Native is used for cross-platform mobile development"]
        signals = classifier._count_entity_references(
            "How does React Native compare to Flutter?",
            prior,
        )
        assert any("react native" in s for s in signals)

    def test_entity_reference_none(self, classifier: DependencyClassifier) -> None:
        prior = ["Python is a programming language"]
        signals = classifier._count_entity_references(
            "What is JavaScript?",
            prior,
        )
        # "Python" won't be found in "What is JavaScript?"
        assert len(signals) == 0

    def test_classify_with_prior_outputs_upgrades_level(self, classifier: DependencyClassifier) -> None:
        prior = [
            "Kubernetes orchestration handles container deployment and scaling",
            "The service mesh pattern with Envoy provides observability",
        ]
        result = classifier.classify(
            "Additionally, how does Kubernetes work with Envoy for scaling?",
            session_step=5,
            prior_outputs=prior,
        )
        # Should be at least PARTIAL (continuation signal + entity refs + depth)
        assert result.level in (DependencyLevel.PARTIAL, DependencyLevel.DEPENDENT)
        assert result.confidence > 0.5
