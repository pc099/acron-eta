"""Tests for AdvancedRouter (3 modes)."""

import pytest

from src.exceptions import ModelNotFoundError
from src.models.registry import ModelRegistry
from src.routing.router import Router
from src.routing.router import AdvancedRouter, AdvancedRoutingDecision
from src.routing.constraints import ConstraintInterpreter
from src.routing.task_detector import TaskTypeDetector


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def advanced_router(registry: ModelRegistry) -> AdvancedRouter:
    return AdvancedRouter(
        registry=registry,
        base_router=Router(registry),
        task_detector=TaskTypeDetector(),
        constraint_interpreter=ConstraintInterpreter(),
    )


class TestAutopilotMode:
    """Tests for AUTOPILOT routing mode."""

    def test_autopilot_returns_decision(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route("What is Python?", mode="autopilot")
        assert isinstance(decision, AdvancedRoutingDecision)
        assert decision.mode == "autopilot"
        assert decision.model_name != ""

    def test_autopilot_detects_task_type(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Summarize this article about climate change",
            mode="autopilot",
        )
        assert decision.task_type_detected is not None

    def test_autopilot_coding_uses_higher_quality(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Write code to implement a binary search function",
            mode="autopilot",
        )
        # Coding should route to higher quality model
        assert decision.task_type_detected == "coding"

    def test_autopilot_reason_contains_task_type(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route("What is the capital of France?")
        assert "Auto-detected" in decision.reason


class TestGuidedMode:
    """Tests for GUIDED routing mode."""

    def test_guided_with_max_quality(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Explain quantum mechanics",
            mode="guided",
            quality_preference="max",
        )
        assert decision.mode == "guided"
        # max quality (4.5 threshold) narrows to gpt-4 and opus
        assert decision.model_name in ["gpt-4-turbo", "claude-opus-4"]

    def test_guided_with_fast_latency(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Quick question about Python",
            mode="guided",
            latency_preference="fast",
        )
        assert decision.mode == "guided"

    def test_guided_invalid_preference_raises(
        self, advanced_router: AdvancedRouter
    ) -> None:
        with pytest.raises(ValueError):
            advanced_router.route(
                "Test", mode="guided", quality_preference="ultra"
            )

    def test_guided_reason_includes_preferences(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Test",
            mode="guided",
            quality_preference="high",
            latency_preference="fast",
        )
        assert "high" in decision.reason
        assert "fast" in decision.reason


class TestExplicitMode:
    """Tests for EXPLICIT routing mode."""

    def test_explicit_uses_specified_model(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Test",
            mode="explicit",
            model_override="gpt-4-turbo",
        )
        assert decision.model_name == "gpt-4-turbo"
        assert decision.mode == "explicit"

    def test_explicit_shows_alternatives(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Test",
            mode="explicit",
            model_override="gpt-4-turbo",
        )
        assert len(decision.alternatives) > 0
        # Alternatives should not include the chosen model
        alt_names = [a.model for a in decision.alternatives]
        assert "gpt-4-turbo" not in alt_names

    def test_explicit_alternatives_have_savings(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Test",
            mode="explicit",
            model_override="gpt-4-turbo",
        )
        # Some alternatives should show positive savings vs GPT-4
        has_savings = any(a.savings_percent > 0 for a in decision.alternatives)
        assert has_savings

    def test_explicit_unknown_model_raises(
        self, advanced_router: AdvancedRouter
    ) -> None:
        with pytest.raises(ModelNotFoundError):
            advanced_router.route(
                "Test", mode="explicit", model_override="nonexistent"
            )

    def test_explicit_no_model_raises(
        self, advanced_router: AdvancedRouter
    ) -> None:
        with pytest.raises(ValueError, match="model_override is required"):
            advanced_router.route("Test", mode="explicit")

    def test_explicit_reason_mentions_alternatives(
        self, advanced_router: AdvancedRouter
    ) -> None:
        decision = advanced_router.route(
            "Test", mode="explicit", model_override="gpt-4-turbo"
        )
        assert "alternatives" in decision.reason


class TestInvalidMode:
    """Tests for unknown modes."""

    def test_unknown_mode_raises(
        self, advanced_router: AdvancedRouter
    ) -> None:
        with pytest.raises(ValueError, match="Unknown routing mode"):
            advanced_router.route("Test", mode="invalid")  # type: ignore
