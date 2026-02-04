# US-505: Conversation Intelligence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an LLM-powered service that extracts actionable insights (objections, buying signals, commitments, risks, opportunities) from lead events.

**Architecture:** The ConversationIntelligence class analyzes LeadEvent instances using Claude to extract structured insights. Insights are stored in the existing `lead_memory_insights` Supabase table with confidence scoring and source event linking. The service supports both single-event analysis and batch retroactive processing.

**Tech Stack:** Python 3.11, FastAPI async patterns, Anthropic Claude API (via existing LLMClient), Supabase (existing table), Pydantic models (existing InsightType enum)

---

## Task 1: Create Insight Dataclass

**Files:**
- Create: `backend/src/memory/conversation_intelligence.py`
- Reference: `backend/src/memory/lead_memory_events.py:73-184` (dataclass pattern)
- Reference: `backend/src/models/lead_memory.py:49-55` (InsightType enum)

**Step 1: Write the failing test**

Create test file `backend/tests/test_conversation_intelligence.py`:

```python
"""Tests for ConversationIntelligence and Insight dataclass.

This module tests the conversation intelligence service that extracts
actionable insights from lead events using LLM analysis.
"""

from datetime import UTC, datetime

import pytest

from src.memory.conversation_intelligence import Insight
from src.models.lead_memory import InsightType


class TestInsightDataclass:
    """Tests for the Insight dataclass."""

    def test_insight_creation_all_fields(self):
        """Test creating an Insight with all fields populated."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        insight = Insight(
            id="insight-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.OBJECTION,
            content="Concerned about implementation timeline",
            confidence=0.85,
            source_event_id="event-789",
            detected_at=detected_at,
            addressed_at=None,
            addressed_by=None,
        )

        assert insight.id == "insight-123"
        assert insight.lead_memory_id == "lead-456"
        assert insight.insight_type == InsightType.OBJECTION
        assert insight.content == "Concerned about implementation timeline"
        assert insight.confidence == 0.85
        assert insight.source_event_id == "event-789"
        assert insight.detected_at == detected_at
        assert insight.addressed_at is None
        assert insight.addressed_by is None

    def test_insight_creation_minimal_fields(self):
        """Test creating an Insight without optional source_event_id."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        insight = Insight(
            id="insight-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.BUYING_SIGNAL,
            content="Asked about pricing tiers",
            confidence=0.75,
            source_event_id=None,
            detected_at=detected_at,
            addressed_at=None,
            addressed_by=None,
        )

        assert insight.source_event_id is None
        assert insight.insight_type == InsightType.BUYING_SIGNAL
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestInsightDataclass -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.memory.conversation_intelligence'"

**Step 3: Write minimal implementation**

Create `backend/src/memory/conversation_intelligence.py`:

```python
"""Conversation intelligence for extracting insights from lead events.

This module provides LLM-powered analysis of lead events to extract
actionable insights including objections, buying signals, commitments,
risks, and opportunities.

Usage:
    ```python
    from src.memory.conversation_intelligence import ConversationIntelligence, Insight
    from src.models.lead_memory import InsightType

    # Initialize service
    service = ConversationIntelligence()

    # Analyze an event
    insights = await service.analyze_event(
        user_id="user-123",
        lead_memory_id="lead-456",
        event=lead_event,
    )

    # Mark an insight as addressed
    await service.mark_addressed(
        user_id="user-123",
        insight_id="insight-789",
    )
    ```
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from supabase import Client

from src.models.lead_memory import InsightType

logger = logging.getLogger(__name__)


@dataclass
class Insight:
    """A domain model representing an extracted insight from a lead event.

    Insights capture actionable intelligence from conversations and
    interactions, including objections, buying signals, commitments,
    risks, and opportunities.

    Attributes:
        id: Unique identifier for this insight.
        lead_memory_id: ID of the lead memory this insight belongs to.
        insight_type: The category of insight (objection, buying_signal, etc.).
        content: The extracted insight content.
        confidence: Confidence score from 0.0 to 1.0.
        source_event_id: Optional ID of the event that generated this insight.
        detected_at: When this insight was detected.
        addressed_at: When this insight was marked as addressed (if applicable).
        addressed_by: User ID who addressed the insight (if applicable).
    """

    id: str
    lead_memory_id: str
    insight_type: InsightType
    content: str
    confidence: float
    source_event_id: str | None
    detected_at: datetime
    addressed_at: datetime | None
    addressed_by: str | None

    def to_dict(self) -> dict[str, object]:
        """Serialize the insight to a dictionary.

        Converts the insight to a dictionary suitable for JSON serialization,
        with datetime fields converted to ISO format strings.

        Returns:
            Dictionary representation of the insight.
        """
        return {
            "id": self.id,
            "lead_memory_id": self.lead_memory_id,
            "insight_type": self.insight_type.value,
            "content": self.content,
            "confidence": self.confidence,
            "source_event_id": self.source_event_id,
            "detected_at": self.detected_at.isoformat(),
            "addressed_at": self.addressed_at.isoformat() if self.addressed_at else None,
            "addressed_by": self.addressed_by,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Insight:
        """Create an Insight from a dictionary.

        Deserializes a dictionary back into an Insight instance,
        handling both ISO format strings and datetime objects.

        Args:
            data: Dictionary containing insight data.

        Returns:
            An Insight instance with restored state.
        """
        # Parse detected_at - handle both string and datetime
        detected_at_raw = data["detected_at"]
        if isinstance(detected_at_raw, str):
            detected_at = datetime.fromisoformat(detected_at_raw)
        else:
            detected_at = cast(datetime, detected_at_raw)

        # Parse addressed_at - handle both string and datetime
        addressed_at_raw = data.get("addressed_at")
        addressed_at: datetime | None = None
        if addressed_at_raw is not None:
            if isinstance(addressed_at_raw, str):
                addressed_at = datetime.fromisoformat(addressed_at_raw)
            else:
                addressed_at = cast(datetime, addressed_at_raw)

        # Parse insight_type - handle both string and InsightType enum
        insight_type_raw = data["insight_type"]
        if isinstance(insight_type_raw, str):
            insight_type = InsightType(insight_type_raw)
        else:
            insight_type = cast(InsightType, insight_type_raw)

        return cls(
            id=cast(str, data["id"]),
            lead_memory_id=cast(str, data["lead_memory_id"]),
            insight_type=insight_type,
            content=cast(str, data["content"]),
            confidence=cast(float, data["confidence"]),
            source_event_id=cast(str | None, data.get("source_event_id")),
            detected_at=detected_at,
            addressed_at=addressed_at,
            addressed_by=cast(str | None, data.get("addressed_by")),
        )
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestInsightDataclass -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): add Insight dataclass for conversation intelligence"
```

---

## Task 2: Add Insight Serialization Tests

**Files:**
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
    def test_insight_to_dict(self):
        """Test serialization to dict with all fields."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        addressed_at = datetime(2025, 2, 4, 10, 0, tzinfo=UTC)

        insight = Insight(
            id="insight-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.COMMITMENT,
            content="They agreed to schedule a demo next week",
            confidence=0.92,
            source_event_id="event-789",
            detected_at=detected_at,
            addressed_at=addressed_at,
            addressed_by="user-abc",
        )

        result = insight.to_dict()

        assert result["id"] == "insight-123"
        assert result["lead_memory_id"] == "lead-456"
        assert result["insight_type"] == "commitment"
        assert result["content"] == "They agreed to schedule a demo next week"
        assert result["confidence"] == 0.92
        assert result["source_event_id"] == "event-789"
        assert result["detected_at"] == "2025-02-03T14:30:00+00:00"
        assert result["addressed_at"] == "2025-02-04T10:00:00+00:00"
        assert result["addressed_by"] == "user-abc"

    def test_insight_to_dict_with_none_values(self):
        """Test serialization to dict with None values."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        insight = Insight(
            id="insight-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.RISK,
            content="Budget freeze mentioned",
            confidence=0.65,
            source_event_id=None,
            detected_at=detected_at,
            addressed_at=None,
            addressed_by=None,
        )

        result = insight.to_dict()

        assert result["source_event_id"] is None
        assert result["addressed_at"] is None
        assert result["addressed_by"] is None

    def test_insight_from_dict(self):
        """Test deserialization from dict with all fields."""
        data = {
            "id": "insight-123",
            "lead_memory_id": "lead-456",
            "insight_type": "opportunity",
            "content": "They mentioned expanding to new regions",
            "confidence": 0.88,
            "source_event_id": "event-789",
            "detected_at": "2025-02-03T14:30:00+00:00",
            "addressed_at": "2025-02-04T10:00:00+00:00",
            "addressed_by": "user-abc",
        }

        insight = Insight.from_dict(data)

        assert insight.id == "insight-123"
        assert insight.lead_memory_id == "lead-456"
        assert insight.insight_type == InsightType.OPPORTUNITY
        assert insight.content == "They mentioned expanding to new regions"
        assert insight.confidence == 0.88
        assert insight.source_event_id == "event-789"
        assert insight.detected_at == datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        assert insight.addressed_at == datetime(2025, 2, 4, 10, 0, tzinfo=UTC)
        assert insight.addressed_by == "user-abc"

    def test_insight_from_dict_with_none_values(self):
        """Test deserialization from dict with None values."""
        data = {
            "id": "insight-123",
            "lead_memory_id": "lead-456",
            "insight_type": "buying_signal",
            "content": "Asked about contract terms",
            "confidence": 0.72,
            "source_event_id": None,
            "detected_at": "2025-02-03T14:30:00+00:00",
            "addressed_at": None,
            "addressed_by": None,
        }

        insight = Insight.from_dict(data)

        assert insight.source_event_id is None
        assert insight.addressed_at is None
        assert insight.addressed_by is None

    def test_insight_from_dict_with_datetime_objects(self):
        """Test deserialization when datetime fields are already datetime objects."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)
        addressed_at = datetime(2025, 2, 4, 10, 0, tzinfo=UTC)

        data = {
            "id": "insight-123",
            "lead_memory_id": "lead-456",
            "insight_type": InsightType.OBJECTION,
            "content": "Pricing concerns",
            "confidence": 0.80,
            "source_event_id": "event-789",
            "detected_at": detected_at,
            "addressed_at": addressed_at,
            "addressed_by": "user-abc",
        }

        insight = Insight.from_dict(data)

        assert insight.detected_at == detected_at
        assert insight.addressed_at == addressed_at

    def test_round_trip_serialization(self):
        """Test that to_dict and from_dict preserve all data."""
        detected_at = datetime(2025, 2, 3, 14, 30, tzinfo=UTC)

        original = Insight(
            id="insight-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.COMMITMENT,
            content="Committed to pilot program",
            confidence=0.95,
            source_event_id="event-789",
            detected_at=detected_at,
            addressed_at=None,
            addressed_by=None,
        )

        # Serialize and deserialize
        dict_data = original.to_dict()
        restored = Insight.from_dict(dict_data)

        # Check all fields match
        assert restored.id == original.id
        assert restored.lead_memory_id == original.lead_memory_id
        assert restored.insight_type == original.insight_type
        assert restored.content == original.content
        assert restored.confidence == original.confidence
        assert restored.source_event_id == original.source_event_id
        assert restored.detected_at == original.detected_at
        assert restored.addressed_at == original.addressed_at
        assert restored.addressed_by == original.addressed_by
```

**Step 2: Run test to verify they pass**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestInsightDataclass -v`
Expected: PASS (implementation already exists from Task 1)

**Step 3: Commit**

```bash
git add backend/tests/test_conversation_intelligence.py
git commit -m "test(lead-memory): add Insight serialization tests"
```

---

## Task 3: Add ConversationIntelligence Service Skeleton

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
from unittest.mock import MagicMock

from src.memory.conversation_intelligence import ConversationIntelligence, Insight


class TestConversationIntelligenceService:
    """Tests for the ConversationIntelligence service class."""

    def test_service_initialization(self):
        """Test that ConversationIntelligence can be instantiated."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)
        assert service is not None
        assert service.db == mock_client
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService::test_service_initialization -v`
Expected: FAIL with "ImportError" or "AttributeError"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/conversation_intelligence.py` after the Insight class:

```python
class ConversationIntelligence:
    """Service for extracting insights from lead events using LLM.

    Provides async interface for analyzing lead events and extracting
    actionable insights. Insights are stored in Supabase with links
    to their source events.
    """

    def __init__(self, db_client: Client) -> None:
        """Initialize the conversation intelligence service.

        Args:
            db_client: Supabase client for database operations.
        """
        self.db = db_client
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService::test_service_initialization -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): add ConversationIntelligence service skeleton"
```

---

## Task 4: Add LLM Prompt Template

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
    def test_build_analysis_prompt_email(self):
        """Test prompt building for email events."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import Direction, EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        event = LeadEvent(
            id="event-123",
            lead_memory_id="lead-456",
            event_type=EventType.EMAIL_RECEIVED,
            direction=Direction.INBOUND,
            subject="Re: Proposal",
            content="We love the proposal but the timeline seems aggressive. Can we discuss alternatives?",
            participants=["john@acme.com"],
            occurred_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
            source="gmail",
            source_id="msg-abc",
            created_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
        )

        prompt = service._build_analysis_prompt(event)

        assert "email_received" in prompt
        assert "Re: Proposal" in prompt
        assert "timeline seems aggressive" in prompt
        assert "objections" in prompt.lower()
        assert "buying signals" in prompt.lower()
        assert "commitments" in prompt.lower()
        assert "risks" in prompt.lower()
        assert "opportunities" in prompt.lower()
        assert "JSON" in prompt
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService::test_build_analysis_prompt_email -v`
Expected: FAIL with "AttributeError: 'ConversationIntelligence' object has no attribute '_build_analysis_prompt'"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    # Import at top of file
    from src.memory.lead_memory_events import LeadEvent

    def _build_analysis_prompt(self, event: LeadEvent) -> str:
        """Build the LLM prompt for analyzing a lead event.

        Args:
            event: The LeadEvent to analyze.

        Returns:
            Prompt string for the LLM.
        """
        content = event.content or ""
        subject = event.subject or "(no subject)"

        return f"""Analyze this {event.event_type.value} and extract actionable sales insights.

Event Type: {event.event_type.value}
Direction: {event.direction.value if event.direction else "N/A"}
Subject: {subject}
Content: {content}

Extract the following types of insights if present:

1. **Objections**: Any concerns, pushback, or hesitations raised
2. **Buying Signals**: Indications of readiness or interest to proceed
3. **Commitments**: Promises or agreements made by either party
4. **Risks**: Potential threats to the deal or relationship
5. **Opportunities**: Chances to advance the deal or expand scope

For each insight found, provide:
- type: one of "objection", "buying_signal", "commitment", "risk", "opportunity"
- content: A clear, concise description of the insight
- confidence: A score from 0.0 to 1.0 indicating how confident you are

Return a JSON array of insights. If no insights are found, return an empty array [].

Example response:
[
  {{"type": "objection", "content": "Concerned about implementation timeline", "confidence": 0.85}},
  {{"type": "buying_signal", "content": "Asked about contract terms", "confidence": 0.75}}
]

Important:
- Only extract insights that are clearly present in the content
- Be conservative with confidence scores
- Focus on actionable intelligence for sales teams
- Keep content descriptions concise but specific

Respond with ONLY the JSON array, no additional text."""
```

Update the imports at the top of the file:

```python
from src.memory.lead_memory_events import LeadEvent
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService::test_build_analysis_prompt_email -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): add LLM prompt template for insight extraction"
```

---

## Task 5: Add LLM Response Parsing

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
    def test_parse_llm_response_valid(self):
        """Test parsing valid LLM JSON response."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        llm_response = """[
            {"type": "objection", "content": "Timeline concerns", "confidence": 0.85},
            {"type": "buying_signal", "content": "Asked about pricing", "confidence": 0.75}
        ]"""

        insights = service._parse_llm_response(llm_response)

        assert len(insights) == 2
        assert insights[0]["type"] == "objection"
        assert insights[0]["content"] == "Timeline concerns"
        assert insights[0]["confidence"] == 0.85
        assert insights[1]["type"] == "buying_signal"

    def test_parse_llm_response_empty_array(self):
        """Test parsing empty array response."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        llm_response = "[]"
        insights = service._parse_llm_response(llm_response)

        assert insights == []

    def test_parse_llm_response_with_markdown(self):
        """Test parsing response wrapped in markdown code block."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        llm_response = """```json
[{"type": "risk", "content": "Budget freeze", "confidence": 0.70}]
```"""

        insights = service._parse_llm_response(llm_response)

        assert len(insights) == 1
        assert insights[0]["type"] == "risk"

    def test_parse_llm_response_invalid_json(self):
        """Test parsing invalid JSON returns empty list."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        llm_response = "This is not valid JSON"
        insights = service._parse_llm_response(llm_response)

        assert insights == []

    def test_parse_llm_response_filters_invalid_types(self):
        """Test that invalid insight types are filtered out."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        llm_response = """[
            {"type": "objection", "content": "Valid", "confidence": 0.85},
            {"type": "invalid_type", "content": "Invalid", "confidence": 0.75},
            {"type": "commitment", "content": "Also valid", "confidence": 0.80}
        ]"""

        insights = service._parse_llm_response(llm_response)

        assert len(insights) == 2
        assert insights[0]["type"] == "objection"
        assert insights[1]["type"] == "commitment"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService::test_parse_llm_response_valid -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    import json
    import re

    # Valid insight types (must match InsightType enum values)
    VALID_INSIGHT_TYPES = {"objection", "buying_signal", "commitment", "risk", "opportunity"}

    def _parse_llm_response(self, response: str) -> list[dict[str, Any]]:
        """Parse the LLM response JSON into insight dictionaries.

        Handles common LLM response formatting issues like markdown
        code blocks and validates insight types.

        Args:
            response: Raw LLM response string.

        Returns:
            List of validated insight dictionaries.
        """
        # Strip markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            # Remove opening ```json or ``` and closing ```
            lines = cleaned.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)

        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON", extra={"response": response[:200]})
            return []

        if not isinstance(parsed, list):
            logger.warning("LLM response is not a list", extra={"response_type": type(parsed).__name__})
            return []

        # Filter to valid insight types
        valid_insights = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            insight_type = item.get("type")
            if insight_type not in self.VALID_INSIGHT_TYPES:
                logger.debug("Skipping invalid insight type", extra={"type": insight_type})
                continue
            valid_insights.append(item)

        return valid_insights
```

Add `import json` and `import re` to the imports at the top of the file.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestConversationIntelligenceService -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): add LLM response parsing with validation"
```

---

## Task 6: Implement analyze_event Method

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


class TestAnalyzeEvent:
    """Tests for the analyze_event method."""

    @pytest.mark.asyncio
    async def test_analyze_event_extracts_insights(self):
        """Test that analyze_event extracts and stores insights."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import Direction, EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        event = LeadEvent(
            id="event-123",
            lead_memory_id="lead-456",
            event_type=EventType.EMAIL_RECEIVED,
            direction=Direction.INBOUND,
            subject="Re: Demo",
            content="Great demo! We're concerned about pricing but ready to move forward.",
            participants=["john@acme.com"],
            occurred_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
            source="gmail",
            source_id="msg-abc",
            created_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
        )

        # Mock LLM response
        mock_llm = AsyncMock()
        mock_llm.generate_response.return_value = """[
            {"type": "objection", "content": "Pricing concerns", "confidence": 0.80},
            {"type": "buying_signal", "content": "Ready to move forward", "confidence": 0.90}
        ]"""

        # Mock database insert
        mock_response = MagicMock()
        mock_response.data = [
            {"id": "insight-1", "detected_at": "2025-02-03T14:30:00+00:00"},
            {"id": "insight-2", "detected_at": "2025-02-03T14:30:00+00:00"},
        ]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch("src.memory.conversation_intelligence.LLMClient", return_value=mock_llm):
            insights = await service.analyze_event(
                user_id="user-123",
                lead_memory_id="lead-456",
                event=event,
            )

        assert len(insights) == 2
        assert insights[0].insight_type == InsightType.OBJECTION
        assert insights[0].content == "Pricing concerns"
        assert insights[0].confidence == 0.80
        assert insights[1].insight_type == InsightType.BUYING_SIGNAL

    @pytest.mark.asyncio
    async def test_analyze_event_returns_empty_for_no_insights(self):
        """Test that analyze_event returns empty list when no insights found."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        event = LeadEvent(
            id="event-123",
            lead_memory_id="lead-456",
            event_type=EventType.NOTE,
            direction=None,
            subject=None,
            content="Internal note: need to follow up",
            participants=[],
            occurred_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
            source=None,
            source_id=None,
            created_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
        )

        # Mock LLM response with no insights
        mock_llm = AsyncMock()
        mock_llm.generate_response.return_value = "[]"

        with patch("src.memory.conversation_intelligence.LLMClient", return_value=mock_llm):
            insights = await service.analyze_event(
                user_id="user-123",
                lead_memory_id="lead-456",
                event=event,
            )

        assert insights == []

    @pytest.mark.asyncio
    async def test_analyze_event_links_source_event(self):
        """Test that insights are linked to source event."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        event = LeadEvent(
            id="event-789",
            lead_memory_id="lead-456",
            event_type=EventType.CALL,
            direction=None,
            subject="Discovery call",
            content="They committed to a pilot next month",
            participants=["john@acme.com"],
            occurred_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
            source="zoom",
            source_id="call-123",
            created_at=datetime(2025, 2, 3, 14, 30, tzinfo=UTC),
        )

        mock_llm = AsyncMock()
        mock_llm.generate_response.return_value = """[
            {"type": "commitment", "content": "Pilot next month", "confidence": 0.95}
        ]"""

        mock_response = MagicMock()
        mock_response.data = [{"id": "insight-1", "detected_at": "2025-02-03T14:30:00+00:00"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch("src.memory.conversation_intelligence.LLMClient", return_value=mock_llm):
            insights = await service.analyze_event(
                user_id="user-123",
                lead_memory_id="lead-456",
                event=event,
            )

        # Verify the insert was called with source_event_id
        insert_call = mock_client.table.return_value.insert.call_args
        assert insert_call is not None
        inserted_data = insert_call[0][0]
        assert isinstance(inserted_data, list)
        assert inserted_data[0]["source_event_id"] == "event-789"
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestAnalyzeEvent::test_analyze_event_extracts_insights -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    import uuid

    async def analyze_event(
        self,
        user_id: str,
        lead_memory_id: str,
        event: LeadEvent,
    ) -> list[Insight]:
        """Analyze a lead event and extract insights using LLM.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            event: The LeadEvent to analyze.

        Returns:
            List of extracted Insight instances.

        Raises:
            DatabaseError: If storage fails.
        """
        from src.core.exceptions import DatabaseError
        from src.core.llm import LLMClient

        # Build prompt and call LLM
        prompt = self._build_analysis_prompt(event)
        llm = LLMClient()

        try:
            response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for more consistent extraction
            )
        except Exception as e:
            logger.exception("LLM call failed during event analysis")
            raise DatabaseError(f"LLM analysis failed: {e}") from e

        # Parse response
        raw_insights = self._parse_llm_response(response)

        if not raw_insights:
            return []

        # Convert to database records
        now = datetime.now(UTC)
        records = []
        for raw in raw_insights:
            records.append({
                "id": str(uuid.uuid4()),
                "lead_memory_id": lead_memory_id,
                "insight_type": raw["type"],
                "content": raw["content"],
                "confidence": raw.get("confidence", 0.7),
                "source_event_id": event.id,
                "detected_at": now.isoformat(),
            })

        # Store in database
        try:
            response = self.db.table("lead_memory_insights").insert(records).execute()

            if not response.data:
                raise DatabaseError("Failed to insert insights")

            # Convert to Insight instances
            insights = []
            for i, record in enumerate(response.data):
                record_dict = cast(dict[str, Any], record)
                # Merge our local data with DB response
                insight_data = {
                    "id": record_dict.get("id", records[i]["id"]),
                    "lead_memory_id": lead_memory_id,
                    "insight_type": records[i]["insight_type"],
                    "content": records[i]["content"],
                    "confidence": records[i]["confidence"],
                    "source_event_id": records[i]["source_event_id"],
                    "detected_at": record_dict.get("detected_at", records[i]["detected_at"]),
                    "addressed_at": None,
                    "addressed_by": None,
                }
                insights.append(Insight.from_dict(insight_data))

            logger.info(
                "Extracted insights from event",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "event_id": event.id,
                    "insight_count": len(insights),
                },
            )

            return insights

        except DatabaseError:
            raise
        except Exception as e:
            logger.exception("Failed to store insights")
            raise DatabaseError(f"Failed to store insights: {e}") from e
```

Add `import uuid` to the imports at the top of the file.

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestAnalyzeEvent -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): implement analyze_event with LLM extraction"
```

---

## Task 7: Implement mark_addressed Method

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
class TestMarkAddressed:
    """Tests for the mark_addressed method."""

    @pytest.mark.asyncio
    async def test_mark_addressed_success(self):
        """Test marking an insight as addressed."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [{"id": "insight-123", "addressed_at": "2025-02-04T10:00:00+00:00"}]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        result = await service.mark_addressed(
            user_id="user-123",
            insight_id="insight-123",
        )

        assert result is True
        mock_client.table.assert_called_with("lead_memory_insights")
        mock_client.table.return_value.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_mark_addressed_not_found(self):
        """Test marking non-existent insight returns False."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = []
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = mock_response

        result = await service.mark_addressed(
            user_id="user-123",
            insight_id="nonexistent-id",
        )

        assert result is False
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestMarkAddressed -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    async def mark_addressed(
        self,
        user_id: str,
        insight_id: str,
    ) -> bool:
        """Mark an insight as addressed.

        Args:
            user_id: The user marking the insight.
            insight_id: The ID of the insight to mark.

        Returns:
            True if the insight was found and updated, False otherwise.

        Raises:
            DatabaseError: If the update fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            now = datetime.now(UTC)
            response = (
                self.db.table("lead_memory_insights")
                .update({
                    "addressed_at": now.isoformat(),
                    "addressed_by": user_id,
                })
                .eq("id", insight_id)
                .execute()
            )

            if not response.data:
                logger.info(
                    "Insight not found for marking addressed",
                    extra={"user_id": user_id, "insight_id": insight_id},
                )
                return False

            logger.info(
                "Marked insight as addressed",
                extra={
                    "user_id": user_id,
                    "insight_id": insight_id,
                },
            )
            return True

        except Exception as e:
            logger.exception("Failed to mark insight as addressed")
            raise DatabaseError(f"Failed to mark insight as addressed: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestMarkAddressed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): implement mark_addressed method"
```

---

## Task 8: Implement Batch Analysis for Retroactive Processing

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
class TestBatchAnalysis:
    """Tests for the analyze_batch method."""

    @pytest.mark.asyncio
    async def test_analyze_batch_multiple_events(self):
        """Test batch analysis of multiple events."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import Direction, EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        events = [
            LeadEvent(
                id="event-1",
                lead_memory_id="lead-456",
                event_type=EventType.EMAIL_SENT,
                direction=Direction.OUTBOUND,
                subject="Proposal",
                content="Here's our proposal for your review.",
                participants=["john@acme.com"],
                occurred_at=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
                source="gmail",
                source_id="msg-1",
                created_at=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
            ),
            LeadEvent(
                id="event-2",
                lead_memory_id="lead-456",
                event_type=EventType.EMAIL_RECEIVED,
                direction=Direction.INBOUND,
                subject="Re: Proposal",
                content="Looks good! But we need to discuss pricing.",
                participants=["john@acme.com"],
                occurred_at=datetime(2025, 2, 2, 14, 0, tzinfo=UTC),
                source="gmail",
                source_id="msg-2",
                created_at=datetime(2025, 2, 2, 14, 0, tzinfo=UTC),
            ),
        ]

        # Mock LLM to return different insights for each event
        mock_llm = AsyncMock()
        mock_llm.generate_response.side_effect = [
            "[]",  # No insights for first event
            '[{"type": "buying_signal", "content": "Positive response", "confidence": 0.85}]',
        ]

        # Mock database insert
        mock_response = MagicMock()
        mock_response.data = [{"id": "insight-1", "detected_at": "2025-02-02T14:00:00+00:00"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch("src.memory.conversation_intelligence.LLMClient", return_value=mock_llm):
            results = await service.analyze_batch(
                user_id="user-123",
                lead_memory_id="lead-456",
                events=events,
            )

        assert len(results) == 2
        assert len(results["event-1"]) == 0
        assert len(results["event-2"]) == 1
        assert results["event-2"][0].insight_type == InsightType.BUYING_SIGNAL

    @pytest.mark.asyncio
    async def test_analyze_batch_empty_events(self):
        """Test batch analysis with no events."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        results = await service.analyze_batch(
            user_id="user-123",
            lead_memory_id="lead-456",
            events=[],
        )

        assert results == {}

    @pytest.mark.asyncio
    async def test_analyze_batch_continues_on_error(self):
        """Test that batch analysis continues even if one event fails."""
        from src.memory.lead_memory_events import LeadEvent
        from src.models.lead_memory import EventType

        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        events = [
            LeadEvent(
                id="event-1",
                lead_memory_id="lead-456",
                event_type=EventType.NOTE,
                direction=None,
                subject=None,
                content="First note",
                participants=[],
                occurred_at=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
                source=None,
                source_id=None,
                created_at=datetime(2025, 2, 1, 10, 0, tzinfo=UTC),
            ),
            LeadEvent(
                id="event-2",
                lead_memory_id="lead-456",
                event_type=EventType.NOTE,
                direction=None,
                subject=None,
                content="Second note with commitment",
                participants=[],
                occurred_at=datetime(2025, 2, 2, 10, 0, tzinfo=UTC),
                source=None,
                source_id=None,
                created_at=datetime(2025, 2, 2, 10, 0, tzinfo=UTC),
            ),
        ]

        # First call fails, second succeeds
        mock_llm = AsyncMock()
        mock_llm.generate_response.side_effect = [
            Exception("API error"),
            '[{"type": "commitment", "content": "Agreed to pilot", "confidence": 0.90}]',
        ]

        mock_response = MagicMock()
        mock_response.data = [{"id": "insight-1", "detected_at": "2025-02-02T10:00:00+00:00"}]
        mock_client.table.return_value.insert.return_value.execute.return_value = mock_response

        with patch("src.memory.conversation_intelligence.LLMClient", return_value=mock_llm):
            results = await service.analyze_batch(
                user_id="user-123",
                lead_memory_id="lead-456",
                events=events,
            )

        # First event should have empty list due to error, second should succeed
        assert len(results) == 2
        assert results["event-1"] == []
        assert len(results["event-2"]) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestBatchAnalysis -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    async def analyze_batch(
        self,
        user_id: str,
        lead_memory_id: str,
        events: list[LeadEvent],
    ) -> dict[str, list[Insight]]:
        """Analyze multiple lead events for retroactive insight extraction.

        Processes events sequentially, continuing even if individual events
        fail. This is useful for backfilling insights on historical data.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            events: List of LeadEvents to analyze.

        Returns:
            Dictionary mapping event IDs to their extracted insights.
            Events that fail analysis will have empty lists.
        """
        if not events:
            return {}

        results: dict[str, list[Insight]] = {}

        for event in events:
            try:
                insights = await self.analyze_event(
                    user_id=user_id,
                    lead_memory_id=lead_memory_id,
                    event=event,
                )
                results[event.id] = insights
            except Exception as e:
                logger.warning(
                    "Failed to analyze event in batch",
                    extra={
                        "user_id": user_id,
                        "lead_memory_id": lead_memory_id,
                        "event_id": event.id,
                        "error": str(e),
                    },
                )
                results[event.id] = []

        logger.info(
            "Completed batch analysis",
            extra={
                "user_id": user_id,
                "lead_memory_id": lead_memory_id,
                "event_count": len(events),
                "total_insights": sum(len(insights) for insights in results.values()),
            },
        )

        return results
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestBatchAnalysis -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): implement batch analysis for retroactive processing"
```

---

## Task 9: Add get_insights_for_lead Method

**Files:**
- Modify: `backend/src/memory/conversation_intelligence.py`
- Modify: `backend/tests/test_conversation_intelligence.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_conversation_intelligence.py`:

```python
class TestGetInsights:
    """Tests for the get_insights_for_lead method."""

    @pytest.mark.asyncio
    async def test_get_insights_for_lead(self):
        """Test retrieving all insights for a lead."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "insight-1",
                "lead_memory_id": "lead-456",
                "insight_type": "objection",
                "content": "Timeline concerns",
                "confidence": 0.85,
                "source_event_id": "event-1",
                "detected_at": "2025-02-03T14:00:00+00:00",
                "addressed_at": None,
                "addressed_by": None,
            },
            {
                "id": "insight-2",
                "lead_memory_id": "lead-456",
                "insight_type": "buying_signal",
                "content": "Positive response",
                "confidence": 0.90,
                "source_event_id": "event-2",
                "detected_at": "2025-02-03T15:00:00+00:00",
                "addressed_at": "2025-02-04T10:00:00+00:00",
                "addressed_by": "user-123",
            },
        ]

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        insights = await service.get_insights_for_lead(
            user_id="user-123",
            lead_memory_id="lead-456",
        )

        assert len(insights) == 2
        assert insights[0].insight_type == InsightType.OBJECTION
        assert insights[1].insight_type == InsightType.BUYING_SIGNAL
        assert insights[1].addressed_at is not None

    @pytest.mark.asyncio
    async def test_get_insights_for_lead_filtered_by_type(self):
        """Test retrieving insights filtered by type."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "insight-1",
                "lead_memory_id": "lead-456",
                "insight_type": "objection",
                "content": "Timeline concerns",
                "confidence": 0.85,
                "source_event_id": "event-1",
                "detected_at": "2025-02-03T14:00:00+00:00",
                "addressed_at": None,
                "addressed_by": None,
            },
        ]

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        insights = await service.get_insights_for_lead(
            user_id="user-123",
            lead_memory_id="lead-456",
            insight_type=InsightType.OBJECTION,
        )

        assert len(insights) == 1
        assert insights[0].insight_type == InsightType.OBJECTION

    @pytest.mark.asyncio
    async def test_get_insights_for_lead_unaddressed_only(self):
        """Test retrieving only unaddressed insights."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "insight-1",
                "lead_memory_id": "lead-456",
                "insight_type": "risk",
                "content": "Budget freeze",
                "confidence": 0.75,
                "source_event_id": "event-1",
                "detected_at": "2025-02-03T14:00:00+00:00",
                "addressed_at": None,
                "addressed_by": None,
            },
        ]

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.is_.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        insights = await service.get_insights_for_lead(
            user_id="user-123",
            lead_memory_id="lead-456",
            unaddressed_only=True,
        )

        assert len(insights) == 1
        assert insights[0].addressed_at is None

    @pytest.mark.asyncio
    async def test_get_insights_for_lead_empty_result(self):
        """Test retrieving insights when none exist."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = []

        mock_query = MagicMock()
        mock_query.eq.return_value = mock_query
        mock_query.order.return_value = mock_query
        mock_query.execute.return_value = mock_response
        mock_client.table.return_value.select.return_value = mock_query

        insights = await service.get_insights_for_lead(
            user_id="user-123",
            lead_memory_id="lead-456",
        )

        assert insights == []
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestGetInsights -v`
Expected: FAIL with "AttributeError"

**Step 3: Write minimal implementation**

Add to `ConversationIntelligence` class:

```python
    async def get_insights_for_lead(
        self,
        user_id: str,
        lead_memory_id: str,
        insight_type: InsightType | None = None,
        unaddressed_only: bool = False,
    ) -> list[Insight]:
        """Get insights for a lead with optional filtering.

        Args:
            user_id: The user who owns the lead.
            lead_memory_id: The lead memory ID.
            insight_type: Optional filter by insight type.
            unaddressed_only: If True, only return unaddressed insights.

        Returns:
            List of Insight instances ordered by detected_at descending.

        Raises:
            DatabaseError: If retrieval fails.
        """
        from src.core.exceptions import DatabaseError

        try:
            query = (
                self.db.table("lead_memory_insights")
                .select("*")
                .eq("lead_memory_id", lead_memory_id)
            )

            if insight_type:
                query = query.eq("insight_type", insight_type.value)

            if unaddressed_only:
                query = query.is_("addressed_at", "null")

            query = query.order("detected_at", desc=True)
            response = query.execute()

            insights = []
            for item in response.data:
                insight_dict = cast(dict[str, Any], item)
                insights.append(Insight.from_dict(insight_dict))

            logger.info(
                "Retrieved insights for lead",
                extra={
                    "user_id": user_id,
                    "lead_memory_id": lead_memory_id,
                    "insight_count": len(insights),
                    "insight_type": insight_type.value if insight_type else None,
                    "unaddressed_only": unaddressed_only,
                },
            )

            return insights

        except Exception as e:
            logger.exception("Failed to get insights for lead")
            raise DatabaseError(f"Failed to get insights for lead: {e}") from e
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence.py::TestGetInsights -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py
git commit -m "feat(lead-memory): implement get_insights_for_lead with filtering"
```

---

## Task 10: Update Module Exports

**Files:**
- Modify: `backend/src/memory/__init__.py`

**Step 1: Write the failing test**

Create `backend/tests/test_conversation_intelligence_exports.py`:

```python
"""Tests for conversation intelligence module exports."""


class TestConversationIntelligenceExports:
    """Tests for module exports."""

    def test_insight_exported(self):
        """Test that Insight is exported from memory module."""
        from src.memory import Insight

        assert Insight is not None

    def test_conversation_intelligence_exported(self):
        """Test that ConversationIntelligence is exported from memory module."""
        from src.memory import ConversationIntelligence

        assert ConversationIntelligence is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_conversation_intelligence_exports.py -v`
Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

Add to `backend/src/memory/__init__.py`:

After the existing imports, add:
```python
from src.memory.conversation_intelligence import ConversationIntelligence, Insight
```

Add to the `__all__` list:
```python
    # Conversation Intelligence
    "ConversationIntelligence",
    "Insight",
```

**Step 4: Run test to verify it passes**

Run: `pytest backend/tests/test_conversation_intelligence_exports.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/memory/__init__.py backend/tests/test_conversation_intelligence_exports.py
git commit -m "feat(lead-memory): export ConversationIntelligence from memory module"
```

---

## Task 11: Run Full Test Suite and Type Check

**Files:**
- None (verification only)

**Step 1: Run all conversation intelligence tests**

Run: `pytest backend/tests/test_conversation_intelligence.py backend/tests/test_conversation_intelligence_exports.py -v`
Expected: All PASS

**Step 2: Run type checking**

Run: `mypy backend/src/memory/conversation_intelligence.py --strict`
Expected: No errors (or fix any reported issues)

**Step 3: Run linting**

Run: `ruff check backend/src/memory/conversation_intelligence.py`
Expected: No errors (or fix any reported issues)

**Step 4: Format code**

Run: `ruff format backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py backend/tests/test_conversation_intelligence_exports.py`
Expected: Files formatted

**Step 5: Commit if any fixes were needed**

```bash
git add backend/src/memory/conversation_intelligence.py backend/tests/test_conversation_intelligence.py backend/tests/test_conversation_intelligence_exports.py
git commit -m "fix(lead-memory): address type and lint issues in conversation intelligence"
```

---

## Task 12: Final Verification

**Files:**
- None (verification only)

**Step 1: Run the full backend test suite**

Run: `pytest backend/tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Verify imports work correctly**

Run: `python -c "from src.memory import ConversationIntelligence, Insight; print('Imports OK')"`
Expected: "Imports OK"

**Step 3: Commit final state**

```bash
git status
git add -A
git commit -m "feat(lead-memory): complete US-505 conversation intelligence implementation"
```

---

## Summary

This plan implements US-505: Conversation Intelligence with:

1. **Insight dataclass** with `to_dict()` and `from_dict()` methods
2. **InsightType enum** (reused from existing `src/models/lead_memory.py`)
3. **ConversationIntelligence class** with:
   - `analyze_event()` - LLM-powered insight extraction
   - `mark_addressed()` - Mark insights as handled
   - `get_insights_for_lead()` - Retrieve insights with filtering
   - `analyze_batch()` - Retroactive batch processing
4. **Prompt template** for objections, signals, commitments, risks, opportunities
5. **Confidence scoring** (0.0-1.0) from LLM
6. **Source event linking** via `source_event_id`
7. **Comprehensive unit tests** with mock LLM responses

The implementation follows existing codebase patterns from `lead_memory_events.py` and integrates with the existing `lead_memory_insights` Supabase table.
