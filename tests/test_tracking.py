"""
Tests for the event tracking and analytics module.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.tracking import EventTracker, InferenceEvent


class TestInferenceEvent:
    """Tests for InferenceEvent Pydantic model."""

    def test_create_event(self) -> None:
        event = InferenceEvent(
            request_id="req_001",
            model_selected="gpt-4-turbo",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=200,
            cost=0.01,
            routing_reason="test",
        )
        assert event.request_id == "req_001"
        assert event.cache_hit is False
        assert isinstance(event.timestamp, datetime)

    def test_event_defaults(self) -> None:
        event = InferenceEvent(request_id="req_002")
        assert event.user_id is None
        assert event.task_type is None
        assert event.input_tokens == 0
        assert event.cost == 0.0


class TestEventTracker:
    """Tests for EventTracker."""

    @pytest.fixture
    def tracker(self, tmp_path: Path) -> EventTracker:
        return EventTracker(log_dir=tmp_path / "logs")

    @pytest.fixture
    def sample_event(self) -> InferenceEvent:
        return InferenceEvent(
            request_id="req_test",
            model_selected="gpt-4-turbo",
            input_tokens=500,
            output_tokens=200,
            total_tokens=700,
            latency_ms=150,
            cost=0.011,
            routing_reason="Best quality/cost ratio",
        )

    def test_log_event(
        self, tracker: EventTracker, sample_event: InferenceEvent
    ) -> None:
        tracker.log_event(sample_event)
        assert tracker.event_count == 1

    def test_log_event_persists_to_file(
        self, tracker: EventTracker, sample_event: InferenceEvent, tmp_path: Path
    ) -> None:
        tracker.log_event(sample_event)
        log_dir = tmp_path / "logs"
        log_files = list(log_dir.glob("events_*.jsonl"))
        assert len(log_files) >= 1

        with open(log_files[0]) as f:
            line = f.readline()
        data = json.loads(line)
        assert data["request_id"] == "req_test"

    def test_get_metrics_empty(self, tracker: EventTracker) -> None:
        metrics = tracker.get_metrics()
        assert metrics["requests"] == 0
        assert metrics["total_cost"] == 0.0

    def test_get_metrics_with_events(self, tracker: EventTracker) -> None:
        for i in range(5):
            event = InferenceEvent(
                request_id=f"req_{i}",
                model_selected="gpt-4-turbo",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                latency_ms=200,
                cost=0.01,
                routing_reason="test",
            )
            tracker.log_event(event)

        metrics = tracker.get_metrics()
        assert metrics["requests"] == 5
        assert metrics["total_cost"] == pytest.approx(0.05, abs=0.001)
        assert metrics["avg_latency_ms"] == 200.0

    def test_get_metrics_cache_hit_rate(self, tracker: EventTracker) -> None:
        for i in range(4):
            event = InferenceEvent(
                request_id=f"req_{i}",
                model_selected="model",
                cache_hit=(i < 2),  # 2 hits, 2 misses
                cost=0.0 if i < 2 else 0.01,
                routing_reason="test",
            )
            tracker.log_event(event)

        metrics = tracker.get_metrics()
        assert metrics["cache_hit_rate"] == 0.5

    def test_get_metrics_cost_by_model(self, tracker: EventTracker) -> None:
        tracker.log_event(
            InferenceEvent(
                request_id="r1",
                model_selected="model-a",
                cost=0.05,
                routing_reason="test",
            )
        )
        tracker.log_event(
            InferenceEvent(
                request_id="r2",
                model_selected="model-b",
                cost=0.03,
                routing_reason="test",
            )
        )

        metrics = tracker.get_metrics()
        assert "model-a" in metrics["cost_by_model"]
        assert "model-b" in metrics["cost_by_model"]

    def test_get_events_all(
        self, tracker: EventTracker, sample_event: InferenceEvent
    ) -> None:
        tracker.log_event(sample_event)
        events = tracker.get_events()
        assert len(events) == 1
        assert events[0].request_id == "req_test"

    def test_get_events_with_limit(self, tracker: EventTracker) -> None:
        for i in range(10):
            tracker.log_event(
                InferenceEvent(request_id=f"req_{i}", routing_reason="test")
            )
        events = tracker.get_events(limit=3)
        assert len(events) == 3

    def test_get_events_with_since(self, tracker: EventTracker) -> None:
        old_event = InferenceEvent(
            request_id="old",
            timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
            routing_reason="test",
        )
        new_event = InferenceEvent(
            request_id="new",
            routing_reason="test",
        )
        tracker.log_event(old_event)
        tracker.log_event(new_event)

        since = datetime(2024, 1, 1, tzinfo=timezone.utc)
        events = tracker.get_events(since=since)
        assert len(events) == 1
        assert events[0].request_id == "new"

    def test_load_from_file(self, tracker: EventTracker, tmp_path: Path) -> None:
        # Write a JSONL file
        jsonl_path = tmp_path / "test_events.jsonl"
        event = InferenceEvent(
            request_id="loaded_event",
            model_selected="gpt-4-turbo",
            cost=0.01,
            routing_reason="test",
        )
        with open(jsonl_path, "w") as f:
            f.write(event.model_dump_json() + "\n")

        tracker.load_from_file(jsonl_path)
        assert tracker.event_count == 1
        events = tracker.get_events()
        assert events[0].request_id == "loaded_event"

    def test_load_from_file_skips_corrupted_lines(
        self, tracker: EventTracker, tmp_path: Path
    ) -> None:
        jsonl_path = tmp_path / "corrupted.jsonl"
        event = InferenceEvent(
            request_id="good_event",
            routing_reason="test",
        )
        with open(jsonl_path, "w") as f:
            f.write(event.model_dump_json() + "\n")
            f.write("this is not valid JSON\n")
            f.write(event.model_dump_json() + "\n")

        tracker.load_from_file(jsonl_path)
        # Should load 2 events (skipping the corrupted line)
        assert tracker.event_count == 2

    def test_load_from_nonexistent_file(
        self, tracker: EventTracker, tmp_path: Path
    ) -> None:
        tracker.load_from_file(tmp_path / "nonexistent.jsonl")
        assert tracker.event_count == 0

    def test_export_csv(self, tracker: EventTracker, tmp_path: Path) -> None:
        tracker.log_event(
            InferenceEvent(
                request_id="csv_event",
                model_selected="gpt-4-turbo",
                cost=0.01,
                routing_reason="test",
            )
        )
        csv_path = tmp_path / "export.csv"
        tracker.export_csv(csv_path)
        assert csv_path.exists()
        content = csv_path.read_text()
        assert "csv_event" in content
        assert "gpt-4-turbo" in content

    def test_export_csv_empty(self, tracker: EventTracker, tmp_path: Path) -> None:
        csv_path = tmp_path / "empty.csv"
        tracker.export_csv(csv_path)
        assert not csv_path.exists()

    def test_reset(
        self, tracker: EventTracker, sample_event: InferenceEvent
    ) -> None:
        tracker.log_event(sample_event)
        assert tracker.event_count == 1
        tracker.reset()
        assert tracker.event_count == 0

    def test_midnight_boundary(self, tracker: EventTracker) -> None:
        """Events across midnight should go to different log files."""
        event_before = InferenceEvent(
            request_id="before",
            timestamp=datetime(2025, 6, 15, 23, 59, 59, tzinfo=timezone.utc),
            routing_reason="test",
        )
        event_after = InferenceEvent(
            request_id="after",
            timestamp=datetime(2025, 6, 16, 0, 0, 1, tzinfo=timezone.utc),
            routing_reason="test",
        )
        tracker.log_event(event_before)
        tracker.log_event(event_after)
        assert tracker.event_count == 2
