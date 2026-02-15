"""Tests for EmailContextGatherer service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from src.services.email_context_gatherer import (
    EmailContextGatherer,
    DraftContext,
    ThreadContext,
    ThreadMessage,
    RecipientResearch,
    RecipientWritingStyle,
    RelationshipHistory,
    CalendarContext,
    CRMContext,
    CorporateMemoryContext,
)


@pytest.fixture
def gatherer():
    """Create an EmailContextGatherer instance with mocked DB."""
    with patch("src.db.supabase.SupabaseClient") as mock_supabase:
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client

        g = EmailContextGatherer()
        g._db = mock_client
        yield g


@pytest.fixture
def sample_thread_messages():
    """Sample thread messages for testing."""
    return [
        ThreadMessage(
            sender_email="john@acme.com",
            sender_name="John Smith",
            body="Hi, I wanted to follow up on our discussion about the Q2 proposal.",
            timestamp="2026-02-13T10:00:00Z",
            is_from_user=False,
        ),
        ThreadMessage(
            sender_email="user@company.com",
            sender_name="Current User",
            body="Thanks John, I'll have the revised numbers by Friday.",
            timestamp="2026-02-13T11:30:00Z",
            is_from_user=True,
        ),
    ]


class TestDraftContext:
    """Tests for DraftContext model."""

    def test_to_db_dict(self):
        """Test serialization to database dictionary."""
        context = DraftContext(
            user_id="user-123",
            email_id="email-456",
            thread_id="thread-789",
            sender_email="john@acme.com",
            subject="Q2 Proposal",
        )

        db_dict = context.to_db_dict()

        assert db_dict["user_id"] == "user-123"
        assert db_dict["email_id"] == "email-456"
        assert db_dict["thread_id"] == "thread-789"
        assert db_dict["sender_email"] == "john@acme.com"
        assert db_dict["subject"] == "Q2 Proposal"
        assert "id" in db_dict
        assert "created_at" in db_dict

    def test_to_db_dict_with_nested_context(self):
        """Test serialization with nested context objects."""
        context = DraftContext(
            user_id="user-123",
            email_id="email-456",
            thread_id="thread-789",
            sender_email="john@acme.com",
            subject="Test",
            thread_context=ThreadContext(
                thread_id="thread-789",
                messages=[],
                summary="Test thread",
                message_count=0,
            ),
        )

        db_dict = context.to_db_dict()

        assert db_dict["thread_context"]["thread_id"] == "thread-789"
        assert db_dict["thread_context"]["summary"] == "Test thread"


class TestThreadMessage:
    """Tests for ThreadMessage model."""

    def test_from_user_detection(self):
        """Test is_from_user flag."""
        msg = ThreadMessage(
            sender_email="user@company.com",
            body="Test",
            timestamp="2026-02-13T10:00:00Z",
            is_from_user=True,
        )

        assert msg.is_from_user is True


class TestEmailContextGatherer:
    """Tests for EmailContextGatherer service."""

    @pytest.mark.asyncio
    async def test_extract_email_address(self, gatherer):
        """Test email extraction from From header."""
        assert gatherer._extract_email_address("John <john@acme.com>") == "john@acme.com"
        assert gatherer._extract_email_address("john@acme.com") == "john@acme.com"
        assert gatherer._extract_email_address("John Smith <JOHN@ACME.COM>") == "john@acme.com"

    @pytest.mark.asyncio
    async def test_extract_name(self, gatherer):
        """Test name extraction from From header."""
        assert gatherer._extract_name("John <john@acme.com>") == "John"
        assert gatherer._extract_name("John Smith <john@acme.com>") == "John Smith"
        assert gatherer._extract_name("john@acme.com") is None

    @pytest.mark.asyncio
    async def test_get_recipient_style_found(self, gatherer):
        """Test getting recipient style when profile exists."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={
                "formality_level": 0.8,
                "greeting_style": "Hi John,",
                "signoff_style": "Best regards,",
                "tone": "formal",
                "uses_emoji": False,
                "email_count": 15,
            }
        )

        style = await gatherer._get_recipient_style("user-123", "john@acme.com")

        assert style.exists is True
        assert style.formality_level == 0.8
        assert style.greeting_style == "Hi John,"
        assert style.tone == "formal"
        assert style.email_count == 15

    @pytest.mark.asyncio
    async def test_get_recipient_style_not_found(self, gatherer):
        """Test getting recipient style when no profile exists."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )

        style = await gatherer._get_recipient_style("user-123", "new@contact.com")

        assert style.exists is False
        assert style.formality_level == 0.5  # Default

    @pytest.mark.asyncio
    async def test_get_relationship_history(self, gatherer):
        """Test getting relationship history from memory."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.ilike.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "fact-1",
                    "fact": "john@acme.com is VP of Sales at Acme",
                    "confidence": 0.9,
                    "source": "email_bootstrap",
                    "created_at": "2026-02-10T10:00:00Z",
                    "metadata": {"relationship_type": "client"},
                },
            ]
        )

        history = await gatherer._get_relationship_history("user-123", "john@acme.com")

        assert len(history.memory_facts) == 1
        assert history.relationship_type == "client"
        assert len(history.memory_fact_ids) == 1

    @pytest.mark.asyncio
    async def test_get_email_integration_gmail(self, gatherer):
        """Test getting Gmail integration."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data={"integration_type": "gmail", "composio_connection_id": "conn-123"}),
            MagicMock(data=None),  # Outlook fallback
        ]

        integration = await gatherer._get_email_integration("user-123")

        assert integration is not None
        assert integration["integration_type"] == "gmail"

    @pytest.mark.asyncio
    async def test_get_email_integration_outlook(self, gatherer):
        """Test getting Outlook integration when Gmail not present."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),  # Gmail not found
            MagicMock(data={"integration_type": "outlook", "composio_connection_id": "conn-456"}),
        ]

        integration = await gatherer._get_email_integration("user-123")

        assert integration is not None
        assert integration["integration_type"] == "outlook"

    @pytest.mark.asyncio
    async def test_get_email_integration_none(self, gatherer):
        """Test when no email integration exists."""
        gatherer._db.table.return_value.select.return_value.eq.return_value.eq.return_value.maybe_single.return_value.execute.side_effect = [
            MagicMock(data=None),
            MagicMock(data=None),
        ]

        integration = await gatherer._get_email_integration("user-123")

        assert integration is None

    @pytest.mark.asyncio
    async def test_calendar_context_no_integration(self, gatherer):
        """Test calendar context when no integration connected."""
        with patch.object(gatherer, "_get_calendar_integration", return_value=None):
            context = await gatherer._get_calendar_context("user-123", "john@acme.com")

        assert context.connected is False
        assert context.upcoming_meetings == []

    @pytest.mark.asyncio
    async def test_crm_context_no_integration(self, gatherer):
        """Test CRM context when no integration connected."""
        with patch.object(gatherer, "_get_crm_integration", return_value=None):
            context = await gatherer._get_crm_context("user-123", "john@acme.com")

        assert context.connected is False
        assert context.lead_stage is None

    @pytest.mark.asyncio
    async def test_gather_context_full_flow(self, gatherer, sample_thread_messages):
        """Test full context gathering flow."""
        # Mock all the sub-methods
        with patch.object(gatherer, "_fetch_thread") as mock_thread, \
             patch.object(gatherer, "_research_recipient") as mock_research, \
             patch.object(gatherer, "_get_recipient_style") as mock_style, \
             patch.object(gatherer, "_get_relationship_history") as mock_history, \
             patch.object(gatherer, "_get_corporate_memory") as mock_corp, \
             patch.object(gatherer, "_get_calendar_context") as mock_cal, \
             patch.object(gatherer, "_get_crm_context") as mock_crm, \
             patch.object(gatherer, "_save_context") as mock_save:

            mock_thread.return_value = ThreadContext(
                thread_id="thread-789",
                messages=sample_thread_messages,
                summary="Discussion about Q2 proposal",
                message_count=2,
            )
            mock_research.return_value = RecipientResearch(
                sender_email="john@acme.com",
                sender_name="John Smith",
                sender_title="VP of Sales",
                sender_company="Acme Corp",
                exa_sources_used=["https://linkedin.com/in/johnsmith"],
            )
            mock_style.return_value = RecipientWritingStyle(exists=True, email_count=10)
            mock_history.return_value = RelationshipHistory(
                sender_email="john@acme.com",
                relationship_type="client",
                total_emails=10,
                memory_facts=[{"id": "fact-1", "fact": "test"}],
            )
            mock_corp.return_value = CorporateMemoryContext(facts=[])
            mock_cal.return_value = CalendarContext(connected=True)
            mock_crm.return_value = CRMContext(connected=False)

            context = await gatherer.gather_context(
                user_id="user-123",
                email_id="email-456",
                thread_id="thread-789",
                sender_email="john@acme.com",
                sender_name="John Smith",
                subject="Q2 Proposal Follow-up",
            )

            assert context.user_id == "user-123"
            assert context.thread_context is not None
            assert context.thread_context.message_count == 2
            assert context.recipient_research.sender_title == "VP of Sales"
            assert context.recipient_style.exists is True
            assert context.relationship_history.relationship_type == "client"
            assert "composio_thread" in context.sources_used
            assert "exa_research" in context.sources_used
            assert "recipient_style_profile" in context.sources_used
            assert "memory_semantic" in context.sources_used

            mock_save.assert_called_once()


class TestSingleton:
    """Tests for singleton accessor."""

    def test_get_email_context_gatherer_creates_singleton(self):
        """Test that accessor creates singleton on first call."""
        # Reset singleton
        import src.services.email_context_gatherer as module
        module._gatherer = None

        with patch("src.db.supabase.SupabaseClient"):
            from src.services.email_context_gatherer import get_email_context_gatherer
            g1 = get_email_context_gatherer()
            g2 = get_email_context_gatherer()

        assert g1 is g2
