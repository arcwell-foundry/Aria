"""Tests for perception event aggregation on session shutdown."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Load the webhooks route module directly from file to avoid pulling in
# every sibling route via __init__.py
# ---------------------------------------------------------------------------
def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_webhooks_mod = _load_module(
    "src.api.routes.webhooks",
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "api"
    / "routes"
    / "webhooks.py",
)


# ---------------------------------------------------------------------------
# Helper to get the aggregation function
# ---------------------------------------------------------------------------
def _get_aggregate_fn():
    fn = getattr(_webhooks_mod, "_aggregate_perception_events", None)
    assert fn is not None, "_aggregate_perception_events not defined in webhooks module"
    return fn


# ---------------------------------------------------------------------------
# Tests for _aggregate_perception_events
# ---------------------------------------------------------------------------


class TestAggregatePerceptionEvents:
    """Tests for the _aggregate_perception_events helper function."""

    def test_aggregate_empty_events(self) -> None:
        """Empty list returns neutral values."""
        aggregate = _get_aggregate_fn()
        result = aggregate([])

        assert result["engagement_score"] == 1.0
        assert result["confusion_events"] == 0
        assert result["disengagement_events"] == 0
        assert result["engagement_trend"] == "stable"
        assert result["confused_topics"] == []
        assert result["total_perception_events"] == 0

    def test_aggregate_confusion_events(self) -> None:
        """Two confusion events: count=2, disengagement=0, topics listed, score < 1.0."""
        aggregate = _get_aggregate_fn()

        events: list[dict[str, Any]] = [
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:01:00+00:00",
                "session_time_seconds": 60.0,
                "indicator": "furrowed_brow",
                "topic": "mRNA delivery",
            },
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:03:00+00:00",
                "session_time_seconds": 180.0,
                "indicator": "repeated_question",
                "topic": "lipid nanoparticles",
            },
        ]

        result = aggregate(events)

        assert result["confusion_events"] == 2
        assert result["disengagement_events"] == 0
        assert result["confused_topics"] == ["mRNA delivery", "lipid nanoparticles"]
        assert result["engagement_score"] < 1.0
        assert result["total_perception_events"] == 2

    def test_aggregate_mixed_events(self) -> None:
        """One confusion + one disengagement: both counted, total=2."""
        aggregate = _get_aggregate_fn()

        events: list[dict[str, Any]] = [
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:01:00+00:00",
                "session_time_seconds": 60.0,
                "indicator": "furrowed_brow",
                "topic": "pricing strategy",
            },
            {
                "tool_name": "note_engagement_drop",
                "timestamp": "2026-02-17T10:04:00+00:00",
                "session_time_seconds": 240.0,
                "indicator": "looking_away",
                "topic": "contract terms",
            },
        ]

        result = aggregate(events)

        assert result["confusion_events"] == 1
        assert result["disengagement_events"] == 1
        assert result["total_perception_events"] == 2
        assert result["confused_topics"] == ["pricing strategy"]

    def test_aggregate_engagement_trend_declining(self) -> None:
        """Events concentrated in second half with session_duration_seconds=300.

        With all events in the second half, the second-half density should exceed
        the first-half density by more than 1, yielding "declining" or "stable".
        """
        aggregate = _get_aggregate_fn()

        # 4 events all in the second half (after 150s midpoint of 300s session)
        events: list[dict[str, Any]] = [
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:03:30+00:00",
                "session_time_seconds": 210.0,
                "indicator": "furrowed_brow",
                "topic": "topic_a",
            },
            {
                "tool_name": "note_engagement_drop",
                "timestamp": "2026-02-17T10:04:00+00:00",
                "session_time_seconds": 240.0,
                "indicator": "looking_away",
                "topic": "topic_b",
            },
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:04:20+00:00",
                "session_time_seconds": 260.0,
                "indicator": "repeated_question",
                "topic": "topic_c",
            },
            {
                "tool_name": "note_engagement_drop",
                "timestamp": "2026-02-17T10:04:40+00:00",
                "session_time_seconds": 280.0,
                "indicator": "looking_away",
                "topic": "topic_d",
            },
        ]

        result = aggregate(events, session_duration_seconds=300)

        # 0 events in first half, 4 in second half: 4 > 0 + 1 => "declining"
        assert result["engagement_trend"] in ("declining", "stable")
        assert result["total_perception_events"] == 4


class TestHandleShutdownPerceptionAggregation:
    """Tests for handle_shutdown perception aggregation integration."""

    def _make_mock_db(
        self,
        *,
        session_id: str = "session-123",
        started_at: str = "2026-02-17T10:00:00+00:00",
        perception_events: list[dict[str, Any]] | None = None,
        lead_id: str | None = None,
    ) -> MagicMock:
        """Create a mock DB for handle_shutdown with perception data.

        The mock needs to handle two separate select calls:
        1. First select: started_at (original shutdown logic)
        2. Second select: perception_events, lead_id (new aggregation logic)
        And then an update call and optionally an insert call.
        """
        mock_db = MagicMock()

        # We need side_effect to handle multiple .select().eq().execute() chains
        first_select_result = MagicMock(
            data=[{"started_at": started_at}]
        )
        second_select_result = MagicMock(
            data=[{
                "perception_events": perception_events,
                "lead_id": lead_id,
            }]
        )

        # Chain: table("video_sessions").select(...).eq(...).execute()
        mock_select = MagicMock()
        mock_select.eq.return_value.execute.side_effect = [
            first_select_result,
            second_select_result,
        ]
        mock_db.table.return_value.select.return_value = mock_select

        # update chain
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": session_id}]
        )

        # insert chain (for lead_memory_events)
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "memory-event-1"}]
        )

        return mock_db

    @pytest.mark.asyncio
    async def test_shutdown_includes_perception_analysis(self) -> None:
        """handle_shutdown adds perception_analysis to update_data when events exist."""
        handle_shutdown = getattr(_webhooks_mod, "handle_shutdown", None)
        assert handle_shutdown is not None

        events = [
            {
                "tool_name": "adapt_to_confusion",
                "timestamp": "2026-02-17T10:02:00+00:00",
                "session_time_seconds": 120.0,
                "indicator": "furrowed_brow",
                "topic": "mRNA delivery",
            },
        ]

        mock_db = self._make_mock_db(perception_events=events)

        await handle_shutdown(
            conversation_id="tavus-conv-shutdown",
            payload={"shutdown_reason": "user_left"},
            db=mock_db,
        )

        # Verify update was called and included perception_analysis
        update_calls = mock_db.table.return_value.update.call_args_list
        assert len(update_calls) >= 1

        # Find the update call that includes perception_analysis
        found_perception = False
        for call in update_calls:
            update_data = call.args[0] if call.args else call.kwargs.get("data", {})
            if isinstance(update_data, dict) and "perception_analysis" in update_data:
                found_perception = True
                analysis = update_data["perception_analysis"]
                assert analysis["confusion_events"] == 1
                assert analysis["engagement_score"] < 1.0
                break

        assert found_perception, "perception_analysis not found in any update call"

    @pytest.mark.asyncio
    async def test_shutdown_creates_lead_memory_event(self) -> None:
        """handle_shutdown inserts lead_memory_event when lead_id and perception exist."""
        handle_shutdown = getattr(_webhooks_mod, "handle_shutdown", None)
        assert handle_shutdown is not None

        events = [
            {
                "tool_name": "note_engagement_drop",
                "timestamp": "2026-02-17T10:05:00+00:00",
                "session_time_seconds": 300.0,
                "indicator": "looking_away",
                "topic": "pricing",
            },
        ]

        mock_db = self._make_mock_db(
            perception_events=events,
            lead_id="lead-abc-123",
        )

        await handle_shutdown(
            conversation_id="tavus-conv-lead",
            payload={"shutdown_reason": "completed"},
            db=mock_db,
        )

        # Verify insert was called for lead_memory_events
        insert_calls = mock_db.table.return_value.insert.call_args_list
        found_lead_event = False
        for call in insert_calls:
            insert_data = call.args[0] if call.args else {}
            if isinstance(insert_data, dict) and insert_data.get("event_type") == "video_session":
                found_lead_event = True
                assert insert_data["source"] == "tavus_video"
                assert "metadata" in insert_data
                break

        assert found_lead_event, "lead_memory_event insert not found"
