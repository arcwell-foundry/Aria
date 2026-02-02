"""Tests for base agent module."""

from abc import ABC
from typing import Any
from unittest.mock import MagicMock

import pytest


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


@pytest.mark.asyncio
async def test_base_agent_run_logs_execution_start_and_end(
    caplog: pytest.LogCaptureFixture,
) -> None:
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
async def test_base_agent_run_logs_execution_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
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