"""
CORS, rate limiting, and request-ID injection middleware for Asahi API.
"""

import logging
import time
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter using a sliding window.

    Args:
        max_requests: Maximum requests per window.
        window_seconds: Window size in seconds.
    """

    def __init__(
        self, max_requests: int = 100, window_seconds: int = 60
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Check if a request from this client is allowed.

        Args:
            client_id: Client identifier (e.g. IP address).

        Returns:
            True if the request is within the rate limit.
        """
        now = time.time()
        window_start = now - self._window_seconds

        # Clean up old entries
        self._requests[client_id] = [
            t for t in self._requests[client_id] if t > window_start
        ]

        if len(self._requests[client_id]) >= self._max_requests:
            return False

        self._requests[client_id].append(now)
        return True
