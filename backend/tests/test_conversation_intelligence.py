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
