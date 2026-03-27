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
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ── Model catalog — single source of truth from config/models.yaml ──────────

_YAML_PATH = Path(__file__).resolve().parents[3] / "config" / "models.yaml"

# Hardcoded fallback — used only if YAML loading fails.
_FALLBACK_MODELS = {
    "gpt-4o": {
        "provider": "openai",
        "cost_per_1k_input": 0.0025,
        "cost_per_1k_output": 0.010,
        "quality_score": 0.93,
        "max_context": 128_000,
        "avg_latency_ms": 200,
    },
    "claude-opus-4-6": {
        "provider": "anthropic",
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.075,
        "quality_score": 0.97,
        "max_context": 200_000,
        "avg_latency_ms": 300,
    },
    "claude-haiku-4-5": {
        "provider": "anthropic",
        "cost_per_1k_input": 0.00025,
        "cost_per_1k_output": 0.00125,
        "quality_score": 0.80,
        "max_context": 200_000,
        "avg_latency_ms": 100,
    },
}

_model_catalog: Optional[dict] = None
_catalog_loaded: bool = False


def _normalize_quality(yaml_score: float) -> float:
    """Normalize YAML quality_score (3.0-5.0 scale) to 0.0-1.0."""
    return round(max(0.0, min(1.0, (yaml_score - 3.0) / 2.0)), 4)


def load_model_catalog(yaml_path: Optional[Path] = None) -> dict:
    """Load model catalog from config/models.yaml, normalizing field names.

    Field mapping:
        cost_per_1k_input_tokens  → cost_per_1k_input
        cost_per_1k_output_tokens → cost_per_1k_output
        quality_score (3.0-5.0)   → quality_score (0.0-1.0)
        max_input_tokens          → max_context
    """
    global _model_catalog, _catalog_loaded
    path = yaml_path or _YAML_PATH

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        models_raw = raw.get("models", {})
        catalog: dict = {}
        for model_id, props in models_raw.items():
            catalog[model_id] = {
                "provider": props.get("provider", "unknown"),
                "cost_per_1k_input": props.get("cost_per_1k_input_tokens", 0.01),
                "cost_per_1k_output": props.get("cost_per_1k_output_tokens", 0.01),
                "quality_score": _normalize_quality(props.get("quality_score", 3.5)),
                "max_context": props.get("max_input_tokens", 4096),
                "avg_latency_ms": props.get("avg_latency_ms", 500),
            }
        _model_catalog = catalog
        _catalog_loaded = True
        logger.info("Loaded %d models from %s", len(catalog), path)
        return catalog
    except Exception:
        logger.warning("Failed to load models from %s — using fallback catalog", path, exc_info=True)
        _model_catalog = dict(_FALLBACK_MODELS)
        _catalog_loaded = True
        return _model_catalog


def get_model_catalog() -> dict:
    """Return the loaded model catalog, loading from YAML on first call."""
    global _model_catalog
    if not _catalog_loaded:
        return load_model_catalog()
    return _model_catalog  # type: ignore[return-value]


@dataclass
class RoutingDecision:
    """Result of the routing engine's model selection."""

    selected_model: str
    selected_provider: str
    confidence: float
    reason: str
    factors: dict = field(default_factory=dict)
    # Debug metadata for routing transparency
    metadata: Optional[dict] = field(default_factory=lambda: None)


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
    """Agent Behavioral Analytics feedback loop for routing adjustments.

    Records per-agent model performance observations and computes routing
    adjustments (quality_boost, avg_latency, confidence_boost) from history.
    The routing engine applies these adjustments to model scores in _route_auto.
    """

    def __init__(self, enabled: bool = True, max_history: int = 100) -> None:
        self._enabled = enabled
        self._max_history = max_history
        # Per-agent history: {agent_id: [obs, ...]}
        self._history: dict[str, list[dict]] = {}

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
        """Record a routing observation for ABA learning."""
        if not self._enabled:
            return

        obs = {
            "model_used": model_used,
            "latency_ms": latency_ms,
            "quality_signal": quality_signal,
            "cost_usd": cost_usd,
        }

        history = self._history.setdefault(agent_id, [])
        history.append(obs)

        # Keep only the last N observations
        if len(history) > self._max_history:
            self._history[agent_id] = history[-self._max_history:]

        logger.debug(
            "ABA observation: agent=%s model=%s latency=%.1fms quality=%s cost=%s",
            agent_id, model_used, latency_ms, quality_signal, cost_usd,
        )

    def get_routing_adjustment(self, agent_id: str) -> Optional[dict]:
        """Return ABA-derived routing adjustments for the given agent.

        Returns a dict with per-model adjustments:
            {
                "model_id": {
                    "quality_boost": float,     # -0.2 to 0.2
                    "avg_latency": float,       # ms
                    "confidence_boost": float,   # 0.0 to 0.1
                }
            }
        Returns None if insufficient history.
        """
        history = self._history.get(agent_id)
        if not history or len(history) < 5:
            return None

        # Aggregate per-model stats
        model_stats: dict[str, dict] = {}
        for obs in history:
            model = obs["model_used"]
            stats = model_stats.setdefault(model, {
                "total": 0,
                "quality_sum": 0.0,
                "quality_count": 0,
                "latency_sum": 0.0,
                "cost_sum": 0.0,
            })
            stats["total"] += 1
            stats["latency_sum"] += obs["latency_ms"]
            if obs["quality_signal"] is not None:
                stats["quality_sum"] += obs["quality_signal"]
                stats["quality_count"] += 1
            if obs["cost_usd"] is not None:
                stats["cost_sum"] += obs["cost_usd"]

        adjustments: dict[str, dict] = {}
        for model, stats in model_stats.items():
            avg_quality = (
                stats["quality_sum"] / stats["quality_count"]
                if stats["quality_count"] > 0
                else 0.5
            )
            avg_latency = stats["latency_sum"] / stats["total"]

            # Quality boost: scale [0,1] quality signal to [-0.2, 0.2]
            quality_boost = (avg_quality - 0.5) * 0.4
            quality_boost = max(-0.2, min(0.2, quality_boost))

            # Confidence boost: more observations = higher confidence
            confidence_boost = min(0.1, stats["total"] / len(history) * 0.1)

            adjustments[model] = {
                "quality_boost": round(quality_boost, 4),
                "avg_latency": round(avg_latency, 1),
                "confidence_boost": round(confidence_boost, 4),
            }

        return adjustments


class RoutingEngine:
    """Selects the best model based on routing mode and context."""

    def __init__(
        self,
        models: Optional[dict] = None,
        aba_hook: Optional[ABAFeedbackHook] = None,
    ) -> None:
        self._models = models or get_model_catalog()
        self._aba_hook = aba_hook

    def route(self, ctx: RoutingContext) -> RoutingDecision:
        """Route a request to the best model based on mode."""
        mode = ctx.routing_mode.upper()
        if mode == "EXPLICIT":
            decision = self._route_explicit(ctx)
        elif mode == "GUIDED":
            decision = self._route_guided(ctx)
        else:
            decision = self._route_auto(ctx)

        # Attach debug metadata for routing transparency
        decision.metadata = self._build_routing_metadata(ctx, decision)
        return decision

    def _build_routing_metadata(self, ctx: RoutingContext, decision: RoutingDecision) -> dict:
        """Build comprehensive routing metadata for debugging.

        Returns metadata including:
        - routing_mode: The mode used (AUTO/EXPLICIT/GUIDED)
        - considered_models: List of all model candidates evaluated
        - selection_factors: Detailed breakdown of why this model was chosen
        - confidence_breakdown: How confidence score was calculated
        - context_snapshot: Key context values at decision time
        """
        metadata = {
            "routing_mode": ctx.routing_mode.upper(),
            "selected_model": decision.selected_model,
            "selected_provider": decision.selected_provider,
            "confidence": decision.confidence,
            "selection_reason": decision.reason,
        }

        # Context snapshot
        metadata["context"] = {
            "quality_preference": ctx.quality_preference,
            "latency_preference": ctx.latency_preference,
            "model_override": ctx.model_override,
            "provider_hint": ctx.provider_hint,
            "provider_health": ctx.provider_health or {},
        }

        # For AUTO mode, include candidates and scoring
        if ctx.routing_mode.upper() == "AUTO":
            # Get all available models
            available_models = []
            for model_id, model_info in self._models.items():
                provider = model_info.get("provider", "unknown")
                health = ctx.provider_health.get(provider, "healthy") if ctx.provider_health else "healthy"
                available_models.append({
                    "model_id": model_id,
                    "provider": provider,
                    "provider_health": health,
                    "cost_per_1k_input": model_info.get("cost_per_1k_input_tokens", 0),
                    "cost_per_1k_output": model_info.get("cost_per_1k_output_tokens", 0),
                    "quality": model_info.get("quality", 0),
                    "latency_class": model_info.get("latency_class", "unknown"),
                })

            metadata["considered_models"] = available_models
            metadata["total_candidates"] = len(available_models)

        # For GUIDED mode, include rules evaluated
        if ctx.routing_mode.upper() == "GUIDED" and ctx.guided_rules:
            metadata["guided_rules"] = ctx.guided_rules

        # Include decision factors (already populated by routing methods)
        metadata["factors"] = decision.factors

        return metadata

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
