"""Circuit breaker, retry with exponential backoff, and timeout enforcement.

Provides per-provider resilience for LLM calls. Each provider gets its own
CircuitBreaker instance. The circuit opens after repeated failures and
automatically recovers after a cooldown period.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are rejected."""

    def __init__(self, provider: str, recovery_in_seconds: float = 0.0) -> None:
        self.provider = provider
        self.recovery_in_seconds = recovery_in_seconds
        super().__init__(
            f"Circuit breaker open for provider '{provider}' — "
            f"recovering in {recovery_in_seconds:.1f}s"
        )


class ProviderTimeoutError(Exception):
    """Raised when a provider call exceeds the hard timeout."""

    def __init__(self, provider: str, timeout_seconds: float) -> None:
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Provider '{provider}' call timed out after {timeout_seconds}s"
        )


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    HALF_OPEN = "HALF_OPEN"
    OPEN = "OPEN"


@dataclass
class CircuitBreakerConfig:
    """Tuneable parameters for a circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 1
    degraded_failure_threshold: int = 2


class CircuitBreaker:
    """Per-provider circuit breaker with three states.

    CLOSED  — all calls allowed; failures counted.
    OPEN    — calls rejected; transitions to HALF_OPEN after recovery timeout.
    HALF_OPEN — limited calls allowed; success closes circuit, failure reopens.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None, redis: Optional[Any] = None) -> None:
        self.name = name
        self._config = config or CircuitBreakerConfig()
        self._redis = redis
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._half_open_calls = 0
        self._effective_threshold = self._config.failure_threshold

        # Load persisted state from Redis if available
        if self._redis:
            asyncio.create_task(self._load_state_from_redis())

    async def _load_state_from_redis(self) -> None:
        """Load circuit breaker state from Redis.

        Restores state, failure_count, and last_failure_time if persisted.
        Allows circuit to maintain state across server restarts.
        """
        if not self._redis:
            return

        try:
            import json
            from datetime import datetime

            key = f"circuit:{self.name}:state"
            data = await self._redis.get(key)

            if data:
                state_dict = json.loads(data)
                self._state = CircuitState(state_dict["state"])
                self._failure_count = state_dict["failure_count"]

                # Convert ISO timestamp back to monotonic time (relative)
                if state_dict.get("last_failure"):
                    # Store as relative time from now
                    last_failure_iso = state_dict["last_failure"]
                    last_failure_dt = datetime.fromisoformat(last_failure_iso)
                    elapsed_since_failure = (datetime.now() - last_failure_dt).total_seconds()
                    self._last_failure_time = time.monotonic() - elapsed_since_failure

                logger.info(
                    "Circuit %s state loaded from Redis: %s (failures=%d)",
                    self.name,
                    self._state.value,
                    self._failure_count,
                )
        except Exception as exc:
            logger.warning("Failed to load circuit state from Redis for %s: %s", self.name, exc)

    async def _save_state_to_redis(self) -> None:
        """Save circuit breaker state to Redis with 1-hour TTL.

        Persists state so it survives server restarts.
        """
        if not self._redis:
            return

        try:
            import json
            from datetime import datetime, timezone

            key = f"circuit:{self.name}:state"

            # Convert monotonic time to absolute timestamp for persistence
            last_failure_iso = None
            if self._last_failure_time > 0:
                elapsed = time.monotonic() - self._last_failure_time
                last_failure_dt = datetime.now(timezone.utc) - timedelta(seconds=elapsed)
                last_failure_iso = last_failure_dt.isoformat()

            data = json.dumps({
                "state": self._state.value,
                "failure_count": self._failure_count,
                "last_failure": last_failure_iso,
            })

            # Save with 1-hour TTL
            await self._redis.set(key, data, ex=3600)

            logger.debug(
                "Circuit %s state saved to Redis: %s (failures=%d)",
                self.name,
                self._state.value,
                self._failure_count,
            )
        except Exception as exc:
            logger.warning("Failed to save circuit state to Redis for %s: %s", self.name, exc)

    @property
    def state(self) -> CircuitState:
        """Current circuit state (may auto-transition OPEN→HALF_OPEN)."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self._config.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info("Circuit %s transitioned OPEN → HALF_OPEN", self.name)
        return self._state

    def can_execute(self) -> bool:
        """Check whether a call is allowed through the circuit."""
        state = self.state  # triggers auto-transition
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._config.half_open_max_calls
        return False  # OPEN

    def record_success(self) -> None:
        """Record a successful call — resets failure count, closes circuit."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit %s HALF_OPEN → CLOSED (success)", self.name)
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0

        # Persist state to Redis
        if self._redis:
            asyncio.create_task(self._save_state_to_redis())

    def record_failure(self) -> None:
        """Record a failed call — may open the circuit."""
        self._failure_count += 1
        self._last_failure_time = time.monotonic()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            logger.warning("Circuit %s HALF_OPEN → OPEN (failure during probe)", self.name)

            # Persist state to Redis
            if self._redis:
                asyncio.create_task(self._save_state_to_redis())

            return

        if self._failure_count >= self._effective_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "Circuit %s CLOSED → OPEN (failures=%d, threshold=%d)",
                self.name, self._failure_count, self._effective_threshold,
            )

            # Persist state to Redis
            if self._redis:
                asyncio.create_task(self._save_state_to_redis())

            # Send alert when circuit opens
            try:
                import asyncio
                from app.core.alerts import alert_circuit_breaker_open

                asyncio.create_task(
                    alert_circuit_breaker_open(
                        provider=self.name,
                        failure_count=self._failure_count,
                        failure_threshold=self._effective_threshold,
                    )
                )
            except Exception:
                logger.error("Failed to send circuit breaker alert")

    def set_provider_health(self, health: str) -> None:
        """Adjust failure threshold based on provider health status.

        Degraded providers get a lower threshold so the circuit opens faster.
        """
        if health in ("degraded", "unreachable"):
            self._effective_threshold = self._config.degraded_failure_threshold
        else:
            self._effective_threshold = self._config.failure_threshold

    def recovery_remaining(self) -> float:
        """Seconds until the circuit will transition to HALF_OPEN."""
        if self._state != CircuitState.OPEN:
            return 0.0
        elapsed = time.monotonic() - self._last_failure_time
        return max(0.0, self._config.recovery_timeout_seconds - elapsed)

    def reset(self) -> None:
        """Reset circuit to initial state (for testing)."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_calls = 0
        self._effective_threshold = self._config.failure_threshold


# ---------------------------------------------------------------------------
# Retry with exponential backoff
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Configuration for retry with exponential backoff."""

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 10.0
    jitter: bool = True


def _compute_delay(attempt: int, config: RetryConfig) -> float:
    """Exponential backoff delay with optional jitter."""
    delay = min(
        config.base_delay_seconds * (2 ** attempt),
        config.max_delay_seconds,
    )
    if config.jitter:
        delay *= random.uniform(0.5, 1.5)
    return delay


async def execute_with_retry(
    func: Callable[[], Any],
    circuit: CircuitBreaker,
    retry_config: Optional[RetryConfig] = None,
    timeout_seconds: float = 30.0,
) -> Any:
    """Execute an async callable with circuit breaker, retry, and timeout.

    Args:
        func: An async callable (coroutine function or lambda returning coroutine).
        circuit: The circuit breaker for this provider.
        retry_config: Retry parameters. Uses defaults if None.
        timeout_seconds: Hard timeout per attempt in seconds.

    Returns:
        The result of the callable on success.

    Raises:
        CircuitOpenError: If the circuit is open.
        ProviderTimeoutError: If all attempts time out.
        Exception: The last exception if all retries are exhausted.
    """
    config = retry_config or RetryConfig()

    if not circuit.can_execute():
        raise CircuitOpenError(circuit.name, circuit.recovery_remaining())

    last_exception: Optional[Exception] = None

    for attempt in range(config.max_attempts):
        if attempt > 0 and not circuit.can_execute():
            raise CircuitOpenError(circuit.name, circuit.recovery_remaining())

        try:
            coro = func()
            result = await asyncio.wait_for(coro, timeout=timeout_seconds)
            circuit.record_success()
            return result
        except asyncio.TimeoutError:
            last_exception = ProviderTimeoutError(circuit.name, timeout_seconds)
            logger.warning(
                "Timeout on attempt %d/%d for %s",
                attempt + 1, config.max_attempts, circuit.name,
            )
        except Exception as exc:
            last_exception = exc
            logger.warning(
                "Error on attempt %d/%d for %s: %s",
                attempt + 1, config.max_attempts, circuit.name, exc,
            )

        # Don't sleep after the last attempt
        if attempt < config.max_attempts - 1:
            delay = _compute_delay(attempt, config)
            await asyncio.sleep(delay)

    # All retries exhausted
    circuit.record_failure()
    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"All {config.max_attempts} retry attempts exhausted for {circuit.name}")
