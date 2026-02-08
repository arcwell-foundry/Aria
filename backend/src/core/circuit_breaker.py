"""Circuit breaker pattern for external service resilience."""

import enum
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a call is attempted on an open circuit."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        super().__init__(f"Circuit breaker is open for {service_name}")


class CircuitBreaker:
    """Circuit breaker for protecting calls to external services.

    Tracks consecutive failures and opens the circuit after a threshold
    is reached. After a recovery timeout, allows a single test request
    (half-open). Closes again on success, re-opens on failure.

    Args:
        service_name: Identifier for the protected service (used in logs).
        failure_threshold: Number of consecutive failures before opening.
        recovery_timeout: Seconds to wait before half-opening.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._state: CircuitState = CircuitState.CLOSED
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state, accounting for recovery timeout."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time > 0:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout and self.recovery_timeout > 0:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning(
                        "Circuit breaker HALF_OPEN for %s (testing recovery)",
                        self.service_name,
                    )
            return self._state

    def check(self) -> None:
        """Check if a call is allowed. Raises if circuit is open."""
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpen(self.service_name)

    def record_success(self) -> None:
        """Record a successful call. Resets failure count and closes circuit."""
        with self._lock:
            if self._state != CircuitState.CLOSED:
                logger.warning(
                    "Circuit breaker CLOSED for %s (recovered)",
                    self.service_name,
                )
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call. Opens circuit after threshold reached."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit breaker OPEN for %s after %d consecutive failures",
                        self.service_name,
                        self._failure_count,
                    )
                self._state = CircuitState.OPEN

    async def call_async(
        self, func: Callable[..., Awaitable[T]], *args: object, **kwargs: object
    ) -> T:
        """Execute an async function through the circuit breaker.

        Args:
            func: Async callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            The return value of func.

        Raises:
            CircuitBreakerOpen: If the circuit is open.
            Exception: Any exception raised by func (after recording the failure).
        """
        self.check()
        try:
            result = await func(*args, **kwargs)
        except Exception:
            self.record_failure()
            raise
        else:
            self.record_success()
            return result
