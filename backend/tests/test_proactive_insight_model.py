"""Tests for ProactiveInsight model."""

import pytest
from datetime import datetime, UTC


class TestInsightType:
    """Tests for InsightType enum."""

    def test_insight_type_values(self) -> None:
        """InsightType should have expected values."""
        from src.models.proactive_insight import InsightType

        assert InsightType.PATTERN_MATCH.value == "pattern_match"
        assert InsightType.CONNECTION.value == "connection"
        assert InsightType.TEMPORAL.value == "temporal"
        assert InsightType.GOAL_RELEVANT.value == "goal_relevant"


class TestProactiveInsight:
    """Tests for ProactiveInsight dataclass."""

    def test_proactive_insight_creation(self) -> None:
        """ProactiveInsight should be creatable with required fields."""
        from src.models.proactive_insight import InsightType, ProactiveInsight

        insight = ProactiveInsight(
            insight_type=InsightType.PATTERN_MATCH,
            content="Dr. Smith mentioned budget concerns in your last meeting",
            relevance_score=0.85,
            source_memory_id="mem-123",
            source_memory_type="episodic",
            explanation="Similar topic discussed previously",
        )

        assert insight.insight_type == InsightType.PATTERN_MATCH
        assert insight.relevance_score == 0.85
        assert insight.source_memory_id == "mem-123"

    def test_proactive_insight_to_dict(self) -> None:
        """ProactiveInsight should serialize to dict."""
        from src.models.proactive_insight import InsightType, ProactiveInsight

        insight = ProactiveInsight(
            insight_type=InsightType.TEMPORAL,
            content="Follow-up due in 2 days",
            relevance_score=0.9,
            source_memory_id="task-456",
            source_memory_type="prospective",
            explanation="Due in 2 day(s)",
        )

        data = insight.to_dict()

        assert data["insight_type"] == "temporal"
        assert data["content"] == "Follow-up due in 2 days"
        assert data["relevance_score"] == 0.9


class TestSurfacedInsightRecord:
    """Tests for SurfacedInsightRecord dataclass."""

    def test_surfaced_insight_record_creation(self) -> None:
        """SurfacedInsightRecord should be creatable with all fields."""
        from src.models.proactive_insight import SurfacedInsightRecord

        now = datetime.now(UTC)
        record = SurfacedInsightRecord(
            id="record-123",
            user_id="user-456",
            memory_type="episodic",
            memory_id="mem-789",
            insight_type="pattern_match",
            context="Current conversation about budgets",
            relevance_score=0.85,
            explanation="Similar topic discussed",
            surfaced_at=now,
            engaged=False,
            engaged_at=None,
            dismissed=False,
            dismissed_at=None,
        )

        assert record.id == "record-123"
        assert record.engaged is False
