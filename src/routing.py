"""
Routing logic for Asahi inference optimizer.

Routes requests to the most cost-efficient model that satisfies
quality and latency constraints.
"""

from src.models import MODELS, estimate_tokens, calculate_cost


class Router:
    def __init__(self, models: dict | None = None):
        self.models = models or MODELS

    def select_model(
        self,
        prompt: str,
        latency_budget_ms: int = 300,
        quality_threshold: float = 3.5,
        cost_budget: float | None = None,
    ) -> tuple[str, str]:
        """
        Route request to optimal model based on constraints.

        Rules (in order):
        1. Filter models that don't meet quality threshold
        2. Filter models that exceed latency budget
        3. If cost_budget set, filter models that exceed it
        4. Among remaining, pick cheapest estimated cost

        Returns:
            (model_name, routing_reason)
        """
        if not prompt or not prompt.strip():
            return self._fallback("empty_prompt")

        estimated_input_tokens = estimate_tokens(prompt)
        # Estimate output at ~60% of input tokens as a heuristic
        estimated_output_tokens = max(50, int(estimated_input_tokens * 0.6))

        candidates = []
        for name, profile in self.models.items():
            # Check quality threshold
            if profile["quality_score"] < quality_threshold:
                continue
            # Check latency budget
            if profile["avg_latency_ms"] > latency_budget_ms:
                continue
            # Check token limits
            if estimated_input_tokens > profile["max_input_tokens"]:
                continue

            est_cost = calculate_cost(
                estimated_input_tokens, estimated_output_tokens, name
            )

            # Check cost budget
            if cost_budget is not None and est_cost > cost_budget:
                continue

            candidates.append((name, est_cost, profile["quality_score"]))

        if not candidates:
            return self._fallback("no_candidates")

        # Sort by cost ascending, then by quality descending as tiebreaker
        candidates.sort(key=lambda c: (c[1], -c[2]))
        chosen = candidates[0]

        reason = (
            f"Selected {chosen[0]}: est_cost=${chosen[1]:.4f}, "
            f"quality={chosen[2]}, "
            f"from {len(candidates)} candidates "
            f"(latency<={latency_budget_ms}ms, quality>={quality_threshold})"
        )
        return chosen[0], reason

    def _fallback(self, reason_code: str) -> tuple[str, str]:
        """Fallback to highest-quality model when no candidates match."""
        best = max(self.models.items(), key=lambda m: m[1]["quality_score"])
        reason = f"Fallback to {best[0]} ({reason_code}): highest quality={best[1]['quality_score']}"
        return best[0], reason

    def estimate_cost_all_models(self, prompt: str) -> dict[str, float]:
        """Return estimated cost for each model given a prompt."""
        input_tokens = estimate_tokens(prompt)
        output_tokens = max(50, int(input_tokens * 0.6))
        return {
            name: calculate_cost(input_tokens, output_tokens, name)
            for name in self.models
        }
