"""Tests for RequestQueue -- thread-safe batching queue."""

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from src.batching.queue import QueuedRequest, RequestQueue


def _make_request(
    request_id: str = "req-1",
    prompt: str = "hello",
    model: str = "claude-3-5-sonnet",
    batch_group: str = "faq:claude-3-5-sonnet",
    deadline_offset_ms: int = 500,
) -> QueuedRequest:
    """Helper to create a QueuedRequest with sensible defaults."""
    now = datetime.now(timezone.utc)
    return QueuedRequest(
        request_id=request_id,
        prompt=prompt,
        model=model,
        batch_group=batch_group,
        enqueued_at=now,
        deadline=now + timedelta(milliseconds=deadline_offset_ms),
    )


class TestQueuedRequest:
    """Tests for QueuedRequest model."""

    def test_creation(self) -> None:
        req = _make_request()
        assert req.request_id == "req-1"
        assert req.batch_group == "faq:claude-3-5-sonnet"
        assert req.future is None

    def test_deadline_is_after_enqueued(self) -> None:
        req = _make_request(deadline_offset_ms=1000)
        assert req.deadline > req.enqueued_at


class TestRequestQueue:
    """Tests for RequestQueue operations."""

    @pytest.fixture
    def queue(self) -> RequestQueue:
        return RequestQueue()

    # ------------------------------------------------------------------
    # enqueue / size
    # ------------------------------------------------------------------

    def test_enqueue_single(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1"))
        assert queue.size() == 1
        assert queue.size("faq:claude-3-5-sonnet") == 1

    def test_enqueue_multiple_same_group(self, queue: RequestQueue) -> None:
        for i in range(5):
            queue.enqueue(_make_request(f"r{i}"))
        assert queue.size() == 5
        assert queue.size("faq:claude-3-5-sonnet") == 5

    def test_enqueue_multiple_groups(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1", batch_group="faq:sonnet"))
        queue.enqueue(_make_request("r2", batch_group="summarization:gpt4"))
        assert queue.size() == 2
        assert queue.size("faq:sonnet") == 1
        assert queue.size("summarization:gpt4") == 1

    def test_enqueue_duplicate_raises(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("dup"))
        with pytest.raises(ValueError, match="already in the queue"):
            queue.enqueue(_make_request("dup"))

    # ------------------------------------------------------------------
    # get_batch
    # ------------------------------------------------------------------

    def test_get_batch_removes_requests(self, queue: RequestQueue) -> None:
        for i in range(5):
            queue.enqueue(_make_request(f"r{i}"))
        batch = queue.get_batch("faq:claude-3-5-sonnet", 3)
        assert len(batch) == 3
        assert queue.size("faq:claude-3-5-sonnet") == 2

    def test_get_batch_respects_max_size(self, queue: RequestQueue) -> None:
        for i in range(10):
            queue.enqueue(_make_request(f"r{i}"))
        batch = queue.get_batch("faq:claude-3-5-sonnet", 5)
        assert len(batch) == 5

    def test_get_batch_empty_group(self, queue: RequestQueue) -> None:
        batch = queue.get_batch("nonexistent", 5)
        assert batch == []

    def test_get_batch_drains_group(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1"))
        batch = queue.get_batch("faq:claude-3-5-sonnet", 10)
        assert len(batch) == 1
        assert queue.size("faq:claude-3-5-sonnet") == 0

    # ------------------------------------------------------------------
    # peek
    # ------------------------------------------------------------------

    def test_peek_does_not_remove(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1"))
        peeked = queue.peek("faq:claude-3-5-sonnet")
        assert len(peeked) == 1
        assert queue.size() == 1  # still in queue

    def test_peek_with_max_size(self, queue: RequestQueue) -> None:
        for i in range(5):
            queue.enqueue(_make_request(f"r{i}"))
        peeked = queue.peek("faq:claude-3-5-sonnet", max_size=2)
        assert len(peeked) == 2

    # ------------------------------------------------------------------
    # get_expired_groups
    # ------------------------------------------------------------------

    def test_no_expired_groups_initially(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1", deadline_offset_ms=10000))
        assert queue.get_expired_groups() == []

    def test_expired_group_detected(self, queue: RequestQueue) -> None:
        now = datetime.now(timezone.utc)
        req = QueuedRequest(
            request_id="expired-1",
            prompt="old request",
            model="claude-3-5-sonnet",
            batch_group="faq:sonnet",
            enqueued_at=now - timedelta(seconds=10),
            deadline=now - timedelta(seconds=1),  # already expired
        )
        queue.enqueue(req)
        expired = queue.get_expired_groups()
        assert "faq:sonnet" in expired

    # ------------------------------------------------------------------
    # get_all_groups
    # ------------------------------------------------------------------

    def test_get_all_groups(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1", batch_group="group-a"))
        queue.enqueue(_make_request("r2", batch_group="group-b"))
        groups = queue.get_all_groups()
        assert set(groups) == {"group-a", "group-b"}

    def test_get_all_groups_empty(self, queue: RequestQueue) -> None:
        assert queue.get_all_groups() == []

    # ------------------------------------------------------------------
    # remove
    # ------------------------------------------------------------------

    def test_remove_existing(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1"))
        assert queue.remove("r1") is True
        assert queue.size() == 0

    def test_remove_nonexistent(self, queue: RequestQueue) -> None:
        assert queue.remove("ghost") is False

    def test_remove_cleans_up_empty_group(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1", batch_group="g1"))
        queue.remove("r1")
        assert queue.get_all_groups() == []

    # ------------------------------------------------------------------
    # has_deadline_expired / oldest_request_age_ms
    # ------------------------------------------------------------------

    def test_has_deadline_expired_false(self, queue: RequestQueue) -> None:
        queue.enqueue(_make_request("r1", deadline_offset_ms=10000))
        assert queue.has_deadline_expired("faq:claude-3-5-sonnet") is False

    def test_has_deadline_expired_true(self, queue: RequestQueue) -> None:
        now = datetime.now(timezone.utc)
        req = QueuedRequest(
            request_id="exp",
            prompt="test",
            model="m",
            batch_group="g",
            enqueued_at=now - timedelta(seconds=5),
            deadline=now - timedelta(seconds=1),
        )
        queue.enqueue(req)
        assert queue.has_deadline_expired("g") is True

    def test_oldest_request_age_ms(self, queue: RequestQueue) -> None:
        now = datetime.now(timezone.utc)
        req = QueuedRequest(
            request_id="old",
            prompt="test",
            model="m",
            batch_group="g",
            enqueued_at=now - timedelta(milliseconds=500),
            deadline=now + timedelta(seconds=10),
        )
        queue.enqueue(req)
        age = queue.oldest_request_age_ms("g")
        assert age >= 400  # at least 400ms (allow some margin)

    def test_oldest_request_age_empty_group(self, queue: RequestQueue) -> None:
        assert queue.oldest_request_age_ms("nonexistent") == 0

    # ------------------------------------------------------------------
    # Thread safety
    # ------------------------------------------------------------------

    def test_concurrent_enqueue(self, queue: RequestQueue) -> None:
        """Multiple threads enqueuing simultaneously should not lose data."""
        errors: List[str] = []

        def enqueue_batch(start: int, count: int) -> None:
            for i in range(start, start + count):
                try:
                    queue.enqueue(
                        _make_request(f"thread-{start}-{i}", batch_group="shared")
                    )
                except Exception as exc:
                    errors.append(str(exc))

        threads = [
            threading.Thread(target=enqueue_batch, args=(t * 100, 50))
            for t in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent enqueue: {errors}"
        assert queue.size("shared") == 200  # 4 threads * 50 each

    def test_concurrent_enqueue_and_get_batch(self, queue: RequestQueue) -> None:
        """Producer and consumer threads operating concurrently."""
        produced = 100
        consumed: List[QueuedRequest] = []
        lock = threading.Lock()

        def producer() -> None:
            for i in range(produced):
                queue.enqueue(_make_request(f"p-{i}", batch_group="shared"))
                time.sleep(0.001)

        def consumer() -> None:
            while True:
                batch = queue.get_batch("shared", 10)
                if batch:
                    with lock:
                        consumed.extend(batch)
                elif queue.size() == 0:
                    time.sleep(0.01)
                    if queue.size() == 0:
                        break
                time.sleep(0.005)

        pt = threading.Thread(target=producer)
        ct = threading.Thread(target=consumer)
        pt.start()
        time.sleep(0.05)  # let producer get a head start
        ct.start()
        pt.join()
        ct.join(timeout=5)

        total = len(consumed) + queue.size("shared")
        assert total == produced
