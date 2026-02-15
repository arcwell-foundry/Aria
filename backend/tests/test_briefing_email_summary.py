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
