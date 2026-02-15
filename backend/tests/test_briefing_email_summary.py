"""Tests for email intelligence in daily briefing."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_needs_attention_item_model_exists() -> None:
    """Test that NeedsAttentionItem model exists with required fields."""
    from src.services.briefing import NeedsAttentionItem

    # Verify model can be instantiated with required fields
    item = NeedsAttentionItem(
        sender="john@example.com",
        company="Acme Corp",
        subject="Urgent: Contract Review",
        summary="Contract needs immediate review",
        urgency="URGENT",
        draft_status="saved_to_drafts",
        draft_confidence="HIGH",
        aria_notes="This is a high-priority contract",
        draft_id="draft-123",
    )

    assert item.sender == "john@example.com"
    assert item.company == "Acme Corp"
    assert item.subject == "Urgent: Contract Review"
    assert item.summary == "Contract needs immediate review"
    assert item.urgency == "URGENT"
    assert item.draft_status == "saved_to_drafts"
    assert item.draft_confidence == "HIGH"
    assert item.aria_notes == "This is a high-priority contract"
    assert item.draft_id == "draft-123"


def test_needs_attention_item_optional_fields() -> None:
    """Test that NeedsAttentionItem optional fields work correctly."""
    from src.services.briefing import NeedsAttentionItem

    # Create with minimal required fields
    item = NeedsAttentionItem(
        sender="jane@example.com",
        subject="Quick update",
        summary="Just a quick update",
        urgency="NORMAL",
        draft_status="no_draft_needed",
    )

    assert item.company is None
    assert item.draft_confidence is None
    assert item.aria_notes is None
    assert item.draft_id is None


def test_email_summary_model_exists() -> None:
    """Test that EmailSummary model exists with required fields."""
    from src.services.briefing import EmailSummary

    # Verify model can be instantiated
    summary = EmailSummary()

    # Verify default values
    assert summary.total_received == 0
    assert summary.needs_attention == []
    assert summary.fyi_count == 0
    assert summary.fyi_highlights == []
    assert summary.filtered_count == 0
    assert summary.filtered_reason is None
    assert summary.drafts_waiting == 0
    assert summary.drafts_high_confidence == 0
    assert summary.drafts_need_review == 0


def test_email_summary_with_needs_attention_items() -> None:
    """Test that EmailSummary can contain NeedsAttentionItem instances."""
    from src.services.briefing import EmailSummary, NeedsAttentionItem

    item = NeedsAttentionItem(
        sender="john@example.com",
        company="Acme Corp",
        subject="Urgent: Contract Review",
        summary="Contract needs immediate review",
        urgency="URGENT",
        draft_status="saved_to_drafts",
        draft_confidence="HIGH",
    )

    summary = EmailSummary(
        total_received=10,
        needs_attention=[item],
        fyi_count=5,
        fyi_highlights=["Company merged", "New product launch"],
        filtered_count=3,
        filtered_reason="Newsletter subscriptions",
        drafts_waiting=2,
        drafts_high_confidence=1,
        drafts_need_review=1,
    )

    assert summary.total_received == 10
    assert len(summary.needs_attention) == 1
    assert summary.needs_attention[0].sender == "john@example.com"
    assert summary.fyi_count == 5
    assert len(summary.fyi_highlights) == 2
    assert summary.filtered_count == 3
    assert summary.filtered_reason == "Newsletter subscriptions"
    assert summary.drafts_waiting == 2
    assert summary.drafts_high_confidence == 1
    assert summary.drafts_need_review == 1


@pytest.mark.asyncio
async def test_email_summary_has_required_structure() -> None:
    """Test that email_summary contains all required fields in briefing."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.briefing.LLMClient") as mock_llm_class,
    ):
        # Setup mocks
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        mock_llm_class.return_value.generate_response = AsyncMock(
            return_value="Good morning!"
        )

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service.generate_briefing(user_id="test-user-123")

        # Verify email_summary structure exists
        assert "email_summary" in result
        email_summary = result["email_summary"]

        # Required fields
        assert "total_received" in email_summary
        assert "needs_attention" in email_summary
        assert "fyi_count" in email_summary
        assert "fyi_highlights" in email_summary
        assert "filtered_count" in email_summary
        assert "filtered_reason" in email_summary
        assert "drafts_waiting" in email_summary
        assert "drafts_high_confidence" in email_summary
        assert "drafts_need_review" in email_summary


# Test _get_email_data method

@pytest.mark.asyncio
async def test_get_email_data_returns_empty_when_no_integration() -> None:
    """Test _get_email_data returns empty structure when no email integration."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
    ):
        # Setup DB mock - no email integration
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_email_data(user_id="test-user-123")

        assert result["total_received"] == 0
        assert result["needs_attention"] == []
        assert result["fyi_count"] == 0
        assert result["filtered_count"] == 0
        assert result["drafts_waiting"] == 0


@pytest.mark.asyncio
async def test_get_email_data_processes_inbox() -> None:
    """Test _get_email_data calls AutonomousDraftEngine and builds summary."""
    with (
        patch("src.services.briefing.SupabaseClient") as mock_db_class,
        patch("src.services.autonomous_draft_engine.AutonomousDraftEngine") as mock_engine_class,
        patch("src.services.email_analyzer.EmailAnalyzer") as mock_analyzer_class,
    ):
        # Setup DB mock - has email integration
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.in_.return_value.maybe_single.return_value.execute.return_value = MagicMock(
            data={"integration_type": "gmail", "status": "active"}
        )
        mock_db_class.get_client.return_value = mock_db

        # Mock AutonomousDraftEngine
        mock_draft = MagicMock()
        mock_draft.draft_id = "draft-123"
        mock_draft.recipient_email = "sarah@moderna.com"
        mock_draft.recipient_name = "Sarah Chen"
        mock_draft.subject = "Re: Pilot Program Proposal"
        mock_draft.confidence_level = 0.85
        mock_draft.aria_notes = "High confidence. Matched casual tone."
        mock_draft.success = True

        mock_engine = MagicMock()
        mock_engine.process_inbox = AsyncMock(return_value=MagicMock(
            run_id="run-123",
            emails_scanned=23,
            drafts=[mock_draft],
            drafts_generated=1,
            drafts_failed=0,
        ))
        mock_engine_class.return_value = mock_engine

        # Mock EmailAnalyzer for FYI/skipped counts
        mock_fyi = MagicMock()
        mock_fyi.subject = "Q2 all-hands meeting scheduled"
        mock_fyi.topic_summary = "Meeting announcement"

        mock_skipped = MagicMock()
        mock_skipped.reason = "Automated no-reply address"

        mock_analyzer = MagicMock()
        mock_analyzer.scan_inbox = AsyncMock(return_value=MagicMock(
            total_emails=23,
            needs_reply=[MagicMock()],
            fyi=[mock_fyi],
            skipped=[mock_skipped],
        ))
        mock_analyzer_class.return_value = mock_analyzer

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_email_data(user_id="test-user-123")

        assert result["total_received"] == 23
        assert result["drafts_waiting"] == 1
        assert result["drafts_high_confidence"] == 1  # confidence >= 0.75
        assert len(result["needs_attention"]) == 1
        assert result["needs_attention"][0]["sender"] == "Sarah Chen"
        assert result["needs_attention"][0]["draft_confidence"] == "HIGH"
