"""Tests for ScribeAgent module."""

from typing import Any
from unittest.mock import MagicMock

import pytest


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


@pytest.mark.asyncio
async def test_draft_email_returns_dict() -> None:
    """Test _draft_email returns a dictionary."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "John Doe", "company": "Acme"},
        context="Following up on our meeting",
        goal="Schedule a call",
        tone="formal",
    )

    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_draft_email_has_subject_and_body() -> None:
    """Test _draft_email returns email with subject and body."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "John Doe"},
        context="Meeting follow-up",
        goal="Schedule next meeting",
        tone="formal",
    )

    assert "subject" in result
    assert "body" in result
    assert len(result["subject"]) > 0
    assert len(result["body"]) > 0


@pytest.mark.asyncio
async def test_draft_email_includes_recipient_name() -> None:
    """Test _draft_email includes recipient name in body."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Sarah Johnson", "company": "TechCorp"},
        context="Product demo follow-up",
        goal="Get feedback on the demo",
        tone="friendly",
    )

    assert "Sarah" in result["body"]


@pytest.mark.asyncio
async def test_draft_email_formal_tone() -> None:
    """Test _draft_email with formal tone has appropriate greeting."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Dr. Smith"},
        context="Initial outreach",
        goal="Introduce our services",
        tone="formal",
    )

    # Formal tone should have "Dear" greeting
    assert "Dear" in result["body"]


@pytest.mark.asyncio
async def test_draft_email_friendly_tone() -> None:
    """Test _draft_email with friendly tone has appropriate greeting."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Mike"},
        context="Catching up",
        goal="Check in on the project",
        tone="friendly",
    )

    # Friendly tone should have "Hi" or "Hello" greeting
    body = result["body"]
    assert "Hi" in body or "Hello" in body


@pytest.mark.asyncio
async def test_draft_email_urgent_tone() -> None:
    """Test _draft_email with urgent tone has urgency indicators."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Team Lead"},
        context="Critical bug in production",
        goal="Get immediate attention to fix the bug",
        tone="urgent",
    )

    # Subject should indicate urgency
    subject = result["subject"].lower()
    body = result["body"].lower()
    assert "urgent" in subject or "immediate" in subject or "urgent" in body or "asap" in body


@pytest.mark.asyncio
async def test_draft_email_includes_call_to_action() -> None:
    """Test _draft_email includes a call to action."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "John"},
        context="Sales follow-up",
        goal="Schedule a demo",
        tone="formal",
    )

    assert result.get("has_call_to_action") is True


@pytest.mark.asyncio
async def test_draft_email_tracks_word_count() -> None:
    """Test _draft_email includes word count."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Jane"},
        context="Follow up",
        goal="Get response",
        tone="formal",
    )

    assert "word_count" in result
    assert isinstance(result["word_count"], int)
    assert result["word_count"] > 0


@pytest.mark.asyncio
async def test_draft_email_logs_drafting(caplog: Any) -> None:
    """Test _draft_email logs the drafting activity."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level("INFO"):
        await agent._draft_email(
            recipient={"name": "Test"},
            context="Test context",
            goal="Test goal",
            tone="formal",
        )

    assert "Drafting email" in caplog.text


@pytest.mark.asyncio
async def test_draft_document_returns_dict() -> None:
    """Test _draft_document returns a dictionary."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="brief",
        context="Q4 sales performance",
        goal="Summarize results for leadership",
        tone="formal",
    )

    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_draft_document_has_title_and_body() -> None:
    """Test _draft_document returns document with title and body."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="report",
        context="Monthly metrics",
        goal="Provide monthly update",
        tone="formal",
    )

    assert "title" in result
    assert "body" in result
    assert len(result["title"]) > 0
    assert len(result["body"]) > 0


@pytest.mark.asyncio
async def test_draft_document_includes_sections() -> None:
    """Test _draft_document includes structured sections."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="report",
        context="Quarterly business review",
        goal="Present Q4 results",
        tone="formal",
    )

    assert "sections" in result
    assert isinstance(result["sections"], list)
    assert len(result["sections"]) > 0

    # Each section should have heading and content
    for section in result["sections"]:
        assert "heading" in section
        assert "content" in section


@pytest.mark.asyncio
async def test_draft_document_brief_type() -> None:
    """Test _draft_document with brief type is concise."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="brief",
        context="Product launch plan",
        goal="Quick overview of launch strategy",
        tone="formal",
    )

    assert result["document_type"] == "brief"
    # Briefs should be concise
    assert result["word_count"] < 500


@pytest.mark.asyncio
async def test_draft_document_report_type() -> None:
    """Test _draft_document with report type is more detailed."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="report",
        context="Annual review data",
        goal="Comprehensive annual summary",
        tone="formal",
    )

    assert result["document_type"] == "report"
    # Reports should have multiple sections
    assert len(result["sections"]) >= 2


@pytest.mark.asyncio
async def test_draft_document_proposal_type() -> None:
    """Test _draft_document with proposal type."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="proposal",
        context="New partnership opportunity",
        goal="Propose collaboration terms",
        tone="formal",
    )

    assert result["document_type"] == "proposal"


@pytest.mark.asyncio
async def test_draft_document_tracks_word_count() -> None:
    """Test _draft_document includes word count."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="brief",
        context="Test",
        goal="Test",
        tone="formal",
    )

    assert "word_count" in result
    assert isinstance(result["word_count"], int)
    assert result["word_count"] > 0


@pytest.mark.asyncio
async def test_draft_document_logs_drafting(caplog: Any) -> None:
    """Test _draft_document logs the drafting activity."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level("INFO"):
        await agent._draft_document(
            document_type="brief",
            context="Test",
            goal="Test",
            tone="formal",
        )

    assert "Drafting document" in caplog.text or "brief" in caplog.text.lower()


@pytest.mark.asyncio
async def test_draft_document_unknown_type_fallback() -> None:
    """Test _draft_document with unknown type uses fallback section."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="memo",  # Unknown type
        context="Test content",
        goal="Test goal",
        tone="formal",
    )

    assert len(result["sections"]) == 1
    assert result["sections"][0]["heading"] == "Content"
    assert result["document_type"] == "memo"


@pytest.mark.asyncio
async def test_personalize_returns_string() -> None:
    """Test _personalize returns a string."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._personalize(
        content="Hello, this is a test message.",
        style=None,
    )

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_personalize_without_style_returns_content() -> None:
    """Test _personalize without style returns original content."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    content = "This is the original content."
    result = await agent._personalize(content=content, style=None)

    # Without style, should return content as-is
    assert result == content


@pytest.mark.asyncio
async def test_personalize_applies_casual_style() -> None:
    """Test _personalize applies casual writing style."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    content = "I would like to schedule a meeting with you."
    style = {"formality": "casual", "contractions": True}

    result = await agent._personalize(content=content, style=style)

    # Casual style might use contractions
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_personalize_applies_signature() -> None:
    """Test _personalize applies signature from style."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    content = "Please review this document."
    style = {"signature": "Best, John"}

    result = await agent._personalize(content=content, style=style)

    assert "Best, John" in result


@pytest.mark.asyncio
async def test_personalize_applies_greeting_preference() -> None:
    """Test _personalize applies greeting preference from style."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    content = "Dear Customer, your order is ready."
    style = {"preferred_greeting": "Hey"}

    result = await agent._personalize(content=content, style=style)

    assert "Hey" in result


@pytest.mark.asyncio
async def test_personalize_logs_style_application(caplog: Any) -> None:
    """Test _personalize logs when applying style."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    style = {"formality": "casual"}

    with caplog.at_level("INFO"):
        await agent._personalize(content="Test content", style=style)

    assert "Personalizing" in caplog.text or "style" in caplog.text.lower()
