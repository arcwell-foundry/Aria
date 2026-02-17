"""Tests for the resilience module (circuit breaker, retry, graceful degradation)."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    CircuitState,
    GracefulDegradation,
    get_all_circuit_breakers,
    graceful_degradation,
    resilient_call,
    retry,
)


# ---------------------------------------------------------------------------
# CircuitBreaker: basic state transitions
# ---------------------------------------------------------------------------


class TestCircuitBreakerStates:
    """Circuit breaker state machine transitions."""

    def test_starts_closed(self) -> None:
        cb = CircuitBreaker("test_starts_closed", failure_threshold=5)
        assert cb.state == CircuitState.CLOSED

    def test_stays_closed_under_threshold(self) -> None:
        cb = CircuitBreaker("test_under_threshold", failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_opens_at_failure_threshold(self) -> None:
        cb = CircuitBreaker("test_opens", failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_open_circuit_raises(self) -> None:
        cb = CircuitBreaker("test_raises", failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpen, match="test_raises"):
            cb.check()

    def test_open_circuit_includes_retry_after(self) -> None:
        cb = CircuitBreaker("test_retry_after", failure_threshold=1, recovery_timeout=60.0)
        cb.record_failure()
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            cb.check()
        assert exc_info.value.retry_after > 0
        assert exc_info.value.retry_after <= 60.0

    def test_transitions_to_half_open_after_timeout(self) -> None:
        cb = CircuitBreaker("test_half_open", failure_threshold=2, recovery_timeout=10.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate time passing beyond recovery timeout
        with patch("src.core.resilience.time.monotonic", return_value=time.monotonic() + 11):
            assert cb.state == CircuitState.HALF_OPEN

    def test_success_resets_failure_count(self) -> None:
        cb = CircuitBreaker("test_reset", failure_threshold=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state == CircuitState.CLOSED


class TestCircuitBreakerHalfOpen:
    """HALF_OPEN → CLOSED requires success_threshold consecutive successes."""

    def test_single_success_not_enough(self) -> None:
        cb = CircuitBreaker(
            "test_half_single", failure_threshold=2, recovery_timeout=0, success_threshold=3,
        )
        cb.record_failure()
        cb.record_failure()
        # recovery_timeout=0 → immediately HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        # Still HALF_OPEN — need 3 successes
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_after_success_threshold(self) -> None:
        cb = CircuitBreaker(
            "test_half_close", failure_threshold=2, recovery_timeout=0, success_threshold=3,
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self) -> None:
        cb = CircuitBreaker(
            "test_half_reopen", failure_threshold=2, recovery_timeout=60, success_threshold=3,
        )
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        # Simulate timeout to get to HALF_OPEN
        with patch("src.core.resilience.time.monotonic", return_value=time.monotonic() + 61):
            assert cb.state == CircuitState.HALF_OPEN

        # One success, then a failure → re-opens
        cb.record_success()
        cb.record_failure()
        # Internal state is OPEN (record_failure sets it)
        assert cb._state == CircuitState.OPEN

    def test_resets_success_count_on_reopen(self) -> None:
        cb = CircuitBreaker(
            "test_half_reset", failure_threshold=2, recovery_timeout=60, success_threshold=3,
        )
        cb.record_failure()
        cb.record_failure()

        # Simulate timeout to get to HALF_OPEN
        with patch("src.core.resilience.time.monotonic", return_value=time.monotonic() + 61):
            assert cb.state == CircuitState.HALF_OPEN

        # Two successes, then fail → should reset to 0 successes
        cb.record_success()
        cb.record_success()
        cb.record_failure()
        assert cb._success_count == 0
        assert cb._state == CircuitState.OPEN


class TestCircuitBreakerCall:
    """The async call() wrapper."""

    @pytest.mark.asyncio
    async def test_call_success(self) -> None:
        cb = CircuitBreaker("test_call_ok")

        async def ok() -> str:
            return "ok"

        result = await cb.call(ok)
        assert result == "ok"
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_call_failure_records(self) -> None:
        cb = CircuitBreaker("test_call_fail")

        async def fail() -> str:
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await cb.call(fail)
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_call_open_rejects(self) -> None:
        cb = CircuitBreaker("test_call_open", failure_threshold=1)
        cb.record_failure()

        async def should_not_run() -> str:
            raise AssertionError("Should not be called")

        with pytest.raises(CircuitBreakerOpen):
            await cb.call(should_not_run)


class TestCircuitBreakerRegistry:
    """Global registry and health-check helpers."""

    def test_registered_on_creation(self) -> None:
        name = "test_registry_entry"
        cb = CircuitBreaker(name)
        registry = get_all_circuit_breakers()
        assert name in registry
        assert registry[name] is cb

    def test_to_dict(self) -> None:
        cb = CircuitBreaker("test_to_dict", failure_threshold=3, recovery_timeout=45.0)
        d = cb.to_dict()
        assert d["service"] == "test_to_dict"
        assert d["state"] == "closed"
        assert d["failure_threshold"] == 3
        assert d["recovery_timeout"] == 45.0

    def test_reset(self) -> None:
        cb = CircuitBreaker("test_manual_reset", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb._failure_count == 0


# ---------------------------------------------------------------------------
# Retry decorator
# ---------------------------------------------------------------------------


class TestRetryDecorator:
    """Retry with exponential backoff + jitter."""

    @pytest.mark.asyncio
    async def test_succeeds_immediately(self) -> None:
        call_count = 0

        @retry(max_retries=3, retry_on=(ConnectionError,))
        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await fn()
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_matching_exception(self) -> None:
        call_count = 0

        @retry(max_retries=2, backoff_factor=0.01, retry_on=(ConnectionError,))
        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await fn()
        assert result == "recovered"
        assert call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self) -> None:
        call_count = 0

        @retry(max_retries=2, backoff_factor=0.01, retry_on=(ConnectionError,))
        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise ConnectionError("persistent")

        with pytest.raises(ConnectionError, match="persistent"):
            await fn()
        assert call_count == 3  # initial + 2 retries

    @pytest.mark.asyncio
    async def test_does_not_retry_non_matching_exceptions(self) -> None:
        call_count = 0

        @retry(max_retries=3, backoff_factor=0.01, retry_on=(ConnectionError,))
        async def fn() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            await fn()
        assert call_count == 1  # No retries

    @pytest.mark.asyncio
    async def test_backoff_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        @retry(max_retries=1, backoff_factor=0.01, retry_on=(ConnectionError,))
        async def fn() -> str:
            raise ConnectionError("fail")

        with caplog.at_level(logging.WARNING, logger="src.core.resilience"):
            with pytest.raises(ConnectionError):
                await fn()

        assert any("Retry 1/1" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Graceful Degradation
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Fallback responses when services are unavailable."""

    @pytest.mark.asyncio
    async def test_returns_normal_result_on_success(self) -> None:
        gd = GracefulDegradation()
        gd.set_fallback("test", lambda e: "fallback")

        async def ok() -> str:
            return "normal"

        result = await gd.call_with_fallback("test", ok)
        assert result == "normal"

    @pytest.mark.asyncio
    async def test_returns_fallback_on_failure(self) -> None:
        gd = GracefulDegradation()
        gd.set_fallback("test", lambda e: {"degraded": True})

        async def fail() -> str:
            raise ConnectionError("down")

        result = await gd.call_with_fallback("test", fail)
        assert result == {"degraded": True}

    @pytest.mark.asyncio
    async def test_raises_if_no_fallback_registered(self) -> None:
        gd = GracefulDegradation()

        async def fail() -> str:
            raise ConnectionError("down")

        with pytest.raises(ConnectionError):
            await gd.call_with_fallback("unregistered", fail)

    def test_decorator_registration(self) -> None:
        gd = GracefulDegradation()

        @gd.register("svc")
        def fb(e: Exception) -> str:
            return "degraded"

        assert gd.has_fallback("svc")
        assert not gd.has_fallback("other")

    def test_shared_instance_has_defaults(self) -> None:
        assert graceful_degradation.has_fallback("exa")
        assert graceful_degradation.has_fallback("tavus")
        assert graceful_degradation.has_fallback("composio")

    def test_exa_fallback_returns_empty_results(self) -> None:
        fb = graceful_degradation._fallbacks["exa"]
        result = fb(ConnectionError("down"))
        assert result["results"] == []
        assert result["degraded"] is True

    def test_tavus_fallback_signals_text_only(self) -> None:
        fb = graceful_degradation._fallbacks["tavus"]
        result = fb(ConnectionError("down"))
        assert result["modality"] == "text_only"
        assert result["degraded"] is True


# ---------------------------------------------------------------------------
# resilient_call (circuit breaker + retry + fallback combined)
# ---------------------------------------------------------------------------


class TestResilientCall:
    """End-to-end resilient_call combining all patterns."""

    @pytest.mark.asyncio
    async def test_success_path(self) -> None:
        cb = CircuitBreaker("resilient_ok", failure_threshold=5)

        async def ok() -> str:
            return "data"

        result = await resilient_call("resilient_ok", ok, circuit_breaker=cb)
        assert result == "data"
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_retries_transient_failure(self) -> None:
        cb = CircuitBreaker("resilient_retry", failure_threshold=10)
        call_count = 0

        async def flaky() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient")
            return "recovered"

        result = await resilient_call(
            "resilient_retry", flaky,
            circuit_breaker=cb, max_retries=3, backoff_factor=0.01,
        )
        assert result == "recovered"

    @pytest.mark.asyncio
    async def test_falls_back_when_retries_exhausted(self) -> None:
        cb = CircuitBreaker("resilient_fallback", failure_threshold=20)

        async def always_fail() -> str:
            raise ConnectionError("permanent")

        result = await resilient_call(
            "resilient_fallback", always_fail,
            circuit_breaker=cb, max_retries=1, backoff_factor=0.01,
            fallback=lambda e: {"degraded": True},
        )
        assert result == {"degraded": True}

    @pytest.mark.asyncio
    async def test_uses_registered_fallback_when_circuit_open(self) -> None:
        cb = CircuitBreaker("exa", failure_threshold=1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

        async def should_not_run() -> str:
            raise AssertionError("Should not be called")

        # "exa" has a registered fallback in graceful_degradation
        result = await resilient_call("exa", should_not_run, circuit_breaker=cb)
        assert result["degraded"] is True
        assert result["results"] == []

        # Reset for other tests
        cb.reset()

    @pytest.mark.asyncio
    async def test_raises_when_circuit_open_and_no_fallback(self) -> None:
        cb = CircuitBreaker("no_fb_svc", failure_threshold=1)
        cb.record_failure()

        async def should_not_run() -> str:
            raise AssertionError("Should not be called")

        with pytest.raises(CircuitBreakerOpen):
            await resilient_call("no_fb_svc", should_not_run, circuit_breaker=cb)

        cb.reset()


# ---------------------------------------------------------------------------
# Full lifecycle scenario
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    """Simulate a realistic service degradation and recovery scenario."""

    @pytest.mark.asyncio
    async def test_service_degrades_and_recovers(self) -> None:
        """Simulate: healthy → failures → open → timeout → half-open → recover."""
        cb = CircuitBreaker(
            "lifecycle_test",
            failure_threshold=3,
            recovery_timeout=30.0,
            success_threshold=2,
        )

        # Phase 1: Service is healthy
        async def healthy() -> str:
            return "ok"

        for _ in range(5):
            result = await cb.call(healthy)
            assert result == "ok"
        assert cb.state == CircuitState.CLOSED

        # Phase 2: Service starts failing
        async def failing() -> str:
            raise ConnectionError("service down")

        for _ in range(3):
            with pytest.raises(ConnectionError):
                await cb.call(failing)
        assert cb.state == CircuitState.OPEN

        # Phase 3: Circuit is open, calls are rejected
        with pytest.raises(CircuitBreakerOpen):
            await cb.call(healthy)

        # Phase 4: Simulate recovery timeout passing → HALF_OPEN
        with patch("src.core.resilience.time.monotonic", return_value=time.monotonic() + 31):
            assert cb.state == CircuitState.HALF_OPEN

        # Phase 5: First success in HALF_OPEN
        await cb.call(healthy)
        assert cb.state == CircuitState.HALF_OPEN  # Need 2 successes

        # Phase 6: Second success → CLOSED
        await cb.call(healthy)
        assert cb.state == CircuitState.CLOSED

        cb.reset()
