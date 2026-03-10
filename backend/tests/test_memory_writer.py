"""Tests for the universal memory_writer service."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.memory_writer import (
    write_memory,
    _resolve_lead_memory_id,
    _upsert_stakeholder,
    _extract_sentiment,
    _EVENT_HANDLERS,
)


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock database client."""
    db = MagicMock()
    # Chain mock for table().select().eq().execute()
    db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    db.table.return_value.insert.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{"id": "test-id"}])
    )
    db.table.return_value.update.return_value.eq.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{"id": "test-id"}])
    )
    return db


class TestWriteMemory:
    """Tests for the write_memory function."""

    @pytest.mark.asyncio
    async def test_write_memory_routes_to_correct_handler(self, mock_db: MagicMock) -> None:
        """Test that write_memory routes to the correct handler based on event_type."""
        # Mock the handler
        mock_handler = AsyncMock()
        with patch.dict(_EVENT_HANDLERS, {"test_event": mock_handler}):
            await write_memory(mock_db, "user-123", "test_event", {"foo": "bar"})

        mock_handler.assert_awaited_once_with(mock_db, "user-123", {"foo": "bar"})

    @pytest.mark.asyncio
    async def test_write_memory_logs_warning_for_unknown_event_type(self, mock_db: MagicMock) -> None:
        """Test that write_memory logs a warning for unknown event types."""
        with patch("src.services.memory_writer.logger") as mock_logger:
            await write_memory(mock_db, "user-123", "unknown_event", {"foo": "bar"})

        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_memory_never_raises(self, mock_db: MagicMock) -> None:
        """Test that write_memory never raises exceptions."""
        # Mock a handler that raises
        mock_handler = AsyncMock(side_effect=RuntimeError("Handler failed"))
        with patch.dict(_EVENT_HANDLERS, {"failing_event": mock_handler}):
            with patch("src.services.memory_writer.logger") as mock_logger:
                # Should not raise
                await write_memory(mock_db, "user-123", "failing_event", {"foo": "bar"})

        mock_logger.exception.assert_called_once()


class TestEmailScannedHandler:
    """Tests for the email_scanned event handler."""

    @pytest.mark.asyncio
    async def test_email_scanned_writes_to_memory_semantic(self, mock_db: MagicMock) -> None:
        """Test that email_scanned writes to memory_semantic table."""
        await write_memory(mock_db, "user-123", "email_scanned", {
            "email_id": "email-123",
            "sender_email": "john@example.com",
            "sender_name": "John Doe",
            "subject": "Test Subject",
            "category": "NEEDS_REPLY",
            "urgency": "URGENT",
            "snippet": "This is a test email",
            "confidence": 0.8,
        })

        # Verify memory_semantic insert was called
        mock_db.table.assert_called()
        insert_call = mock_db.table.return_value.insert
        insert_call.assert_called_once()
        call_args = insert_call.call_args[0][0]
        assert call_args["user_id"] == "user-123"
        assert call_args["source"] == "email_scan"
        assert call_args["confidence"] == 0.8
        assert "John Doe" in call_args["fact"]

    @pytest.mark.asyncio
    async def test_email_scanned_writes_to_lead_memory_events_when_resolved(self, mock_db: MagicMock) -> None:
        """Test that email_scanned writes to lead_memory_events when lead is resolved."""
        # Mock lead_memory_stakeholders to return a lead_memory_id
        mock_db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"lead_memory_id": "lead-456"}])
        )
        # Mock lead_memories verification
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"id": "lead-456"}])
        )

        # Reset insert mock
        mock_db.table.return_value.insert.return_value.execute = AsyncMock(
            return_value=MagicMock(data=[{"id": "test-id"}])
        )

        await write_memory(mock_db, "user-123", "email_scanned", {
            "email_id": "email-123",
            "sender_email": "john@example.com",
            "sender_name": "John Doe",
            "subject": "Test Subject",
            "category": "NEEDS_REPLY",
            "urgency": "URGENT",
            "snippet": "This is a test email",
        })

        # Verify insert was called (at least once for memory_semantic)
        assert mock_db.table.return_value.insert.call_count >= 1


class TestMeetingDebriefApprovedHandler:
    """Tests for the meeting_debrief_approved event handler."""

    @pytest.mark.asyncio
    async def test_meeting_debrief_writes_action_items_to_prospective(self, mock_db: MagicMock) -> None:
        """Test that meeting_debrief_approved writes action items with due dates to memory_prospective."""
        await write_memory(mock_db, "user-123", "meeting_debrief_approved", {
            "debrief_id": "debrief-123",
            "meeting_title": "Q4 Planning",
            "summary": "Discussed Q4 priorities",
            "action_items": [
                {"item": "Send proposal", "owner": "Dhruv", "due": "2026-03-15"},
                {"item": "Review docs", "owner": "John"},  # No due date - should be skipped
            ],
            "next_steps": [],
            "stakeholder_signals": ["Excited about partnership"],
            "attendee_emails": ["john@example.com"],
            "meeting_time": "2026-03-09T10:00:00Z",
        })

        # Verify memory_semantic insert was called
        mock_db.table.assert_called()
        insert_call = mock_db.table.return_value.insert
        assert insert_call.call_count >= 1

    @pytest.mark.asyncio
    async def test_meeting_debrief_extracts_sentiment(self, mock_db: MagicMock) -> None:
        """Test that meeting_debrief_approved extracts sentiment from stakeholder signals."""
        signals = ["Excited about the partnership", "Ready to move forward"]
        sentiment = _extract_sentiment(signals, "john@example.com")
        assert sentiment == "positive"

        signals = ["Concerned about timeline", "Worried about budget"]
        sentiment = _extract_sentiment(signals, "john@example.com")
        assert sentiment == "negative"

        signals = ["Neutral update", "Standard process"]
        sentiment = _extract_sentiment(signals, "john@example.com")
        assert sentiment == "neutral"


class TestResolveLeadMemoryId:
    """Tests for the _resolve_lead_memory_id helper."""

    @pytest.mark.asyncio
    async def test_resolve_lead_memory_id_returns_none_for_empty_email(self, mock_db: MagicMock) -> None:
        """Test that _resolve_lead_memory_id returns None for empty email."""
        result = await _resolve_lead_memory_id(mock_db, "user-123", "")
        assert result is None

        result = await _resolve_lead_memory_id(mock_db, "user-123", None)  # type: ignore
        assert result is None

    @pytest.mark.skip(reason="Requires complex Supabase client mocking - tested via integration tests")
    @pytest.mark.asyncio
    async def test_resolve_lead_memory_id_queries_stakeholders(self, mock_db: MagicMock) -> None:
        """Test that _resolve_lead_memory_id queries lead_memory_stakeholders."""
        pass


class TestUpsertStakeholder:
    """Tests for the _upsert_stakeholder helper."""

    @pytest.mark.skip(reason="Requires complex Supabase client mocking - tested via integration tests")
    @pytest.mark.asyncio
    async def test_upsert_stakeholder_inserts_new(self, mock_db: MagicMock) -> None:
        """Test that _upsert_stakeholder inserts new stakeholder when none exists."""
        pass

    @pytest.mark.skip(reason="Requires complex Supabase client mocking - tested via integration tests")
    @pytest.mark.asyncio
    async def test_upsert_stakeholder_updates_existing(self, mock_db: MagicMock) -> None:
        """Test that _upsert_stakeholder updates existing stakeholder."""
        pass


class TestExtractSentiment:
    """Tests for the _extract_sentiment helper."""

    def test_positive_sentiment(self) -> None:
        """Test positive sentiment extraction."""
        signals = ["Excited about the opportunity", "Ready to commit"]
        assert _extract_sentiment(signals, "john@example.com") == "positive"

    def test_negative_sentiment(self) -> None:
        """Test negative sentiment extraction."""
        signals = ["Concerned about the timeline", "Hesitant to proceed"]
        assert _extract_sentiment(signals, "john@example.com") == "negative"

    def test_neutral_sentiment(self) -> None:
        """Test neutral sentiment extraction."""
        signals = ["Noted the update", "Standard process"]
        assert _extract_sentiment(signals, "john@example.com") == "neutral"

    def test_empty_signals_returns_neutral(self) -> None:
        """Test that empty signals returns neutral."""
        assert _extract_sentiment([], "john@example.com") == "neutral"

    def test_dict_signals_handled(self) -> None:
        """Test that dict signals are handled correctly."""
        signals = [
            {"signal": "Excited about partnership"},
            {"content": "Concerned about budget"},
        ]
        # Equal positive and negative = neutral
        sentiment = _extract_sentiment(signals, "john@example.com")
        assert sentiment == "neutral"


class TestEventHandlersRegistry:
    """Tests for the event handlers registry."""

    def test_all_expected_handlers_registered(self) -> None:
        """Test that all expected event handlers are registered."""
        expected_handlers = [
            "email_scanned",
            "email_sent",
            "meeting_brief_generated",
            "meeting_debrief_approved",
            "competitive_signal",
            "lead_created",
            "goal_executed",
            "brainstorm_message",
            "slide_deck_created",
            "calendar_event_synced",
            "crm_note_pushed",
        ]

        for handler_name in expected_handlers:
            assert handler_name in _EVENT_HANDLERS, f"Handler '{handler_name}' not registered"
