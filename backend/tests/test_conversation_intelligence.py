"""Tests for ConversationIntelligence and Insight dataclass.

This module tests the conversation intelligence service that extracts
actionable insights from lead events using LLM analysis.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.conversation_intelligence import ConversationIntelligence, Insight
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


class TestConversationIntelligenceService:
    """Tests for the ConversationIntelligence service class."""

    def test_service_initialization(self):
        """Test that ConversationIntelligence can be instantiated."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)
        assert service is not None
        assert service.db == mock_client

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
            _insights = await service.analyze_event(
                user_id="user-123",
                lead_memory_id="lead-456",
                event=event,
            )

        # Verify the insert was called with source_event_id
        assert len(_insights) == 1  # Ensure we got insights to validate the flow
        insert_call = mock_client.table.return_value.insert.call_args
        assert insert_call is not None
        inserted_data = insert_call[0][0]
        assert isinstance(inserted_data, list)
        assert inserted_data[0]["source_event_id"] == "event-789"


class TestMarkAddressed:
    """Tests for the mark_addressed method."""

    @pytest.mark.asyncio
    async def test_mark_addressed_success(self):
        """Test marking an insight as addressed."""
        mock_client = MagicMock()
        service = ConversationIntelligence(db_client=mock_client)

        mock_response = MagicMock()
        mock_response.data = [{"id": "insight-123", "addressed_at": "2025-02-04T10:00:00+00:00"}]
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

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
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = (
            mock_response
        )

        result = await service.mark_addressed(
            user_id="user-123",
            insight_id="nonexistent-id",
        )

        assert result is False


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
