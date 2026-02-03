"""Tests for email draft exceptions."""

from src.core.exceptions import EmailDraftError, EmailSendError


def test_email_draft_error_basic() -> None:
    """Test EmailDraftError basic creation."""
    error = EmailDraftError("Generation failed")
    assert error.message == "Email draft operation failed: Generation failed"
    assert error.code == "EMAIL_DRAFT_ERROR"
    assert error.status_code == 500


def test_email_draft_error_with_details() -> None:
    """Test EmailDraftError with details."""
    error = EmailDraftError("Invalid recipient", details={"recipient": "bad@"})
    assert "Email draft operation failed" in error.message
    assert error.details == {"recipient": "bad@"}


def test_email_send_error_basic() -> None:
    """Test EmailSendError basic creation."""
    error = EmailSendError("SMTP timeout")
    assert error.message == "Email send failed: SMTP timeout"
    assert error.code == "EMAIL_SEND_ERROR"
    assert error.status_code == 502


def test_email_send_error_with_draft_id() -> None:
    """Test EmailSendError with draft ID."""
    error = EmailSendError("Connection refused", draft_id="draft-123")
    assert error.details["draft_id"] == "draft-123"
