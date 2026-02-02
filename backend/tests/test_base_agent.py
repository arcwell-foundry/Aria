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