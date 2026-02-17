"""Tests for perception tool call handling in Tavus webhook routes."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
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
# Tests
# ---------------------------------------------------------------------------


class TestPerceptionToolsSet:
    """Tests for PERCEPTION_TOOLS constant."""

    def test_perception_tools_set_contains_expected_tools(self) -> None:
        """Verify PERCEPTION_TOOLS contains both perception tool names."""
        perception_tools = getattr(_webhooks_mod, "PERCEPTION_TOOLS", None)
        assert perception_tools is not None, "PERCEPTION_TOOLS not defined"
        assert isinstance(perception_tools, frozenset)
        assert "adapt_to_confusion" in perception_tools
        assert "note_engagement_drop" in perception_tools
        assert len(perception_tools) == 2


class TestHandlePerceptionToolCall:
    """Tests for handle_perception_tool_call async function."""

    def _make_mock_db(
        self,
        *,
        session_id: str = "session-123",
        user_id: str = "user-456",
        perception_events: list | None = None,
        started_at: str | None = None,
    ) -> MagicMock:
        """Create a mock DB that returns video_sessions data."""
        if started_at is None:
            started_at = "2026-02-17T10:00:00+00:00"
        if perception_events is None:
            perception_events = []

        mock_db = MagicMock()

        # video_sessions select (id, user_id, perception_events, started_at)
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": session_id,
                    "user_id": user_id,
                    "perception_events": perception_events,
                    "started_at": started_at,
                }
            ]
        )
        # update + insert calls
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"id": session_id}]
        )
        mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "activity-789"}]
        )
        # For _upsert_topic_stats select (may return empty)
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[]
        )
        # upsert
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "stats-1"}]
        )
        return mock_db

    @pytest.mark.asyncio
    async def test_handle_perception_tool_call_appends_event(self) -> None:
        """Call with adapt_to_confusion and verify result is not None."""
        mock_db = self._make_mock_db()
        handle_fn = getattr(_webhooks_mod, "handle_perception_tool_call", None)
        assert handle_fn is not None, "handle_perception_tool_call not defined"

        result = await handle_fn(
            conversation_id="tavus-conv-001",
            tool_name="adapt_to_confusion",
            arguments={"indicator": "furrowed_brow", "topic": "mRNA delivery"},
            db=mock_db,
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_handle_perception_tool_call_returns_empty_spoken_text(self) -> None:
        """Verify the returned dict has spoken_text == ''."""
        mock_db = self._make_mock_db()
        handle_fn = getattr(_webhooks_mod, "handle_perception_tool_call", None)
        assert handle_fn is not None, "handle_perception_tool_call not defined"

        result = await handle_fn(
            conversation_id="tavus-conv-002",
            tool_name="note_engagement_drop",
            arguments={"indicator": "looking_away", "topic": "pricing strategy"},
            db=mock_db,
        )

        assert result is not None
        assert "spoken_text" in result
        assert result["spoken_text"] == ""
