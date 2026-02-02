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


def test_validate_input_accepts_valid_email_task() -> None:
    """Test validate_input returns True for valid email task."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "John Doe", "title": "CEO", "company": "Acme Inc"},
        "context": "Following up on our meeting last week",
        "goal": "Schedule a follow-up call",
        "tone": "formal",
    }

    assert agent.validate_input(task) is True


def test_validate_input_accepts_valid_document_task() -> None:
    """Test validate_input returns True for valid document task."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "document",
        "context": "Quarterly sales performance data",
        "goal": "Summarize Q4 results for leadership",
        "tone": "formal",
    }

    assert agent.validate_input(task) is True


def test_validate_input_requires_communication_type() -> None:
    """Test validate_input returns False when communication_type is missing."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "context": "Following up on our meeting",
        "goal": "Schedule a call",
    }

    assert agent.validate_input(task) is False


def test_validate_input_requires_goal() -> None:
    """Test validate_input returns False when goal is missing."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "context": "Following up on our meeting",
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_communication_type() -> None:
    """Test validate_input rejects invalid communication_type."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "telegram",  # Invalid type
        "context": "Following up",
        "goal": "Schedule a call",
    }

    assert agent.validate_input(task) is False


def test_validate_input_validates_tone() -> None:
    """Test validate_input rejects invalid tone."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "context": "Following up",
        "goal": "Schedule a call",
        "tone": "aggressive",  # Invalid tone
    }

    assert agent.validate_input(task) is False


def test_validate_input_allows_optional_recipient() -> None:
    """Test validate_input allows task without recipient."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "context": "General announcement",
        "goal": "Inform team about policy change",
    }

    assert agent.validate_input(task) is True


def test_validate_input_defaults_tone_to_formal() -> None:
    """Test validate_input accepts task without tone (defaults to formal)."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "context": "Meeting request",
        "goal": "Set up a meeting",
    }

    assert agent.validate_input(task) is True
