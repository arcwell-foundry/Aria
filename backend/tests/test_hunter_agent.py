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


def test_validate_input_accepts_valid_task() -> None:
    """Test validate_input returns True for valid task with all required fields."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 10,
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_icp() -> None:
    """Test validate_input returns False when icp is missing."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "target_count": 10,
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_target_count() -> None:
    """Test validate_input returns False when target_count is missing."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
    }

    assert agent.validate_input(task) is False


def test_validate_input_allows_optional_exclusions() -> None:
    """Test validate_input accepts valid task with optional exclusions list."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 10,
        "exclusions": ["competitor1.com", "competitor2.com"],
    }

    assert agent.validate_input(task) is True


def test_validate_input_validates_icp_has_industry() -> None:
    """Test validate_input returns False when icp lacks industry field."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "icp": {"size": "large"},  # Missing industry
        "target_count": 10,
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_target_count_is_positive() -> None:
    """Test validate_input returns False when target_count is not positive."""
    from src.agents.hunter import HunterAgent

    mock_llm = MagicMock()
    agent = HunterAgent(llm_client=mock_llm, user_id="user-123")

    # Test with zero
    task_zero = {
        "icp": {"industry": "Biotechnology"},
        "target_count": 0,
    }
    assert agent.validate_input(task_zero) is False

    # Test with negative number
    task_negative = {
        "icp": {"industry": "Biotechnology"},
        "target_count": -5,
    }
    assert agent.validate_input(task_negative) is False
