"""Tests for the context coherence validator service."""

import pytest

from app.services.coherence_validator import CoherenceValidator


@pytest.fixture
def validator() -> CoherenceValidator:
    return CoherenceValidator()


class TestFormatContinuity:
    """Tests for format continuity check."""

    def test_json_request_with_json_response(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Return the data as JSON",
            cached_response='{"name": "test", "value": 42}',
        )
        assert "format_continuity" not in result.failed_checks

    def test_json_request_with_text_response(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Return the data as JSON",
            cached_response="Here is a plain text response about the data.",
        )
        assert "format_continuity" in result.failed_checks


class TestEntityConsistency:
    """Tests for entity consistency check."""

    def test_matching_entities(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Explain \"microservices architecture\"",
            cached_response="Microservices architecture is a design pattern...",
        )
        assert "entity_consistency" not in result.failed_checks

    def test_missing_entities(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt='Explain "quantum computing"',
            cached_response="Python is a programming language used for data science.",
        )
        assert "entity_consistency" in result.failed_checks

    def test_no_entities_passes(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="what is 2+2?",
            cached_response="The answer is 4.",
        )
        assert "entity_consistency" not in result.failed_checks


class TestTemporalFreshness:
    """Tests for temporal freshness check."""

    def test_temporal_request_fresh_cache(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="What is the current stock price?",
            cached_response="The price is $150.",
            cache_age_seconds=60.0,
        )
        assert "temporal_freshness" not in result.failed_checks

    def test_temporal_request_stale_cache(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="What is the current stock price?",
            cached_response="The price is $150.",
            cache_age_seconds=7200.0,  # 2 hours > default 1 hour
        )
        assert "temporal_freshness" in result.failed_checks

    def test_non_temporal_request_old_cache(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="What is the capital of France?",
            cached_response="Paris is the capital of France.",
            cache_age_seconds=43200.0,  # 12 hours, within 24h default
        )
        assert "temporal_freshness" not in result.failed_checks


class TestStepCompatibility:
    """Tests for step compatibility check."""

    def test_same_step_compatible(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Do something",
            cached_response="Done",
            request_step=3,
            cache_step=3,
        )
        assert "step_compatibility" not in result.failed_checks

    def test_earlier_step_compatible(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Do something",
            cached_response="Done",
            request_step=5,
            cache_step=3,
        )
        assert "step_compatibility" not in result.failed_checks

    def test_later_step_incompatible(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Do something",
            cached_response="Done",
            request_step=2,
            cache_step=5,
        )
        assert "step_compatibility" in result.failed_checks


class TestOverallCoherence:
    """Tests for overall coherence scoring."""

    def test_fully_coherent(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="What is Python?",
            cached_response="Python is a programming language.",
        )
        assert result.is_coherent is True
        assert result.score >= 0.5

    def test_incoherent(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt='Return the current "Bitcoin price" as JSON',
            cached_response="The weather today is sunny and warm.",
            cache_age_seconds=7200.0,
        )
        assert result.is_coherent is False

    def test_elapsed_ms(self, validator: CoherenceValidator) -> None:
        result = validator.validate(
            request_prompt="Hello",
            cached_response="Hi there",
        )
        assert result.elapsed_ms >= 0
        # Should be well under 2ms budget
        assert result.elapsed_ms < 50  # generous bound for CI


class TestCoherenceMetrics:
    """Tests for coherence validation metrics tracking."""

    def test_metrics_track_passes(self) -> None:
        validator = CoherenceValidator()
        validator.validate("Hello", "Hi there")
        assert validator.metrics.total_checks == 1
        assert validator.metrics.passed == 1
        assert validator.metrics.failed == 0

    def test_metrics_track_failures(self) -> None:
        validator = CoherenceValidator()
        validator.validate(
            'Return "Bitcoin price" as JSON',
            "The weather today is sunny.",
            cache_age_seconds=7200.0,
        )
        assert validator.metrics.total_checks == 1
        assert validator.metrics.failed == 1

    def test_metrics_per_check_counters(self) -> None:
        validator = CoherenceValidator()
        # This will fail temporal_freshness AND entity_consistency → overall incoherent
        validator.validate(
            'Return the current "Bitcoin price" as JSON',
            "The weather is sunny.",
            cache_age_seconds=7200.0,
        )
        assert validator.metrics.failed >= 1
        # At least one per-check failure recorded
        total_per_check = sum(validator.metrics.per_check_failures.values())
        assert total_per_check >= 1

    def test_metrics_pass_rate(self) -> None:
        validator = CoherenceValidator()
        validator.validate("Hello", "Hi there")
        validator.validate("Hello", "Hi there")
        validator.validate(
            'Return "Bitcoin price" as JSON',
            "Sunny weather.",
            cache_age_seconds=7200.0,
        )
        # 2 passed out of 3
        assert 0.6 <= validator.metrics.pass_rate <= 0.7
