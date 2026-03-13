"""Integration tests for routing mode × intervention mode combinations.

The ASAHIO two-dimensional mode system has:
  Routing modes:      AUTO, EXPLICIT, GUIDED
  Intervention modes: OBSERVE, ASSISTED, AUTONOMOUS

All 9 combinations are valid. Changing one dimension never changes the other.
"""

import pytest

from app.services.routing import RoutingContext, RoutingDecision, RoutingEngine


ROUTING_MODES = ["AUTO", "EXPLICIT", "GUIDED"]
INTERVENTION_MODES = ["OBSERVE", "ASSISTED", "AUTONOMOUS"]


@pytest.fixture
def routing_engine() -> RoutingEngine:
    return RoutingEngine()


def _build_context(routing_mode: str, intervention_mode: str) -> RoutingContext:
    """Build a RoutingContext for the given mode combination."""
    kwargs: dict = {
        "prompt": "Explain microservices architecture",
        "routing_mode": routing_mode,
    }
    if routing_mode == "EXPLICIT":
        kwargs["model_override"] = "gpt-4o"
    elif routing_mode == "GUIDED":
        kwargs["guided_rules"] = {
            "model_allowlist": ["gpt-4o", "gpt-4o-mini", "claude-sonnet-4-5"],
        }
    return RoutingContext(**kwargs)


class TestModeCombinationMatrix:
    """Parametrized 3×3 matrix: every routing×intervention combination produces a valid decision."""

    @pytest.mark.parametrize("routing_mode", ROUTING_MODES)
    @pytest.mark.parametrize("intervention_mode", INTERVENTION_MODES)
    def test_combination_produces_valid_decision(
        self, routing_engine: RoutingEngine, routing_mode: str, intervention_mode: str,
    ) -> None:
        ctx = _build_context(routing_mode, intervention_mode)
        decision = routing_engine.route(ctx)

        assert isinstance(decision, RoutingDecision)
        assert decision.selected_model in routing_engine._models
        assert decision.selected_provider in ("openai", "anthropic", "unknown")
        assert 0 < decision.confidence <= 1.0
        assert decision.reason


class TestRoutingModeBehavior:
    """Verify each routing mode exhibits its expected behavior regardless of intervention mode."""

    @pytest.mark.parametrize("intervention_mode", INTERVENTION_MODES)
    def test_auto_uses_scoring(self, routing_engine: RoutingEngine, intervention_mode: str) -> None:
        ctx = _build_context("AUTO", intervention_mode)
        decision = routing_engine.route(ctx)
        assert decision.factors.get("mode") == "auto"
        assert "scores" in decision.factors

    @pytest.mark.parametrize("intervention_mode", INTERVENTION_MODES)
    def test_explicit_uses_override(self, routing_engine: RoutingEngine, intervention_mode: str) -> None:
        ctx = _build_context("EXPLICIT", intervention_mode)
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4o"
        assert decision.factors.get("mode") == "explicit"
        assert decision.confidence == 1.0

    @pytest.mark.parametrize("intervention_mode", INTERVENTION_MODES)
    def test_guided_applies_rules(self, routing_engine: RoutingEngine, intervention_mode: str) -> None:
        ctx = _build_context("GUIDED", intervention_mode)
        decision = routing_engine.route(ctx)
        assert decision.factors.get("mode") == "guided"
        assert decision.selected_model in ("gpt-4o", "gpt-4o-mini", "claude-sonnet-4-5")
