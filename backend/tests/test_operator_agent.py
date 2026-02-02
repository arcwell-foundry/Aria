"""Tests for OperatorAgent module."""

from typing import Any
from unittest.mock import MagicMock


def test_operator_agent_has_name_and_description() -> None:
    """Test OperatorAgent has correct name and description class attributes."""
    from src.agents.operator import OperatorAgent

    assert OperatorAgent.name == "Operator"
    assert OperatorAgent.description == "System operations for calendar, CRM, and integrations"


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
        "parameters": {},
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_operation_type() -> None:
    """Test validate_input returns False when operation_type is missing."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "parameters": {},
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_operation_type() -> None:
    """Test validate_input returns False for invalid operation_type."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "invalid_operation",
        "parameters": {},
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters() -> None:
    """Test validate_input returns False when parameters is missing."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_parameters_as_dict() -> None:
    """Test validate_input returns False when parameters is not a dict."""
    from src.agents.operator import OperatorAgent

    mock_llm = MagicMock()
    agent = OperatorAgent(llm_client=mock_llm, user_id="user-123")

    task: dict[str, Any] = {
        "operation_type": "calendar_read",
        "parameters": "not_a_dict",
    }

    assert agent.validate_input(task) is False
