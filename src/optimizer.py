"""
Core inference optimizer for Asahi.

Orchestrates caching, routing, inference execution, cost tracking,
and event logging to minimize inference costs while meeting quality
and latency constraints.
"""

import os
import time
import random
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.models import MODELS, estimate_tokens, calculate_cost, get_model_profile
from src.routing import Router
from src.cache import InferenceCache
from src.tracking import InferenceTracker

load_dotenv()


class InferenceOptimizer:
    def __init__(
        self,
        enable_kafka: bool = False,
        cache_ttl: int = 3600,
        use_mock: bool = False,
    ):
        self.cache = InferenceCache(ttl_seconds=cache_ttl)
        self.tracker = InferenceTracker(enable_kafka=enable_kafka)
        self.router = Router()
        self.use_mock = use_mock
        self._start_time = time.time()

    def infer(
        self,
        prompt: str,
        task_id: str = "",
        latency_budget_ms: int = 300,
        quality_threshold: float = 3.5,
        cost_budget: float | None = None,
        force_model: str | None = None,
    ) -> dict:
        """
        Main inference method.

        Args:
            prompt: The input prompt to send.
            task_id: Optional identifier for this request.
            latency_budget_ms: Maximum acceptable latency.
            quality_threshold: Minimum quality score (out of 5).
            cost_budget: Optional max cost for this request.
            force_model: If set, bypass routing and use this model.

        Returns:
            Dict with response, model_used, cost, latency_ms, cache_hit, etc.
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if not prompt or not prompt.strip():
            return self._error_result(task_id, "Empty prompt", timestamp)

        # 1. Check cache
        cached = self.cache.get(prompt)
        if cached is not None:
            result = {
                **cached,
                "task_id": task_id,
                "cache_hit": True,
                "timestamp": timestamp,
            }
            self.tracker.log_inference(result)
            return result

        # 2. Select model
        if force_model and force_model in MODELS:
            model_name = force_model
            routing_reason = f"Forced model: {force_model}"
        else:
            model_name, routing_reason = self.router.select_model(
                prompt=prompt,
                latency_budget_ms=latency_budget_ms,
                quality_threshold=quality_threshold,
                cost_budget=cost_budget,
            )

        # 3. Execute inference
        start = time.time()
        response_text, output_tokens = self._call_model(model_name, prompt)
        latency_ms = (time.time() - start) * 1000

        # 4. Calculate tokens and cost
        input_tokens = estimate_tokens(prompt)
        cost = calculate_cost(input_tokens, output_tokens, model_name)

        # 5. Build result
        result = {
            "task_id": task_id,
            "response": response_text,
            "model_used": model_name,
            "tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "tokens_total": input_tokens + output_tokens,
            "cost": cost,
            "latency_ms": round(latency_ms, 1),
            "cache_hit": False,
            "routing_reason": routing_reason,
            "timestamp": timestamp,
        }

        # 6. Cache result
        self.cache.put(prompt, result)

        # 7. Log event
        self.tracker.log_inference(result)

        return result

    def _call_model(self, model_name: str, prompt: str) -> tuple[str, int]:
        """
        Call the actual model API, or mock if use_mock is True.

        Returns:
            (response_text, output_token_count)
        """
        if self.use_mock:
            return self._mock_call(model_name, prompt)

        profile = get_model_profile(model_name)
        provider = profile["provider"]

        for attempt in range(3):
            try:
                if provider == "openai":
                    return self._call_openai(model_name, prompt)
                elif provider == "anthropic":
                    return self._call_anthropic(model_name, prompt)
                else:
                    raise ValueError(f"Unknown provider: {provider}")
            except Exception as e:
                if attempt == 2:
                    raise RuntimeError(
                        f"Failed after 3 retries for {model_name}: {e}"
                    ) from e
                # Exponential backoff: 1s, 2s, 4s
                time.sleep(2**attempt)

        # Unreachable, but satisfies type checker
        raise RuntimeError(f"Failed to call {model_name}")

    def _call_openai(self, model_name: str, prompt: str) -> tuple[str, int]:
        """Call OpenAI API."""
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        text = response.choices[0].message.content or ""
        output_tokens = response.usage.completion_tokens if response.usage else estimate_tokens(text)
        return text, output_tokens

    def _call_anthropic(self, model_name: str, prompt: str) -> tuple[str, int]:
        """Call Anthropic API."""
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        output_tokens = response.usage.output_tokens if response.usage else estimate_tokens(text)
        return text, output_tokens

    def _mock_call(self, model_name: str, prompt: str) -> tuple[str, int]:
        """
        Simulate an API call with realistic latency and token counts.
        Used for testing without burning API credits.
        """
        profile = get_model_profile(model_name)
        # Simulate latency with some variance
        base_latency = profile["avg_latency_ms"] / 1000
        jitter = random.uniform(0.8, 1.2)
        time.sleep(base_latency * jitter * 0.01)  # Scale down for tests

        input_tokens = estimate_tokens(prompt)
        output_tokens = max(20, int(input_tokens * random.uniform(0.3, 0.8)))

        response_text = (
            f"[Mock response from {model_name}] "
            f"Processed prompt with {input_tokens} input tokens. "
            f"This is a simulated response for testing purposes."
        )
        return response_text, output_tokens

    def _error_result(self, task_id: str, error: str, timestamp: str) -> dict:
        """Build an error result dict."""
        return {
            "task_id": task_id,
            "response": None,
            "model_used": None,
            "tokens_input": 0,
            "tokens_output": 0,
            "tokens_total": 0,
            "cost": 0.0,
            "latency_ms": 0.0,
            "cache_hit": False,
            "routing_reason": f"Error: {error}",
            "timestamp": timestamp,
            "error": error,
        }

    def get_metrics(self) -> dict:
        """Return current metrics summary."""
        summary = self.tracker.summarize()
        summary["cache_size"] = self.cache.size
        summary["cache_hit_rate"] = round(self.cache.hit_rate, 4)
        summary["uptime_seconds"] = round(time.time() - self._start_time, 1)
        return summary
