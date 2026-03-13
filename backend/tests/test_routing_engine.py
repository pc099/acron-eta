"""Tests for the routing routing_engine service."""

import pytest

from app.services.routing import ABAFeedbackHook, RoutingContext, RoutingDecision, RoutingEngine


@pytest.fixture
def routing_engine() -> RoutingEngine:
    return RoutingEngine()


class TestAutoRouting:
    """Tests for AUTO routing mode."""

    def test_auto_selects_model(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(prompt="What is Python?", routing_mode="AUTO")
        decision = routing_engine.route(ctx)
        assert isinstance(decision, RoutingDecision)
        assert decision.selected_model in routing_engine._models
        assert decision.selected_provider in ("openai", "anthropic")
        assert 0 < decision.confidence <= 1.0
        assert decision.factors.get("mode") == "auto"

    def test_auto_prefers_quality_for_complex_prompt(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Analyze the implications of quantum computing on modern cryptography. "
            "Compare the strengths and weaknesses of lattice-based vs hash-based approaches. "
            "Synthesize your findings into a recommendation for enterprise security teams.",
            routing_mode="AUTO",
            quality_preference="high",
        )
        decision = routing_engine.route(ctx)
        # Complex prompt with high quality preference should pick a high-quality model
        model_info = routing_engine._models[decision.selected_model]
        assert model_info["quality_score"] >= 0.9

    def test_auto_avoids_unhealthy_provider(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="AUTO",
            provider_health={"openai": "unreachable", "anthropic": "healthy"},
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_provider == "anthropic"

    def test_auto_budget_pressure_favors_cheap(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="What is 2+2?",
            routing_mode="AUTO",
            budget_remaining_usd=1.0,
        )
        decision = routing_engine.route(ctx)
        model_info = routing_engine._models[decision.selected_model]
        # Under budget pressure, should pick a cheaper model
        assert model_info["cost_per_1k_input"] < 0.01

    def test_auto_low_latency_preference(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Quick lookup",
            routing_mode="AUTO",
            latency_preference="low",
        )
        decision = routing_engine.route(ctx)
        assert "latency" in decision.factors.get("winner_factors", {})


class TestExplicitRouting:
    """Tests for EXPLICIT routing mode."""

    def test_explicit_uses_specified_model(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.confidence == 1.0
        assert decision.factors.get("mode") == "explicit"

    def test_explicit_without_model_falls_to_auto(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override=None,
        )
        decision = routing_engine.route(ctx)
        # Should fall back to auto mode
        assert decision.factors.get("mode") == "auto"

    def test_explicit_unknown_model(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="custom-model-v1",
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "custom-model-v1"
        assert decision.confidence == 1.0


class TestGuidedRouting:
    """Tests for GUIDED routing mode."""

    def test_guided_model_allowlist(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={"model_allowlist": ["gpt-4o-mini", "claude-haiku-3-5"]},
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model in ("gpt-4o-mini", "claude-haiku-3-5")
        assert decision.factors.get("mode") == "guided"

    def test_guided_provider_restriction(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={"provider_restriction": "anthropic"},
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_provider == "anthropic"

    def test_guided_cost_ceiling(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={"cost_ceiling_per_1k": 0.001},
        )
        decision = routing_engine.route(ctx)
        model_info = routing_engine._models[decision.selected_model]
        assert model_info["cost_per_1k_input"] <= 0.001

    def test_guided_no_match_falls_back(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={"model_allowlist": ["nonexistent-model"]},
        )
        decision = routing_engine.route(ctx)
        # Should fall back to all models
        assert decision.selected_model in routing_engine._models
        assert "fallback=no_match" in decision.factors.get("rules_applied", [])

    def test_guided_combined_rules(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "provider_restriction": "openai",
                "cost_ceiling_per_1k": 0.001,
            },
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_provider == "openai"
        model_info = routing_engine._models[decision.selected_model]
        assert model_info["cost_per_1k_input"] <= 0.001


class TestAdvancedGuidedRouting:
    """Tests for advanced guided routing rules (step_based, time_based, fallback_chain)."""

    def test_step_based_selects_model(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "step_based": [
                    {"step": 1, "model": "gpt-4o-mini"},
                    {"step": 3, "model": "gpt-4-turbo"},
                ]
            },
            session_step=1,
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4o-mini"
        assert decision.factors.get("direct_rule") == "step_based"

    def test_step_based_higher_step(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "step_based": [
                    {"step": 1, "model": "gpt-4o-mini"},
                    {"step": 3, "model": "gpt-4-turbo"},
                ]
            },
            session_step=5,
        )
        decision = routing_engine.route(ctx)
        # Step 5 >= step 3, so gpt-4-turbo is selected
        assert decision.selected_model == "gpt-4-turbo"

    def test_step_based_no_session_step_skips(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "step_based": [{"step": 1, "model": "gpt-4o-mini"}],
            },
            session_step=None,
        )
        decision = routing_engine.route(ctx)
        # Without session_step, step_based rule is skipped
        assert decision.factors.get("direct_rule") != "step_based"

    def test_time_based_selects_model(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "time_based": [
                    {"hours": "0-11", "model": "gpt-4o-mini"},
                    {"hours": "12-23", "model": "gpt-4-turbo"},
                ]
            },
            utc_hour=14,
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.factors.get("direct_rule") == "time_based"

    def test_time_based_midnight_wrap(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "time_based": [{"hours": "22-6", "model": "gpt-4o-mini"}]
            },
            utc_hour=2,
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4o-mini"

    def test_fallback_chain_picks_first_healthy(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "fallback_chain": ["gpt-4-turbo", "gpt-4o-mini"]
            },
            provider_health={"openai": "healthy"},
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.factors.get("direct_rule") == "fallback_chain"

    def test_fallback_chain_skips_unhealthy(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "fallback_chain": ["gpt-4-turbo", "claude-sonnet-4-5", "gpt-4o-mini"]
            },
            provider_health={"openai": "unreachable", "anthropic": "healthy"},
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "claude-sonnet-4-5"

    def test_step_based_takes_priority_over_time_based(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "step_based": [{"step": 1, "model": "gpt-4o-mini"}],
                "time_based": [{"hours": "0-23", "model": "gpt-4-turbo"}],
            },
            session_step=1,
            utc_hour=12,
        )
        decision = routing_engine.route(ctx)
        # step_based has higher priority
        assert decision.selected_model == "gpt-4o-mini"
        assert decision.factors.get("direct_rule") == "step_based"

    def test_filter_rules_with_fallback_chain(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "provider_restriction": "openai",
                "fallback_chain": ["claude-sonnet-4-5", "gpt-4o-mini"],
            },
        )
        decision = routing_engine.route(ctx)
        # Provider restriction takes higher priority than fallback chain
        assert decision.selected_provider == "openai"

    def test_conflict_tracking(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="GUIDED",
            guided_rules={
                "model_allowlist": ["nonexistent-model"],
            },
        )
        decision = routing_engine.route(ctx)
        assert "conflicts" in decision.factors
        assert any("allowlist" in c for c in decision.factors["conflicts"])


class TestExplicitFallback:
    """Tests for explicit mode fallback on unhealthy/capability mismatch."""

    def test_explicit_fallback_on_unhealthy(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
            model_endpoint_health="unreachable",
            fallback_model_id="gpt-4o-mini",
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4o-mini"
        assert decision.factors.get("fallback") is True
        assert decision.factors.get("original_model") == "gpt-4-turbo"
        assert decision.confidence == 0.75

    def test_explicit_no_fallback_when_healthy(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
            model_endpoint_health="healthy",
            fallback_model_id="gpt-4o-mini",
        )
        decision = routing_engine.route(ctx)
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.confidence == 1.0

    def test_explicit_no_fallback_when_no_fallback_id(self, routing_engine: RoutingEngine) -> None:
        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
            model_endpoint_health="unreachable",
            fallback_model_id=None,
        )
        decision = routing_engine.route(ctx)
        # No fallback available — keeps explicit model
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.confidence == 1.0


class TestCapabilityMatch:
    """Tests for capability flags matching."""

    def test_capability_match_all_present(self) -> None:
        is_match, missing = RoutingEngine.check_capability_match(
            {"streaming": True, "json_mode": True},
            {"streaming": True, "json_mode": True, "vision": True},
        )
        assert is_match is True
        assert missing == []

    def test_capability_match_missing(self) -> None:
        is_match, missing = RoutingEngine.check_capability_match(
            {"streaming": True, "vision": True},
            {"streaming": True},
        )
        assert is_match is False
        assert "vision" in missing

    def test_capability_match_empty_requirements(self) -> None:
        is_match, missing = RoutingEngine.check_capability_match({}, {"streaming": True})
        assert is_match is True
        assert missing == []

    def test_explicit_capability_mismatch_with_fallback(self, routing_engine: RoutingEngine) -> None:
        # Add capability_flags to the model catalog for testing
        models = dict(routing_engine._models)
        models["gpt-4-turbo"] = dict(models["gpt-4-turbo"])
        models["gpt-4-turbo"]["capability_flags"] = {"streaming": True}
        engine = RoutingEngine(models=models)

        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
            capability_flags={"vision": True},
            fallback_model_id="gpt-4o-mini",
        )
        decision = engine.route(ctx)
        assert decision.selected_model == "gpt-4o-mini"
        assert decision.factors.get("fallback") is True
        assert "vision" in decision.factors.get("missing_capabilities", [])

    def test_explicit_capability_match_no_fallback(self, routing_engine: RoutingEngine) -> None:
        models = dict(routing_engine._models)
        models["gpt-4-turbo"] = dict(models["gpt-4-turbo"])
        models["gpt-4-turbo"]["capability_flags"] = {"streaming": True, "json_mode": True}
        engine = RoutingEngine(models=models)

        ctx = RoutingContext(
            prompt="Hello",
            routing_mode="EXPLICIT",
            model_override="gpt-4-turbo",
            capability_flags={"streaming": True},
        )
        decision = engine.route(ctx)
        assert decision.selected_model == "gpt-4-turbo"
        assert decision.confidence == 1.0


class TestComplexityEstimation:
    """Tests for query complexity estimation."""

    def test_simple_query(self, routing_engine: RoutingEngine) -> None:
        score = routing_engine._estimate_complexity("What is 2+2?")
        assert score < 0.3

    def test_complex_query(self, routing_engine: RoutingEngine) -> None:
        score = routing_engine._estimate_complexity(
            "Analyze and compare the architectural implications of microservices "
            "versus monolithic architecture. Evaluate the trade-offs in terms of "
            "scalability, maintainability, and deployment complexity. Synthesize "
            "your findings with step by step reasoning."
        )
        assert score > 0.5

    def test_code_query(self, routing_engine: RoutingEngine) -> None:
        score = routing_engine._estimate_complexity(
            "```python\ndef fibonacci(n):\n    pass\n```\nImplement this function."
        )
        assert score > 0.2


class TestABAFeedbackHook:
    """Tests for ABA feedback hook stub."""

    def test_disabled_record_is_noop(self) -> None:
        hook = ABAFeedbackHook(enabled=False)
        # Should not raise
        hook.record_observation(
            agent_id="agent-1",
            model_used="gpt-4o",
            latency_ms=120.0,
            quality_signal=0.9,
            cost_usd=0.002,
        )

    def test_enabled_record_does_not_raise(self) -> None:
        hook = ABAFeedbackHook(enabled=True)
        hook.record_observation(
            agent_id="agent-1",
            model_used="gpt-4o",
            latency_ms=120.0,
        )

    def test_adjustment_returns_none(self) -> None:
        hook = ABAFeedbackHook(enabled=True)
        result = hook.get_routing_adjustment("agent-1")
        assert result is None

    def test_engine_accepts_hook(self) -> None:
        hook = ABAFeedbackHook(enabled=False)
        engine = RoutingEngine(aba_hook=hook)
        assert engine._aba_hook is hook
        # Routing should still work normally
        ctx = RoutingContext(prompt="Hello", routing_mode="AUTO")
        decision = engine.route(ctx)
        assert decision.selected_model in engine._models
