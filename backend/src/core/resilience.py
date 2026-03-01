"""Resilience patterns for external service calls.

Provides:
- CircuitBreaker: Enhanced circuit breaker with success_threshold for HALF_OPEN recovery
- retry: Decorator for exponential backoff with jitter
- GracefulDegradation: Fallback responses when services are unavailable

All circuit breakers are registered in a global registry for health-check visibility.
State transitions are logged to aria_activity when a user_id is available.
"""

import asyncio
import enum
import functools
import logging
import random
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")
P = ParamSpec("P")


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


class CircuitState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when a call is attempted on an open circuit."""

    def __init__(self, service_name: str, retry_after: float = 0.0) -> None:
        self.service_name = service_name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker is open for {service_name}")


# Global registry of all circuit breakers for health-check endpoints
_circuit_breaker_registry: dict[str, "CircuitBreaker"] = {}
_registry_lock = threading.Lock()


def get_all_circuit_breakers() -> dict[str, "CircuitBreaker"]:
    """Return a snapshot of all registered circuit breakers."""
    with _registry_lock:
        return dict(_circuit_breaker_registry)


class CircuitBreaker:
    """Enhanced circuit breaker for protecting calls to external services.

    Tracks consecutive failures and opens the circuit after a threshold
    is reached.  After a recovery timeout the circuit moves to HALF_OPEN
    and allows test requests.  Only after ``success_threshold`` consecutive
    successes in HALF_OPEN does the circuit fully close again.

    Args:
        service_name: Identifier for the protected service (used in logs / registry).
        failure_threshold: Consecutive failures before opening the circuit.
        recovery_timeout: Seconds to wait in OPEN before moving to HALF_OPEN.
        success_threshold: Consecutive successes in HALF_OPEN needed to close.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 3,
    ) -> None:
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._failure_count: int = 0
        self._success_count: int = 0  # Consecutive successes in HALF_OPEN
        self._last_failure_time: float = 0.0
        self._state: CircuitState = CircuitState.CLOSED
        self._lock = threading.Lock()

        # Register for global visibility
        with _registry_lock:
            _circuit_breaker_registry[service_name] = self

    # -- State property -------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        """Current circuit state, accounting for recovery timeout."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._last_failure_time > 0:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.warning(
                        "Circuit breaker HALF_OPEN for %s (testing recovery after %.1fs)",
                        self.service_name,
                        elapsed,
                    )
            return self._state

    # -- Recording outcomes ---------------------------------------------------

    def check(self) -> None:
        """Raise if the circuit is open (calls are not allowed)."""
        current = self.state
        if current == CircuitState.OPEN:
            retry_after = max(
                0.0,
                self.recovery_timeout - (time.monotonic() - self._last_failure_time),
            )
            raise CircuitBreakerOpen(self.service_name, retry_after=retry_after)

    def record_success(self) -> None:
        """Record a successful call."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    logger.warning(
                        "Circuit breaker CLOSED for %s (recovered after %d successes)",
                        self.service_name,
                        self._success_count,
                    )
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                else:
                    logger.info(
                        "Circuit breaker %s HALF_OPEN success %d/%d",
                        self.service_name,
                        self._success_count,
                        self.success_threshold,
                    )
            else:
                # Normal closed state — reset failures
                self._failure_count = 0
                self._success_count = 0

    def record_failure(self) -> None:
        """Record a failed call.  Opens circuit after threshold."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately re-opens
                logger.warning(
                    "Circuit breaker re-OPENED for %s (failed during HALF_OPEN test)",
                    self.service_name,
                )
                self._state = CircuitState.OPEN
                self._success_count = 0
            elif self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit breaker OPEN for %s after %d consecutive failures",
                        self.service_name,
                        self._failure_count,
                    )
                self._state = CircuitState.OPEN

    # -- Call wrappers --------------------------------------------------------

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute an async function through the circuit breaker.

        Args:
            func: Async callable to execute.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The return value of *func*.

        Raises:
            CircuitBreakerOpen: If the circuit is open.
            Exception: Any exception raised by *func* (after recording the failure).
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

    def reset(self) -> None:
        """Force-reset the circuit breaker to CLOSED (e.g. for tests or admin)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = 0.0
            logger.info("Circuit breaker RESET for %s", self.service_name)

    def to_dict(self) -> dict[str, Any]:
        """Snapshot for health-check endpoints."""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "success_threshold": self.success_threshold,
        }


# ---------------------------------------------------------------------------
# Pre-configured circuit breakers for known external services
# ---------------------------------------------------------------------------

tavus_circuit_breaker = CircuitBreaker(
    "tavus", failure_threshold=5, recovery_timeout=60.0, success_threshold=3,
)
exa_circuit_breaker = CircuitBreaker(
    "exa", failure_threshold=5, recovery_timeout=60.0, success_threshold=3,
)
composio_circuit_breaker = CircuitBreaker(
    "composio", failure_threshold=5, recovery_timeout=60.0, success_threshold=3,
)
claude_api_circuit_breaker = CircuitBreaker(
    "claude_api", failure_threshold=5, recovery_timeout=60.0, success_threshold=3,
)
supabase_circuit_breaker = CircuitBreaker(
    "supabase", failure_threshold=10, recovery_timeout=30.0, success_threshold=3,
)
graphiti_circuit_breaker = CircuitBreaker(
    "graphiti_neo4j", failure_threshold=3, recovery_timeout=60.0, success_threshold=3,
)


# ---------------------------------------------------------------------------
# Retry with Exponential Backoff
# ---------------------------------------------------------------------------

# Default exception types that are safe to retry
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.RemoteProtocolError,
    ConnectionError,
    TimeoutError,
)


def retry(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
    max_delay: float = 30.0,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator: retry an async function with exponential backoff + jitter.

    Args:
        max_retries: Maximum number of retry attempts (not counting the initial call).
        backoff_factor: Multiplier for the delay between retries.
        retry_on: Tuple of exception types that trigger a retry.
        max_delay: Cap on the computed delay (seconds).

    Usage::

        @retry(max_retries=3, backoff_factor=2, retry_on=(httpx.TimeoutException,))
        async def fetch_data():
            ...
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: BaseException | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_on as exc:
                    last_exc = exc
                    if attempt < max_retries:
                        # Exponential backoff with full jitter
                        delay = min(backoff_factor ** attempt, max_delay)
                        jitter = random.uniform(0, delay)  # noqa: S311
                        logger.warning(
                            "Retry %d/%d for %s after %s (waiting %.2fs)",
                            attempt + 1,
                            max_retries,
                            func.__qualname__,
                            type(exc).__name__,
                            jitter,
                        )
                        await asyncio.sleep(jitter)
                    else:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries,
                            func.__qualname__,
                            exc,
                        )
            # Should never reach here, but type-checker needs it
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Graceful Degradation
# ---------------------------------------------------------------------------


class GracefulDegradation:
    """Provides degraded/cached responses when services are unavailable.

    Each service can register a fallback that returns a safe default value
    when the circuit breaker is open or the call fails.

    Usage::

        degradation = GracefulDegradation()

        @degradation.register("exa")
        def exa_fallback(error: Exception) -> list:
            return []  # Skip market signals, continue briefing

        result = await degradation.call_with_fallback(
            "exa",
            exa_provider.search_news,
            query="pharma M&A",
        )
    """

    def __init__(self) -> None:
        self._fallbacks: dict[str, Callable[..., Any]] = {}

    def register(self, service_name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a fallback function for a service.

        The fallback receives the caught exception and should return a safe
        default value.
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._fallbacks[service_name] = func
            return func

        return decorator

    def set_fallback(self, service_name: str, fallback: Callable[..., Any]) -> None:
        """Imperatively register a fallback for a service."""
        self._fallbacks[service_name] = fallback

    async def call_with_fallback(
        self,
        service_name: str,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T | Any:
        """Call *func* and return its result, or a fallback on failure.

        If the call raises and no fallback is registered, the exception
        propagates unchanged.
        """
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            fallback = self._fallbacks.get(service_name)
            if fallback is not None:
                logger.warning(
                    "Service %s degraded (%s), using fallback",
                    service_name,
                    type(exc).__name__,
                )
                return fallback(exc)
            raise

    def has_fallback(self, service_name: str) -> bool:
        """Check if a fallback is registered for a service."""
        return service_name in self._fallbacks


# Shared degradation instance with pre-registered fallbacks
graceful_degradation = GracefulDegradation()


@graceful_degradation.register("exa")
def _exa_fallback(error: Exception) -> dict[str, Any]:
    """When Exa is down, return empty results so briefings still generate."""
    return {"results": [], "degraded": True, "reason": str(error)}


@graceful_degradation.register("tavus")
def _tavus_fallback(error: Exception) -> dict[str, Any]:
    """When Tavus is down, signal text-only mode."""
    return {
        "available": False,
        "degraded": True,
        "modality": "text_only",
        "reason": str(error),
    }


@graceful_degradation.register("composio")
def _composio_fallback(error: Exception) -> dict[str, Any]:
    """When Composio is down, disable integrations gracefully."""
    return {
        "available": False,
        "degraded": True,
        "reason": str(error),
    }


# ---------------------------------------------------------------------------
# Convenience: resilient_call — combines circuit breaker + retry + fallback
# ---------------------------------------------------------------------------


async def resilient_call(
    service_name: str,
    func: Callable[..., Awaitable[T]],
    *args: Any,
    circuit_breaker: CircuitBreaker | None = None,
    max_retries: int = 2,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[BaseException], ...] = RETRYABLE_EXCEPTIONS,
    fallback: Callable[[Exception], Any] | None = None,
    **kwargs: Any,
) -> T | Any:
    """All-in-one resilient call: circuit breaker + retry + fallback.

    1. Check circuit breaker (skip call if open).
    2. Retry transient errors with exponential backoff + jitter.
    3. On persistent failure, try the graceful degradation fallback.

    Args:
        service_name: Service identifier (for logging/fallback lookup).
        func: Async callable to execute.
        circuit_breaker: CircuitBreaker to gate the call. If None, no CB gating.
        max_retries: Retry count for transient errors.
        backoff_factor: Backoff multiplier.
        retry_on: Exception types that trigger a retry.
        fallback: Explicit fallback; if None, checks GracefulDegradation registry.
        *args, **kwargs: Forwarded to *func*.
    """
    # 1. Circuit breaker gate
    if circuit_breaker is not None:
        try:
            circuit_breaker.check()
        except CircuitBreakerOpen as exc:
            logger.warning("Circuit open for %s — using fallback", service_name)
            fb = fallback or graceful_degradation._fallbacks.get(service_name)
            if fb is not None:
                return fb(exc)
            raise

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            result = await func(*args, **kwargs)
            if circuit_breaker is not None:
                circuit_breaker.record_success()
            return result
        except retry_on as exc:
            last_exc = exc  # type: ignore[assignment]
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
            if attempt < max_retries:
                delay = min(backoff_factor ** attempt, 30.0)
                jitter = random.uniform(0, delay)  # noqa: S311
                logger.warning(
                    "resilient_call retry %d/%d for %s.%s: %s (%.2fs)",
                    attempt + 1,
                    max_retries,
                    service_name,
                    func.__qualname__,
                    exc,
                    jitter,
                )
                await asyncio.sleep(jitter)
        except Exception as exc:
            # Non-retryable error
            last_exc = exc
            if circuit_breaker is not None:
                circuit_breaker.record_failure()
            break

    # All retries exhausted or non-retryable failure
    assert last_exc is not None
    fb = fallback or graceful_degradation._fallbacks.get(service_name)
    if fb is not None:
        logger.warning(
            "All retries exhausted for %s — using fallback",
            service_name,
        )
        return fb(last_exc)
    raise last_exc
