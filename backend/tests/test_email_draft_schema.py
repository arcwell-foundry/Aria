"""Tests for email draft Pydantic models."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from src.models.email_draft import (
    EmailDraftCreate,
    EmailDraftPurpose,
    EmailDraftResponse,
    EmailDraftStatus,
    EmailDraftTone,
    EmailDraftUpdate,
    EmailRegenerateRequest,
)


def test_email_draft_purpose_enum_values() -> None:
    """Test EmailDraftPurpose enum has all expected values."""
    assert EmailDraftPurpose.INTRO == "intro"
    assert EmailDraftPurpose.FOLLOW_UP == "follow_up"
    assert EmailDraftPurpose.PROPOSAL == "proposal"
    assert EmailDraftPurpose.THANK_YOU == "thank_you"
    assert EmailDraftPurpose.CHECK_IN == "check_in"
    assert EmailDraftPurpose.OTHER == "other"


def test_email_draft_tone_enum_values() -> None:
    """Test EmailDraftTone enum has all expected values."""
    assert EmailDraftTone.FORMAL == "formal"
    assert EmailDraftTone.FRIENDLY == "friendly"
    assert EmailDraftTone.URGENT == "urgent"


def test_email_draft_status_enum_values() -> None:
    """Test EmailDraftStatus enum has all expected values."""
    assert EmailDraftStatus.DRAFT == "draft"
    assert EmailDraftStatus.SENT == "sent"
    assert EmailDraftStatus.FAILED == "failed"


def test_email_draft_create_minimal() -> None:
    """Test EmailDraftCreate with minimal required fields."""
    draft = EmailDraftCreate(
        recipient_email="test@example.com",
        purpose=EmailDraftPurpose.INTRO,
    )
    assert draft.recipient_email == "test@example.com"
    assert draft.purpose == EmailDraftPurpose.INTRO
    assert draft.tone == EmailDraftTone.FRIENDLY  # default
    assert draft.subject_hint is None
    assert draft.context is None
    assert draft.lead_memory_id is None


def test_email_draft_create_full() -> None:
    """Test EmailDraftCreate with all fields."""
    draft = EmailDraftCreate(
        recipient_email="john@acme.com",
        recipient_name="John Smith",
        subject_hint="Follow up on our meeting",
        purpose=EmailDraftPurpose.FOLLOW_UP,
        context="We discussed pricing options",
        tone=EmailDraftTone.FORMAL,
        lead_memory_id="lead-123",
    )
    assert draft.recipient_email == "john@acme.com"
    assert draft.recipient_name == "John Smith"
    assert draft.subject_hint == "Follow up on our meeting"
    assert draft.purpose == EmailDraftPurpose.FOLLOW_UP
    assert draft.context == "We discussed pricing options"
    assert draft.tone == EmailDraftTone.FORMAL
    assert draft.lead_memory_id == "lead-123"


def test_email_draft_create_invalid_email() -> None:
    """Test EmailDraftCreate rejects invalid email."""
    with pytest.raises(ValidationError) as exc_info:
        EmailDraftCreate(
            recipient_email="not-an-email",
            purpose=EmailDraftPurpose.INTRO,
        )
    assert "email" in str(exc_info.value).lower()


def test_email_draft_update_partial() -> None:
    """Test EmailDraftUpdate allows partial updates."""
    update = EmailDraftUpdate(subject="New subject")
    assert update.subject == "New subject"
    assert update.body is None
    assert update.tone is None


def test_email_draft_update_all_fields() -> None:
    """Test EmailDraftUpdate with all fields."""
    update = EmailDraftUpdate(
        subject="Updated subject",
        body="Updated body content",
        tone=EmailDraftTone.URGENT,
        recipient_email="new@example.com",
    )
    assert update.subject == "Updated subject"
    assert update.body == "Updated body content"
    assert update.tone == EmailDraftTone.URGENT
    assert update.recipient_email == "new@example.com"


def test_email_draft_response_full() -> None:
    """Test EmailDraftResponse with all fields."""
    response = EmailDraftResponse(
        id="draft-123",
        user_id="user-456",
        recipient_email="test@example.com",
        recipient_name="Test User",
        subject="Test Subject",
        body="Test body content",
        purpose=EmailDraftPurpose.INTRO,
        tone=EmailDraftTone.FRIENDLY,
        context={"key": "value"},
        lead_memory_id="lead-789",
        style_match_score=0.85,
        status=EmailDraftStatus.DRAFT,
        sent_at=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    assert response.id == "draft-123"
    assert response.style_match_score == 0.85
    assert response.status == EmailDraftStatus.DRAFT


def test_email_regenerate_request_defaults() -> None:
    """Test EmailRegenerateRequest with defaults."""
    request = EmailRegenerateRequest()
    assert request.tone is None
    assert request.additional_context is None


def test_email_regenerate_request_custom() -> None:
    """Test EmailRegenerateRequest with custom values."""
    request = EmailRegenerateRequest(
        tone=EmailDraftTone.URGENT,
        additional_context="Make it more concise",
    )
    assert request.tone == EmailDraftTone.URGENT
    assert request.additional_context == "Make it more concise"
