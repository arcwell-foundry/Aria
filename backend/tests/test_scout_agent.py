"""Tests for ScoutAgent module."""

import pytest
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
