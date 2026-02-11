"""
Thread-safe request queue for Asahi batch scheduling.

Holds pending requests organised by batch group.  All mutations are
protected by a ``threading.Lock`` so the queue is safe for concurrent
producers (API handlers) and a single consumer (the batch scheduler).
"""

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class QueuedRequest(BaseModel):
    """A single request waiting in the batch queue.

    Attributes:
        request_id: Unique identifier for the request.
        prompt: The user's input prompt.
        model: Target model for inference.
        batch_group: Key that groups compatible requests (e.g. ``"faq:sonnet"``).
        enqueued_at: UTC timestamp when the request entered the queue.
        deadline: UTC timestamp by which this request must be dispatched.
        future: An ``asyncio.Future`` resolved when the batch completes.
            Excluded from Pydantic serialisation.
    """

    request_id: str
    prompt: str
    model: str
    batch_group: str
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    deadline: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    future: Optional[asyncio.Future] = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}


class RequestQueue:
    """Thread-safe queue for pending batch requests.

    Requests are organised by batch group.  The scheduler periodically
    inspects the queue to decide when to flush a group.

    Thread safety:
        Every public method acquires an internal ``threading.Lock``
        before reading or mutating state.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._groups: Dict[str, List[QueuedRequest]] = defaultdict(list)
        self._request_index: Dict[str, str] = {}  # request_id -> group
        logger.info("RequestQueue initialised")

    def enqueue(self, request: QueuedRequest) -> None:
        """Add a request to the queue.

        Args:
            request: The request to enqueue.  Must have ``batch_group`` set.

        Raises:
            ValueError: If a request with the same ``request_id`` is already queued.
        """
        with self._lock:
            if request.request_id in self._request_index:
                raise ValueError(
                    f"Request '{request.request_id}' is already in the queue"
                )
            self._groups[request.batch_group].append(request)
            self._request_index[request.request_id] = request.batch_group

            logger.debug(
                "Request enqueued",
                extra={
                    "request_id": request.request_id,
                    "batch_group": request.batch_group,
                    "group_size": len(self._groups[request.batch_group]),
                },
            )

    def get_batch(self, group: str, max_size: int) -> List[QueuedRequest]:
        """Atomically pop up to ``max_size`` requests from a group.

        The popped requests are removed from the queue.

        Args:
            group: Batch group key.
            max_size: Maximum number of requests to return.

        Returns:
            List of requests (may be empty if the group does not exist
            or is already empty).
        """
        with self._lock:
            if group not in self._groups or not self._groups[group]:
                return []

            batch = self._groups[group][:max_size]
            self._groups[group] = self._groups[group][max_size:]

            for req in batch:
                self._request_index.pop(req.request_id, None)

            # Clean up empty groups
            if not self._groups[group]:
                del self._groups[group]

            logger.debug(
                "Batch popped",
                extra={"group": group, "batch_size": len(batch)},
            )
            return batch

    def peek(self, group: str, max_size: Optional[int] = None) -> List[QueuedRequest]:
        """Return requests from a group without removing them.

        Args:
            group: Batch group key.
            max_size: Maximum number of requests to return.
                ``None`` returns all.

        Returns:
            List of requests (may be empty).
        """
        with self._lock:
            items = self._groups.get(group, [])
            if max_size is not None:
                return list(items[:max_size])
            return list(items)

    def get_expired_groups(self) -> List[str]:
        """Return groups that contain at least one request past its deadline.

        Returns:
            List of group keys with expired requests.
        """
        now = datetime.now(timezone.utc)
        expired: List[str] = []

        with self._lock:
            for group, requests in self._groups.items():
                for req in requests:
                    if req.deadline <= now:
                        expired.append(group)
                        break

        return expired

    def get_all_groups(self) -> List[str]:
        """Return all non-empty group keys.

        Returns:
            List of group key strings.
        """
        with self._lock:
            return [g for g, items in self._groups.items() if items]

    def size(self, group: Optional[str] = None) -> int:
        """Return the number of queued requests.

        Args:
            group: If provided, count only that group.
                If ``None``, count across all groups.

        Returns:
            Request count.
        """
        with self._lock:
            if group is not None:
                return len(self._groups.get(group, []))
            return sum(len(items) for items in self._groups.values())

    def remove(self, request_id: str) -> bool:
        """Remove a specific request by ID.

        Args:
            request_id: The request to remove.

        Returns:
            ``True`` if the request was found and removed,
            ``False`` otherwise.
        """
        with self._lock:
            group = self._request_index.pop(request_id, None)
            if group is None:
                return False

            items = self._groups.get(group, [])
            for idx, req in enumerate(items):
                if req.request_id == request_id:
                    items.pop(idx)
                    break

            # Clean up empty groups
            if group in self._groups and not self._groups[group]:
                del self._groups[group]

            logger.debug(
                "Request removed",
                extra={"request_id": request_id, "group": group},
            )
            return True

    def has_deadline_expired(self, group: str) -> bool:
        """Check whether any request in a group has passed its deadline.

        Args:
            group: Batch group key.

        Returns:
            ``True`` if at least one request is past deadline.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            for req in self._groups.get(group, []):
                if req.deadline <= now:
                    return True
        return False

    def oldest_request_age_ms(self, group: str) -> int:
        """Return the age of the oldest request in a group in milliseconds.

        Args:
            group: Batch group key.

        Returns:
            Age in milliseconds, or ``0`` if the group is empty.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            items = self._groups.get(group, [])
            if not items:
                return 0
            oldest = items[0].enqueued_at
            delta = now - oldest
            return int(delta.total_seconds() * 1000)
