"""Tests for ScribeAgent module."""

from unittest.mock import MagicMock


def test_scribe_agent_has_name_and_description() -> None:
    """Test ScribeAgent has correct name and description class attributes."""
    from src.agents.scribe import ScribeAgent

    assert ScribeAgent.name == "Scribe"
    assert ScribeAgent.description == "Drafts emails and documents with style matching"


def test_scribe_agent_extends_base_agent() -> None:
    """Test ScribeAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.scribe import ScribeAgent

    assert issubclass(ScribeAgent, BaseAgent)


def test_scribe_agent_initializes_with_llm_and_user() -> None:
    """Test ScribeAgent initializes with llm_client, user_id, and template cache."""
    from src.agents.base import AgentStatus
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_templates")
    assert isinstance(agent._templates, dict)


def test_scribe_agent_registers_four_tools() -> None:
    """Test ScribeAgent._register_tools returns dict with 4 tools."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "draft_email" in tools
    assert "draft_document" in tools
    assert "personalize" in tools
    assert "apply_template" in tools
