"""
Event logging and analytics for Asahi inference optimizer.

Tracks all inference events and provides cost/latency/quality analytics.
"""

import json
import os
from datetime import datetime, timezone


class InferenceTracker:
    def __init__(self, enable_kafka: bool = False, log_dir: str = "data"):
        self.enable_kafka = enable_kafka
        self.local_logs: list[dict] = []
        self.log_dir = log_dir
        self.kafka_producer = None

        if enable_kafka:
            self._init_kafka()

    def _init_kafka(self):
        """Initialize Kafka producer if available."""
        try:
            from kafka import KafkaProducer

            servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
            self.kafka_producer = KafkaProducer(
                bootstrap_servers=servers,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
        except Exception:
            self.kafka_producer = None
            self.enable_kafka = False

    def log_inference(self, event: dict) -> None:
        """Log an inference event to local storage and optionally Kafka."""
        event["logged_at"] = datetime.now(timezone.utc).isoformat()
        self.local_logs.append(event)

        if self.enable_kafka and self.kafka_producer:
            try:
                self.kafka_producer.send("asahi_inference_events", value=event)
            except Exception:
                pass  # Don't fail on Kafka errors

    def summarize(self) -> dict:
        """Return comprehensive analytics across all logged events."""
        if not self.local_logs:
            return {
                "total_cost": 0.0,
                "requests": 0,
                "avg_latency_ms": 0.0,
                "cache_hit_rate": 0.0,
                "cost_by_model": {},
                "requests_by_model": {},
                "cost_per_request_by_model": {},
                "top_models_by_usage": [],
                "estimated_savings_vs_gpt4": 0.0,
            }

        total_cost = sum(e.get("cost", 0) for e in self.local_logs)
        requests = len(self.local_logs)
        avg_latency = (
            sum(e.get("latency_ms", 0) for e in self.local_logs) / requests
        )
        cache_hits = sum(1 for e in self.local_logs if e.get("cache_hit", False))
        cache_hit_rate = cache_hits / requests

        # Cost by model
        cost_by_model: dict[str, float] = {}
        requests_by_model: dict[str, int] = {}
        for e in self.local_logs:
            model = e.get("model_used", "unknown")
            cost_by_model[model] = cost_by_model.get(model, 0) + e.get("cost", 0)
            requests_by_model[model] = requests_by_model.get(model, 0) + 1

        cost_per_request_by_model = {
            model: cost_by_model[model] / requests_by_model[model]
            for model in cost_by_model
        }

        # Top models by usage
        top_models = sorted(
            requests_by_model.items(), key=lambda x: x[1], reverse=True
        )

        # Estimate savings vs all-GPT-4: recalculate what GPT-4 would have cost
        from src.models import calculate_cost

        gpt4_total = 0.0
        for e in self.local_logs:
            input_tokens = e.get("tokens_input", 0)
            output_tokens = e.get("tokens_output", 0)
            gpt4_total += calculate_cost(input_tokens, output_tokens, "gpt-4-turbo")

        savings = gpt4_total - total_cost if gpt4_total > 0 else 0.0
        savings_pct = (savings / gpt4_total * 100) if gpt4_total > 0 else 0.0

        return {
            "total_cost": round(total_cost, 4),
            "gpt4_equivalent_cost": round(gpt4_total, 4),
            "requests": requests,
            "avg_latency_ms": round(avg_latency, 1),
            "cache_hit_rate": round(cache_hit_rate, 4),
            "cost_by_model": {k: round(v, 4) for k, v in cost_by_model.items()},
            "requests_by_model": requests_by_model,
            "cost_per_request_by_model": {
                k: round(v, 6) for k, v in cost_per_request_by_model.items()
            },
            "top_models_by_usage": top_models,
            "estimated_savings_vs_gpt4": round(savings_pct, 1),
            "absolute_savings": round(savings, 4),
        }

    def save_to_file(self, filename: str) -> str:
        """Save current logs to a JSON file. Returns the file path."""
        os.makedirs(self.log_dir, exist_ok=True)
        filepath = os.path.join(self.log_dir, filename)
        with open(filepath, "w") as f:
            json.dump(self.local_logs, f, indent=2)
        return filepath

    def save_summary(self, filename: str) -> str:
        """Save summary analytics to a JSON file. Returns the file path."""
        os.makedirs(self.log_dir, exist_ok=True)
        filepath = os.path.join(self.log_dir, filename)
        with open(filepath, "w") as f:
            json.dump(self.summarize(), f, indent=2)
        return filepath

    def reset(self) -> None:
        """Clear all logged events."""
        self.local_logs.clear()
