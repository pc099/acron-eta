"""Tests for AdaptiveThresholdTuner."""

import pytest

from src.embeddings.threshold import AdaptiveThresholdTuner, ThresholdConfig


@pytest.fixture
def tuner() -> AdaptiveThresholdTuner:
    return AdaptiveThresholdTuner()


class TestGetThreshold:
    """Tests for get_threshold."""

    def test_known_task_medium(self, tuner: AdaptiveThresholdTuner) -> None:
        t = tuner.get_threshold("faq", "medium")
        assert t == 0.80

    def test_faq_high_sensitivity(self, tuner: AdaptiveThresholdTuner) -> None:
        t = tuner.get_threshold("faq", "high")
        assert t == 0.70

    def test_faq_low_sensitivity(self, tuner: AdaptiveThresholdTuner) -> None:
        t = tuner.get_threshold("faq", "low")
        assert t == 0.90

    def test_coding_stricter_than_faq(self, tuner: AdaptiveThresholdTuner) -> None:
        coding = tuner.get_threshold("coding", "medium")
        faq = tuner.get_threshold("faq", "medium")
        assert coding > faq

    def test_unknown_task_uses_default(self, tuner: AdaptiveThresholdTuner) -> None:
        t = tuner.get_threshold("unknown_task", "medium")
        default = tuner.get_threshold("default", "medium")
        assert t == default

    def test_all_sensitivities_ordered(self, tuner: AdaptiveThresholdTuner) -> None:
        high = tuner.get_threshold("faq", "high")
        med = tuner.get_threshold("faq", "medium")
        low = tuner.get_threshold("faq", "low")
        assert high < med < low


class TestUpdateThreshold:
    """Tests for update_threshold."""

    def test_update_existing(self, tuner: AdaptiveThresholdTuner) -> None:
        tuner.update_threshold("faq", "medium", 0.75)
        assert tuner.get_threshold("faq", "medium") == 0.75

    def test_update_new_task(self, tuner: AdaptiveThresholdTuner) -> None:
        tuner.update_threshold("medical", "medium", 0.95)
        assert tuner.get_threshold("medical", "medium") == 0.95

    def test_update_out_of_range_raises(self, tuner: AdaptiveThresholdTuner) -> None:
        with pytest.raises(ValueError):
            tuner.update_threshold("faq", "medium", 1.5)

    def test_update_negative_raises(self, tuner: AdaptiveThresholdTuner) -> None:
        with pytest.raises(ValueError):
            tuner.update_threshold("faq", "medium", -0.1)
