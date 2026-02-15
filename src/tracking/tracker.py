"""
Event tracking and analytics for Asahi inference optimizer.

Logs every inference event with full metadata for cost accounting,
quality measurement, and operational observability.  Persists to
local JSONL files (MVP) with a pluggable backend interface.
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from src.config import get_settings

logger = logging.getLogger(__name__)


class InferenceEvent(BaseModel):
    """A single inference event with full metadata.

    Attributes:
        request_id: UUID-based unique identifier.
        timestamp: UTC time of the event.
        user_id: Caller identity (if available).
        task_type: Task category, e.g. ``summarization``, ``faq``.
        model_selected: Model that handled the request.
        cache_hit: Whether the result came from cache.
        input_tokens: Actual input token count.
        output_tokens: Actual output token count.
        total_tokens: Sum of input and output tokens.
        latency_ms: End-to-end latency in milliseconds.
        cost: Computed dollar cost.
        routing_reason: Why this model was chosen.
        quality_score: Predicted or measured quality.
    """

    request_id: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    organization_id: Optional[str] = None
    user_id: Optional[str] = None
    task_type: Optional[str] = None
    model_selected: str = ""
    cache_hit: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int = 0
    cost: float = 0.0
    routing_reason: str = ""
    quality_score: Optional[float] = None


class EventTracker:
    """Tracks inference events and computes analytics.

    Persists events to daily JSONL files and keeps an in-memory copy
    for fast metric aggregation.

    Args:
        log_dir: Directory for JSONL log files.  Created if it does
            not exist.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir if log_dir is not None else Path(get_settings().tracking.log_dir)
        self._events: List[InferenceEvent] = []

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(
                "Could not create log directory",
                extra={"path": str(self._log_dir), "error": str(exc)},
            )

    def log_event(self, event: InferenceEvent) -> None:
        """Append an event to memory and persist to the daily JSONL file.

        Args:
            event: The inference event to record.
        """
        self._events.append(event)

        date_str = event.timestamp.strftime("%Y-%m-%d")
        filename = f"events_{date_str}.jsonl"
        filepath = self._log_dir / filename

        try:
            with open(filepath, "a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        except OSError as exc:
            logger.error(
                "Failed to write event to log file",
                extra={"path": str(filepath), "error": str(exc)},
            )

        logger.debug(
            "Event logged",
            extra={
                "request_id": event.request_id,
                "model": event.model_selected,
                "cache_hit": event.cache_hit,
            },
        )

    def get_metrics(self, org_id: Optional[str] = None) -> Dict[str, Any]:
        """Compute aggregate analytics across all tracked events.

        Args:
            org_id: If set, only include events for this organization.

        Returns:
            Dict containing analytics summary.
        """
        events = self._events if org_id is None else [e for e in self._events if e.organization_id == org_id]
        if not events:
            return {
                "total_cost": 0.0,
                "gpt4_equivalent_cost": 0.0,
                "requests": 0,
                "avg_latency_ms": 0.0,
                "cache_hit_rate": 0.0,
                "cost_by_model": {},
                "requests_by_model": {},
                "estimated_savings_vs_gpt4": 0.0,
                "absolute_savings": 0.0,
                "avg_quality": None,
            }

        total_cost = sum(e.cost for e in events)
        requests = len(events)
        avg_latency = sum(e.latency_ms for e in events) / requests
        cache_hits = sum(1 for e in events if e.cache_hit)
        cache_hit_rate = cache_hits / requests

        cost_by_model: Dict[str, float] = {}
        requests_by_model: Dict[str, int] = {}
        for event in events:
            model = event.model_selected or "unknown"
            cost_by_model[model] = cost_by_model.get(model, 0.0) + event.cost
            requests_by_model[model] = requests_by_model.get(model, 0) + 1

        _s = get_settings().tracking
        gpt4_input_rate = _s.baseline_input_rate
        gpt4_output_rate = _s.baseline_output_rate
        gpt4_total = sum(
            (e.input_tokens * gpt4_input_rate + e.output_tokens * gpt4_output_rate)
            / 1000
            for e in events
        )
        savings = gpt4_total - total_cost if gpt4_total > 0 else 0.0
        savings_pct = (savings / gpt4_total * 100) if gpt4_total > 0 else 0.0

        quality_scores = [e.quality_score for e in events if e.quality_score is not None]
        avg_quality = (
            round(sum(quality_scores) / len(quality_scores), 1)
            if quality_scores
            else None
        )

        return {
            "total_cost": round(total_cost, 4),
            "gpt4_equivalent_cost": round(gpt4_total, 4),
            "requests": requests,
            "avg_latency_ms": round(avg_latency, 1),
            "cache_hit_rate": round(cache_hit_rate, 4),
            "cost_by_model": {k: round(v, 4) for k, v in cost_by_model.items()},
            "requests_by_model": requests_by_model,
            "estimated_savings_vs_gpt4": round(savings_pct, 1),
            "absolute_savings": round(savings, 4),
            "avg_quality": avg_quality,
        }

    def get_events(
        self,
        since: Optional[datetime] = None,
        limit: int = 100,
        org_id: Optional[str] = None,
    ) -> List[InferenceEvent]:
        """Query in-memory events with optional time and org filter.

        Args:
            since: If provided, only return events after this timestamp.
            limit: Maximum number of events to return.
            org_id: If provided, only return events for this organization.

        Returns:
            List of matching events, newest first, capped at ``limit``.
        """
        events = self._events
        if org_id is not None:
            events = [e for e in events if e.organization_id == org_id]
        if since is not None:
            events = [e for e in events if e.timestamp >= since]
        return list(reversed(events[-limit:]))

    def load_from_file(self, path: Path) -> None:
        """Re-hydrate events from an existing JSONL file.

        Corrupted lines are skipped with a warning.

        Args:
            path: Path to the JSONL file.
        """
        if not path.exists():
            logger.warning(
                "Log file does not exist",
                extra={"path": str(path)},
            )
            return

        loaded = 0
        with open(path, "r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = InferenceEvent(**data)
                    self._events.append(event)
                    loaded += 1
                except (json.JSONDecodeError, Exception) as exc:
                    logger.warning(
                        "Skipping corrupted JSONL line",
                        extra={
                            "path": str(path),
                            "line_number": line_num,
                            "error": str(exc),
                        },
                    )

        logger.info(
            "Events loaded from file",
            extra={"path": str(path), "count": loaded},
        )

    def export_csv(self, path: Path) -> None:
        """Export all tracked events to a CSV file.

        Args:
            path: Output CSV file path.
        """
        if not self._events:
            logger.warning("No events to export")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(InferenceEvent.model_fields.keys())

        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for event in self._events:
                row = event.model_dump()
                row["timestamp"] = event.timestamp.isoformat()
                writer.writerow(row)

        logger.info(
            "Events exported to CSV",
            extra={"path": str(path), "count": len(self._events)},
        )

    def reset(self) -> None:
        """Clear all in-memory events."""
        self._events.clear()

    @property
    def event_count(self) -> int:
        """Number of events tracked in memory."""
        return len(self._events)
