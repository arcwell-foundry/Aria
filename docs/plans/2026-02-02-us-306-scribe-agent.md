# US-306: Scribe Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Scribe agent for communication drafting that produces emails and documents matching the user's Digital Twin writing style.

**Architecture:** The ScribeAgent extends BaseAgent and implements communication drafting through four main tools: draft_email (compose emails with context), draft_document (longer-form content), personalize (adjust tone/style), and apply_template (use predefined templates). The execute method orchestrates drafting based on communication type, applies Digital Twin style matching when available, and returns drafts ready for user review. Multiple tone options (formal, friendly, urgent) and template support for common communications are included.

**Tech Stack:** Python 3.11+, async/await patterns, Pydantic for data models, unittest.mock for testing

---

## Acceptance Criteria Checklist

From PHASE_3_AGENTS.md US-306:

- [ ] `src/agents/scribe.py` extends BaseAgent
- [ ] Tools: draft_email, draft_document, personalize
- [ ] Uses Digital Twin for style matching
- [ ] Accepts: communication type, recipient, context, goal
- [ ] Returns: draft ready for user review
- [ ] Multiple tone options (formal, friendly, urgent)
- [ ] Template support for common communications
- [ ] Unit tests for drafting

---

## Data Models Reference

### DraftRequest (Communication Request)

```python
{
    "communication_type": str,        # "email", "document", "message"
    "recipient": dict | None,         # {"name": str, "title": str, "company": str} or None
    "context": str,                   # Background information for the draft
    "goal": str,                      # What this communication should achieve
    "tone": str,                      # "formal", "friendly", "urgent"
    "template_name": str | None,      # Optional template to use
    "max_length": int | None,         # Optional length constraint
}
```

### Email (Drafted)

```python
{
    "subject": str,
    "body": str,
    "recipient_name": str | None,
    "recipient_email": str | None,
    "tone": str,
    "word_count": int,
    "has_call_to_action": bool,
}
```

### Document (Drafted)

```python
{
    "title": str,
    "body": str,
    "sections": list[dict],           # {"heading": str, "content": str}
    "word_count": int,
    "document_type": str,             # "brief", "report", "proposal", etc.
}
```

### DraftResult (Agent Output)

```python
{
    "draft_type": str,                # "email" or "document"
    "content": Email | Document,      # The drafted content
    "style_applied": str | None,      # Digital Twin style used, if any
    "template_used": str | None,      # Template name if used
    "ready_for_review": bool,
}
```

---

### Task 1: Create Scribe Agent Skeleton with Basic Structure

**Files:**
- Create: `backend/src/agents/scribe.py`
- Create: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for ScribeAgent initialization**

Create `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.scribe'"

**Step 3: Write minimal implementation**

Create `backend/src/agents/scribe.py`:

```python
"""ScribeAgent module for ARIA.

Drafts emails and documents with style matching using Digital Twin.
"""

import logging
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult, BaseAgent

if TYPE_CHECKING:
    from src.core.llm import LLMClient

logger = logging.getLogger(__name__)


class ScribeAgent(BaseAgent):
    """Drafts emails and documents with style matching.

    The Scribe agent creates communications tailored to the user's
    writing style using Digital Twin, with support for multiple
    tones and templates.
    """

    name = "Scribe"
    description = "Drafts emails and documents with style matching"

    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Scribe agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._templates: dict[str, dict[str, Any]] = {}
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Scribe agent's drafting tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "draft_email": self._draft_email,
            "draft_document": self._draft_document,
            "personalize": self._personalize,
            "apply_template": self._apply_template,
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the scribe agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        return AgentResult(success=True, data={})

    async def _draft_email(
        self,
        recipient: dict[str, Any] | None = None,
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft an email.

        Args:
            recipient: Recipient information.
            context: Background context for the email.
            goal: What this email should achieve.
            tone: Tone of the email (formal, friendly, urgent).

        Returns:
            Drafted email with subject and body.
        """
        return {}

    async def _draft_document(
        self,
        document_type: str = "brief",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft a document.

        Args:
            document_type: Type of document (brief, report, proposal).
            context: Background context for the document.
            goal: What this document should achieve.
            tone: Tone of the document.

        Returns:
            Drafted document with title and body.
        """
        return {}

    async def _personalize(
        self,
        content: str,
        style: dict[str, Any] | None = None,
    ) -> str:
        """Personalize content to match a writing style.

        Args:
            content: The content to personalize.
            style: Style parameters from Digital Twin.

        Returns:
            Personalized content.
        """
        return content

    async def _apply_template(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> str:
        """Apply a template with variables.

        Args:
            template_name: Name of the template to use.
            variables: Variables to substitute in template.

        Returns:
            Rendered template content.
        """
        return ""
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): add ScribeAgent skeleton with tool registration"
```

---

### Task 2: Implement validate_input for Task Schema Validation

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for input validation**

Add to `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: Some tests pass (default True), some fail (need actual validation logic)

**Step 3: Write minimal implementation**

Add to `ScribeAgent` class in `backend/src/agents/scribe.py`:

```python
    # Valid communication types and tones
    VALID_COMMUNICATION_TYPES = {"email", "document", "message"}
    VALID_TONES = {"formal", "friendly", "urgent"}

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate draft task input.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required fields
        if "communication_type" not in task:
            return False

        if "goal" not in task:
            return False

        # Validate communication_type
        comm_type = task["communication_type"]
        if comm_type not in self.VALID_COMMUNICATION_TYPES:
            return False

        # Validate tone if present
        if "tone" in task:
            tone = task["tone"]
            if tone not in self.VALID_TONES:
                return False

        # Validate recipient if present
        if "recipient" in task and task["recipient"] is not None:
            recipient = task["recipient"]
            if not isinstance(recipient, dict):
                return False

        return True
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (12 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): add input validation to ScribeAgent"
```

---

### Task 3: Implement draft_email Tool

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for draft_email**

Add to `backend/tests/test_scribe_agent.py`:

```python
import pytest


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


from typing import Any
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_draft_email_returns_dict tests/test_scribe_agent.py::test_draft_email_has_subject_and_body tests/test_scribe_agent.py::test_draft_email_includes_recipient_name tests/test_scribe_agent.py::test_draft_email_formal_tone tests/test_scribe_agent.py::test_draft_email_friendly_tone tests/test_scribe_agent.py::test_draft_email_urgent_tone tests/test_scribe_agent.py::test_draft_email_includes_call_to_action tests/test_scribe_agent.py::test_draft_email_tracks_word_count tests/test_scribe_agent.py::test_draft_email_logs_drafting -v`

Expected: FAIL - current implementation returns empty dict

**Step 3: Write minimal implementation**

Replace `_draft_email` in `backend/src/agents/scribe.py`:

```python
    async def _draft_email(
        self,
        recipient: dict[str, Any] | None = None,
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft an email.

        This is a mock implementation that generates template-based emails.
        In production, this would use the LLM with Digital Twin style.

        Args:
            recipient: Recipient information with name, title, company.
            context: Background context for the email.
            goal: What this email should achieve.
            tone: Tone of the email (formal, friendly, urgent).

        Returns:
            Drafted email with subject, body, and metadata.
        """
        recipient_name = "there"
        recipient_company = ""
        if recipient:
            recipient_name = recipient.get("name", "there")
            recipient_company = recipient.get("company", "")

        logger.info(
            f"Drafting email to {recipient_name}",
            extra={
                "recipient": recipient_name,
                "tone": tone,
                "goal": goal[:50] if goal else "",
            },
        )

        # Generate greeting based on tone
        if tone == "formal":
            greeting = f"Dear {recipient_name},"
        elif tone == "friendly":
            greeting = f"Hi {recipient_name},"
        else:  # urgent
            greeting = f"Dear {recipient_name},"

        # Generate subject based on tone and goal
        if tone == "urgent":
            subject = f"Urgent: {goal[:50]}" if goal else "Urgent: Action Required"
        else:
            subject = goal[:60] if goal else "Follow-up"

        # Generate body
        context_line = f"\n\n{context}" if context else ""

        if tone == "urgent":
            urgency_note = "\n\nThis requires your immediate attention. Please respond as soon as possible."
        else:
            urgency_note = ""

        # Generate call to action
        cta = "\n\nPlease let me know your availability to discuss further."

        # Closing based on tone
        if tone == "formal":
            closing = "\n\nBest regards"
        elif tone == "friendly":
            closing = "\n\nThanks!"
        else:  # urgent
            closing = "\n\nThank you for your prompt attention to this matter."

        body = f"{greeting}{context_line}{urgency_note}{cta}{closing}"

        word_count = len(body.split())

        return {
            "subject": subject,
            "body": body,
            "recipient_name": recipient_name if recipient else None,
            "recipient_company": recipient_company if recipient_company else None,
            "tone": tone,
            "word_count": word_count,
            "has_call_to_action": True,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (21 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): implement draft_email tool with tone support"
```

---

### Task 4: Implement draft_document Tool

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for draft_document**

Add to `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_draft_document_returns_dict tests/test_scribe_agent.py::test_draft_document_has_title_and_body tests/test_scribe_agent.py::test_draft_document_includes_sections tests/test_scribe_agent.py::test_draft_document_brief_type tests/test_scribe_agent.py::test_draft_document_report_type tests/test_scribe_agent.py::test_draft_document_proposal_type tests/test_scribe_agent.py::test_draft_document_tracks_word_count tests/test_scribe_agent.py::test_draft_document_logs_drafting -v`

Expected: FAIL - current implementation returns empty dict

**Step 3: Write minimal implementation**

Replace `_draft_document` in `backend/src/agents/scribe.py`:

```python
    async def _draft_document(
        self,
        document_type: str = "brief",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Draft a document.

        This is a mock implementation that generates template-based documents.
        In production, this would use the LLM with Digital Twin style.

        Args:
            document_type: Type of document (brief, report, proposal).
            context: Background context for the document.
            goal: What this document should achieve.
            tone: Tone of the document.

        Returns:
            Drafted document with title, body, sections, and metadata.
        """
        logger.info(
            f"Drafting {document_type} document",
            extra={
                "document_type": document_type,
                "tone": tone,
                "goal": goal[:50] if goal else "",
            },
        )

        # Generate title from goal
        title = goal if goal else f"{document_type.capitalize()} Document"

        # Generate sections based on document type
        if document_type == "brief":
            sections = [
                {"heading": "Summary", "content": context if context else "Summary content here."},
                {"heading": "Key Points", "content": "• Point 1\n• Point 2\n• Point 3"},
            ]
        elif document_type == "report":
            sections = [
                {"heading": "Executive Summary", "content": context if context else "Executive summary."},
                {"heading": "Background", "content": "Background information and context."},
                {"heading": "Analysis", "content": "Detailed analysis of the situation."},
                {"heading": "Recommendations", "content": "Recommended actions moving forward."},
            ]
        elif document_type == "proposal":
            sections = [
                {"heading": "Introduction", "content": context if context else "Introduction to the proposal."},
                {"heading": "Proposed Solution", "content": "Details of the proposed solution."},
                {"heading": "Benefits", "content": "Expected benefits and outcomes."},
                {"heading": "Next Steps", "content": "Proposed next steps and timeline."},
            ]
        else:
            sections = [
                {"heading": "Content", "content": context if context else "Document content."},
            ]

        # Build body from sections
        body_parts = []
        for section in sections:
            body_parts.append(f"## {section['heading']}\n\n{section['content']}")
        body = "\n\n".join(body_parts)

        word_count = len(body.split())

        return {
            "title": title,
            "body": body,
            "sections": sections,
            "document_type": document_type,
            "word_count": word_count,
        }
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (29 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): implement draft_document tool with section support"
```

---

### Task 5: Implement personalize Tool with Digital Twin Support

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for personalize**

Add to `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_personalize_returns_string tests/test_scribe_agent.py::test_personalize_without_style_returns_content tests/test_scribe_agent.py::test_personalize_applies_casual_style tests/test_scribe_agent.py::test_personalize_applies_signature tests/test_scribe_agent.py::test_personalize_applies_greeting_preference tests/test_scribe_agent.py::test_personalize_logs_style_application -v`

Expected: Some PASS (returns content), some FAIL

**Step 3: Write minimal implementation**

Replace `_personalize` in `backend/src/agents/scribe.py`:

```python
    async def _personalize(
        self,
        content: str,
        style: dict[str, Any] | None = None,
    ) -> str:
        """Personalize content to match a writing style.

        Applies Digital Twin style parameters to the content.
        In production, this would use the LLM for more sophisticated style matching.

        Args:
            content: The content to personalize.
            style: Style parameters from Digital Twin containing:
                - formality: "formal", "casual"
                - contractions: bool
                - signature: str
                - preferred_greeting: str

        Returns:
            Personalized content matching the style.
        """
        if not style:
            return content

        logger.info(
            "Personalizing content with style",
            extra={"style_keys": list(style.keys())},
        )

        result = content

        # Apply greeting preference
        if "preferred_greeting" in style:
            preferred = style["preferred_greeting"]
            # Replace common greetings with preferred one
            greetings = ["Dear", "Hello", "Hi", "Hey"]
            for greeting in greetings:
                if result.startswith(f"{greeting} "):
                    result = result.replace(f"{greeting} ", f"{preferred} ", 1)
                    break

        # Apply signature
        if "signature" in style:
            sig = style["signature"]
            if sig not in result:
                result = f"{result}\n\n{sig}"

        return result
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (35 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): implement personalize tool with Digital Twin style support"
```

---

### Task 6: Implement apply_template Tool

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for apply_template**

Add to `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_apply_template_returns_string tests/test_scribe_agent.py::test_apply_template_substitutes_variables tests/test_scribe_agent.py::test_apply_template_unknown_template_returns_empty tests/test_scribe_agent.py::test_apply_template_handles_missing_variables tests/test_scribe_agent.py::test_apply_template_uses_builtin_templates tests/test_scribe_agent.py::test_apply_template_follow_up_email tests/test_scribe_agent.py::test_apply_template_meeting_request tests/test_scribe_agent.py::test_apply_template_logs_usage -v`

Expected: FAIL - current implementation returns empty string

**Step 3: Write minimal implementation**

First, update `__init__` to include built-in templates:

```python
    def __init__(self, llm_client: "LLMClient", user_id: str) -> None:
        """Initialize the Scribe agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._templates: dict[str, str] = self._get_builtin_templates()
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _get_builtin_templates(self) -> dict[str, str]:
        """Get built-in communication templates.

        Returns:
            Dictionary of template name to template string.
        """
        return {
            "follow_up_email": (
                "Hi {name},\n\n"
                "I wanted to follow up on {meeting_topic}. "
                "I hope you found our discussion valuable.\n\n"
                "Please let me know if you have any questions or would like to schedule a follow-up.\n\n"
                "Best regards"
            ),
            "meeting_request": (
                "Hi {name},\n\n"
                "I would like to schedule a meeting to {purpose}. "
                "Would you have time this week or next?\n\n"
                "Please let me know your availability.\n\n"
                "Best regards"
            ),
            "introduction": (
                "Hi {name},\n\n"
                "I'm {sender_name} from {company}. "
                "I'm reaching out because {reason}.\n\n"
                "I'd love to connect and discuss how we might work together.\n\n"
                "Best regards"
            ),
            "thank_you": (
                "Hi {name},\n\n"
                "Thank you for {reason}. "
                "I really appreciate your time and {detail}.\n\n"
                "Best regards"
            ),
        }
```

Then replace `_apply_template`:

```python
    async def _apply_template(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> str:
        """Apply a template with variables.

        Substitutes variables into a named template.

        Args:
            template_name: Name of the template to use.
            variables: Variables to substitute in template.

        Returns:
            Rendered template content, or empty string if template not found.
        """
        if template_name not in self._templates:
            logger.warning(f"Template not found: {template_name}")
            return ""

        logger.info(
            f"Applying template: {template_name}",
            extra={"template": template_name, "variables": list(variables.keys())},
        )

        template = self._templates[template_name]

        # Substitute variables
        try:
            # Use str.format with partial substitution support
            result = template
            for key, value in variables.items():
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value))
            return result
        except KeyError as e:
            logger.warning(f"Missing variable in template: {e}")
            return template
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (43 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): implement apply_template tool with built-in templates"
```

---

### Task 7: Implement execute Method (Full Orchestration)

**Files:**
- Modify: `backend/src/agents/scribe.py`
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write failing tests for execute**

Add to `backend/tests/test_scribe_agent.py`:

```python
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
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_execute_returns_agent_result tests/test_scribe_agent.py::test_execute_email_returns_email_draft tests/test_scribe_agent.py::test_execute_document_returns_document_draft tests/test_scribe_agent.py::test_execute_uses_template_when_specified tests/test_scribe_agent.py::test_execute_applies_style_when_provided tests/test_scribe_agent.py::test_execute_sets_ready_for_review tests/test_scribe_agent.py::test_execute_handles_message_type tests/test_scribe_agent.py::test_execute_success_flag -v`

Expected: FAIL - current execute returns empty dict

**Step 3: Write minimal implementation**

Replace `execute` method in `backend/src/agents/scribe.py`:

```python
    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the draft task.

        Orchestrates the full drafting workflow:
        1. Determine communication type
        2. Apply template if specified
        3. Draft the content
        4. Personalize with Digital Twin style
        5. Return draft ready for review

        Args:
            task: Task specification with:
                - communication_type: "email", "document", "message"
                - recipient: Optional recipient info
                - context: Background context
                - goal: What to achieve
                - tone: "formal", "friendly", "urgent"
                - template_name: Optional template to use
                - style: Optional Digital Twin style

        Returns:
            AgentResult with drafted content.
        """
        comm_type = task["communication_type"]
        recipient = task.get("recipient")
        context = task.get("context", "")
        goal = task.get("goal", "")
        tone = task.get("tone", "formal")
        template_name = task.get("template_name")
        style = task.get("style")

        logger.info(
            f"Starting draft for {comm_type}",
            extra={
                "communication_type": comm_type,
                "tone": tone,
                "has_template": template_name is not None,
                "has_style": style is not None,
            },
        )

        template_used = None
        style_applied = None

        try:
            # Handle email or message types
            if comm_type in ("email", "message"):
                # Use template if specified
                if template_name:
                    variables = {
                        "name": recipient.get("name", "there") if recipient else "there",
                        "meeting_topic": context,
                        "purpose": goal,
                        "reason": context,
                    }
                    content_body = await self._apply_template(template_name, variables)

                    if content_body:
                        template_used = template_name
                        content = {
                            "subject": goal[:60] if goal else "Follow-up",
                            "body": content_body,
                            "recipient_name": recipient.get("name") if recipient else None,
                            "tone": tone,
                            "word_count": len(content_body.split()),
                            "has_call_to_action": True,
                        }
                    else:
                        # Fallback to regular draft
                        content = await self._draft_email(
                            recipient=recipient,
                            context=context,
                            goal=goal,
                            tone=tone,
                        )
                else:
                    content = await self._draft_email(
                        recipient=recipient,
                        context=context,
                        goal=goal,
                        tone=tone,
                    )

                draft_type = "email"

            # Handle document type
            elif comm_type == "document":
                document_type = task.get("document_type", "brief")
                content = await self._draft_document(
                    document_type=document_type,
                    context=context,
                    goal=goal,
                    tone=tone,
                )
                draft_type = "document"

            else:
                # Fallback to email
                content = await self._draft_email(
                    recipient=recipient,
                    context=context,
                    goal=goal,
                    tone=tone,
                )
                draft_type = "email"

            # Apply personalization if style provided
            if style and "body" in content:
                content["body"] = await self._personalize(content["body"], style)
                style_applied = "custom"

            result_data = {
                "draft_type": draft_type,
                "content": content,
                "style_applied": style_applied,
                "template_used": template_used,
                "ready_for_review": True,
            }

            logger.info(
                f"Draft complete: {draft_type}",
                extra={
                    "draft_type": draft_type,
                    "word_count": content.get("word_count", 0),
                },
            )

            return AgentResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Draft failed: {e}", extra={"error": str(e)})
            return AgentResult(
                success=False,
                data={},
                error=str(e),
            )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (51 tests)

**Step 5: Commit**

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py
git commit -m "feat(agents): implement execute method with full orchestration"
```

---

### Task 8: Add Integration Test for Full Scribe Workflow

**Files:**
- Modify: `backend/tests/test_scribe_agent.py`

**Step 1: Write integration test**

Add to `backend/tests/test_scribe_agent.py`:

```python
@pytest.mark.asyncio
async def test_full_scribe_email_workflow() -> None:
    """Integration test demonstrating complete Scribe agent email workflow."""
    from src.agents.base import AgentStatus
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
```

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_scribe_agent.py::test_full_scribe_email_workflow tests/test_scribe_agent.py::test_full_scribe_document_workflow tests/test_scribe_agent.py::test_scribe_agent_handles_validation_failure tests/test_scribe_agent.py::test_scribe_with_template_and_style tests/test_scribe_agent.py::test_scribe_urgent_tone_workflow -v`

Expected: PASS

**Step 3: Run full test suite**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (56 tests)

**Step 4: Commit**

```bash
git add backend/tests/test_scribe_agent.py
git commit -m "test(agents): add integration tests for Scribe agent workflow"
```

---

### Task 9: Update Module Exports

**Files:**
- Modify: `backend/src/agents/__init__.py`

**Step 1: Add ScribeAgent to exports**

Update `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent
from src.agents.scribe import ScribeAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "AnalystAgent",
    "BaseAgent",
    "HunterAgent",
    "ScribeAgent",
]
```

**Step 2: Verify exports work**

Run: `cd backend && python -c "from src.agents import ScribeAgent; print(ScribeAgent.name)"`

Expected output: "Scribe"

**Step 3: Commit**

```bash
git add backend/src/agents/__init__.py
git commit -m "feat(agents): export ScribeAgent from agents module"
```

---

### Task 10: Run Quality Gates and Fix Issues

**Files:**
- Verify: All quality gates pass

**Step 1: Run type checking**

Run: `cd backend && mypy src/agents/scribe.py --strict`

If mypy reports issues:
- Fix missing type annotations
- Add `from __future__ import annotations` if needed
- Fix any `Any` usage that should be more specific

**Step 2: Run linting**

Run: `cd backend && ruff check src/agents/scribe.py`

If ruff reports issues:
- Fix import ordering
- Fix line length issues
- Fix any linting violations

**Step 3: Run formatting**

Run: `cd backend && ruff format src/agents/scribe.py`

**Step 4: Run all Scribe tests**

Run: `cd backend && pytest tests/test_scribe_agent.py -v`

Expected: PASS (56 tests)

**Step 5: Run full backend test suite to ensure no regressions**

Run: `cd backend && pytest tests/ -v`

Expected: All tests pass

**Step 6: Fix any issues and commit**

If any issues were found and fixed:

```bash
git add backend/src/agents/scribe.py backend/tests/test_scribe_agent.py backend/src/agents/__init__.py
git commit -m "style(agents): fix quality gate issues in Scribe agent"
```

---

## Summary

This plan implements US-306: Scribe Agent with the following components:

1. **ScribeAgent class** - Extends BaseAgent with communication drafting capabilities
2. **Input validation** - Ensures task has communication_type, goal, and valid tone
3. **Four core tools**:
   - `draft_email`: Compose emails with tone-appropriate greetings and CTAs
   - `draft_document`: Create structured documents (brief, report, proposal)
   - `personalize`: Apply Digital Twin style parameters to content
   - `apply_template`: Use built-in templates for common communications
4. **Built-in templates** - follow_up_email, meeting_request, introduction, thank_you
5. **Full orchestration** via `execute()` - Routes to appropriate tool, applies style
6. **Comprehensive tests** - 56 tests covering all functionality
7. **Quality gates** - mypy strict, ruff linting, and formatting

The agent is ready for production integration with the LLM for more sophisticated drafting by replacing the mock implementations. Digital Twin integration requires connecting to the existing Digital Twin service for actual style extraction.

All code follows the project's patterns:
- Async-first with proper type hints
- Logging instead of print
- Comprehensive docstrings
- TDD approach with tests before implementation
- YAGNI - only what's needed for the US
- DRY - shared template logic, reusable personalization
