"""Tests for circuit breaker module."""

import asyncio
import time
from unittest.mock import patch

import pytest

from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen, CircuitState


def test_circuit_starts_closed() -> None:
    cb = CircuitBreaker("test_service")
    assert cb.state == CircuitState.CLOSED


def test_circuit_stays_closed_under_threshold() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5)
    for _ in range(4):
        cb.record_failure()
    assert cb.state == CircuitState.CLOSED


def test_circuit_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5)
    for _ in range(5):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_open_circuit_raises_circuit_breaker_open() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5)
    for _ in range(5):
        cb.record_failure()
    with pytest.raises(CircuitBreakerOpen, match="test_service"):
        cb.check()


def test_circuit_half_opens_after_recovery_timeout() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5, recovery_timeout=30)
    for _ in range(5):
        cb.record_failure()
    assert cb.state == CircuitState.OPEN

    with patch("src.core.circuit_breaker.time.monotonic", return_value=time.monotonic() + 31):
        assert cb.state == CircuitState.HALF_OPEN


def test_half_open_circuit_closes_on_success() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5, recovery_timeout=0)
    for _ in range(5):
        cb.record_failure()
    # recovery_timeout=0 means it immediately goes half-open
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_half_open_circuit_reopens_on_failure() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5, recovery_timeout=0)
    for _ in range(5):
        cb.record_failure()
    # Now half-open (recovery_timeout=0), another failure should re-open
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_success_resets_failure_count() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=5)
    for _ in range(3):
        cb.record_failure()
    cb.record_success()
    assert cb._failure_count == 0


@pytest.mark.asyncio
async def test_call_async_success() -> None:
    cb = CircuitBreaker("test_service")

    async def ok() -> str:
        return "ok"

    result = await cb.call_async(ok)
    assert result == "ok"
    assert cb._failure_count == 0


@pytest.mark.asyncio
async def test_call_async_failure_increments_count() -> None:
    cb = CircuitBreaker("test_service")

    async def fail() -> str:
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await cb.call_async(fail)
    assert cb._failure_count == 1


@pytest.mark.asyncio
async def test_call_async_open_circuit_raises_immediately() -> None:
    cb = CircuitBreaker("test_service", failure_threshold=2)

    async def fail() -> str:
        raise ConnectionError("down")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            await cb.call_async(fail)

    with pytest.raises(CircuitBreakerOpen):
        await cb.call_async(fail)


def test_state_change_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    cb = CircuitBreaker("test_service", failure_threshold=2)
    with caplog.at_level(logging.WARNING, logger="src.core.circuit_breaker"):
        cb.record_failure()
        cb.record_failure()
    assert any("OPEN" in record.message and "test_service" in record.message for record in caplog.records)
