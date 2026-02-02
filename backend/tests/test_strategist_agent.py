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
