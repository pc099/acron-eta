"""Routing engine — selects the best model based on routing mode.

Supports three routing modes:
- AUTO:     Multi-factor scoring (complexity, context length, budget, provider health)
- EXPLICIT: Pass-through to specified model
- GUIDED:   Rule-based evaluation with conflict resolution

Guided rule types (priority order):
  step_based > time_based > cost_ceiling > model_allowlist > provider_restriction > fallback_chain
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Default model catalog — maps model IDs to their properties.
# In production, this would be loaded from ModelEndpoint or config/models.yaml.
DEFAULT_MODELS = {
    "gpt-4-turbo": {
        "provider": "openai",
        "cost_per_1k_input": 0.01,
        "cost_per_1k_output": 0.03,
        "quality_score": 0.95,
        "max_context": 128_000,
        "avg_latency_ms": 2000,
    },
    "gpt-4o": {
        "provider": "openai",
        "cost_per_1k_input": 0.005,
        "cost_per_1k_output": 0.015,
        "quality_score": 0.93,
        "max_context": 128_000,
        "avg_latency_ms": 1500,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
        "quality_score": 0.82,
        "max_context": 128_000,
        "avg_latency_ms": 800,
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "cost_per_1k_input": 0.003,
        "cost_per_1k_output": 0.015,
        "quality_score": 0.94,
        "max_context": 200_000,
        "avg_latency_ms": 1800,
    },
    "claude-haiku-3-5": {
        "provider": "anthropic",
        "cost_per_1k_input": 0.0008,
        "cost_per_1k_output": 0.004,
        "quality_score": 0.80,
        "max_context": 200_000,
        "avg_latency_ms": 600,
    },
}


@dataclass
class RoutingDecision:
    """Result of the routing engine's model selection."""

    selected_model: str
    selected_provider: str
    confidence: float
    reason: str
    factors: dict = field(default_factory=dict)


@dataclass
class RoutingContext:
    """Input context for a routing decision."""

    prompt: str
    routing_mode: str = "AUTO"
    quality_preference: str = "high"
    latency_preference: str = "normal"
    model_override: Optional[str] = None
    provider_hint: Optional[str] = None
    budget_remaining_usd: Optional[float] = None
    provider_health: Optional[dict] = None  # {"openai": "healthy", "anthropic": "degraded"}
    guided_rules: Optional[dict] = None  # Rules from agent metadata
    session_step: Optional[int] = None  # Current step in session (for step_based rules)
    utc_hour: Optional[int] = None  # Override UTC hour for testing time_based rules
    capability_flags: Optional[dict] = None  # Required capabilities for this request
    model_endpoint_health: Optional[str] = None  # "healthy", "degraded", "unreachable"
    fallback_model_id: Optional[str] = None  # Fallback model if explicit model fails


class ABAFeedbackHook:
    """Stub for the Adaptive Budget Allocation (ABA) feedback loop.

    Phase 3 will implement the full ABA engine. This stub provides the
    interface so the routing engine can accept it now without breaking.
    """

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def record_observation(
        self,
        agent_id: str,
        model_used: str,
        latency_ms: float,
        quality_signal: Optional[float] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """Record a routing observation for ABA learning. No-op when disabled."""
        if not self._enabled:
            return
        logger.debug(
            "ABA observation: agent=%s model=%s latency=%.1fms quality=%s cost=%s",
            agent_id, model_used, latency_ms, quality_signal, cost_usd,
        )

    def get_routing_adjustment(self, agent_id: str) -> Optional[dict]:
        """Return an ABA-derived routing adjustment for the given agent.

        Returns None until Phase 3 implements the full engine.
        """
        return None


class RoutingEngine:
    """Selects the best model based on routing mode and context."""

    def __init__(
        self,
        models: Optional[dict] = None,
        aba_hook: Optional[ABAFeedbackHook] = None,
    ) -> None:
        self._models = models or DEFAULT_MODELS
        self._aba_hook = aba_hook

    def route(self, ctx: RoutingContext) -> RoutingDecision:
        """Route a request to the best model based on mode."""
        mode = ctx.routing_mode.upper()
        if mode == "EXPLICIT":
            return self._route_explicit(ctx)
        elif mode == "GUIDED":
            return self._route_guided(ctx)
        else:
            return self._route_auto(ctx)

    @staticmethod
    def check_capability_match(
        required: dict, available: dict,
    ) -> tuple[bool, list[str]]:
        """Check if a model endpoint's capabilities satisfy requirements.

        Returns ``(is_match, missing_capabilities)``.
        """
        missing: list[str] = []
        for key, value in required.items():
            if key not in available:
                missing.append(key)
            elif available[key] != value:
                missing.append(f"{key}={value}")
        return (len(missing) == 0, missing)

    def _route_explicit(self, ctx: RoutingContext) -> RoutingDecision:
        """EXPLICIT mode: use the specified model directly.

        Falls back to ``fallback_model_id`` when the explicit model is
        unhealthy or fails a capability check.
        """
        model_id = ctx.model_override
        if not model_id:
            return self._route_auto(ctx)

        model_info = self._models.get(model_id, {})
        provider = model_info.get("provider", ctx.provider_hint or "unknown")

        # Health-based fallback
        if ctx.model_endpoint_health in ("degraded", "unreachable") and ctx.fallback_model_id:
            fb_info = self._models.get(ctx.fallback_model_id, {})
            return RoutingDecision(
                selected_model=ctx.fallback_model_id,
                selected_provider=fb_info.get("provider", "unknown"),
                confidence=0.75,
                reason=f"Explicit model {model_id} unhealthy, fell back to {ctx.fallback_model_id}",
                factors={
                    "mode": "explicit",
                    "fallback": True,
                    "original_model": model_id,
                    "health": ctx.model_endpoint_health,
                },
            )

        # Capability check fallback
        if ctx.capability_flags:
            model_caps = model_info.get("capability_flags", {})
            is_match, missing = self.check_capability_match(ctx.capability_flags, model_caps)
            if not is_match and ctx.fallback_model_id:
                fb_info = self._models.get(ctx.fallback_model_id, {})
                return RoutingDecision(
                    selected_model=ctx.fallback_model_id,
                    selected_provider=fb_info.get("provider", "unknown"),
                    confidence=0.7,
                    reason=f"Explicit model {model_id} missing capabilities {missing}, fell back",
                    factors={
                        "mode": "explicit",
                        "fallback": True,
                        "original_model": model_id,
                        "missing_capabilities": missing,
                    },
                )

        return RoutingDecision(
            selected_model=model_id,
            selected_provider=provider,
            confidence=1.0,
            reason=f"Explicit model selection: {model_id}",
            factors={"mode": "explicit", "model_override": model_id},
        )

    # Rule priority order — higher number = higher priority.
    _RULE_PRIORITY: dict[str, int] = {
        "fallback_chain": 10,
        "provider_restriction": 20,
        "model_allowlist": 30,
        "cost_ceiling_per_1k": 40,
        "time_based": 50,
        "step_based": 60,
    }

    def _route_guided(self, ctx: RoutingContext) -> RoutingDecision:
        """GUIDED mode: apply customer-defined routing rules with conflict resolution.

        Rule priority (highest first):
          step_based > time_based > cost_ceiling > model_allowlist > provider_restriction > fallback_chain

        If a higher-priority rule produces a direct model selection (step_based, time_based,
        fallback_chain), it wins outright. Filter rules (allowlist, provider, cost ceiling)
        narrow the eligible set, then the highest-quality model from that set is chosen.
        """
        rules = ctx.guided_rules or {}
        eligible = dict(self._models)
        applied_rules: list[str] = []
        conflicts: list[str] = []

        # --- Direct-selection rules (checked in priority order, highest first) ---

        # step_based — select model based on session step number
        step_rules = rules.get("step_based")
        if step_rules and ctx.session_step is not None:
            model_id = self._apply_step_based(step_rules, ctx.session_step)
            if model_id and model_id in self._models:
                applied_rules.append(f"step_based=step{ctx.session_step}->{model_id}")
                return self._guided_decision(
                    model_id, applied_rules, conflicts, direct_rule="step_based",
                )

        # time_based — select model based on hour of day (UTC)
        time_rules = rules.get("time_based")
        if time_rules:
            model_id = self._apply_time_based(time_rules, ctx.utc_hour)
            if model_id and model_id in self._models:
                applied_rules.append(f"time_based=hour{ctx.utc_hour or datetime.now(timezone.utc).hour}->{model_id}")
                return self._guided_decision(
                    model_id, applied_rules, conflicts, direct_rule="time_based",
                )

        # --- Filter rules (narrow eligible set) ---

        # model allowlist
        allowlist = rules.get("model_allowlist")
        if allowlist:
            filtered = {k: v for k, v in eligible.items() if k in allowlist}
            if filtered:
                eligible = filtered
                applied_rules.append(f"allowlist={allowlist}")
            else:
                conflicts.append("allowlist_empty")

        # provider restriction
        provider_restriction = rules.get("provider_restriction")
        if provider_restriction:
            filtered = {
                k: v for k, v in eligible.items()
                if v.get("provider") == provider_restriction
            }
            if filtered:
                eligible = filtered
                applied_rules.append(f"provider={provider_restriction}")
            else:
                conflicts.append(f"provider_{provider_restriction}_empty")

        # cost ceiling (per 1k tokens)
        cost_ceiling = rules.get("cost_ceiling_per_1k")
        if cost_ceiling is not None:
            filtered = {
                k: v for k, v in eligible.items()
                if v.get("cost_per_1k_input", 0) <= cost_ceiling
            }
            if filtered:
                eligible = filtered
                applied_rules.append(f"cost_ceiling={cost_ceiling}")
            else:
                conflicts.append(f"cost_ceiling_{cost_ceiling}_empty")

        # fallback_chain — try models in order, skipping unhealthy providers
        fallback_chain = rules.get("fallback_chain")
        if fallback_chain:
            model_id = self._apply_fallback_chain(fallback_chain, ctx.provider_health)
            if model_id:
                # Only use fallback if no filter rules already selected a better candidate
                if not applied_rules:
                    applied_rules.append(f"fallback_chain={model_id}")
                    return self._guided_decision(
                        model_id, applied_rules, conflicts, direct_rule="fallback_chain",
                    )
                else:
                    conflicts.append(f"fallback_chain_deferred={model_id}")

        # If any filter rule failed (conflicts) and no filter rules succeeded, fall back
        if conflicts and not applied_rules:
            eligible = dict(self._models)
            applied_rules.append("fallback=no_match")
        elif not eligible:
            eligible = dict(self._models)
            applied_rules.append("fallback=no_match")

        # Within eligible models, pick highest quality
        best_model = max(eligible, key=lambda k: eligible[k].get("quality_score", 0))
        model_info = eligible[best_model]

        return RoutingDecision(
            selected_model=best_model,
            selected_provider=model_info.get("provider", "unknown"),
            confidence=0.85,
            reason=f"Guided routing with rules: {', '.join(applied_rules)}",
            factors={
                "mode": "guided",
                "rules_applied": applied_rules,
                "eligible_count": len(eligible),
                "conflicts": conflicts,
            },
        )

    def _guided_decision(
        self,
        model_id: str,
        applied_rules: list[str],
        conflicts: list[str],
        direct_rule: str,
    ) -> RoutingDecision:
        """Build a RoutingDecision for a direct-selection guided rule."""
        model_info = self._models.get(model_id, {})
        return RoutingDecision(
            selected_model=model_id,
            selected_provider=model_info.get("provider", "unknown"),
            confidence=0.90,
            reason=f"Guided routing via {direct_rule}: {', '.join(applied_rules)}",
            factors={
                "mode": "guided",
                "direct_rule": direct_rule,
                "rules_applied": applied_rules,
                "conflicts": conflicts,
            },
        )

    @staticmethod
    def _apply_step_based(rules: list[dict], step: int) -> Optional[str]:
        """Match current session step to a step_based rule."""
        # Sort by step descending — pick the highest matching step <= current
        sorted_rules = sorted(rules, key=lambda r: r.get("step", 0), reverse=True)
        for rule in sorted_rules:
            if step >= rule.get("step", 0):
                return rule.get("model")
        return None

    @staticmethod
    def _apply_time_based(rules: list[dict], utc_hour_override: Optional[int] = None) -> Optional[str]:
        """Match current UTC hour to a time_based rule."""
        current_hour = utc_hour_override if utc_hour_override is not None else datetime.now(timezone.utc).hour
        for rule in rules:
            hours_str = rule.get("hours", "")
            if "-" in hours_str:
                parts = hours_str.split("-")
                start, end = int(parts[0]), int(parts[1])
                if start <= end:
                    if start <= current_hour <= end:
                        return rule.get("model")
                else:
                    # Wraps midnight (e.g., "22-6")
                    if current_hour >= start or current_hour <= end:
                        return rule.get("model")
        return None

    def _apply_fallback_chain(
        self, chain: list[str], provider_health: Optional[dict] = None,
    ) -> Optional[str]:
        """Pick the first healthy model from the fallback chain."""
        health = provider_health or {}
        for model_id in chain:
            model_info = self._models.get(model_id)
            if not model_info:
                continue
            provider = model_info.get("provider", "unknown")
            if health.get(provider) not in ("degraded", "unreachable"):
                return model_id
        # All unhealthy — return first known model anyway
        for model_id in chain:
            if model_id in self._models:
                return model_id
        return None

    def _route_auto(self, ctx: RoutingContext) -> RoutingDecision:
        """AUTO mode: multi-factor scoring to select the best model."""
        scores: dict[str, float] = {}
        factor_details: dict[str, dict] = {}

        # Factor 1: Query complexity
        complexity = self._estimate_complexity(ctx.prompt)

        # Factor 2: Context length
        prompt_tokens = len(ctx.prompt.split()) * 1.3  # rough estimate

        # Factor 3: Provider health
        provider_health = ctx.provider_health or {}

        # Factor 4: Budget awareness
        budget_remaining = ctx.budget_remaining_usd

        for model_id, model_info in self._models.items():
            score = 0.0
            factors = {}

            # Quality factor (0-1) — weighted by preference
            quality = model_info.get("quality_score", 0.5)
            quality_weight = 0.4 if ctx.quality_preference == "high" else 0.2
            quality_score = quality * quality_weight
            factors["quality"] = round(quality_score, 4)
            score += quality_score

            # Cost factor (0-1) — cheaper is better, inversely proportional
            cost = model_info.get("cost_per_1k_input", 0.01)
            max_cost = max(m.get("cost_per_1k_input", 0.01) for m in self._models.values())
            cost_score = (1.0 - cost / max_cost) * 0.25 if max_cost > 0 else 0.0
            factors["cost"] = round(cost_score, 4)
            score += cost_score

            # Complexity match factor — complex queries need high-quality models
            if complexity > 0.4 and quality >= 0.9:
                complexity_bonus = 0.15
            elif complexity < 0.3 and quality < 0.85:
                complexity_bonus = 0.1  # simple query, cheap model is fine
            else:
                complexity_bonus = 0.0
            factors["complexity_match"] = round(complexity_bonus, 4)
            score += complexity_bonus

            # Context length factor — reject if model can't handle the prompt
            max_context = model_info.get("max_context", 4096)
            if prompt_tokens > max_context * 0.9:
                factors["context_fit"] = -1.0
                score -= 1.0  # effectively disqualify
            else:
                factors["context_fit"] = 0.0

            # Latency factor — fast models preferred when latency preference is low
            avg_latency = model_info.get("avg_latency_ms", 2000)
            if ctx.latency_preference == "low":
                latency_score = max(0, (3000 - avg_latency) / 3000) * 0.15
            else:
                latency_score = max(0, (3000 - avg_latency) / 3000) * 0.05
            factors["latency"] = round(latency_score, 4)
            score += latency_score

            # Provider health factor
            provider = model_info.get("provider", "unknown")
            health = provider_health.get(provider, "healthy")
            if health == "degraded":
                factors["health_penalty"] = -0.2
                score -= 0.2
            elif health == "unreachable":
                factors["health_penalty"] = -1.0
                score -= 1.0
            else:
                factors["health_penalty"] = 0.0

            # Budget factor — prefer cheaper models when budget is low
            if budget_remaining is not None and budget_remaining < 10.0:
                budget_penalty = cost / max_cost * 0.2 if max_cost > 0 else 0.0
                factors["budget_pressure"] = round(-budget_penalty, 4)
                score -= budget_penalty
            else:
                factors["budget_pressure"] = 0.0

            scores[model_id] = round(score, 4)
            factor_details[model_id] = factors

        # Select the highest-scoring model
        best_model = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_model]
        model_info = self._models[best_model]

        # Confidence based on margin over second-best
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else 0.5
        confidence = min(1.0, 0.5 + margin)

        return RoutingDecision(
            selected_model=best_model,
            selected_provider=model_info.get("provider", "unknown"),
            confidence=round(confidence, 4),
            reason=f"Auto routing selected {best_model} (score={best_score})",
            factors={
                "mode": "auto",
                "complexity": round(complexity, 4),
                "prompt_tokens_est": int(prompt_tokens),
                "scores": scores,
                "winner_factors": factor_details[best_model],
            },
        )

    def _estimate_complexity(self, prompt: str) -> float:
        """Estimate query complexity on a 0-1 scale using heuristics."""
        score = 0.0
        word_count = len(prompt.split())

        # Length factor
        if word_count > 200:
            score += 0.3
        elif word_count > 20:
            score += 0.15

        # Complexity indicators
        complex_patterns = [
            r"\banalyze\b", r"\bcompare\b", r"\bsynthesize\b", r"\bevaluate\b",
            r"\bexplain.*why\b", r"\bwhat.*implications\b", r"\bdesign\b",
            r"\barchitect\b", r"\bimplement\b", r"\brefactor\b",
            r"\bstep.by.step\b", r"\bchain.of.thought\b",
        ]
        matches = sum(1 for p in complex_patterns if re.search(p, prompt, re.IGNORECASE))
        score += min(0.4, matches * 0.1)

        # Code presence
        if "```" in prompt or "def " in prompt or "class " in prompt:
            score += 0.2

        # Question complexity
        question_count = prompt.count("?")
        if question_count > 2:
            score += 0.1

        return min(1.0, score)
