"""Tests for admin routes security logging (US-932 Task 10)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from src.api.routes.admin import change_role, ChangeRoleRequest
from src.services.account_service import AccountService


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    user = MagicMock()
    user.id = "admin-user-123"
    return user


@pytest.fixture
def mock_account_service():
    """Mock AccountService."""
    service = MagicMock(spec=AccountService)
    service.log_security_event = AsyncMock()
    return service


@pytest.fixture
def mock_team_service():
    """Mock TeamService."""
    service = MagicMock()
    service.change_role = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_change_role_logs_security_event(
    mock_current_user, mock_account_service, mock_team_service
):
    """Test that change_role logs a security event."""
    user_id = "target-user-456"
    new_role = "admin"
    old_role = "user"

    target_profile = {
        "id": user_id,
        "full_name": "Test User",
        "role": old_role,
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-02T00:00:00Z",
    }

    updated_profile = target_profile.copy()
    updated_profile["role"] = new_role

    mock_team_service.change_role.return_value = updated_profile

    request_data = ChangeRoleRequest(role=new_role)

    with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
        mock_get_user.side_effect = [
            {"company_id": "company-123"},  # admin profile
            target_profile,  # target profile (old role)
        ]
        with patch("src.api.routes.admin.account_service", mock_account_service):
            with patch("src.api.routes.admin.team_service", mock_team_service):
                result = await change_role(
                    user_id=user_id,
                    data=request_data,
                    current_user=mock_current_user,
                )

                # Verify security event was logged
                mock_account_service.log_security_event.assert_called_once()
                call_args = mock_account_service.log_security_event.call_args

                assert call_args[1]["user_id"] == mock_current_user.id
                assert call_args[1]["event_type"] == mock_account_service.EVENT_ROLE_CHANGED
                assert call_args[1]["metadata"]["target_user_id"] == user_id
                assert call_args[1]["metadata"]["old_role"] == old_role
                assert call_args[1]["metadata"]["new_role"] == new_role

                # Verify response
                assert result["id"] == user_id
                assert result["role"] == new_role


@pytest.mark.asyncio
async def test_change_role_manager_to_admin_logs_security_event(
    mock_current_user, mock_account_service, mock_team_service
):
    """Test that promoting manager to admin logs a security event."""
    user_id = "manager-user-789"
    new_role = "admin"
    old_role = "manager"

    target_profile = {
        "id": user_id,
        "full_name": "Manager User",
        "role": old_role,
        "is_active": True,
    }

    updated_profile = target_profile.copy()
    updated_profile["role"] = new_role

    mock_team_service.change_role.return_value = updated_profile

    request_data = ChangeRoleRequest(role=new_role)

    with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
        mock_get_user.side_effect = [
            {"company_id": "company-123"},
            target_profile,
        ]
        with patch("src.api.routes.admin.account_service", mock_account_service):
            with patch("src.api.routes.admin.team_service", mock_team_service):
                await change_role(
                    user_id=user_id,
                    data=request_data,
                    current_user=mock_current_user,
                )

                # Verify security event was logged with role transition
                mock_account_service.log_security_event.assert_called_once()
                call_args = mock_account_service.log_security_event.call_args

                assert call_args[1]["metadata"]["old_role"] == old_role
                assert call_args[1]["metadata"]["new_role"] == new_role


@pytest.mark.asyncio
async def test_change_role_demotion_logs_security_event(
    mock_current_user, mock_account_service, mock_team_service
):
    """Test that demoting admin to user logs a security event."""
    user_id = "demoted-admin-999"
    new_role = "user"
    old_role = "admin"

    target_profile = {
        "id": user_id,
        "full_name": "Demoted Admin",
        "role": old_role,
        "is_active": True,
    }

    updated_profile = target_profile.copy()
    updated_profile["role"] = new_role

    mock_team_service.change_role.return_value = updated_profile

    request_data = ChangeRoleRequest(role=new_role)

    with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
        mock_get_user.side_effect = [
            {"company_id": "company-123"},
            target_profile,
        ]
        with patch("src.api.routes.admin.account_service", mock_account_service):
            with patch("src.api.routes.admin.team_service", mock_team_service):
                await change_role(
                    user_id=user_id,
                    data=request_data,
                    current_user=mock_current_user,
                )

                # Verify security event was logged
                mock_account_service.log_security_event.assert_called_once()
                call_args = mock_account_service.log_security_event.call_args

                assert call_args[1]["metadata"]["old_role"] == old_role
                assert call_args[1]["metadata"]["new_role"] == new_role


@pytest.mark.asyncio
async def test_change_role_no_company_id_does_not_log_security_event(
    mock_current_user, mock_account_service, mock_team_service
):
    """Test that change_role without company_id does not log security event."""
    user_id = "target-user-456"
    new_role = "admin"

    request_data = ChangeRoleRequest(role=new_role)

    with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
        mock_get_user.return_value = {"company_id": None}  # No company
        with patch("src.api.routes.admin.account_service", mock_account_service):
            with patch("src.api.routes.admin.team_service", mock_team_service):
                with pytest.raises(HTTPException, match="You must belong to a company"):
                    await change_role(
                        user_id=user_id,
                        data=request_data,
                        current_user=mock_current_user,
                    )

                # Verify security event was NOT logged due to early exit
                mock_account_service.log_security_event.assert_not_called()


@pytest.mark.asyncio
async def test_change_role_default_old_role(
    mock_current_user, mock_account_service, mock_team_service
):
    """Test that change_role handles missing old_role gracefully."""
    user_id = "target-user-456"
    new_role = "admin"
    old_role = "user"  # default when not set

    target_profile = {
        "id": user_id,
        "full_name": "Test User",
        # role not set - should default to "user"
        "is_active": True,
    }

    updated_profile = target_profile.copy()
    updated_profile["role"] = new_role

    mock_team_service.change_role.return_value = updated_profile

    request_data = ChangeRoleRequest(role=new_role)

    with patch("src.db.supabase.SupabaseClient.get_user_by_id") as mock_get_user:
        mock_get_user.side_effect = [
            {"company_id": "company-123"},
            target_profile,
        ]
        with patch("src.api.routes.admin.account_service", mock_account_service):
            with patch("src.api.routes.admin.team_service", mock_team_service):
                await change_role(
                    user_id=user_id,
                    data=request_data,
                    current_user=mock_current_user,
                )

                # Verify security event was logged with default old_role
                mock_account_service.log_security_event.assert_called_once()
                call_args = mock_account_service.log_security_event.call_args

                assert call_args[1]["metadata"]["old_role"] == old_role
