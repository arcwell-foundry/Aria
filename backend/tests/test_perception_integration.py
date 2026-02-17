"""Integration test for full perception tool webhook flow."""

import pytest
from unittest.mock import MagicMock
from datetime import UTC, datetime


@pytest.mark.asyncio
async def test_full_perception_flow():
    """Full flow: perception tool call -> shutdown aggregation."""
    from src.api.routes.webhooks import (
        handle_perception_tool_call,
        _aggregate_perception_events,
    )

    # 1. Simulate perception tool call
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{
            "id": "session-1",
            "user_id": "user-1",
            "perception_events": [],
            "started_at": "2026-02-17T14:00:00+00:00",
        }]
    )
    # Additional chained .eq() for _upsert_topic_stats (user_id + topic)
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.upsert.return_value.execute.return_value = MagicMock(data=[{}])
    db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{}])

    result = await handle_perception_tool_call(
        conversation_id="conv-1",
        tool_name="adapt_to_confusion",
        arguments={"confusion_indicator": "brow furrow", "topic": "pricing"},
        db=db,
    )

    assert result is not None
    assert result["spoken_text"] == ""

    # 2. Simulate aggregation (as would happen on shutdown)
    events = [
        {
            "tool_name": "adapt_to_confusion",
            "timestamp": "2026-02-17T14:01:00+00:00",
            "session_time_seconds": 60,
            "indicator": "brow furrow",
            "topic": "pricing",
            "metadata": {},
        },
        {
            "tool_name": "note_engagement_drop",
            "timestamp": "2026-02-17T14:05:00+00:00",
            "session_time_seconds": 300,
            "indicator": "checking phone",
            "topic": "clinical_data",
            "metadata": {},
        },
    ]

    aggregation = _aggregate_perception_events(events, session_duration_seconds=600)

    assert aggregation["confusion_events"] == 1
    assert aggregation["disengagement_events"] == 1
    assert aggregation["engagement_score"] < 1.0
    assert "pricing" in aggregation["confused_topics"]
    assert aggregation["total_perception_events"] == 2
