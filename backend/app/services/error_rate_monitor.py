"""Error rate monitoring for alerting on spikes.

Monitors the error rate from Prometheus metrics and triggers alerts
when error rate exceeds threshold.

Background task runs every 60 seconds and checks error rate over
last 60 seconds. Alerts if rate exceeds 10 errors/min.
"""

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Deque, Optional

logger = logging.getLogger(__name__)


class ErrorRateMonitor:
    """Monitors error rate and triggers alerts on spikes."""

    def __init__(
        self,
        threshold_per_minute: int = 10,
        check_interval_seconds: int = 60,
    ):
        """Initialize error rate monitor.

        Args:
            threshold_per_minute: Alert if errors/minute exceeds this
            check_interval_seconds: How often to check error rate
        """
        self.threshold = threshold_per_minute
        self.check_interval = check_interval_seconds
        self._errors: Deque[tuple[datetime, str]] = deque(maxlen=1000)
        self._last_alert_time: Optional[datetime] = None
        self._alert_cooldown_seconds = 300  # 5 minutes between alerts

    def record_error(self, error_message: str) -> None:
        """Record an error occurrence.

        Args:
            error_message: The error message
        """
        self._errors.append((datetime.now(timezone.utc), error_message))

    def _get_recent_errors(self, seconds: int) -> list[tuple[datetime, str]]:
        """Get errors that occurred in the last N seconds.

        Args:
            seconds: Time window in seconds

        Returns:
            List of (timestamp, error_message) tuples
        """
        now = datetime.now(timezone.utc)
        cutoff = now.timestamp() - seconds

        recent = []
        for timestamp, error in self._errors:
            if timestamp.timestamp() >= cutoff:
                recent.append((timestamp, error))

        return recent

    async def _check_and_alert(self) -> None:
        """Check error rate and send alert if threshold exceeded."""
        recent_errors = self._get_recent_errors(60)  # Last 60 seconds
        error_count = len(recent_errors)

        if error_count <= self.threshold:
            return

        # Check alert cooldown
        now = datetime.now(timezone.utc)
        if self._last_alert_time:
            elapsed = (now - self._last_alert_time).total_seconds()
            if elapsed < self._alert_cooldown_seconds:
                logger.debug(
                    "Error rate spike detected but alert suppressed (cooldown: %ds remaining)",
                    int(self._alert_cooldown_seconds - elapsed)
                )
                return

        # Send alert
        sample_errors = [msg for _, msg in recent_errors[:10]]
        logger.warning(
            "Error rate spike: %d errors in 60s (threshold: %d)",
            error_count,
            self.threshold,
            extra={
                "error_count": error_count,
                "threshold": self.threshold,
                "sample_errors": sample_errors[:5],
            }
        )

        try:
            from app.core.alerts import alert_error_rate_spike

            await alert_error_rate_spike(
                error_count=error_count,
                time_window_seconds=60,
                threshold=self.threshold,
                sample_errors=sample_errors,
            )
            self._last_alert_time = now
        except Exception as exc:
            logger.error("Failed to send error rate alert: %s", exc)

    async def run(self) -> None:
        """Run error rate monitoring loop (background task)."""
        logger.info(
            "Error rate monitor started (threshold: %d errors/min, check interval: %ds)",
            self.threshold,
            self.check_interval,
        )

        while True:
            try:
                await asyncio.sleep(self.check_interval)
                await self._check_and_alert()
            except asyncio.CancelledError:
                logger.info("Error rate monitor stopped")
                break
            except Exception as exc:
                logger.error("Error in error rate monitor: %s", exc, exc_info=True)


# Global instance
_monitor: Optional[ErrorRateMonitor] = None


def get_error_rate_monitor() -> ErrorRateMonitor:
    """Get or create the global error rate monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = ErrorRateMonitor()
    return _monitor


def record_error(error_message: str) -> None:
    """Convenience function to record an error in the global monitor.

    Args:
        error_message: The error message

    Usage:
        from app.services.error_rate_monitor import record_error
        record_error("Failed to connect to Redis")
    """
    monitor = get_error_rate_monitor()
    monitor.record_error(error_message)
