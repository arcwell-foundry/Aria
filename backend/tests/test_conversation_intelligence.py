"""Tests for ConversationIntelligence and Insight dataclass.

This module tests the conversation intelligence service that extracts
actionable insights from lead events using LLM analysis.
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock

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
