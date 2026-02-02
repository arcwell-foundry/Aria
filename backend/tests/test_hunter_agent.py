"""Tests for HunterAgent module."""

from unittest.mock import MagicMock


def test_hunter_agent_has_name_and_description() -> None:
    """Test HunterAgent has correct name and description class attributes."""
    from src.agents.hunter import HunterAgent

    assert HunterAgent.name == "Hunter Pro"
    assert HunterAgent.description == "Discovers and qualifies new leads based on ICP"


def test_hunter_agent_extends_base_agent() -> None:
    """Test HunterAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.hunter import HunterAgent

    assert issubclass(HunterAgent, BaseAgent)


def test_hunter_agent_initializes_with_llm_and_user() -> None:
    """Test HunterAgent initializes with llm_client, user_id, and _company_cache."""
    from src.agents.base import AgentStatus
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_company_cache")
    assert agent._company_cache == {}


def test_hunter_agent_registers_four_tools() -> None:
    """Test HunterAgent._register_tools returns dict with 4 tools."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "search_companies" in tools
    assert "enrich_company" in tools
    assert "find_contacts" in tools
    assert "score_fit" in tools
