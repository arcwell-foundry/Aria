"""Tests for AnalystAgent module."""

from unittest.mock import MagicMock


def test_analyst_agent_has_name_and_description() -> None:
    """Test AnalystAgent has correct name and description class attributes."""
    from src.agents.analyst import AnalystAgent

    assert AnalystAgent.name == "Analyst"
    assert AnalystAgent.description == "Scientific research agent for life sciences queries"


def test_analyst_agent_extends_base_agent() -> None:
    """Test AnalystAgent extends BaseAgent."""
    from src.agents.analyst import AnalystAgent
    from src.agents.base import BaseAgent

    assert issubclass(AnalystAgent, BaseAgent)


def test_analyst_agent_initializes_with_llm_and_user() -> None:
    """Test AnalystAgent initializes with llm_client, user_id, and _research_cache."""
    from src.agents.analyst import AnalystAgent
    from src.agents.base import AgentStatus

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_research_cache")
    assert agent._research_cache == {}


def test_analyst_agent_registers_four_tools() -> None:
    """Test AnalystAgent._register_tools returns dict with 4 tools."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "pubmed_search" in tools
    assert "clinical_trials_search" in tools
    assert "fda_drug_search" in tools
    assert "chembl_search" in tools
