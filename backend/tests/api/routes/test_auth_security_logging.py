"""Tests for auth security logging (US-932 Task 5).

These tests verify that login success/failure and logout events
are properly logged to the security audit log.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from src.main import app
from src.services.account_service import AccountService


@pytest.fixture
def mock_request() -> MagicMock:
    """Create a mock FastAPI request with client info."""
    request = MagicMock(spec=Request)
    request.client = ("192.168.1.1", 12345)
    request.headers = MagicMock()
    request.headers.get = MagicMock(return_value=None)
    request.state = MagicMock()
    return request


@pytest.fixture
def mock_log_security_event() -> AsyncMock:
    """Create a mock log_security_event method."""
    return AsyncMock()


def test_login_success_logs_security_event(mock_log_security_event: AsyncMock) -> None:
    """Test that successful login is logged to security audit log."""
    from src.api.routes.auth import login, LoginRequest

    # Mock Supabase client
    mock_auth_response = MagicMock()
    mock_auth_response.session.access_token = "test_access_token"
    mock_auth_response.session.refresh_token = "test_refresh_token"
    mock_auth_response.session.expires_in = 3600
    mock_auth_response.user.id = "user-123"

    with patch("src.api.routes.auth.SupabaseClient.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.return_value = mock_auth_response
        mock_get_client.return_value = mock_client

        # Mock account_service.log_security_event
        with patch.object(
            AccountService, "log_security_event", mock_log_security_event
        ):
            mock_request = MagicMock(spec=Request)
            mock_request.client = ("192.168.1.100", 54321)
            mock_request.headers = MagicMock()
            mock_request.headers.get = MagicMock(
                side_effect=lambda x, y=None: {
                    "X-Forwarded-For": "203.0.113.1",
                    "User-Agent": None,
                }.get(x, y)
            )
            mock_request.state = MagicMock()

            login_request = LoginRequest(email="test@example.com", password="password123")

            result = asyncio.run(login(mock_request, login_request))

            # Verify security event was logged
            mock_log_security_event.assert_called_once()
            call_args = mock_log_security_event.call_args

            assert call_args.kwargs["user_id"] == "user-123"
            assert call_args.kwargs["event_type"] == AccountService.EVENT_LOGIN
            assert call_args.kwargs["ip_address"] == "203.0.113.1"  # X-Forwarded-For


def test_login_failure_logs_security_event(mock_log_security_event: AsyncMock) -> None:
    """Test that failed login is logged to security audit log."""
    from src.api.routes.auth import login, LoginRequest

    # Mock Supabase client to raise exception (login failure)
    with patch("src.api.routes.auth.SupabaseClient.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_in_with_password.side_effect = Exception("Invalid credentials")
        # Mock admin client for user lookup - list_users returns a list directly
        mock_user = MagicMock()
        mock_user.email = "test@example.com"
        mock_user.id = "user-456"
        mock_admin = MagicMock()
        mock_admin.list_users.return_value = [mock_user]
        mock_client.auth.admin = mock_admin
        mock_get_client.return_value = mock_client

        # Mock account_service.log_security_event
        with patch.object(
            AccountService, "log_security_event", mock_log_security_event
        ):
            mock_request = MagicMock(spec=Request)
            mock_request.client = ("192.168.1.100", 54321)
            mock_request.headers = MagicMock()
            mock_request.headers.get = MagicMock(return_value=None)
            mock_request.state = MagicMock()

            login_request = LoginRequest(email="test@example.com", password="wrong_password")

            with pytest.raises(Exception):
                asyncio.run(login(mock_request, login_request))

            # Verify security event was logged
            mock_log_security_event.assert_called_once()
            call_args = mock_log_security_event.call_args

            assert call_args.kwargs["user_id"] == "user-456"
            assert call_args.kwargs["event_type"] == AccountService.EVENT_LOGIN_FAILED


def test_logout_logs_security_event(mock_log_security_event: AsyncMock) -> None:
    """Test that logout is logged to security audit log."""
    from src.api.routes.auth import logout

    # Create a mock current user and request
    mock_current_user = MagicMock()
    mock_current_user.id = "user-789"

    mock_request = MagicMock(spec=Request)
    mock_request.client = ("192.168.1.100", 54321)
    mock_request.headers = MagicMock()
    mock_request.headers.get = MagicMock(return_value=None)
    mock_request.state = MagicMock()

    # Mock Supabase client
    with patch("src.api.routes.auth.SupabaseClient.get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.auth.sign_out.return_value = None
        mock_get_client.return_value = mock_client

        # Mock account_service.log_security_event
        with patch.object(
            AccountService, "log_security_event", mock_log_security_event
        ):
            result = asyncio.run(logout(mock_request, mock_current_user))

            # Verify security event was logged
            mock_log_security_event.assert_called_once()
            call_args = mock_log_security_event.call_args

            assert call_args.kwargs["user_id"] == "user-789"
            assert call_args.kwargs["event_type"] == AccountService.EVENT_LOGOUT


def test_get_client_ip_from_x_forwarded_for() -> None:
    """Test that _get_client_ip extracts IP from X-Forwarded-For header."""
    from src.api.routes.auth import _get_client_ip

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"X-Forwarded-For": "203.0.113.1, 198.51.100.1"}

    ip = _get_client_ip(mock_request)
    assert ip == "203.0.113.1"


def test_get_client_ip_from_x_real_ip() -> None:
    """Test that _get_client_ip extracts IP from X-Real-IP header."""
    from src.api.routes.auth import _get_client_ip

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"X-Real-IP": "203.0.113.50"}

    ip = _get_client_ip(mock_request)
    assert ip == "203.0.113.50"


def test_get_client_ip_returns_none_when_no_headers() -> None:
    """Test that _get_client_ip returns None when no headers are present."""
    from src.api.routes.auth import _get_client_ip

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}

    ip = _get_client_ip(mock_request)
    assert ip is None


def test_x_forwarded_for_takes_precedence() -> None:
    """Test that X-Forwarded-For takes precedence over X-Real-IP."""
    from src.api.routes.auth import _get_client_ip

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {
        "X-Forwarded-For": "203.0.113.1",
        "X-Real-IP": "203.0.113.50",
    }

    ip = _get_client_ip(mock_request)
    assert ip == "203.0.113.1"


def test_login_failed_constant_exists() -> None:
    """Test that EVENT_LOGIN_FAILED constant is defined in AccountService."""
    from src.services.account_service import AccountService

    assert hasattr(AccountService, "EVENT_LOGIN_FAILED")
    assert AccountService.EVENT_LOGIN_FAILED == "login_failed"
