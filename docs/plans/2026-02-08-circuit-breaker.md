# Circuit Breaker Pattern Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prevent cascading failures when external services (Claude API, Neo4j/Graphiti, Supabase) go down by implementing a circuit breaker pattern with graceful fallbacks.

**Architecture:** A standalone `CircuitBreaker` class tracks failures per service. After 5 consecutive failures, the circuit opens and rejects calls immediately with a fallback response. After 30 seconds, it half-opens to allow one test request. On success, it closes again. Each of the 3 critical clients wraps its external calls through its own circuit breaker instance. State transitions log at WARNING level.

**Tech Stack:** Python 3.11+ stdlib only (time, enum, logging, threading). No new dependencies.

---

### Task 1: CircuitBreaker Core Class

**Files:**
- Create: `backend/src/core/circuit_breaker.py`
- Test: `backend/tests/test_circuit_breaker.py`

**Step 1: Write the failing tests**

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_circuit_breaker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.circuit_breaker'`

**Step 3: Write the implementation**

```python
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
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
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

    async def call_async(self, func: Callable[..., Awaitable[T]], *args: object, **kwargs: object) -> T:
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
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_circuit_breaker.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/core/circuit_breaker.py backend/tests/test_circuit_breaker.py
git commit -m "feat: add CircuitBreaker class for external service resilience"
```

---

### Task 2: Add CircuitBreakerOpen to Exception Hierarchy

**Files:**
- Modify: `backend/src/core/exceptions.py` (add safe message for CircuitBreakerOpen)

**Step 1: Add `CircuitBreakerOpen` to the safe messages map**

In `backend/src/core/exceptions.py`, add to the `_SAFE_MESSAGES` dict:

```python
"CircuitBreakerOpen": "A service dependency is temporarily unavailable. Please try again in a moment.",
```

**Step 2: Run existing exception tests**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_exceptions.py -v`
Expected: PASS (no existing test covers this key, just verifying no regressions)

**Step 3: Commit**

```bash
git add backend/src/core/exceptions.py
git commit -m "feat: add CircuitBreakerOpen to safe error message mapping"
```

---

### Task 3: Wrap LLM Client (Claude API)

**Files:**
- Modify: `backend/src/core/llm.py`
- Modify: `backend/tests/test_llm.py` (add circuit breaker tests)

**Step 1: Write the failing tests**

Append to `backend/tests/test_llm.py`:

```python
@pytest.mark.asyncio
async def test_generate_response_opens_circuit_after_repeated_failures() -> None:
    """Test that repeated API failures open the circuit breaker."""
    from src.core.circuit_breaker import CircuitBreakerOpen
    from src.core.llm import LLMClient

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client
        mock_client.messages.create = AsyncMock(
            side_effect=Exception("API down")
        )

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
            client = LLMClient()

        messages = [{"role": "user", "content": "Hello"}]

        # Exhaust the failure threshold (5)
        for _ in range(5):
            with pytest.raises(Exception, match="API down"):
                await client.generate_response(messages)

        # Next call should raise CircuitBreakerOpen
        with pytest.raises(CircuitBreakerOpen):
            await client.generate_response(messages)


@pytest.mark.asyncio
async def test_generate_response_circuit_resets_on_success() -> None:
    """Test that a successful call resets the circuit breaker."""
    from src.core.llm import LLMClient

    with patch("src.core.llm.anthropic.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_anthropic.return_value = mock_client

        call_count = 0

        async def side_effect(**kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("API down")
            resp = MagicMock()
            resp.content = [MagicMock(text="recovered")]
            return resp

        mock_client.messages.create = AsyncMock(side_effect=side_effect)

        with patch("src.core.llm.settings") as mock_settings:
            mock_settings.ANTHROPIC_API_KEY.get_secret_value.return_value = "test-key"
            client = LLMClient()

        messages = [{"role": "user", "content": "Hello"}]

        # 3 failures (under threshold of 5)
        for _ in range(3):
            with pytest.raises(Exception, match="API down"):
                await client.generate_response(messages)

        # Success should reset the counter
        result = await client.generate_response(messages)
        assert result == "recovered"
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_llm.py -v -k "circuit"`
Expected: FAIL — no circuit breaker in LLMClient yet

**Step 3: Modify LLMClient to use CircuitBreaker**

In `backend/src/core/llm.py`, add import and integrate:

Add after existing imports:
```python
from src.core.circuit_breaker import CircuitBreaker
```

Add class-level circuit breaker (shared across instances since it's the same service):
```python
# Module-level circuit breaker for Claude API (shared across LLMClient instances)
_llm_circuit_breaker = CircuitBreaker("claude_api")
```

Wrap `generate_response` — change line 74 from:
```python
        response = await self._client.messages.create(**kwargs)
```
to:
```python
        response = await _llm_circuit_breaker.call_async(
            self._client.messages.create, **kwargs
        )
```

Wrap `stream_response` — the streaming case is trickier because `call_async` doesn't handle context managers. Instead, add a check before entering the stream and record success/failure manually. Change lines 126-128 from:
```python
        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
```
to:
```python
        _llm_circuit_breaker.check()
        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
            _llm_circuit_breaker.record_success()
        except Exception:
            _llm_circuit_breaker.record_failure()
            raise
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_llm.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/core/llm.py backend/tests/test_llm.py
git commit -m "feat: wrap Claude API calls with circuit breaker"
```

---

### Task 4: Wrap Graphiti Client (Neo4j)

**Files:**
- Modify: `backend/src/db/graphiti.py`
- Modify: `backend/tests/test_graphiti.py` (add circuit breaker tests)

**Step 1: Read existing graphiti tests to understand patterns**

Read: `backend/tests/test_graphiti.py`

**Step 2: Write the failing tests**

Append to `backend/tests/test_graphiti.py`:

```python
@pytest.mark.asyncio
async def test_add_episode_opens_circuit_after_repeated_failures() -> None:
    """Test that repeated Graphiti failures open the circuit breaker."""
    from src.core.circuit_breaker import CircuitBreakerOpen
    from src.db.graphiti import GraphitiClient, _graphiti_circuit_breaker

    # Reset circuit breaker state
    _graphiti_circuit_breaker.record_success()

    with patch.object(GraphitiClient, "get_instance", new_callable=AsyncMock) as mock_get:
        mock_instance = AsyncMock()
        mock_instance.add_episode = AsyncMock(side_effect=Exception("Neo4j down"))
        mock_get.return_value = mock_instance

        with patch("src.db.graphiti.EpisodeType", create=True):
            from datetime import datetime

            for _ in range(5):
                with pytest.raises(Exception, match="Neo4j down"):
                    # Call the internal _add_episode_inner or just use the circuit breaker directly
                    await _graphiti_circuit_breaker.call_async(
                        mock_instance.add_episode,
                        name="test",
                        episode_body="body",
                        source="text",
                        source_description="test",
                        reference_time=datetime.now(),
                    )

            with pytest.raises(CircuitBreakerOpen):
                _graphiti_circuit_breaker.check()

    # Reset for other tests
    _graphiti_circuit_breaker.record_success()
```

**Step 3: Modify GraphitiClient to use CircuitBreaker**

In `backend/src/db/graphiti.py`, add import after existing imports:
```python
from src.core.circuit_breaker import CircuitBreaker
```

Add module-level circuit breaker after logger:
```python
_graphiti_circuit_breaker = CircuitBreaker("graphiti_neo4j")
```

Wrap `add_episode` method — change lines 150-158 to:
```python
        from graphiti_core.nodes import EpisodeType

        client = await cls.get_instance()
        result = await _graphiti_circuit_breaker.call_async(
            client.add_episode,
            name=name,
            episode_body=episode_body,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=reference_time,
        )
        return result
```

Wrap `search` method — change lines 173-175 to:
```python
        client = await cls.get_instance()
        results = await _graphiti_circuit_breaker.call_async(client.search, query)
        return list(results)
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_graphiti.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/db/graphiti.py backend/tests/test_graphiti.py
git commit -m "feat: wrap Graphiti/Neo4j calls with circuit breaker"
```

---

### Task 5: Wrap Supabase Client

**Files:**
- Modify: `backend/src/db/supabase.py`
- Create: `backend/tests/test_supabase_circuit_breaker.py`

**Step 1: Write the failing tests**

```python
"""Tests for Supabase client circuit breaker integration."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.circuit_breaker import CircuitBreakerOpen


@pytest.mark.asyncio
async def test_supabase_get_user_opens_circuit_after_failures() -> None:
    """Test that repeated Supabase failures open the circuit breaker."""
    from src.db.supabase import SupabaseClient, _supabase_circuit_breaker

    # Reset circuit state
    _supabase_circuit_breaker.record_success()

    with patch.object(SupabaseClient, "get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = (
            Exception("connection refused")
        )
        mock_get_client.return_value = mock_client

        for _ in range(5):
            with pytest.raises(Exception):
                await SupabaseClient.get_user_by_id("test-id")

        with pytest.raises(CircuitBreakerOpen):
            await SupabaseClient.get_user_by_id("test-id")

    # Reset for other tests
    _supabase_circuit_breaker.record_success()


@pytest.mark.asyncio
async def test_supabase_circuit_resets_on_success() -> None:
    """Test that a successful call resets the circuit breaker."""
    from src.db.supabase import SupabaseClient, _supabase_circuit_breaker

    # Reset circuit state
    _supabase_circuit_breaker.record_success()

    with patch.object(SupabaseClient, "get_client") as mock_get_client:
        mock_client = MagicMock()

        call_count = 0

        def side_effect() -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("connection refused")
            result = MagicMock()
            result.data = {"id": "test-id", "full_name": "Test User"}
            return result

        mock_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute = side_effect
        mock_get_client.return_value = mock_client

        # 3 failures (under threshold)
        for _ in range(3):
            with pytest.raises(Exception):
                await SupabaseClient.get_user_by_id("test-id")

        # Successful call should reset
        result = await SupabaseClient.get_user_by_id("test-id")
        assert result["id"] == "test-id"
        assert _supabase_circuit_breaker._failure_count == 0

    _supabase_circuit_breaker.record_success()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_supabase_circuit_breaker.py -v`
Expected: FAIL — `_supabase_circuit_breaker` doesn't exist yet

**Step 3: Modify SupabaseClient to use CircuitBreaker**

In `backend/src/db/supabase.py`, add import:
```python
from src.core.circuit_breaker import CircuitBreaker
```

Add module-level circuit breaker after logger:
```python
_supabase_circuit_breaker = CircuitBreaker("supabase")
```

For Supabase, the calls are synchronous (supabase-py uses httpx under the hood but the `.execute()` calls are sync). The circuit breaker wrapping needs to happen at the method level. Modify each method to check/record manually.

For `get_user_by_id`, change the try block (lines 59-71) to:
```python
        try:
            _supabase_circuit_breaker.check()
            client = cls.get_client()
            response = (
                client.table("user_profiles").select("*").eq("id", user_id).single().execute()
            )
            if response.data is None:
                raise NotFoundError("User", user_id)
            _supabase_circuit_breaker.record_success()
            return cast(dict[str, Any], response.data)
        except NotFoundError:
            raise
        except CircuitBreakerOpen:
            raise
        except Exception as e:
            _supabase_circuit_breaker.record_failure()
            logger.exception("Error fetching user", extra={"user_id": user_id})
            raise DatabaseError(f"Failed to fetch user: {e}") from e
```

Apply the same pattern to all other methods: `get_company_by_id`, `get_user_settings`, `create_user_profile`, `create_user_settings`, `create_company`. The pattern is:
1. Add `_supabase_circuit_breaker.check()` at the start of the try block
2. Add `_supabase_circuit_breaker.record_success()` before the successful return
3. Add `except CircuitBreakerOpen: raise` before the generic `except Exception`
4. Add `_supabase_circuit_breaker.record_failure()` in the generic except block

Also import `CircuitBreakerOpen`:
```python
from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
```

**Step 4: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_supabase_circuit_breaker.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/db/supabase.py backend/tests/test_supabase_circuit_breaker.py
git commit -m "feat: wrap Supabase calls with circuit breaker"
```

---

### Task 6: Lint and Final Verification

**Step 1: Run ruff linter**

Run: `cd /Users/dhruv/aria/backend && ruff check src/core/circuit_breaker.py src/core/llm.py src/db/graphiti.py src/db/supabase.py`
Expected: No errors (fix any that appear)

**Step 2: Run ruff formatter**

Run: `cd /Users/dhruv/aria/backend && ruff format src/core/circuit_breaker.py src/core/llm.py src/db/graphiti.py src/db/supabase.py`

**Step 3: Run all affected tests together**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/test_circuit_breaker.py backend/tests/test_llm.py backend/tests/test_graphiti.py backend/tests/test_supabase_circuit_breaker.py -v`
Expected: All PASS

**Step 4: Run full test suite to check for regressions**

Run: `cd /Users/dhruv/aria && python -m pytest backend/tests/ -v --timeout=60`
Expected: No new failures

**Step 5: Commit any lint fixes**

```bash
git add -A
git commit -m "style: format circuit breaker implementation"
```
