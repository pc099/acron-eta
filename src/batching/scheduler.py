"""
Batch scheduler for Asahi inference optimizer.

Background process that monitors the :class:`RequestQueue`, forms
batches when size or deadline thresholds are met, and dispatches them
to an executor callback.  Runs in its own daemon thread.
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from src.batching.engine import BatchConfig
from src.batching.queue import QueuedRequest, RequestQueue
from src.exceptions import BatchingError

logger = logging.getLogger(__name__)

# Type alias for the executor callback
BatchExecutor = Callable[[List[QueuedRequest]], List[str]]


class BatchScheduler:
    """Background scheduler that forms and dispatches request batches.

    The scheduler runs a polling loop (default every 50 ms) that inspects
    the queue and flushes groups when one of three conditions is met:

    1. **Size threshold** -- the group has ``max_batch_size`` requests.
    2. **Deadline** -- at least one request in the group has passed its
       deadline.
    3. **Approaching deadline** -- the group has ``min_batch_size``
       requests and the oldest request is older than 70% of
       ``max_wait_ms``.

    Args:
        queue: The shared request queue to monitor.
        executor: Callback that receives a list of requests and returns
            a list of response strings (one per request).
        config: Batch configuration (shared with :class:`BatchEngine`).
        poll_interval_ms: How often the scheduler checks the queue.
    """

    def __init__(
        self,
        queue: RequestQueue,
        executor: BatchExecutor,
        config: Optional[BatchConfig] = None,
        poll_interval_ms: int = 50,
    ) -> None:
        self._queue = queue
        self._executor = executor
        self._config = config or BatchConfig()
        self._poll_interval_s = poll_interval_ms / 1000.0

        self._thread: Optional[threading.Thread] = None
        self._running = threading.Event()
        self._lock = threading.Lock()

        # Counters
        self._batches_executed: int = 0
        self._requests_processed: int = 0
        self._batch_errors: int = 0
        self._individual_fallbacks: int = 0

        logger.info(
            "BatchScheduler initialised",
            extra={
                "poll_interval_ms": poll_interval_ms,
                "max_batch_size": self._config.max_batch_size,
                "min_batch_size": self._config.min_batch_size,
            },
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the scheduler background thread.

        Raises:
            BatchingError: If the scheduler is already running.
        """
        with self._lock:
            if self._running.is_set():
                raise BatchingError("BatchScheduler is already running")

            self._running.set()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="asahi-batch-scheduler",
                daemon=True,
            )
            self._thread.start()
            logger.info("BatchScheduler started")

    def stop(self, timeout: float = 5.0) -> None:
        """Stop the scheduler gracefully.

        Drains remaining queued requests via individual calls before
        shutting down.

        Args:
            timeout: Maximum seconds to wait for the thread to finish.
        """
        with self._lock:
            if not self._running.is_set():
                return
            self._running.clear()

        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

        # Drain remaining requests individually
        self._drain_remaining()
        logger.info("BatchScheduler stopped")

    @property
    def is_running(self) -> bool:
        """Whether the scheduler loop is active."""
        return self._running.is_set()

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    def flush_group(self, group: str) -> None:
        """Immediately flush all pending requests in a group.

        Args:
            group: The batch group key to flush.
        """
        batch = self._queue.get_batch(group, self._config.max_batch_size)
        if batch:
            self._execute_batch(batch)

    def stats(self) -> Dict[str, Any]:
        """Return scheduler statistics.

        Returns:
            Dict with counters for batches executed, requests processed,
            errors, fallbacks, queue size, and running state.
        """
        return {
            "running": self._running.is_set(),
            "batches_executed": self._batches_executed,
            "requests_processed": self._requests_processed,
            "batch_errors": self._batch_errors,
            "individual_fallbacks": self._individual_fallbacks,
            "queue_size": self._queue.size(),
        }

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main scheduler loop running in a daemon thread."""
        logger.debug("Scheduler loop started")
        try:
            while self._running.is_set():
                self._tick()
                time.sleep(self._poll_interval_s)
        except Exception as exc:
            logger.error(
                "Scheduler loop crashed; draining queue",
                extra={"error": str(exc)},
                exc_info=True,
            )
            self._running.clear()
            self._drain_remaining()

    def _tick(self) -> None:
        """Single iteration of the scheduler loop.

        Inspects every group and decides whether to flush based on
        size, deadline, or approaching-deadline heuristics.
        """
        groups = self._queue.get_all_groups()

        for group in groups:
            group_size = self._queue.size(group)
            if group_size == 0:
                continue

            # Condition 1: size threshold met
            if group_size >= self._config.max_batch_size:
                logger.debug(
                    "Flushing group: size threshold",
                    extra={"group": group, "size": group_size},
                )
                batch = self._queue.get_batch(
                    group, self._config.max_batch_size
                )
                if batch:
                    self._execute_batch(batch)
                continue

            # Condition 2: deadline expired
            if self._queue.has_deadline_expired(group):
                logger.debug(
                    "Flushing group: deadline expired",
                    extra={"group": group, "size": group_size},
                )
                batch = self._queue.get_batch(
                    group, self._config.max_batch_size
                )
                if batch:
                    self._execute_batch(batch)
                continue

            # Condition 3: approaching deadline with enough requests
            if group_size >= self._config.min_batch_size:
                oldest_age_ms = self._queue.oldest_request_age_ms(group)
                threshold_ms = int(self._config.max_wait_ms * 0.7)
                if oldest_age_ms > threshold_ms:
                    logger.debug(
                        "Flushing group: approaching deadline",
                        extra={
                            "group": group,
                            "oldest_age_ms": oldest_age_ms,
                            "threshold_ms": threshold_ms,
                        },
                    )
                    batch = self._queue.get_batch(
                        group, self._config.max_batch_size
                    )
                    if batch:
                        self._execute_batch(batch)

    # ------------------------------------------------------------------
    # Batch execution
    # ------------------------------------------------------------------

    def _execute_batch(self, batch: List[QueuedRequest]) -> None:
        """Execute a batch of requests via the executor callback.

        On failure, falls back to individual execution for each request.

        Args:
            batch: List of queued requests to execute together.
        """
        try:
            results = self._executor(batch)
            self._resolve_futures(batch, results)
            self._batches_executed += 1
            self._requests_processed += len(batch)

            logger.info(
                "Batch executed successfully",
                extra={
                    "batch_size": len(batch),
                    "batch_group": batch[0].batch_group if batch else "unknown",
                },
            )

        except Exception as exc:
            logger.error(
                "Batch execution failed; falling back to individual calls",
                extra={
                    "batch_size": len(batch),
                    "error": str(exc),
                },
                exc_info=True,
            )
            self._batch_errors += 1
            self._fallback_individual(batch)

    def _resolve_futures(
        self,
        batch: List[QueuedRequest],
        results: List[str],
    ) -> None:
        """Resolve each request's future with its corresponding result.

        If the results list is shorter than the batch, remaining futures
        are resolved with an error string.

        Args:
            batch: The batch of requests.
            results: Response strings from the executor.
        """
        for idx, req in enumerate(batch):
            if req.future is not None and not req.future.done():
                if idx < len(results):
                    try:
                        req.future.get_loop().call_soon_threadsafe(
                            req.future.set_result, results[idx]
                        )
                    except Exception:
                        # If the loop is closed or future already resolved
                        pass
                else:
                    try:
                        req.future.get_loop().call_soon_threadsafe(
                            req.future.set_exception,
                            BatchingError("No result returned for request"),
                        )
                    except Exception:
                        pass

    def _fallback_individual(self, batch: List[QueuedRequest]) -> None:
        """Execute each request individually when batch execution fails.

        Args:
            batch: Requests that failed as a batch.
        """
        for req in batch:
            try:
                results = self._executor([req])
                if req.future is not None and not req.future.done():
                    try:
                        req.future.get_loop().call_soon_threadsafe(
                            req.future.set_result, results[0]
                        )
                    except Exception:
                        pass
                self._individual_fallbacks += 1
                self._requests_processed += 1
            except Exception as exc:
                logger.error(
                    "Individual fallback also failed",
                    extra={
                        "request_id": req.request_id,
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                if req.future is not None and not req.future.done():
                    try:
                        req.future.get_loop().call_soon_threadsafe(
                            req.future.set_exception,
                            BatchingError(f"All execution paths failed: {exc}"),
                        )
                    except Exception:
                        pass

    def _drain_remaining(self) -> None:
        """Drain all remaining queued requests via individual execution."""
        groups = self._queue.get_all_groups()
        for group in groups:
            while self._queue.size(group) > 0:
                batch = self._queue.get_batch(group, 1)
                for req in batch:
                    try:
                        results = self._executor([req])
                        if req.future is not None and not req.future.done():
                            try:
                                req.future.get_loop().call_soon_threadsafe(
                                    req.future.set_result, results[0]
                                )
                            except Exception:
                                pass
                        self._requests_processed += 1
                    except Exception as exc:
                        logger.error(
                            "Drain failed for request",
                            extra={
                                "request_id": req.request_id,
                                "error": str(exc),
                            },
                        )
