"""Tests for Lead Memory exceptions."""


def test_lead_memory_error_initialization() -> None:
    """Test LeadMemoryError initializes with correct attributes."""
    from src.core.exceptions import LeadMemoryError

    error = LeadMemoryError("Database connection failed")

    assert error.message == "Lead memory error: Database connection failed"
    assert error.code == "LEAD_MEMORY_ERROR"
    assert error.status_code == 500


def test_lead_not_found_error_initialization() -> None:
    """Test LeadNotFoundError initializes with correct attributes."""
    from src.core.exceptions import LeadNotFoundError

    error = LeadNotFoundError("lead-123")

    assert "lead-123" in error.message
    assert error.code == "NOT_FOUND"
    assert error.status_code == 404


def test_invalid_stage_transition_error() -> None:
    """Test InvalidStageTransitionError initializes with correct attributes."""
    from src.core.exceptions import InvalidStageTransitionError

    error = InvalidStageTransitionError("lead", "account")

    assert "lead" in error.message
    assert "account" in error.message
    assert error.code == "INVALID_STAGE_TRANSITION"
    assert error.status_code == 400
