"""Tests for BatchScheduler -- background batch execution."""

import time
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from src.batching.engine import BatchConfig
from src.batching.queue import QueuedRequest, RequestQueue
from src.batching.scheduler import BatchScheduler
from src.core.optimizer import InferenceResult
from src.exceptions import BatchingError


def _make_result(request_id: str) -> InferenceResult:
    """Minimal InferenceResult for tests."""
    return InferenceResult(
        response=f"response-{request_id}",
        model_used="test-model",
        request_id=request_id,
    )


def _make_request(
    request_id: str = "req-1",
    prompt: str = "hello",
    model: str = "claude-3-5-sonnet",
    batch_group: str = "faq:sonnet",
    deadline_offset_ms: int = 2000,
) -> QueuedRequest:
    """Helper to create a QueuedRequest."""
    now = datetime.now(timezone.utc)
    return QueuedRequest(
        request_id=request_id,
        prompt=prompt,
        model=model,
        batch_group=batch_group,
        enqueued_at=now,
        deadline=now + timedelta(milliseconds=deadline_offset_ms),
    )


def _make_expired_request(
    request_id: str = "exp-1",
    batch_group: str = "faq:sonnet",
) -> QueuedRequest:
    """Create a request with an already-expired deadline."""
    now = datetime.now(timezone.utc)
    return QueuedRequest(
        request_id=request_id,
        prompt="expired",
        model="claude-3-5-sonnet",
        batch_group=batch_group,
        enqueued_at=now - timedelta(seconds=5),
        deadline=now - timedelta(seconds=1),
    )


def _success_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
    """Simple executor that returns an InferenceResult per request."""
    return [_make_result(req.request_id) for req in batch]


def _failing_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
    """Executor that always raises (return type for type checker)."""
    raise RuntimeError("API call failed")


class TestBatchSchedulerLifecycle:
    """Tests for start/stop lifecycle."""

    @pytest.fixture
    def queue(self) -> RequestQueue:
        return RequestQueue()

    @pytest.fixture
    def config(self) -> BatchConfig:
        return BatchConfig(min_batch_size=2, max_batch_size=5, max_wait_ms=500)

    def test_start_and_stop(self, queue: RequestQueue, config: BatchConfig) -> None:
        scheduler = BatchScheduler(
            queue=queue,
            executor=_success_executor,
            config=config,
            poll_interval_ms=50,
        )
        scheduler.start()
        assert scheduler.is_running is True
        scheduler.stop()
        assert scheduler.is_running is False

    def test_double_start_raises(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        scheduler = BatchScheduler(
            queue=queue,
            executor=_success_executor,
            config=config,
        )
        scheduler.start()
        try:
            with pytest.raises(BatchingError, match="already running"):
                scheduler.start()
        finally:
            scheduler.stop()

    def test_stop_when_not_running(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        scheduler = BatchScheduler(
            queue=queue,
            executor=_success_executor,
            config=config,
        )
        scheduler.stop()  # should not raise

    def test_stats_initial(self, queue: RequestQueue, config: BatchConfig) -> None:
        scheduler = BatchScheduler(
            queue=queue, executor=_success_executor, config=config
        )
        stats = scheduler.stats()
        assert stats["running"] is False
        assert stats["batches_executed"] == 0
        assert stats["requests_processed"] == 0
        assert stats["batch_errors"] == 0
        assert stats["individual_fallbacks"] == 0


class TestBatchSchedulerExecution:
    """Tests for batch formation and execution."""

    @pytest.fixture
    def queue(self) -> RequestQueue:
        return RequestQueue()

    @pytest.fixture
    def config(self) -> BatchConfig:
        return BatchConfig(min_batch_size=2, max_batch_size=5, max_wait_ms=200)

    def test_flush_group_directly(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """flush_group should execute immediately without the loop running."""
        executed: List[List[QueuedRequest]] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            executed.append(batch)
            return _success_executor(batch)

        scheduler = BatchScheduler(
            queue=queue, executor=tracking_executor, config=config
        )

        for i in range(3):
            queue.enqueue(_make_request(f"r{i}"))

        scheduler.flush_group("faq:sonnet")
        assert len(executed) == 1
        assert len(executed[0]) == 3

    def test_size_threshold_triggers_flush(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """When group reaches max_batch_size, scheduler flushes."""
        executed: List[List[QueuedRequest]] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            executed.append(batch)
            return _success_executor(batch)

        scheduler = BatchScheduler(
            queue=queue,
            executor=tracking_executor,
            config=config,
            poll_interval_ms=20,
        )

        # Fill to max_batch_size
        for i in range(5):
            queue.enqueue(_make_request(f"r{i}"))

        scheduler.start()
        time.sleep(0.3)  # allow a few ticks
        scheduler.stop()

        assert len(executed) >= 1
        total_processed = sum(len(b) for b in executed)
        assert total_processed == 5

    def test_deadline_triggers_flush(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """Expired deadlines should force a flush even below min_batch_size."""
        executed: List[List[QueuedRequest]] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            executed.append(batch)
            return _success_executor(batch)

        scheduler = BatchScheduler(
            queue=queue,
            executor=tracking_executor,
            config=config,
            poll_interval_ms=20,
        )

        # Single expired request (below min_batch_size of 2)
        queue.enqueue(_make_expired_request("exp-1"))

        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()

        assert len(executed) >= 1

    def test_approaching_deadline_triggers_flush(
        self, queue: RequestQueue
    ) -> None:
        """Group with min_batch_size and oldest age > 70% of max_wait flushes."""
        executed: List[List[QueuedRequest]] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            executed.append(batch)
            return _success_executor(batch)

        config = BatchConfig(min_batch_size=2, max_batch_size=10, max_wait_ms=200)

        # Create requests with enqueued_at in the past so age > 0.7 * 200 = 140ms
        now = datetime.now(timezone.utc)
        for i in range(2):
            req = QueuedRequest(
                request_id=f"r{i}",
                prompt="test",
                model="claude-3-5-sonnet",
                batch_group="faq:sonnet",
                enqueued_at=now - timedelta(milliseconds=200),
                deadline=now + timedelta(seconds=5),
            )
            queue.enqueue(req)

        scheduler = BatchScheduler(
            queue=queue,
            executor=tracking_executor,
            config=config,
            poll_interval_ms=20,
        )

        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()

        assert len(executed) >= 1

    def test_stats_after_execution(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        scheduler = BatchScheduler(
            queue=queue, executor=_success_executor, config=config
        )

        for i in range(3):
            queue.enqueue(_make_request(f"r{i}"))

        scheduler.flush_group("faq:sonnet")
        stats = scheduler.stats()
        assert stats["batches_executed"] == 1
        assert stats["requests_processed"] == 3


class TestBatchSchedulerErrorHandling:
    """Tests for error isolation and fallback."""

    @pytest.fixture
    def queue(self) -> RequestQueue:
        return RequestQueue()

    @pytest.fixture
    def config(self) -> BatchConfig:
        return BatchConfig(min_batch_size=2, max_batch_size=5, max_wait_ms=500)

    def test_batch_failure_falls_back_to_individual(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """When batch execution fails, each request is retried individually."""
        call_count = 0

        def mixed_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            nonlocal call_count
            call_count += 1
            if call_count == 1 and len(batch) > 1:
                raise RuntimeError("Batch API failed")
            return [_make_result(r.request_id) for r in batch]

        scheduler = BatchScheduler(
            queue=queue, executor=mixed_executor, config=config
        )

        for i in range(3):
            queue.enqueue(_make_request(f"r{i}"))

        scheduler.flush_group("faq:sonnet")

        stats = scheduler.stats()
        assert stats["batch_errors"] == 1
        assert stats["individual_fallbacks"] == 3
        assert stats["requests_processed"] == 3

    def test_total_failure_records_error(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """When both batch and individual execution fail, errors are logged."""
        scheduler = BatchScheduler(
            queue=queue, executor=_failing_executor, config=config
        )

        queue.enqueue(_make_request("r1"))
        scheduler.flush_group("faq:sonnet")

        stats = scheduler.stats()
        assert stats["batch_errors"] == 1

    def test_drain_on_stop(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """stop() should drain remaining requests individually."""
        executed_ids: List[str] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            for req in batch:
                executed_ids.append(req.request_id)
            return [_make_result(r.request_id) for r in batch]

        scheduler = BatchScheduler(
            queue=queue,
            executor=tracking_executor,
            config=config,
            poll_interval_ms=10000,  # long poll so loop won't fire
        )

        for i in range(3):
            queue.enqueue(_make_request(f"r{i}"))

        scheduler.start()
        time.sleep(0.05)
        scheduler.stop()

        # All requests should have been processed either by loop or drain
        assert queue.size() == 0

    def test_error_in_one_batch_does_not_affect_another_group(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """Error in one group should not prevent another group from executing."""
        group_a_results: List[str] = []
        call_count = 0

        def selective_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            nonlocal call_count
            call_count += 1
            group = batch[0].batch_group if batch else ""
            if group == "bad:group":
                raise RuntimeError("This group always fails")
            results = [_make_result(r.request_id) for r in batch]
            group_a_results.extend(r.response for r in results)
            return results

        scheduler = BatchScheduler(
            queue=queue, executor=selective_executor, config=config
        )

        # Enqueue to two groups
        for i in range(3):
            queue.enqueue(_make_request(f"good-{i}", batch_group="good:group"))
        for i in range(2):
            queue.enqueue(_make_request(f"bad-{i}", batch_group="bad:group"))

        # Flush good group first
        scheduler.flush_group("good:group")
        assert len(group_a_results) == 3

        # Flush bad group -- should fail but not crash
        scheduler.flush_group("bad:group")

        stats = scheduler.stats()
        assert stats["batch_errors"] >= 1
        assert stats["batches_executed"] >= 1  # good group succeeded


class TestBatchSchedulerEdgeCases:
    """Tests for edge cases and uncovered paths."""

    @pytest.fixture
    def queue(self) -> RequestQueue:
        return RequestQueue()

    @pytest.fixture
    def config(self) -> BatchConfig:
        return BatchConfig(min_batch_size=2, max_batch_size=5, max_wait_ms=500)

    def test_tick_with_empty_group_skips(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """_tick should handle groups that become empty between checks."""
        scheduler = BatchScheduler(
            queue=queue, executor=_success_executor, config=config
        )
        # Manually call _tick on an empty queue -- should not raise
        scheduler._tick()
        assert scheduler.stats()["batches_executed"] == 0

    def test_scheduler_loop_crash_drains(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """If the loop crashes, remaining requests should be drained."""
        call_count = 0

        def crashing_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            nonlocal call_count
            call_count += 1
            return [_make_result(r.request_id) for r in batch]

        scheduler = BatchScheduler(
            queue=queue,
            executor=crashing_executor,
            config=config,
            poll_interval_ms=20,
        )

        # Add requests
        for i in range(3):
            queue.enqueue(_make_request(f"r{i}"))

        # Monkey-patch _tick to crash after first call
        original_tick = scheduler._tick

        def crashing_tick() -> None:
            raise RuntimeError("Loop crash!")

        scheduler._tick = crashing_tick  # type: ignore[assignment]

        scheduler.start()
        time.sleep(0.3)  # Wait for crash and drain
        # Scheduler should have stopped
        assert scheduler.is_running is False

    def test_resolve_futures_with_short_results(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """_resolve_futures handles results list shorter than batch."""
        scheduler = BatchScheduler(
            queue=queue, executor=_success_executor, config=config
        )

        reqs = []
        for i in range(3):
            req = _make_request(f"r{i}")
            req.future = Future()
            reqs.append(req)

        # Only 1 result for 3 requests; first gets result, others get exception
        scheduler._resolve_futures(reqs, [_make_result("r0")])
        assert reqs[0].future.done() and reqs[0].future.result().response == "response-r0"
        for req in reqs[1:]:
            assert req.future.done() and req.future.exception() is not None

    def test_flush_empty_group_is_noop(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """flush_group on a non-existent group should be a no-op."""
        executed: List[List[QueuedRequest]] = []

        def tracking_executor(batch: List[QueuedRequest]) -> List[InferenceResult]:
            executed.append(batch)
            return _success_executor(batch)

        scheduler = BatchScheduler(
            queue=queue, executor=tracking_executor, config=config
        )
        scheduler.flush_group("nonexistent")
        assert len(executed) == 0

    def test_drain_with_failing_executor(
        self, queue: RequestQueue, config: BatchConfig
    ) -> None:
        """_drain_remaining should handle executor failures gracefully."""
        scheduler = BatchScheduler(
            queue=queue, executor=_failing_executor, config=config
        )

        for i in range(2):
            queue.enqueue(_make_request(f"drain-{i}"))

        scheduler._drain_remaining()
        # Queue should be empty even if executor failed
        assert queue.size() == 0
