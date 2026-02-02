"""Tests for ScoutAgent module."""

from unittest.mock import MagicMock


def test_scout_agent_has_name_and_description() -> None:
    """Test ScoutAgent has correct name and description class attributes."""
    from src.agents.scout import ScoutAgent

    assert ScoutAgent.name == "Scout"
    assert ScoutAgent.description == "Intelligence gathering and filtering"


def test_scout_agent_extends_base_agent() -> None:
    """Test ScoutAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.scout import ScoutAgent

    assert issubclass(ScoutAgent, BaseAgent)


def test_scout_agent_initializes_with_llm_and_user() -> None:
    """Test ScoutAgent initializes with llm_client and user_id."""
    from src.agents.base import AgentStatus
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with entities."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp", "Beta Inc"],
        "signal_types": ["funding", "hiring"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_entities() -> None:
    """Test validate_input returns False when entities is missing."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "signal_types": ["funding"],
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_entities_is_list() -> None:
    """Test validate_input returns False when entities is not a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": "Acme Corp",  # Should be list
    }

    assert agent.validate_input(task) is False


def test_validate_input_allows_optional_signal_types() -> None:
    """Test validate_input accepts valid task with optional signal_types."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp"],
        "signal_types": ["funding", "hiring", "leadership"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_validates_signal_types_is_list_if_present() -> None:
    """Test validate_input returns False when signal_types is not a list."""
    from src.agents.scout import ScoutAgent

    mock_llm = MagicMock()
    agent = ScoutAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "entities": ["Acme Corp"],
        "signal_types": "funding",  # Should be list
    }

    assert agent.validate_input(task) is False
