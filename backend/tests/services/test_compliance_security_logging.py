"""Tests for ComplianceService security logging (US-932 Task 9)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.compliance_service import ComplianceService, ComplianceError
from src.services.account_service import AccountService


@pytest.fixture
def mock_supabase_client():
    """Mock Supabase client."""
    client = MagicMock()
    return client


@pytest.fixture
def mock_account_service():
    """Mock AccountService."""
    service = MagicMock(spec=AccountService)
    service.log_security_event = AsyncMock()
    return service


@pytest.fixture
def compliance_service(mock_account_service):
    """ComplianceService fixture with mocked AccountService."""
    return ComplianceService(account_service=mock_account_service)


@pytest.mark.asyncio
async def test_export_user_data_logs_security_event(
    compliance_service, mock_supabase_client, mock_account_service
):
    """Test that export_user_data logs a security event."""
    user_id = "test-user-123"

    # Mock SupabaseClient.get_client to return our mock
    with patch("src.services.compliance_service.SupabaseClient.get_client", return_value=mock_supabase_client):
        # Mock table responses
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data={"id": user_id, "full_name": "Test User"}),  # user profile
            MagicMock(data={"user_id": user_id, "preferences": {}}),  # user settings
        ]
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        mock_supabase_client.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])

        result = await compliance_service.export_user_data(user_id)

        # Verify security event was logged
        mock_account_service.log_security_event.assert_called_once()
        call_args = mock_account_service.log_security_event.call_args

        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["event_type"] == mock_account_service.EVENT_DATA_EXPORT
        assert "data_types" in call_args[1]["metadata"]
        assert "export_date" in result
        assert result["user_id"] == user_id


@pytest.mark.asyncio
async def test_delete_user_data_logs_security_event(
    compliance_service, mock_supabase_client, mock_account_service
):
    """Test that delete_user_data logs a security event."""
    user_id = "test-user-123"

    # Mock SupabaseClient.get_client to return our mock
    with patch("src.services.compliance_service.SupabaseClient.get_client", return_value=mock_supabase_client):
        # Mock conversations select
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        # Mock delete operations
        mock_supabase_client.table.return_value.delete.return_value.eq.return_value.execute.return_value = MagicMock(data=None)
        mock_supabase_client.table.return_value.delete.return_value.in_.return_value.execute.return_value = MagicMock(data=None)

        result = await compliance_service.delete_user_data(user_id, "DELETE MY DATA")

        # Verify security event was logged
        mock_account_service.log_security_event.assert_called_once()
        call_args = mock_account_service.log_security_event.call_args

        assert call_args[1]["user_id"] == user_id
        assert call_args[1]["event_type"] == mock_account_service.EVENT_DATA_DELETION
        # metadata is the summary dict directly
        assert "auth_user" in call_args[1]["metadata"]
        assert result["deleted"] is True
        assert result["user_id"] == user_id


@pytest.mark.asyncio
async def test_delete_user_data_invalid_confirmation(
    compliance_service, mock_supabase_client, mock_account_service
):
    """Test that delete_user_data with invalid confirmation does not log security event."""
    user_id = "test-user-123"

    with patch("src.services.compliance_service.SupabaseClient.get_client", return_value=mock_supabase_client):
        with pytest.raises(ComplianceError, match="Confirmation must be exactly"):
            await compliance_service.delete_user_data(user_id, "WRONG CONFIRMATION")

        # Verify security event was NOT logged
        mock_account_service.log_security_event.assert_not_called()


@pytest.mark.asyncio
async def test_export_user_data_failure_does_not_log_security_event(
    compliance_service, mock_supabase_client, mock_account_service
):
    """Test that export_user_data failure does not log security event."""
    user_id = "test-user-123"

    with patch("src.services.compliance_service.SupabaseClient.get_client", return_value=mock_supabase_client):
        # Mock to raise exception
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.single.return_value.execute.side_effect = Exception("DB error")

        with pytest.raises(ComplianceError):
            await compliance_service.export_user_data(user_id)

        # Verify security event was NOT logged due to failure
        mock_account_service.log_security_event.assert_not_called()


@pytest.mark.asyncio
async def test_compliance_service_uses_default_account_service():
    """Test that ComplianceService creates AccountService if not provided."""
    with patch("src.services.compliance_service.AccountService") as MockAccountService:
        service = ComplianceService()
        # Verify AccountService was instantiated
        MockAccountService.assert_called_once()
        assert service.account_service is not None
