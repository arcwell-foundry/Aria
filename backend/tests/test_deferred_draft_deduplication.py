"""Tests for email draft deduplication system.

Tests the deduplication methods in AutonomousDraftEngine and the
deferred draft retry job.
"""

import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Load env vars manually for testing
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value.strip('"').strip("'")

# Mock external dependencies before importing
sys.modules['composio'] = MagicMock()
sys.modules['resend'] = MagicMock()

# Mock the settings
os.environ["ENABLE_SCHEDULER"] = "false"


class MockEmailCategory:
    """Mock EmailCategory for testing."""

    def __init__(
        self,
        email_id: str,
        thread_id: str | None = None,
        sender_email: str = "test@example.com",
        sender_name: str = "Test Sender",
        subject: str = "Test Subject",
        snippet: str = "Test snippet",
        urgency: str = "NORMAL",
        scanned_at: datetime | None = None,
    ):
        self.email_id = email_id
        self.thread_id = thread_id or email_id
        self.sender_email = sender_email
        self.sender_name = sender_name
        self.subject = subject
        self.snippet = snippet
        self.urgency = urgency
        self.scanned_at = scanned_at or datetime.now(UTC)


# Now import after mocking
from src.services.autonomous_draft_engine import (
    AutonomousDraftEngine,
    DraftResult,
    ProcessingRunResult,
)


class TestGroupEmailsByThread:
    """Tests for _group_emails_by_thread method."""

    @pytest.mark.asyncio
    async def test_groups_emails_by_thread_id(self):
        """Emails with same thread_id are grouped together."""
        engine = AutonomousDraftEngine()

        emails = [
            MockEmailCategory("email1", thread_id="threadA"),
            MockEmailCategory("email2", thread_id="threadA"),
            MockEmailCategory("email3", thread_id="threadB"),
        ]

        grouped = await engine._group_emails_by_thread(emails)

        assert len(grouped) == 2
        assert len(grouped["threadA"]) == 2
        assert len(grouped["threadB"]) == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_email_id(self):
        """Emails without thread_id use email_id as key."""
        engine = AutonomousDraftEngine()

        emails = [
            MockEmailCategory("email1", thread_id=None),
            MockEmailCategory("email2", thread_id=None),
        ]

        grouped = await engine._group_emails_by_thread(emails)

        assert len(grouped) == 2
        assert "email1" in grouped
        assert "email2" in grouped

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_dict(self):
        """Empty email list returns empty dict."""
        engine = AutonomousDraftEngine()

        grouped = await engine._group_emails_by_thread([])

        assert grouped == {}


class TestGetLatestEmailInThread:
    """Tests for _get_latest_email_in_thread method."""

    @pytest.mark.asyncio
    async def test_returns_single_email_unchanged(self):
        """Single email in thread is returned as-is."""
        engine = AutonomousDraftEngine()

        email = MockEmailCategory("email1")
        result = await engine._get_latest_email_in_thread([email])

        assert result.email_id == "email1"

    @pytest.mark.asyncio
    async def test_returns_most_recent_by_scanned_at(self):
        """Returns email with most recent scanned_at timestamp."""
        engine = AutonomousDraftEngine()

        now = datetime.now(UTC)
        emails = [
            MockEmailCategory("email1", scanned_at=now - timedelta(hours=2)),
            MockEmailCategory("email2", scanned_at=now - timedelta(hours=1)),
            MockEmailCategory("email3", scanned_at=now),
        ]

        result = await engine._get_latest_email_in_thread(emails)

        assert result.email_id == "email3"

    @pytest.mark.asyncio
    async def test_falls_back_to_email_id_comparison(self):
        """Uses email_id for comparison when scanned_at is None."""
        engine = AutonomousDraftEngine()

        emails = [
            MockEmailCategory("email_a", scanned_at=None),
            MockEmailCategory("email_b", scanned_at=None),
            MockEmailCategory("email_z", scanned_at=None),
        ]

        result = await engine._get_latest_email_in_thread(emails)

        # email_z should be returned as it's "max" by lexicographic string comparison
        assert result.email_id == "email_z"


class TestCheckExistingDraft:
    """Tests for _check_existing_draft method."""

    @pytest.mark.asyncio
    async def test_returns_true_when_draft_exists(self):
        """Returns True when a draft exists for the thread."""
        engine = AutonomousDraftEngine()

        # Create a proper async mock response
        async def mock_execute():
            return MagicMock(data={"id": "draft-123"})

        # Build the mock chain
        mock_maybe_single = MagicMock()
        mock_maybe_single.execute = mock_execute

        mock_in = MagicMock()
        mock_in.maybe_single = MagicMock(return_value=mock_maybe_single)

        mock_eq2 = MagicMock()
        mock_eq2.in_ = MagicMock(return_value=mock_in)

        mock_eq1 = MagicMock()
        mock_eq1.eq = MagicMock(return_value=mock_eq2)

        mock_select = MagicMock()
        mock_select.eq = MagicMock(return_value=mock_eq1)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)

        # Replace the _db.table method
        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            result = await engine._check_existing_draft("user-123", "thread-123")
            assert result is True
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_false_when_no_draft(self):
        """Returns False when no draft exists for the thread."""
        engine = AutonomousDraftEngine()

        # Create a proper async mock response
        async def mock_execute():
            return MagicMock(data=None)

        # Build the mock chain
        mock_maybe_single = MagicMock()
        mock_maybe_single.execute = mock_execute

        mock_in = MagicMock()
        mock_in.maybe_single = MagicMock(return_value=mock_maybe_single)

        mock_eq2 = MagicMock()
        mock_eq2.in_ = MagicMock(return_value=mock_in)

        mock_eq1 = MagicMock()
        mock_eq1.eq = MagicMock(return_value=mock_eq2)

        mock_select = MagicMock()
        mock_select.eq = MagicMock(return_value=mock_eq1)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            result = await engine._check_existing_draft("user-123", "thread-123")
            assert result is False
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        """Returns False on database error (safe default)."""
        engine = AutonomousDraftEngine()

        original_table = engine._db.table
        engine._db.table = MagicMock(side_effect=Exception("Database error"))

        try:
            result = await engine._check_existing_draft("user-123", "thread-123")
            assert result is False
        finally:
            engine._db.table = original_table


class TestIsActiveConversation:
    """Tests for _is_active_conversation method."""

    @pytest.mark.asyncio
    async def test_returns_true_for_rapid_thread(self):
        """Returns True when 3+ messages from 2+ senders in last hour."""
        engine = AutonomousDraftEngine()

        # Create a proper async mock response
        async def mock_execute():
            return MagicMock(data=[
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
                {"sender_email": "bob@example.com", "scanned_at": datetime.now(UTC).isoformat()},
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
            ])

        # Build the mock chain
        mock_order = MagicMock()
        mock_order.execute = mock_execute

        mock_gte = MagicMock()
        mock_gte.order = MagicMock(return_value=mock_order)

        mock_eq2 = MagicMock()
        mock_eq2.gte = MagicMock(return_value=mock_gte)

        mock_eq1 = MagicMock()
        mock_eq1.eq = MagicMock(return_value=mock_eq2)

        mock_select = MagicMock()
        mock_select.eq = MagicMock(return_value=mock_eq1)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            result = await engine._is_active_conversation("user-123", "thread-123")
            assert result is True
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_false_for_low_message_count(self):
        """Returns False when less than 3 messages in thread."""
        engine = AutonomousDraftEngine()

        async def mock_execute():
            return MagicMock(data=[
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
                {"sender_email": "bob@example.com", "scanned_at": datetime.now(UTC).isoformat()},
            ])

        mock_order = MagicMock()
        mock_order.execute = mock_execute

        mock_gte = MagicMock()
        mock_gte.order = MagicMock(return_value=mock_order)

        mock_eq2 = MagicMock()
        mock_eq2.gte = MagicMock(return_value=mock_gte)

        mock_eq1 = MagicMock()
        mock_eq1.eq = MagicMock(return_value=mock_eq2)

        mock_select = MagicMock()
        mock_select.eq = MagicMock(return_value=mock_eq1)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            result = await engine._is_active_conversation("user-123", "thread-123")
            assert result is False
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_false_for_single_sender(self):
        """Returns False when all messages from single sender."""
        engine = AutonomousDraftEngine()

        async def mock_execute():
            return MagicMock(data=[
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
                {"sender_email": "alice@example.com", "scanned_at": datetime.now(UTC).isoformat()},
            ])

        mock_order = MagicMock()
        mock_order.execute = mock_execute

        mock_gte = MagicMock()
        mock_gte.order = MagicMock(return_value=mock_order)

        mock_eq2 = MagicMock()
        mock_eq2.gte = MagicMock(return_value=mock_gte)

        mock_eq1 = MagicMock()
        mock_eq1.eq = MagicMock(return_value=mock_eq2)

        mock_select = MagicMock()
        mock_select.eq = MagicMock(return_value=mock_eq1)

        mock_table = MagicMock()
        mock_table.select = MagicMock(return_value=mock_select)

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            result = await engine._is_active_conversation("user-123", "thread-123")
            assert result is False
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_false_on_error(self):
        """Returns False on database error (safe default)."""
        engine = AutonomousDraftEngine()

        original_table = engine._db.table
        engine._db.table = MagicMock(side_effect=Exception("Database error"))

        try:
            result = await engine._is_active_conversation("user-123", "thread-123")
            assert result is False
        finally:
            engine._db.table = original_table


class TestDeferDraft:
    """Tests for _defer_draft method."""

    @pytest.mark.asyncio
    async def test_creates_deferred_record(self):
        """Creates a deferred draft record with correct fields."""
        engine = AutonomousDraftEngine()

        email = MockEmailCategory(
            "email-123",
            thread_id="thread-123",
            sender_email="test@example.com",
            subject="Test Subject",
        )

        mock_execute = AsyncMock()
        mock_execute.return_value = MagicMock(data=[{"id": "deferred-123"}])

        mock_table = MagicMock()
        mock_table.insert.return_value.execute = mock_execute

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            deferred_id = await engine._defer_draft(
                "user-123", "thread-123", email, "active_conversation"
            )
            assert deferred_id is not None
            assert mock_execute.called
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_returns_id_even_on_error(self):
        """Returns generated ID even if database insert fails."""
        engine = AutonomousDraftEngine()

        email = MockEmailCategory("email-123", thread_id="thread-123")

        original_table = engine._db.table
        engine._db.table = MagicMock(side_effect=Exception("Database error"))

        try:
            deferred_id = await engine._defer_draft(
                "user-123", "thread-123", email, "active_conversation"
            )
            # Should return the generated UUID even on error
            assert deferred_id is not None
            assert len(deferred_id) == 36  # UUID format
        finally:
            engine._db.table = original_table


class TestLogSkipDecision:
    """Tests for _log_skip_decision method."""

    @pytest.mark.asyncio
    async def test_logs_to_email_scan_log(self):
        """Creates a log entry in email_scan_log table."""
        engine = AutonomousDraftEngine()

        mock_execute = AsyncMock()
        mock_execute.return_value = MagicMock(data=[{"id": "log-123"}])

        mock_table = MagicMock()
        mock_table.insert.return_value.execute = mock_execute

        original_table = engine._db.table
        engine._db.table = MagicMock(return_value=mock_table)

        try:
            await engine._log_skip_decision("user-123", "thread-123", "existing_draft")
            assert mock_execute.called
        finally:
            engine._db.table = original_table

    @pytest.mark.asyncio
    async def test_handles_database_error_gracefully(self):
        """Does not raise exception on database error."""
        engine = AutonomousDraftEngine()

        original_table = engine._db.table
        engine._db.table = MagicMock(side_effect=Exception("Database error"))

        try:
            # Should not raise
            await engine._log_skip_decision("user-123", "thread-123", "existing_draft")
        finally:
            engine._db.table = original_table


class TestIntegration:
    """Integration tests using real database (if available)."""

    @pytest.mark.asyncio
    async def test_deferred_draft_table_exists(self):
        """Verify the deferred_email_drafts table exists in database."""
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            pytest.skip("Supabase credentials not available")

        client = create_client(url, key)

        # Try to query the table
        result = client.table("deferred_email_drafts").select("id").limit(1).execute()

        # If we get here without error, table exists
        assert result is not None

    @pytest.mark.asyncio
    async def test_email_scan_log_table_exists(self):
        """Verify the email_scan_log table exists in database."""
        from supabase import create_client

        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not key:
            pytest.skip("Supabase credentials not available")

        client = create_client(url, key)

        # Try to query the table
        result = client.table("email_scan_log").select("id").limit(1).execute()

        # If we get here without error, table exists
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
