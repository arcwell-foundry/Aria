"""Tests for video perception integration in conversion scoring sentiment trend."""

import pytest
from unittest.mock import MagicMock
from datetime import UTC, datetime
from src.services.conversion_scoring import ConversionScoringService


@pytest.mark.asyncio
async def test_sentiment_trend_includes_video_perception():
    service = ConversionScoringService()

    stakeholder_result = MagicMock()
    stakeholder_result.data = [{"sentiment": "positive"}, {"sentiment": "neutral"}]

    video_result = MagicMock()
    video_result.data = [{"perception_analysis": {"engagement_score": 0.3, "confusion_events": 4}}]

    def mock_table(name):
        result = MagicMock()
        if name == "lead_memory_stakeholders":
            result.select.return_value.eq.return_value.execute.return_value = stakeholder_result
        elif name == "video_sessions":
            result.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = video_result
        return result

    service._db = MagicMock()
    service._db.table.side_effect = mock_table

    score = await service._calculate_sentiment_trend("lead-123", datetime.now(UTC))
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
    # With poor video engagement (0.3), score should be lower than pure stakeholder
    # Pure stakeholder: (1 positive, 1 neutral) = net 0.5/2=0.25 => (0.25+1)/2=0.625
    # Blended: 0.625*0.7 + 0.3*0.3 = 0.4375 + 0.09 = 0.5275
    assert score < 0.625  # lower than pure stakeholder


@pytest.mark.asyncio
async def test_sentiment_trend_no_video_sessions():
    service = ConversionScoringService()

    stakeholder_result = MagicMock()
    stakeholder_result.data = [{"sentiment": "positive"}]

    video_result = MagicMock()
    video_result.data = []

    def mock_table(name):
        result = MagicMock()
        if name == "lead_memory_stakeholders":
            result.select.return_value.eq.return_value.execute.return_value = stakeholder_result
        elif name == "video_sessions":
            result.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = video_result
        return result

    service._db = MagicMock()
    service._db.table.side_effect = mock_table

    score = await service._calculate_sentiment_trend("lead-123", datetime.now(UTC))
    # With no video sessions, should be pure stakeholder score
    # 1 positive out of 1 = net 1.0/1=1.0 => (1.0+1)/2=1.0
    assert score == 1.0
