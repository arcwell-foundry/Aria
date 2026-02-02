"""Tests for StrategistAgent module."""

from unittest.mock import MagicMock


def test_strategist_agent_has_name_and_description() -> None:
    """Test StrategistAgent has correct name and description class attributes."""
    from src.agents.strategist import StrategistAgent

    assert StrategistAgent.name == "Strategist"
    assert StrategistAgent.description == "Strategic planning and pursuit orchestration"


def test_strategist_agent_extends_base_agent() -> None:
    """Test StrategistAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.strategist import StrategistAgent

    assert issubclass(StrategistAgent, BaseAgent)


def test_strategist_agent_initializes_with_llm_and_user() -> None:
    """Test StrategistAgent initializes with llm_client, user_id."""
    from src.agents.base import AgentStatus
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE


def test_strategist_agent_registers_three_tools() -> None:
    """Test StrategistAgent._register_tools returns dict with 3 tools."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 3
    assert "analyze_account" in tools
    assert "generate_strategy" in tools
    assert "create_timeline" in tools


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input accepts properly formatted task."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    valid_task = {
        "goal": {
            "title": "Close deal with Acme Corp",
            "type": "close",
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst"],
            "time_horizon_days": 90,
        },
    }

    assert agent.validate_input(valid_task) is True


def test_validate_input_requires_goal() -> None:
    """Test validate_input rejects task without goal."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_goal_title() -> None:
    """Test validate_input requires goal to have title."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "type": "research",
        },
        "resources": {
            "available_agents": ["Analyst"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_goal_type() -> None:
    """Test validate_input requires goal to have type."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
        },
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_resources() -> None:
    """Test validate_input rejects task without resources."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "lead_gen",
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_requires_time_horizon() -> None:
    """Test validate_input requires time_horizon_days in resources."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "outreach",
        },
        "resources": {
            "available_agents": ["Scribe"],
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_validates_goal_type() -> None:
    """Test validate_input validates goal type is one of allowed values."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    invalid_task = {
        "goal": {
            "title": "Some goal",
            "type": "invalid_type",
        },
        "resources": {
            "available_agents": ["Hunter"],
            "time_horizon_days": 30,
        },
    }

    assert agent.validate_input(invalid_task) is False


def test_validate_input_allows_optional_constraints() -> None:
    """Test validate_input allows optional constraints."""
    from src.agents.strategist import StrategistAgent

    mock_llm = MagicMock()
    agent = StrategistAgent(llm_client=mock_llm, user_id="user-123")

    task_with_constraints = {
        "goal": {
            "title": "Close deal with Acme Corp",
            "type": "close",
        },
        "resources": {
            "available_agents": ["Hunter", "Analyst"],
            "time_horizon_days": 90,
        },
        "constraints": {
            "deadline": "2026-06-01",
            "exclusions": ["Competitor Inc"],
        },
    }

    assert agent.validate_input(task_with_constraints) is True
