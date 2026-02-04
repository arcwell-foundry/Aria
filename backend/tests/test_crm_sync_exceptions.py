"""Tests for CRM sync exceptions."""

import pytest


class TestCRMSyncError:
    """Tests for CRMSyncError exception."""

    def test_crm_sync_error_initialization(self) -> None:
        """Test CRMSyncError initializes correctly."""
        from src.core.exceptions import CRMSyncError

        error = CRMSyncError("Sync failed")
        assert "CRM sync error" in str(error)
        assert error.code == "CRM_SYNC_ERROR"
        assert error.status_code == 500

    def test_crm_sync_error_with_provider(self) -> None:
        """Test CRMSyncError with provider context."""
        from src.core.exceptions import CRMSyncError

        error = CRMSyncError("API rate limit exceeded", provider="salesforce")
        assert error.details["provider"] == "salesforce"


class TestCRMConnectionError:
    """Tests for CRMConnectionError exception."""

    def test_crm_connection_error(self) -> None:
        """Test CRMConnectionError initializes correctly."""
        from src.core.exceptions import CRMConnectionError

        error = CRMConnectionError("salesforce")
        assert "salesforce" in str(error)
        assert error.code == "CRM_CONNECTION_ERROR"
        assert error.status_code == 502


class TestCRMSyncConflictError:
    """Tests for CRMSyncConflictError exception."""

    def test_conflict_error_with_fields(self) -> None:
        """Test CRMSyncConflictError with field details."""
        from src.core.exceptions import CRMSyncConflictError

        error = CRMSyncConflictError(
            lead_id="lead-123",
            conflicting_fields=["stage", "expected_value"],
        )
        assert error.code == "CRM_SYNC_CONFLICT"
        assert error.status_code == 409
        assert "lead-123" in error.details["lead_id"]
        assert "stage" in error.details["conflicting_fields"]


class TestCRMSyncNotFoundError:
    """Tests for CRMSyncNotFoundError exception."""

    def test_sync_not_found_error(self) -> None:
        """Test CRMSyncNotFoundError initializes correctly."""
        from src.core.exceptions import CRMSyncNotFoundError

        error = CRMSyncNotFoundError("lead-123")
        assert "lead-123" in str(error)
        assert error.code == "NOT_FOUND"
        assert error.status_code == 404
