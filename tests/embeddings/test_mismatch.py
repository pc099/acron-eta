"""Tests for MismatchCostCalculator."""

import pytest

from src.embeddings.mismatch import MismatchConfig, MismatchCostCalculator


@pytest.fixture
def calc() -> MismatchCostCalculator:
    return MismatchCostCalculator()


class TestCalculateMismatchCost:
    """Tests for calculate_mismatch_cost."""

    def test_perfect_similarity_zero_cost(self, calc: MismatchCostCalculator) -> None:
        cost = calc.calculate_mismatch_cost(1.0, "faq", 0.01)
        assert cost == 0.0

    def test_zero_similarity_high_cost(self, calc: MismatchCostCalculator) -> None:
        cost = calc.calculate_mismatch_cost(0.0, "faq", 0.01)
        assert cost > 0.0

    def test_higher_similarity_lower_cost(self, calc: MismatchCostCalculator) -> None:
        high = calc.calculate_mismatch_cost(0.9, "faq", 0.01)
        low = calc.calculate_mismatch_cost(0.5, "faq", 0.01)
        assert high < low

    def test_coding_more_expensive_than_faq(self, calc: MismatchCostCalculator) -> None:
        faq_cost = calc.calculate_mismatch_cost(0.8, "faq", 0.01)
        coding_cost = calc.calculate_mismatch_cost(0.8, "coding", 0.01)
        assert coding_cost > faq_cost

    def test_legal_highest_sensitivity(self, calc: MismatchCostCalculator) -> None:
        legal_cost = calc.calculate_mismatch_cost(0.8, "legal", 0.01)
        faq_cost = calc.calculate_mismatch_cost(0.8, "faq", 0.01)
        assert legal_cost > faq_cost

    def test_unknown_task_uses_general(self, calc: MismatchCostCalculator) -> None:
        cost = calc.calculate_mismatch_cost(0.8, "unknown_task", 0.01)
        general_cost = calc.calculate_mismatch_cost(0.8, "general", 0.01)
        assert cost == general_cost


class TestShouldUseCache:
    """Tests for should_use_cache."""

    def test_high_similarity_should_cache(self, calc: MismatchCostCalculator) -> None:
        should, reason = calc.should_use_cache(0.95, "faq", 0.01)
        assert should is True
        assert "Using cache" in reason

    def test_low_similarity_should_recompute(self, calc: MismatchCostCalculator) -> None:
        should, reason = calc.should_use_cache(0.3, "coding", 0.001)
        assert should is False
        assert "Recomputing" in reason

    def test_perfect_match_always_caches(self, calc: MismatchCostCalculator) -> None:
        should, _ = calc.should_use_cache(1.0, "legal", 0.01)
        assert should is True

    def test_returns_reason(self, calc: MismatchCostCalculator) -> None:
        _, reason = calc.should_use_cache(0.85, "faq", 0.01)
        assert isinstance(reason, str)
        assert len(reason) > 0

    def test_custom_config(self) -> None:
        config = MismatchConfig(
            quality_penalty_weight=10.0,
            task_weights={"faq": 5.0},
        )
        calc = MismatchCostCalculator(config)
        should, _ = calc.should_use_cache(0.95, "faq", 0.01)
        # Very high penalty should make caching unlikely
        assert should is False
