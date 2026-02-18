"""Tests for ScribeAgent module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

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


def test_scribe_agent_registers_tools() -> None:
    """Test ScribeAgent._register_tools returns dict with 6 tools."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 6
    assert "draft_email" in tools
    assert "draft_document" in tools
    assert "personalize" in tools
    assert "apply_template" in tools
    assert "research_recipient" in tools
    assert "explain_choices" in tools


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


@pytest.mark.asyncio
async def test_apply_template_returns_string() -> None:
    """Test _apply_template returns a string."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    # First register a template
    agent._templates["welcome"] = "Welcome to {company}, {name}!"

    result = await agent._apply_template(
        template_name="welcome",
        variables={"company": "Acme Inc", "name": "John"},
    )

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_apply_template_substitutes_variables() -> None:
    """Test _apply_template substitutes variables correctly."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    agent._templates["intro"] = "Hello {name}, I'm reaching out about {topic}."

    result = await agent._apply_template(
        template_name="intro",
        variables={"name": "Sarah", "topic": "our partnership"},
    )

    assert "Sarah" in result
    assert "our partnership" in result


@pytest.mark.asyncio
async def test_apply_template_unknown_template_returns_empty() -> None:
    """Test _apply_template returns empty string for unknown template."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._apply_template(
        template_name="nonexistent",
        variables={},
    )

    assert result == ""


@pytest.mark.asyncio
async def test_apply_template_handles_missing_variables() -> None:
    """Test _apply_template handles missing variables gracefully."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    agent._templates["greeting"] = "Hello {name}, welcome to {company}!"

    result = await agent._apply_template(
        template_name="greeting",
        variables={"name": "John"},  # Missing 'company'
    )

    # Should handle missing variable
    assert "John" in result


@pytest.mark.asyncio
async def test_apply_template_uses_builtin_templates() -> None:
    """Test _apply_template has built-in templates."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    # Should have some built-in templates
    assert len(agent._templates) > 0


@pytest.mark.asyncio
async def test_apply_template_follow_up_email() -> None:
    """Test _apply_template has follow_up_email template."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._apply_template(
        template_name="follow_up_email",
        variables={"name": "Mike", "meeting_topic": "the demo"},
    )

    assert "Mike" in result
    assert "demo" in result


@pytest.mark.asyncio
async def test_apply_template_meeting_request() -> None:
    """Test _apply_template has meeting_request template."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._apply_template(
        template_name="meeting_request",
        variables={"name": "Sarah", "purpose": "discuss Q1 goals"},
    )

    assert "Sarah" in result
    assert "Q1 goals" in result or "discuss" in result


@pytest.mark.asyncio
async def test_apply_template_logs_usage(caplog: Any) -> None:
    """Test _apply_template logs template usage."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    with caplog.at_level("INFO"):
        await agent._apply_template(
            template_name="follow_up_email",
            variables={"name": "Test"},
        )

    assert "template" in caplog.text.lower()


@pytest.mark.asyncio
async def test_execute_returns_agent_result() -> None:
    """Test execute returns AgentResult with draft data."""
    from src.agents.base import AgentResult
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "John Doe"},
        "context": "Following up on meeting",
        "goal": "Schedule next steps",
        "tone": "formal",
    }

    result = await agent.execute(task)

    assert isinstance(result, AgentResult)


@pytest.mark.asyncio
async def test_execute_email_returns_email_draft() -> None:
    """Test execute with email type returns email draft."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Jane Smith", "company": "TechCorp"},
        "context": "Product demo follow-up",
        "goal": "Get feedback and schedule next call",
        "tone": "friendly",
    }

    result = await agent.execute(task)
    data = result.data

    assert data["draft_type"] == "email"
    assert "content" in data
    assert "subject" in data["content"]
    assert "body" in data["content"]


@pytest.mark.asyncio
async def test_execute_document_returns_document_draft() -> None:
    """Test execute with document type returns document draft."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "document",
        "context": "Q4 sales performance data",
        "goal": "Executive summary for leadership",
        "tone": "formal",
    }

    result = await agent.execute(task)
    data = result.data

    assert data["draft_type"] == "document"
    assert "content" in data
    assert "title" in data["content"]
    assert "body" in data["content"]


@pytest.mark.asyncio
async def test_execute_uses_template_when_specified() -> None:
    """Test execute uses template when template_name is provided."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Sarah"},
        "context": "the product demo",
        "goal": "Follow up",
        "template_name": "follow_up_email",
    }

    result = await agent.execute(task)
    data = result.data

    assert data.get("template_used") == "follow_up_email"


@pytest.mark.asyncio
async def test_execute_applies_style_when_provided() -> None:
    """Test execute applies Digital Twin style when style is provided."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Mike"},
        "context": "Check-in",
        "goal": "Weekly update",
        "tone": "friendly",
        "style": {"signature": "Cheers, Alex"},
    }

    result = await agent.execute(task)
    data = result.data

    assert data.get("style_applied") is not None
    # Signature should be in the content
    assert "Cheers, Alex" in data["content"]["body"]


@pytest.mark.asyncio
async def test_execute_sets_ready_for_review() -> None:
    """Test execute sets ready_for_review flag."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Test"},
        "context": "Test",
        "goal": "Test",
    }

    result = await agent.execute(task)
    data = result.data

    assert data["ready_for_review"] is True


@pytest.mark.asyncio
async def test_execute_handles_message_type() -> None:
    """Test execute handles message communication type."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "message",
        "recipient": {"name": "Team"},
        "context": "Quick update",
        "goal": "Inform team about deadline",
        "tone": "urgent",
    }

    result = await agent.execute(task)

    assert result.success is True
    # Messages are treated like short emails
    assert result.data["draft_type"] == "email"


@pytest.mark.asyncio
async def test_execute_success_flag() -> None:
    """Test execute sets success flag correctly."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "context": "Test",
        "goal": "Test",
    }

    result = await agent.execute(task)

    assert result.success is True


# ============================================================================
# Integration Tests - Full Workflow
# ============================================================================


@pytest.mark.asyncio
async def test_full_scribe_email_workflow() -> None:
    """Integration test demonstrating complete Scribe agent email workflow."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    # Verify initial state
    assert agent.is_idle
    assert agent.total_tokens_used == 0

    # Define a realistic email task
    task = {
        "communication_type": "email",
        "recipient": {
            "name": "Dr. Sarah Chen",
            "title": "VP of Research",
            "company": "BioTech Solutions",
        },
        "context": "Following up on our conversation at the conference last week about potential collaboration opportunities in gene therapy research",
        "goal": "Schedule a call to discuss partnership possibilities",
        "tone": "formal",
    }

    # Run the agent
    result = await agent.run(task)

    # Verify execution result
    assert result.success is True
    assert result.execution_time_ms >= 0

    # Verify draft structure
    data = result.data
    assert data["draft_type"] == "email"
    assert data["ready_for_review"] is True

    # Verify email content
    content = data["content"]
    assert "subject" in content
    assert "body" in content
    assert len(content["subject"]) > 0
    assert len(content["body"]) > 0
    assert "Sarah" in content["body"]  # Recipient name should be included
    assert content["tone"] == "formal"
    assert "Dear" in content["body"]  # Formal tone

    # Verify agent state
    assert agent.is_complete


@pytest.mark.asyncio
async def test_full_scribe_document_workflow() -> None:
    """Integration test demonstrating complete Scribe agent document workflow."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    # Define a document task
    task = {
        "communication_type": "document",
        "document_type": "report",
        "context": "Q4 2024 sales exceeded targets by 15%, driven by strong performance in the biotech vertical",
        "goal": "Executive Summary: Q4 Sales Performance",
        "tone": "formal",
    }

    # Run the agent
    result = await agent.run(task)

    # Verify execution result
    assert result.success is True

    # Verify document structure
    data = result.data
    assert data["draft_type"] == "document"
    assert data["ready_for_review"] is True

    # Verify document content
    content = data["content"]
    assert "title" in content
    assert "body" in content
    assert "sections" in content
    assert len(content["sections"]) >= 2  # Reports should have multiple sections

    # Verify agent state
    assert agent.is_complete


@pytest.mark.asyncio
async def test_scribe_agent_handles_validation_failure() -> None:
    """Test Scribe agent handles invalid input gracefully."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    # Invalid task - missing goal
    invalid_task = {
        "communication_type": "email",
        "context": "Some context",
    }

    result = await agent.run(invalid_task)

    # Should fail validation
    assert result.success is False
    assert "validation" in (result.error or "").lower()
    assert agent.is_failed


@pytest.mark.asyncio
async def test_scribe_with_template_and_style() -> None:
    """Test Scribe agent with both template and style customization."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Alex"},
        "context": "our product demo yesterday",
        "goal": "Follow up on demo",
        "template_name": "follow_up_email",
        "style": {"signature": "Best regards,\nJohn Smith\nSales Manager"},
    }

    result = await agent.run(task)

    assert result.success is True
    data = result.data

    # Template should be used
    assert data.get("template_used") == "follow_up_email"
    # Style should be applied
    assert data.get("style_applied") is not None
    # Signature should be in content
    assert "John Smith" in data["content"]["body"]


@pytest.mark.asyncio
async def test_scribe_urgent_tone_workflow() -> None:
    """Test Scribe agent with urgent tone."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Engineering Team"},
        "context": "Critical production issue affecting customer data",
        "goal": "Immediate action required on production bug",
        "tone": "urgent",
    }

    result = await agent.run(task)

    assert result.success is True
    content = result.data["content"]

    # Should have urgency indicators
    subject = content["subject"].lower()
    body = content["body"].lower()
    assert "urgent" in subject or "urgent" in body or "immediate" in body or "asap" in body


# ============================================================================
# New Tests - PersonaBuilder, ColdMemory, CostGovernor, Metadata Integration
# ============================================================================


def test_scribe_agent_accepts_persona_builder() -> None:
    """Test ScribeAgent accepts persona_builder parameter."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_persona = MagicMock()
    agent = ScribeAgent(
        llm_client=mock_llm,
        user_id="user-123",
        persona_builder=mock_persona,
    )

    assert agent.persona_builder is mock_persona


def test_scribe_agent_accepts_cold_retriever() -> None:
    """Test ScribeAgent accepts cold_retriever parameter."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_retriever = MagicMock()
    agent = ScribeAgent(
        llm_client=mock_llm,
        user_id="user-123",
        cold_retriever=mock_retriever,
    )

    assert agent._cold_retriever is mock_retriever


@pytest.mark.asyncio
async def test_draft_email_passes_user_id_to_llm() -> None:
    """Test _draft_email passes user_id to generate_response for CostGovernor."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello John, test body.", "tone_notes": "formal", "confidence": 0.8, "alternatives": []}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-456")

    await agent._draft_email(
        recipient={"name": "John"},
        context="Test",
        goal="Test goal",
        tone="formal",
    )

    # Verify user_id was passed
    call_kwargs = mock_llm.generate_response.call_args
    assert call_kwargs.kwargs.get("user_id") == "user-456"


@pytest.mark.asyncio
async def test_draft_document_passes_user_id_to_llm() -> None:
    """Test _draft_document passes user_id to generate_response for CostGovernor."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"title": "Report", "body": "Content here.", "sections": [{"heading": "Summary", "content": "Summary text."}], "confidence": 0.85, "alternatives": []}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-789")

    await agent._draft_document(
        document_type="brief",
        context="Test context",
        goal="Test goal",
        tone="formal",
    )

    call_kwargs = mock_llm.generate_response.call_args
    assert call_kwargs.kwargs.get("user_id") == "user-789"


@pytest.mark.asyncio
async def test_draft_email_uses_persona_builder() -> None:
    """Test _draft_email uses PersonaBuilder when available."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello Sarah, body text.", "tone_notes": "formal", "confidence": 0.9, "alternatives": []}'
    )

    # Create a mock PersonaBuilder that returns a persona context
    mock_persona = MagicMock()
    mock_persona_ctx = MagicMock()
    mock_persona_ctx.to_system_prompt.return_value = "You are ARIA, a professional colleague."
    mock_persona.build = AsyncMock(return_value=mock_persona_ctx)

    agent = ScribeAgent(
        llm_client=mock_llm,
        user_id="user-123",
        persona_builder=mock_persona,
    )

    result = await agent._draft_email(
        recipient={"name": "Sarah", "company": "BioTech"},
        context="Follow up",
        goal="Schedule call",
        tone="formal",
    )

    # PersonaBuilder should have been called
    mock_persona.build.assert_called_once()
    # Metadata should reflect persona_builder was used
    assert "persona_builder" in result["metadata"]["context_used"]
    assert result["metadata"]["persona_layers_used"] is True


@pytest.mark.asyncio
async def test_draft_document_uses_persona_builder() -> None:
    """Test _draft_document uses PersonaBuilder when available."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"title": "Report", "body": "Report body.", "sections": [{"heading": "Summary", "content": "Text."}], "confidence": 0.8, "alternatives": []}'
    )

    mock_persona = MagicMock()
    mock_persona_ctx = MagicMock()
    mock_persona_ctx.to_system_prompt.return_value = "You are ARIA writing a document."
    mock_persona.build = AsyncMock(return_value=mock_persona_ctx)

    agent = ScribeAgent(
        llm_client=mock_llm,
        user_id="user-123",
        persona_builder=mock_persona,
    )

    result = await agent._draft_document(
        document_type="brief",
        context="Q4 data",
        goal="Summarize results",
        tone="formal",
    )

    mock_persona.build.assert_called_once()
    assert "persona_builder" in result["metadata"]["context_used"]
    assert result["metadata"]["persona_layers_used"] is True


@pytest.mark.asyncio
async def test_draft_email_retrieves_cold_memory() -> None:
    """Test _draft_email retrieves cold memory for recipient context."""
    from src.agents.scribe import ScribeAgent
    from src.memory.cold_retrieval import ColdMemoryResult, EntityContext, MemorySource

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello John, body.", "tone_notes": "formal", "confidence": 0.8, "alternatives": []}'
    )

    mock_retriever = MagicMock()
    mock_retriever.retrieve_for_entity = AsyncMock(
        return_value=EntityContext(
            entity_id="John",
            direct_facts=[
                ColdMemoryResult(
                    source=MemorySource.SEMANTIC,
                    content="John is VP of Sales at Acme",
                    relevance_score=0.9,
                )
            ],
        )
    )
    mock_retriever.retrieve = AsyncMock(return_value=[])

    agent = ScribeAgent(
        llm_client=mock_llm,
        user_id="user-123",
        cold_retriever=mock_retriever,
    )

    result = await agent._draft_email(
        recipient={"name": "John", "company": "Acme"},
        context="Follow up",
        goal="Schedule call",
        tone="formal",
    )

    # Cold retriever should have been called for entity context
    mock_retriever.retrieve_for_entity.assert_called_once()
    assert "cold_memory" in result["metadata"]["context_used"]


@pytest.mark.asyncio
async def test_draft_email_metadata_includes_confidence() -> None:
    """Test _draft_email metadata includes confidence score."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello, test.", "tone_notes": "formal", "confidence": 0.92, "alternatives": []}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Test"},
        context="Test",
        goal="Test",
        tone="formal",
    )

    assert "metadata" in result
    assert "confidence_score" in result["metadata"]
    assert result["metadata"]["confidence_score"] == 0.92


@pytest.mark.asyncio
async def test_draft_document_metadata_includes_confidence() -> None:
    """Test _draft_document metadata includes confidence score."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"title": "Doc", "body": "Content.", "sections": [{"heading": "S", "content": "C"}], "confidence": 0.75, "alternatives": []}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_document(
        document_type="brief",
        context="Test",
        goal="Test",
        tone="formal",
    )

    assert "metadata" in result
    assert result["metadata"]["confidence_score"] == 0.75


@pytest.mark.asyncio
async def test_draft_email_metadata_includes_alternatives() -> None:
    """Test _draft_email metadata includes alternatives from LLM."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello, body.", "tone_notes": "formal", "confidence": 0.8, "alternatives": [{"approach": "shorter version", "rationale": "more concise"}]}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    result = await agent._draft_email(
        recipient={"name": "Test"},
        context="Test",
        goal="Test",
        tone="formal",
    )

    assert len(result["metadata"]["alternatives"]) == 1
    assert result["metadata"]["alternatives"][0]["approach"] == "shorter version"


@pytest.mark.asyncio
async def test_explain_choices_returns_explanation() -> None:
    """Test _explain_choices returns a structured explanation."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    metadata = {
        "confidence_score": 0.85,
        "context_used": ["persona_builder", "exa_research"],
        "alternatives": [{"approach": "direct", "rationale": "shorter"}],
    }

    result = await agent._explain_choices(draft_metadata=metadata)

    assert "explanation" in result
    assert "style_references" in result
    assert "context_references" in result
    assert "persona_builder" in result["style_references"]
    assert "exa_research" in result["context_references"]
    assert "alternatives" in result


@pytest.mark.asyncio
async def test_explain_choices_with_question_calls_llm() -> None:
    """Test _explain_choices with a question makes an LLM call."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(return_value="The tone was chosen because the recipient is senior.")
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    metadata = {
        "confidence_score": 0.8,
        "context_used": ["persona_builder"],
        "alternatives": [],
    }

    result = await agent._explain_choices(
        draft_metadata=metadata,
        question="Why was this tone chosen?",
    )

    assert "answer" in result
    mock_llm.generate_response.assert_called_once()
    assert result["answer"] == "The tone was chosen because the recipient is senior."


@pytest.mark.asyncio
async def test_execute_propagates_metadata() -> None:
    """Test execute() propagates metadata from draft content to result_data."""
    from src.agents.scribe import ScribeAgent

    mock_llm = MagicMock()
    mock_llm.generate_response = AsyncMock(
        return_value='{"subject": "Test", "body": "Hello, body text here.", "tone_notes": "formal", "confidence": 0.85, "alternatives": []}'
    )
    agent = ScribeAgent(llm_client=mock_llm, user_id="user-123")

    task = {
        "communication_type": "email",
        "recipient": {"name": "Test"},
        "context": "Test context",
        "goal": "Test goal",
        "tone": "formal",
    }

    result = await agent.execute(task)

    assert result.success is True
    assert "metadata" in result.data
    assert "confidence_score" in result.data["metadata"]
