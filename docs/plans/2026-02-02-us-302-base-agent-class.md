# US-302: Base Agent Class Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the abstract BaseAgent class that provides common behavior for all ARIA specialized agents.

**Architecture:** The BaseAgent class is an abstract base providing tool registration, execution lifecycle management (status tracking), input validation, error handling with retries, execution logging, and token usage tracking. All six core agents (Hunter, Analyst, Strategist, Scribe, Operator, Scout) will extend this class, implementing their domain-specific tools and execute logic.

**Tech Stack:** Python 3.11+, ABC (abstract base classes), dataclasses, async/await patterns, logging module

---

## Acceptance Criteria Checklist

- [ ] `src/agents/base.py` defines abstract Agent class
- [ ] Common methods: execute, validate_input, format_output
- [ ] Tool registration system
- [ ] Error handling and retry logic
- [ ] Execution logging
- [ ] Token usage tracking
- [ ] Status reporting (idle, running, complete, failed)
- [ ] Unit tests for base functionality

---

### Task 1: Create AgentStatus Enum and AgentResult Dataclass

**Files:**
- Create: `backend/src/agents/base.py`
- Test: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for AgentStatus and AgentResult**

Create `backend/tests/test_base_agent.py`:

```python
"""Tests for base agent module."""

from typing import Any


def test_agent_status_enum_has_four_states() -> None:
    """Test AgentStatus enum has idle, running, complete, failed."""
    from src.agents.base import AgentStatus

    assert AgentStatus.IDLE.value == "idle"
    assert AgentStatus.RUNNING.value == "running"
    assert AgentStatus.COMPLETE.value == "complete"
    assert AgentStatus.FAILED.value == "failed"
    assert len(AgentStatus) == 4


def test_agent_result_initializes_with_required_fields() -> None:
    """Test AgentResult initializes with success and data."""
    from src.agents.base import AgentResult

    result = AgentResult(success=True, data={"key": "value"})

    assert result.success is True
    assert result.data == {"key": "value"}
    assert result.error is None
    assert result.tokens_used == 0
    assert result.execution_time_ms == 0


def test_agent_result_initializes_with_all_fields() -> None:
    """Test AgentResult initializes with all optional fields."""
    from src.agents.base import AgentResult

    result = AgentResult(
        success=False,
        data=None,
        error="Something went wrong",
        tokens_used=150,
        execution_time_ms=1200,
    )

    assert result.success is False
    assert result.data is None
    assert result.error == "Something went wrong"
    assert result.tokens_used == 150
    assert result.execution_time_ms == 1200


def test_agent_result_to_dict_serializes_correctly() -> None:
    """Test AgentResult.to_dict produces valid dictionary."""
    from src.agents.base import AgentResult

    result = AgentResult(
        success=True,
        data={"results": ["item1", "item2"]},
        tokens_used=100,
        execution_time_ms=500,
    )

    serialized = result.to_dict()

    assert serialized["success"] is True
    assert serialized["data"] == {"results": ["item1", "item2"]}
    assert serialized["error"] is None
    assert serialized["tokens_used"] == 100
    assert serialized["execution_time_ms"] == 500
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

Create `backend/src/agents/base.py`:

```python
"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AgentStatus(Enum):
    """Current execution status of an agent."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class AgentResult:
    """Result of an agent execution.

    Captures success/failure status, output data, error information,
    and execution metrics.
    """

    success: bool
    data: Any
    error: str | None = None
    tokens_used: int = 0
    execution_time_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dictionary.

        Returns:
            Dictionary representation suitable for JSON.
        """
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "tokens_used": self.tokens_used,
            "execution_time_ms": self.execution_time_ms,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add AgentStatus enum and AgentResult dataclass"
```

---

### Task 2: Create BaseAgent Abstract Class with Tool Registration

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for BaseAgent and tool registration**

Add to `backend/tests/test_base_agent.py`:

```python
from abc import ABC
from unittest.mock import MagicMock

import pytest


def test_base_agent_is_abstract() -> None:
    """Test BaseAgent cannot be instantiated directly."""
    from src.agents.base import BaseAgent

    assert issubclass(BaseAgent, ABC)

    # Should fail to instantiate
    with pytest.raises(TypeError):
        BaseAgent(llm_client=MagicMock(), user_id="user-123")  # type: ignore[abstract]


def test_base_agent_requires_name_and_description() -> None:
    """Test BaseAgent subclass requires name and description class attributes."""
    from src.agents.base import AgentResult, BaseAgent

    # Create a minimal concrete subclass
    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.name == "Test Agent"
    assert agent.description == "A test agent"


def test_base_agent_initializes_with_idle_status() -> None:
    """Test BaseAgent initializes with IDLE status."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.status == AgentStatus.IDLE
    assert agent.user_id == "user-123"


def test_base_agent_registers_tools_on_init() -> None:
    """Test BaseAgent calls _register_tools on initialization."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {
                "tool_one": self._tool_one,
                "tool_two": self._tool_two,
            }

        async def _tool_one(self) -> str:
            return "result_one"

        async def _tool_two(self) -> str:
            return "result_two"

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert "tool_one" in agent.tools
    assert "tool_two" in agent.tools
    assert len(agent.tools) == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_is_abstract tests/test_base_agent.py::test_base_agent_requires_name_and_description tests/test_base_agent.py::test_base_agent_initializes_with_idle_status tests/test_base_agent.py::test_base_agent_registers_tools_on_init -v`

Expected: FAIL with "cannot import name 'BaseAgent'"

**Step 3: Write minimal implementation**

Update `backend/src/agents/base.py`, add after AgentResult:

```python
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Abstract base class for all ARIA agents.

    Provides common functionality including tool registration,
    status tracking, and execution lifecycle management.
    """

    name: str
    description: str

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.status = AgentStatus.IDLE
        self.tools: dict[str, Callable[..., Any]] = self._register_tools()

    @abstractmethod
    def _register_tools(self) -> dict[str, Callable[..., Any]]:
        """Register agent-specific tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        pass

    @abstractmethod
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        pass
```

Also update the imports at the top of the file:

```python
"""Base agent module for ARIA.

Provides the abstract base class and common types for all specialized agents.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add BaseAgent abstract class with tool registration"
```

---

### Task 3: Add validate_input Method

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for validate_input**

Add to `backend/tests/test_base_agent.py`:

```python
def test_base_agent_validate_input_returns_true_by_default() -> None:
    """Test validate_input returns True for any input by default."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    # Default implementation should accept anything
    assert agent.validate_input({}) is True
    assert agent.validate_input({"any": "value"}) is True


def test_base_agent_validate_input_can_be_overridden() -> None:
    """Test subclass can override validate_input with custom logic."""
    from src.agents.base import AgentResult, BaseAgent

    class StrictAgent(BaseAgent):
        name = "Strict Agent"
        description = "Agent with strict validation"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        def validate_input(self, task: dict[str, Any]) -> bool:
            # Require 'query' field
            return "query" in task

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = StrictAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.validate_input({"query": "search term"}) is True
    assert agent.validate_input({"other": "field"}) is False
    assert agent.validate_input({}) is False
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_validate_input_returns_true_by_default tests/test_base_agent.py::test_base_agent_validate_input_can_be_overridden -v`

Expected: FAIL with "has no attribute 'validate_input'"

**Step 3: Write minimal implementation**

Add to `BaseAgent` class in `backend/src/agents/base.py`:

```python
    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate task input before execution.

        Subclasses can override to add custom validation logic.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        return True
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (10 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add validate_input method to BaseAgent"
```

---

### Task 4: Add format_output Method

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for format_output**

Add to `backend/tests/test_base_agent.py`:

```python
def test_base_agent_format_output_returns_data_unchanged_by_default() -> None:
    """Test format_output returns data as-is by default."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    data = {"results": [1, 2, 3], "count": 3}
    formatted = agent.format_output(data)

    assert formatted == data


def test_base_agent_format_output_can_be_overridden() -> None:
    """Test subclass can override format_output with custom logic."""
    from src.agents.base import AgentResult, BaseAgent

    class FormattingAgent(BaseAgent):
        name = "Formatting Agent"
        description = "Agent with custom formatting"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        def format_output(self, data: Any) -> Any:
            # Add metadata wrapper
            return {"formatted": True, "data": data}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = FormattingAgent(llm_client=mock_llm, user_id="user-123")

    result = agent.format_output({"raw": "data"})

    assert result["formatted"] is True
    assert result["data"] == {"raw": "data"}
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_format_output_returns_data_unchanged_by_default tests/test_base_agent.py::test_base_agent_format_output_can_be_overridden -v`

Expected: FAIL with "has no attribute 'format_output'"

**Step 3: Write minimal implementation**

Add to `BaseAgent` class in `backend/src/agents/base.py`:

```python
    def format_output(self, data: Any) -> Any:
        """Format output data before returning.

        Subclasses can override to transform or enrich output.

        Args:
            data: Raw output data from execution.

        Returns:
            Formatted output data.
        """
        return data
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add format_output method to BaseAgent"
```

---

### Task 5: Add Tool Calling with Error Handling

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for _call_tool**

Add to `backend/tests/test_base_agent.py`:

```python
@pytest.mark.asyncio
async def test_base_agent_call_tool_executes_registered_tool() -> None:
    """Test _call_tool executes a registered tool."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {
                "greet": self._greet,
            }

        async def _greet(self, name: str) -> str:
            return f"Hello, {name}!"

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._call_tool("greet", name="World")

    assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_base_agent_call_tool_raises_for_unknown_tool() -> None:
    """Test _call_tool raises ValueError for unknown tool."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {"known_tool": lambda: "result"}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    with pytest.raises(ValueError, match="Unknown tool: unknown_tool"):
        await agent._call_tool("unknown_tool")


@pytest.mark.asyncio
async def test_base_agent_call_tool_handles_sync_tools() -> None:
    """Test _call_tool can handle synchronous tool functions."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {
                "sync_tool": self._sync_tool,
            }

        def _sync_tool(self, value: int) -> int:
            return value * 2

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._call_tool("sync_tool", value=21)

    assert result == 42
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_call_tool_executes_registered_tool tests/test_base_agent.py::test_base_agent_call_tool_raises_for_unknown_tool tests/test_base_agent.py::test_base_agent_call_tool_handles_sync_tools -v`

Expected: FAIL with "has no attribute '_call_tool'"

**Step 3: Write minimal implementation**

Add imports at top of `backend/src/agents/base.py`:

```python
import asyncio
```

Add to `BaseAgent` class:

```python
    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool with error handling.

        Args:
            tool_name: Name of the tool to call.
            **kwargs: Arguments to pass to the tool.

        Returns:
            Tool execution result.

        Raises:
            ValueError: If tool_name is not registered.
        """
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool = self.tools[tool_name]

        # Handle both sync and async tools
        if asyncio.iscoroutinefunction(tool):
            return await tool(**kwargs)
        else:
            return tool(**kwargs)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (15 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add _call_tool method with error handling"
```

---

### Task 6: Add Retry Logic for Tool Calls

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for _call_tool_with_retry**

Add to `backend/tests/test_base_agent.py`:

```python
@pytest.mark.asyncio
async def test_base_agent_call_tool_with_retry_succeeds_first_try() -> None:
    """Test _call_tool_with_retry returns on first success."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {"reliable_tool": self._reliable_tool}

        async def _reliable_tool(self) -> str:
            return "success"

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._call_tool_with_retry("reliable_tool", max_retries=3)

    assert result == "success"


@pytest.mark.asyncio
async def test_base_agent_call_tool_with_retry_retries_on_failure() -> None:
    """Test _call_tool_with_retry retries on transient failures."""
    from src.agents.base import AgentResult, BaseAgent

    call_count = 0

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {"flaky_tool": self._flaky_tool}

        async def _flaky_tool(self) -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success after retries"

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._call_tool_with_retry("flaky_tool", max_retries=3, retry_delay=0.01)

    assert result == "success after retries"
    assert call_count == 3


@pytest.mark.asyncio
async def test_base_agent_call_tool_with_retry_raises_after_max_retries() -> None:
    """Test _call_tool_with_retry raises after exhausting retries."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {"always_fails": self._always_fails}

        async def _always_fails(self) -> str:
            raise RuntimeError("Permanent failure")

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    with pytest.raises(RuntimeError, match="Permanent failure"):
        await agent._call_tool_with_retry("always_fails", max_retries=2, retry_delay=0.01)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_call_tool_with_retry_succeeds_first_try tests/test_base_agent.py::test_base_agent_call_tool_with_retry_retries_on_failure tests/test_base_agent.py::test_base_agent_call_tool_with_retry_raises_after_max_retries -v`

Expected: FAIL with "has no attribute '_call_tool_with_retry'"

**Step 3: Write minimal implementation**

Add to `BaseAgent` class in `backend/src/agents/base.py`:

```python
    async def _call_tool_with_retry(
        self,
        tool_name: str,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs: Any,
    ) -> Any:
        """Call a tool with automatic retry on failure.

        Args:
            tool_name: Name of the tool to call.
            max_retries: Maximum number of retry attempts.
            retry_delay: Delay in seconds between retries.
            **kwargs: Arguments to pass to the tool.

        Returns:
            Tool execution result.

        Raises:
            Exception: If all retries are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return await self._call_tool(tool_name, **kwargs)
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Tool {tool_name} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)

        # Re-raise the last error after exhausting retries
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Tool {tool_name} failed with no error captured")
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (18 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add _call_tool_with_retry with exponential backoff"
```

---

### Task 7: Add Execution Logging

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for execution logging**

Add to `backend/tests/test_base_agent.py`:

```python
@pytest.mark.asyncio
async def test_base_agent_run_logs_execution_start_and_end(caplog: pytest.LogCaptureFixture) -> None:
    """Test run() logs execution start and completion."""
    import logging

    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={"result": "done"})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level(logging.INFO, logger="src.agents.base"):
        result = await agent.run({"task": "test"})

    assert result.success is True
    # Check logs contain start and complete messages
    log_messages = [record.message for record in caplog.records]
    assert any("starting" in msg.lower() for msg in log_messages)
    assert any("complete" in msg.lower() or "finished" in msg.lower() for msg in log_messages)


@pytest.mark.asyncio
async def test_base_agent_run_logs_execution_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Test run() logs execution failure."""
    import logging

    from src.agents.base import AgentResult, BaseAgent

    class FailingAgent(BaseAgent):
        name = "Failing Agent"
        description = "An agent that fails"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            raise RuntimeError("Execution failed")

    mock_llm = MagicMock()
    agent = FailingAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level(logging.ERROR, logger="src.agents.base"):
        result = await agent.run({"task": "test"})

    assert result.success is False
    assert "Execution failed" in (result.error or "")
    log_messages = [record.message for record in caplog.records]
    assert any("error" in msg.lower() or "failed" in msg.lower() for msg in log_messages)
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_run_logs_execution_start_and_end tests/test_base_agent.py::test_base_agent_run_logs_execution_failure -v`

Expected: FAIL with "has no attribute 'run'"

**Step 3: Write minimal implementation**

Add to `BaseAgent` class in `backend/src/agents/base.py`:

```python
    async def run(self, task: dict[str, Any]) -> AgentResult:
        """Run the agent with full lifecycle management.

        Handles status transitions, input validation, execution,
        error handling, and logging.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with execution outcome.
        """
        import time

        start_time = time.perf_counter()
        self.status = AgentStatus.RUNNING

        logger.info(
            f"Agent {self.name} starting execution",
            extra={
                "agent": self.name,
                "user_id": self.user_id,
                "task_keys": list(task.keys()),
            },
        )

        try:
            # Validate input
            if not self.validate_input(task):
                self.status = AgentStatus.FAILED
                return AgentResult(
                    success=False,
                    data=None,
                    error="Input validation failed",
                )

            # Execute the task
            result = await self.execute(task)

            # Format output
            result.data = self.format_output(result.data)

            # Calculate execution time
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms

            self.status = AgentStatus.COMPLETE if result.success else AgentStatus.FAILED

            logger.info(
                f"Agent {self.name} execution complete",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "success": result.success,
                    "execution_time_ms": elapsed_ms,
                    "tokens_used": result.tokens_used,
                },
            )

            return result

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self.status = AgentStatus.FAILED

            logger.error(
                f"Agent {self.name} execution failed: {e}",
                extra={
                    "agent": self.name,
                    "user_id": self.user_id,
                    "error": str(e),
                    "execution_time_ms": elapsed_ms,
                },
            )

            return AgentResult(
                success=False,
                data=None,
                error=str(e),
                execution_time_ms=elapsed_ms,
            )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (20 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add run() method with execution logging"
```

---

### Task 8: Add Token Usage Tracking

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for token tracking**

Add to `backend/tests/test_base_agent.py`:

```python
def test_base_agent_tracks_total_tokens_used() -> None:
    """Test BaseAgent tracks cumulative token usage."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.total_tokens_used == 0


@pytest.mark.asyncio
async def test_base_agent_run_accumulates_tokens() -> None:
    """Test run() accumulates token usage across executions."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={}, tokens_used=100)

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    await agent.run({"task": "first"})
    assert agent.total_tokens_used == 100

    await agent.run({"task": "second"})
    assert agent.total_tokens_used == 200

    await agent.run({"task": "third"})
    assert agent.total_tokens_used == 300


def test_base_agent_reset_token_count() -> None:
    """Test reset_token_count clears accumulated tokens."""
    from src.agents.base import AgentResult, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    agent.total_tokens_used = 500
    agent.reset_token_count()

    assert agent.total_tokens_used == 0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_tracks_total_tokens_used tests/test_base_agent.py::test_base_agent_run_accumulates_tokens tests/test_base_agent.py::test_base_agent_reset_token_count -v`

Expected: FAIL with "has no attribute 'total_tokens_used'"

**Step 3: Write minimal implementation**

Update `BaseAgent.__init__` in `backend/src/agents/base.py`:

```python
    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self.llm = llm_client
        self.user_id = user_id
        self.status = AgentStatus.IDLE
        self.tools: dict[str, Callable[..., Any]] = self._register_tools()
        self.total_tokens_used: int = 0
```

Add method to `BaseAgent`:

```python
    def reset_token_count(self) -> None:
        """Reset the accumulated token usage counter."""
        self.total_tokens_used = 0
```

Update `run()` method to accumulate tokens after successful execution (add after `result.execution_time_ms = elapsed_ms`):

```python
            # Accumulate token usage
            self.total_tokens_used += result.tokens_used
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (23 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add token usage tracking to BaseAgent"
```

---

### Task 9: Add Status Transition Helpers

**Files:**
- Modify: `backend/src/agents/base.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for status helpers**

Add to `backend/tests/test_base_agent.py`:

```python
def test_base_agent_is_idle_property() -> None:
    """Test is_idle property returns correct status."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.is_idle is True
    agent.status = AgentStatus.RUNNING
    assert agent.is_idle is False


def test_base_agent_is_running_property() -> None:
    """Test is_running property returns correct status."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.is_running is False
    agent.status = AgentStatus.RUNNING
    assert agent.is_running is True


def test_base_agent_is_complete_property() -> None:
    """Test is_complete property returns correct status."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.is_complete is False
    agent.status = AgentStatus.COMPLETE
    assert agent.is_complete is True


def test_base_agent_is_failed_property() -> None:
    """Test is_failed property returns correct status."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    class TestAgent(BaseAgent):
        name = "Test Agent"
        description = "A test agent"

        def _register_tools(self) -> dict[str, Any]:
            return {}

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            return AgentResult(success=True, data={})

    mock_llm = MagicMock()
    agent = TestAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.is_failed is False
    agent.status = AgentStatus.FAILED
    assert agent.is_failed is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_base_agent_is_idle_property tests/test_base_agent.py::test_base_agent_is_running_property tests/test_base_agent.py::test_base_agent_is_complete_property tests/test_base_agent.py::test_base_agent_is_failed_property -v`

Expected: FAIL with "has no attribute 'is_idle'"

**Step 3: Write minimal implementation**

Add properties to `BaseAgent` class in `backend/src/agents/base.py`:

```python
    @property
    def is_idle(self) -> bool:
        """Check if agent is idle."""
        return self.status == AgentStatus.IDLE

    @property
    def is_running(self) -> bool:
        """Check if agent is currently running."""
        return self.status == AgentStatus.RUNNING

    @property
    def is_complete(self) -> bool:
        """Check if agent completed successfully."""
        return self.status == AgentStatus.COMPLETE

    @property
    def is_failed(self) -> bool:
        """Check if agent failed."""
        return self.status == AgentStatus.FAILED
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (27 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/base.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add status property helpers to BaseAgent"
```

---

### Task 10: Add Agent Exception Class

**Files:**
- Modify: `backend/src/core/exceptions.py`
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write failing tests for AgentError**

Add to `backend/tests/test_base_agent.py`:

```python
def test_agent_error_exception_has_correct_properties() -> None:
    """Test AgentError exception captures agent context."""
    from src.core.exceptions import AgentError

    error = AgentError(
        agent_name="Hunter Agent",
        message="Failed to search companies",
    )

    assert error.message == "Agent 'Hunter Agent' failed: Failed to search companies"
    assert error.code == "AGENT_ERROR"
    assert error.status_code == 500
    assert error.details["agent_name"] == "Hunter Agent"


def test_agent_execution_error_exception() -> None:
    """Test AgentExecutionError exception for execution failures."""
    from src.core.exceptions import AgentExecutionError

    error = AgentExecutionError(
        agent_name="Analyst Agent",
        task_type="research",
        message="PubMed API unavailable",
    )

    assert "Analyst Agent" in error.message
    assert "research" in error.message
    assert error.code == "AGENT_EXECUTION_ERROR"
    assert error.details["task_type"] == "research"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_base_agent.py::test_agent_error_exception_has_correct_properties tests/test_base_agent.py::test_agent_execution_error_exception -v`

Expected: FAIL with "cannot import name 'AgentError'"

**Step 3: Write minimal implementation**

Add to `backend/src/core/exceptions.py`:

```python
class AgentError(ARIAException):
    """Agent operation error (500).

    Used for failures in agent execution.
    """

    def __init__(self, agent_name: str, message: str = "Unknown error") -> None:
        """Initialize agent error.

        Args:
            agent_name: Name of the agent that failed.
            message: Error details.
        """
        super().__init__(
            message=f"Agent '{agent_name}' failed: {message}",
            code="AGENT_ERROR",
            status_code=500,
            details={"agent_name": agent_name},
        )


class AgentExecutionError(ARIAException):
    """Agent execution error (500).

    Used for failures during task execution.
    """

    def __init__(
        self,
        agent_name: str,
        task_type: str,
        message: str = "Unknown error",
    ) -> None:
        """Initialize agent execution error.

        Args:
            agent_name: Name of the agent that failed.
            task_type: Type of task being executed.
            message: Error details.
        """
        super().__init__(
            message=f"Agent '{agent_name}' failed to execute {task_type}: {message}",
            code="AGENT_EXECUTION_ERROR",
            status_code=500,
            details={"agent_name": agent_name, "task_type": task_type},
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (29 tests)

**Step 5: Commit**

```bash
git add backend/src/core/exceptions.py backend/tests/test_base_agent.py
git commit -m "feat(agents): add AgentError and AgentExecutionError exceptions"
```

---

### Task 11: Update Module Exports and Run Quality Gates

**Files:**
- Modify: `backend/src/agents/__init__.py`
- Verify all quality gates pass

**Step 1: Update module exports**

Update `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.base import AgentResult, AgentStatus, BaseAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "BaseAgent",
]
```

**Step 2: Run all quality gates**

Run backend quality gates:

```bash
cd backend && pytest tests/ -v
cd backend && mypy src/ --strict
cd backend && ruff check src/
cd backend && ruff format src/ --check
```

Expected: All pass

**Step 3: Fix any issues**

If mypy reports issues, fix type annotations. Common fixes:
- Add `from __future__ import annotations` if needed
- Ensure all return types are annotated
- Fix any `Any` usage that should be more specific

**Step 4: Commit**

```bash
git add backend/src/agents/__init__.py
git commit -m "feat(agents): export BaseAgent and types from agents module"
```

---

### Task 12: Final Integration Test

**Files:**
- Modify: `backend/tests/test_base_agent.py`

**Step 1: Write an integration test demonstrating full agent lifecycle**

Add to `backend/tests/test_base_agent.py`:

```python
@pytest.mark.asyncio
async def test_full_agent_lifecycle() -> None:
    """Integration test demonstrating complete agent lifecycle."""
    from src.agents.base import AgentResult, AgentStatus, BaseAgent

    # Track tool calls for verification
    tool_calls: list[str] = []

    class ResearchAgent(BaseAgent):
        name = "Research Agent"
        description = "Agent that researches topics"

        def _register_tools(self) -> dict[str, Any]:
            return {
                "search": self._search,
                "analyze": self._analyze,
            }

        def validate_input(self, task: dict[str, Any]) -> bool:
            return "query" in task

        def format_output(self, data: Any) -> Any:
            return {"formatted": True, "results": data}

        async def _search(self, query: str) -> list[str]:
            tool_calls.append(f"search:{query}")
            return ["result1", "result2"]

        async def _analyze(self, data: list[str]) -> str:
            tool_calls.append(f"analyze:{len(data)}")
            return "Analysis complete"

        async def execute(self, task: dict[str, Any]) -> AgentResult:
            query = task["query"]

            # Use tools
            results = await self._call_tool("search", query=query)
            analysis = await self._call_tool("analyze", data=results)

            return AgentResult(
                success=True,
                data={"search_results": results, "analysis": analysis},
                tokens_used=150,
            )

    mock_llm = MagicMock()
    agent = ResearchAgent(llm_client=mock_llm, user_id="user-123")

    # Initial state
    assert agent.is_idle
    assert agent.total_tokens_used == 0

    # Run the agent
    result = await agent.run({"query": "AI research"})

    # Verify execution
    assert result.success is True
    assert result.data["formatted"] is True
    assert result.data["results"]["search_results"] == ["result1", "result2"]
    assert result.tokens_used == 150
    assert result.execution_time_ms > 0

    # Verify agent state
    assert agent.is_complete
    assert agent.total_tokens_used == 150

    # Verify tools were called
    assert "search:AI research" in tool_calls
    assert "analyze:2" in tool_calls

    # Test validation failure
    agent.status = AgentStatus.IDLE
    invalid_result = await agent.run({"no_query": "field"})
    assert invalid_result.success is False
    assert "validation" in (invalid_result.error or "").lower()
```

**Step 2: Run the integration test**

Run: `cd backend && pytest tests/test_base_agent.py::test_full_agent_lifecycle -v`

Expected: PASS

**Step 3: Run full test suite**

Run: `cd backend && pytest tests/test_base_agent.py -v`

Expected: PASS (30 tests)

**Step 4: Final commit**

```bash
git add backend/tests/test_base_agent.py
git commit -m "test(agents): add integration test for full agent lifecycle"
```

---

## Summary

This plan implements US-302 with the following components:

1. **AgentStatus enum** - Four states: IDLE, RUNNING, COMPLETE, FAILED
2. **AgentResult dataclass** - Captures success, data, error, tokens, and execution time
3. **BaseAgent abstract class** with:
   - Tool registration via `_register_tools()`
   - Input validation via `validate_input()`
   - Output formatting via `format_output()`
   - Tool calling with `_call_tool()` and `_call_tool_with_retry()`
   - Full lifecycle management via `run()`
   - Status property helpers
   - Token usage tracking
4. **Custom exceptions** - AgentError and AgentExecutionError

All code follows the project's patterns:
- Async-first with proper type hints
- Logging instead of print
- Comprehensive docstrings
- TDD approach with tests before implementation
